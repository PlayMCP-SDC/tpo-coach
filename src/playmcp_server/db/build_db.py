"""K-Fashion 라벨링 JSON → read-only outfits.db 생성 + 유효성 검증.

CLI:  python -m playmcp_server.db.build_db --src <라벨링데이터 루트> [--dest <db>]
      (--src 생략 시 환경변수 KFASHION_LABEL_DIR 사용)

입력 구조:  <루트>/<스타일폴더>/<이미지식별자>.json
출력:       data/clothing.db (테이블 outfits)

한 JSON = 한 셋업(코디) = outfits 한 행. 부위(상의/하의/아우터/원피스)별
카테고리·기장·소매기장·소재를 추출하고(소재→보온등급 파생), 좌표·색상 등
나머지는 버린다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from playmcp_server.db import schema
from playmcp_server.db.vocab import (
    CATEGORIES_BY_PART,
    LENGTHS,
    MATERIALS,
    SLEEVES,
    STYLES,
    SUBSTYLES,
    normalize_length,
    warmth_of,
)

logger = logging.getLogger("playmcp_server.db.build_db")

_DATA = Path(__file__).resolve().parent.parent / "data"

# 라벨링 부위 → outfits 컬럼 prefix.
_PART_PREFIX: dict[str, str] = {
    "상의": "top",
    "하의": "bottom",
    "아우터": "outer",
    "원피스": "dress",
}

# 소매기장이 있는 부위(하의 제외).
_SLEEVE_PARTS: frozenset[str] = frozenset({"상의", "아우터", "원피스"})

_INSERT = (
    "INSERT INTO outfits ("
    "id,image_url,style,substyle,"
    "top_category,top_length,top_sleeve,top_material,top_warmth,"
    "bottom_category,bottom_length,bottom_material,bottom_warmth,"
    "outer_category,outer_length,outer_sleeve,outer_material,outer_warmth,"
    "dress_category,dress_length,dress_sleeve,dress_material,dress_warmth,"
    "created_at,updated_at,deleted_at) "
    "VALUES (:id,:image_url,:style,:substyle,"
    ":top_category,:top_length,:top_sleeve,:top_material,:top_warmth,"
    ":bottom_category,:bottom_length,:bottom_material,:bottom_warmth,"
    ":outer_category,:outer_length,:outer_sleeve,:outer_material,:outer_warmth,"
    ":dress_category,:dress_length,:dress_sleeve,:dress_material,:dress_warmth,"
    ":created_at,:updated_at,NULL)"
)


def _image_url(oid: str, url_base: str) -> str:
    """전역 고유 id 로 버킷 공개 URL 을 만든다('{base}/{id}.jpg').

    url_base 가 비면 객체 키('{id}.jpg')만 저장한다(업로드 후 보정 전제).
    """
    key = f"{oid}.jpg"
    return f"{url_base.rstrip('/')}/{key}" if url_base else key


class ParseError(ValueError):
    """라벨링 JSON 이 기대 구조·어휘에서 벗어났을 때."""


def _first(arr: object) -> dict:
    """라벨링의 [{...}] 형태에서 첫 비어있지 않은 dict 를 돌려준다(없으면 {})."""
    if isinstance(arr, list):
        for x in arr:
            if isinstance(x, dict) and x:
                return x
    return {}


# 시그니처에 포함하는 부위별 속성(저장 안 하는 색상·소재·핏 등까지 전부).
_SIG_ATTRS = (
    "카테고리", "색상", "서브색상", "기장", "소매기장",
    "소재", "프린트", "핏", "넥라인", "옷깃", "디테일",
)


def _label_signature(lab: dict) -> str:
    """전체 라벨(저장 안 하는 속성 포함)로 dedupe 키를 만든다.

    같은 셋업의 동일 라벨 컷만 합치고, 한 속성이라도 다르면 분리(안전).
    """
    s = _first(lab.get("스타일"))
    parts: list[tuple] = []
    for part in _PART_PREFIX:
        it = _first(lab.get(part))
        vals = []
        for a in _SIG_ATTRS:
            v = it.get(a)
            if a == "기장":
                v = normalize_length(v)
            elif isinstance(v, list):
                v = tuple(sorted(map(str, v)))
            vals.append(v)
        parts.append((part, *vals))
    return repr((s.get("스타일"), s.get("서브스타일"), tuple(parts)))


def parse_outfit(doc: dict, *, now: str, url_base: str = "") -> dict:
    """라벨링 JSON 문서 → outfits 행 dict. 어휘 위반 시 ParseError.

    image_url 은 id 로 조립한다(디스크/JSON 파일명이 아니라 버킷 키 기준).
    """
    img = doc.get("이미지 정보", {})
    ds = doc.get("데이터셋 정보", {})
    lab = ds.get("데이터셋 상세설명", {}).get("라벨링", {})

    oid = img.get("이미지 식별자")
    if oid is None:
        raise ParseError("이미지 식별자 누락")
    oid = str(oid)

    style_obj = _first(lab.get("스타일"))
    style = style_obj.get("스타일")
    substyle = style_obj.get("서브스타일") or None
    if style not in STYLES:
        raise ParseError(f"스타일 미등록: {style!r}")
    if substyle is not None and substyle not in SUBSTYLES:
        raise ParseError(f"서브스타일 미등록: {substyle!r}")

    row: dict[str, object | None] = {
        "id": oid,
        "image_url": _image_url(oid, url_base),
        "style": style,
        "substyle": substyle,
        "created_at": ds.get("파일 생성일자") or None,
        "updated_at": now,
    }
    for part, prefix in _PART_PREFIX.items():
        item = _first(lab.get(part))
        category = item.get("카테고리") or None
        if category is not None and category not in CATEGORIES_BY_PART[part]:
            raise ParseError(f"{part} 카테고리 미등록: {category!r}")
        length = normalize_length(item.get("기장"))
        if length is not None and length not in LENGTHS:
            raise ParseError(f"{part} 기장 미등록: {length!r}")
        row[f"{prefix}_category"] = category
        row[f"{prefix}_length"] = length

        # 소재: 원값(리스트) 보존 + 보온등급 파생.
        materials = item.get("소재") or []
        if not isinstance(materials, list):
            materials = [materials]
        for m in materials:
            if m not in MATERIALS:
                raise ParseError(f"{part} 소재 미등록: {m!r}")
        row[f"{prefix}_material"] = ",".join(materials) or None
        row[f"{prefix}_warmth"] = warmth_of(materials)

        # 소매기장: 상의/아우터/원피스만.
        if part in _SLEEVE_PARTS:
            sleeve = item.get("소매기장") or None
            if sleeve is not None and sleeve not in SLEEVES:
                raise ParseError(f"{part} 소매기장 미등록: {sleeve!r}")
            row[f"{prefix}_sleeve"] = sleeve
    # dedupe 키(INSERT 시 무시되는 부가 키). 전체 라벨 기준.
    row["_sig"] = _label_signature(lab)
    return row


def iter_json_files(root: Path) -> Iterator[Path]:
    """<루트>/<스타일>/*.json 을 정렬 순서로 순회한다."""
    for style_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        yield from sorted(style_dir.glob("*.json"))


def build(
    root: Path,
    dest: Path,
    *,
    url_base: str = "",
    strict: bool = False,
    batch: int = 1000,
) -> tuple[int, int, int]:
    """root 의 라벨링 JSON 을 검증·적재해 dest DB 를 만든다(기존 파일 덮어씀).

    url_base: 버킷 공개 base URL. image_url = "{url_base}/{id}.jpg".
    전체 라벨 시그니처가 같은 컷은 1개만 적재한다(첫 등장이 대표).
    Returns: (적재 수, 스킵 수, 중복제거 수). strict=True 면 첫 오류에서 중단.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    loaded = skipped = deduped = 0
    seen: set[str] = set()
    conn = sqlite3.connect(dest)
    try:
        schema.init_schema(conn)
        buf: list[dict] = []
        for fp in iter_json_files(root):
            try:
                doc = json.loads(fp.read_text(encoding="utf-8"))
                row = parse_outfit(doc, now=now, url_base=url_base)
            except (ParseError, json.JSONDecodeError, OSError) as e:
                if strict:
                    raise ParseError(f"{fp}: {e}") from e
                skipped += 1
                logger.warning("스킵 %s: %s", fp.name, e)
                continue
            sig = row.pop("_sig")
            if sig in seen:
                deduped += 1
                continue
            seen.add(sig)
            buf.append(row)
            if len(buf) >= batch:
                conn.executemany(_INSERT, buf)
                loaded += len(buf)
                buf.clear()
        if buf:
            conn.executemany(_INSERT, buf)
            loaded += len(buf)
        conn.commit()
    finally:
        conn.close()
    return loaded, skipped, deduped


def _resolve_src(arg: str | None) -> Path:
    src = arg or os.environ.get("KFASHION_LABEL_DIR")
    if not src:
        raise SystemExit(
            "라벨링데이터 루트를 지정하세요: --src <경로> 또는 "
            "환경변수 KFASHION_LABEL_DIR"
        )
    root = Path(src).expanduser()
    if not root.is_dir():
        raise SystemExit(f"라벨링데이터 루트가 없습니다: {root}")
    return root


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    parser = argparse.ArgumentParser(description="K-Fashion 라벨링 → outfits.db")
    parser.add_argument("--src", help="라벨링데이터 루트 (스타일 폴더들의 부모)")
    parser.add_argument("--dest", default=str(_DATA / "clothing.db"))
    parser.add_argument(
        "--url-base",
        default=os.environ.get("IMAGE_URL_BASE", ""),
        help="버킷 공개 base URL (env IMAGE_URL_BASE). image_url='{base}/{id}.jpg'",
    )
    parser.add_argument(
        "--strict", action="store_true", help="첫 오류에서 중단(기본: 스킵)"
    )
    args = parser.parse_args()

    root = _resolve_src(args.src)
    if not args.url_base:
        logger.warning(
            "--url-base 미지정 — image_url 에 객체 키('{id}.jpg')만 저장됨"
        )
    loaded, skipped, deduped = build(
        root, Path(args.dest), url_base=args.url_base, strict=args.strict
    )
    logger.info(
        "outfits.db 생성: loaded=%d deduped=%d skipped=%d → %s",
        loaded, deduped, skipped, args.dest,
    )


if __name__ == "__main__":
    main()
