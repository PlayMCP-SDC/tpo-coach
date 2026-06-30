"""outfits DB 의 이미지를 Cloudflare R2(S3 호환)에 일괄 업로드한다.

업로드 대상 = DB 에 살아남은 행의 id 뿐(dedupe 후). 로컬 원천 폴더에서
`<id>.jpg` 를 찾아 버킷에 평면 키 `<id>.jpg` 로 올린다. **ContentType=image/jpeg
명시 필수**(안 하면 octet-stream 으로 서빙돼 카톡 마크다운 렌더 실패).

멱등: 이미 버킷에 있는 키는 건너뛴다 → 중단해도 다시 실행하면 이어서 올림.

사용:
  cp .env.example .env  # R2_* 값 채우기
  uv run --extra upload python scripts/upload_images.py \\
      --img-root '/.../원천데이터_modify' \\
      [--db src/playmcp_server/data/clothing.db] \\
      [--workers 32] [--limit N] [--dry-run]

자격증명/버킷은 .env(또는 OS 환경변수):
  R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger("upload_images")

_DEFAULT_DB = (
    Path(__file__).resolve().parent.parent
    / "src" / "playmcp_server" / "data" / "clothing.db"
)


def _load_env() -> None:
    """.env 를 읽어 환경변수에 채운다(python-dotenv 있으면)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def _db_ids(db: Path) -> list[str]:
    """활성 outfits 의 id 목록."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT id FROM outfits WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def _index_images(img_root: Path, needed: set[str]) -> dict[str, Path]:
    """img_root 를 재귀 순회해 {id: 경로} 인덱스를 만든다(needed 만 보관).

    원천데이터_1/3 은 스타일 폴더, _2 는 평면 구조라 재귀로 통합 처리.
    """
    index: dict[str, Path] = {}
    for dp, _dirs, files in os.walk(img_root):
        for fn in files:
            if not fn.lower().endswith(".jpg"):
                continue
            stem = fn[:-4]
            if stem in needed and stem not in index:
                index[stem] = Path(dp) / fn
        if len(index) == len(needed):
            break
    return index


def _existing_keys(client, bucket: str) -> set[str]:
    """버킷에 이미 있는 객체 키 집합(멱등 스킵용)."""
    keys: set[str] = set()
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def _make_client(endpoint: str, key: str, secret: str, pool: int = 32):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        region_name="auto",
        config=Config(
            retries={"max_attempts": 5, "mode": "standard"},
            max_pool_connections=pool,
        ),
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    _load_env()
    p = argparse.ArgumentParser(description="R2 이미지 일괄 업로드")
    p.add_argument("--img-root", required=True, help="원천데이터 루트(재귀 검색)")
    p.add_argument("--db", default=str(_DEFAULT_DB))
    p.add_argument("--workers", type=int, default=32)
    p.add_argument("--limit", type=int, default=0, help="처음 N개만(테스트)")
    p.add_argument("--dry-run", action="store_true", help="업로드 없이 점검만")
    args = p.parse_args()

    endpoint = os.environ.get("R2_ENDPOINT_URL")
    akey = os.environ.get("R2_ACCESS_KEY_ID")
    asecret = os.environ.get("R2_SECRET_ACCESS_KEY")
    bucket = os.environ.get("R2_BUCKET")
    if not args.dry_run and not all([endpoint, akey, asecret, bucket]):
        raise SystemExit(
            "R2_ENDPOINT_URL/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY/R2_BUCKET "
            "를 .env 또는 환경변수로 설정하세요(--dry-run 은 예외)."
        )

    ids = _db_ids(Path(args.db))
    if args.limit:
        ids = ids[: args.limit]
    needed = set(ids)
    logger.info("업로드 대상 id: %d", len(ids))

    logger.info("로컬 이미지 인덱싱 중… (%s)", args.img_root)
    index = _index_images(Path(args.img_root).expanduser(), needed)
    missing_local = [i for i in ids if i not in index]
    logger.info(
        "인덱스 완료: 발견 %d / 누락 %d", len(index), len(missing_local)
    )
    if missing_local[:5]:
        logger.warning("로컬 이미지 없음 예시: %s", missing_local[:5])

    if args.dry_run:
        logger.info(
            "[dry-run] 업로드 예정 %d개 (로컬누락 %d). 종료.",
            len(index), len(missing_local),
        )
        return

    client = _make_client(endpoint, akey, asecret, pool=args.workers)
    logger.info("기존 버킷 객체 조회 중…")
    existing = _existing_keys(client, bucket)
    logger.info("버킷 기존 객체: %d", len(existing))

    todo = [(i, index[i]) for i in ids if i in index and f"{i}.jpg" not in existing]
    skipped_existing = len(index) - len(todo)
    logger.info("올릴 것 %d / 이미있음 스킵 %d", len(todo), skipped_existing)

    uploaded = 0
    errors: list[tuple[str, str]] = []
    lock = threading.Lock()

    def _put(item: tuple[str, Path]) -> None:
        nonlocal uploaded
        oid, path = item
        try:
            client.upload_file(
                str(path), bucket, f"{oid}.jpg",
                ExtraArgs={"ContentType": "image/jpeg"},
            )
            with lock:
                uploaded += 1
                if uploaded % 5000 == 0:
                    logger.info("진행: %d/%d", uploaded, len(todo))
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append((oid, str(e)))

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_put, it) for it in todo]
        for _ in as_completed(futs):
            pass

    logger.info(
        "완료: 업로드 %d / 기존스킵 %d / 로컬누락 %d / 오류 %d",
        uploaded, skipped_existing, len(missing_local), len(errors),
    )
    for oid, msg in errors[:10]:
        logger.error("업로드 실패 %s: %s", oid, msg)
    if errors:
        raise SystemExit(f"{len(errors)}개 실패 — 재실행하면 멱등 이어올림.")


if __name__ == "__main__":
    main()
