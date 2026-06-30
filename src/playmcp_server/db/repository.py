"""셋업(코디) 저장소.

도구는 OutfitRepository Protocol 에만 의존한다(백엔드 교체 가능).
지금은 SQLiteOutfitRepository 하나만 구현한다(하나의 read-only db 파일).
soft delete: deleted_at 이 NULL 인 활성 행만 조회한다.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Protocol

from playmcp_server.models import Outfit


class OutfitRepository(Protocol):
    """셋업 조회 인터페이스."""

    def get_outfit(self, outfit_id: str) -> Outfit | None: ...

    def find_outfits(
        self,
        *,
        style: str | None = None,
        substyle: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Outfit]: ...


def _outfit(row: sqlite3.Row) -> Outfit:
    return Outfit(
        id=row["id"],
        image_url=row["image_url"],
        style=row["style"],
        substyle=row["substyle"],
        top_category=row["top_category"],
        top_length=row["top_length"],
        bottom_category=row["bottom_category"],
        bottom_length=row["bottom_length"],
        outer_category=row["outer_category"],
        outer_length=row["outer_length"],
        dress_category=row["dress_category"],
        dress_length=row["dress_length"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )


class SQLiteOutfitRepository:
    """SQLite 기반 구현. 주어진 연결을 그대로 쓴다."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        self._conn = conn

    def get_outfit(self, outfit_id: str) -> Outfit | None:
        row = self._conn.execute(
            "SELECT * FROM outfits WHERE id = ? AND deleted_at IS NULL",
            (outfit_id,),
        ).fetchone()
        return _outfit(row) if row else None

    def find_outfits(
        self,
        *,
        style: str | None = None,
        substyle: str | None = None,
        category: str | None = None,
        limit: int = 20,
    ) -> list[Outfit]:
        where = ["deleted_at IS NULL"]
        params: list[object] = []
        if style is not None:
            where.append("style = ?")
            params.append(style)
        if substyle is not None:
            where.append("substyle = ?")
            params.append(substyle)
        if category is not None:
            # 카테고리는 부위별 컬럼에 흩어져 있어 4개 중 하나라도 일치하면 포함.
            where.append(
                "(top_category = ? OR bottom_category = ? "
                "OR outer_category = ? OR dress_category = ?)"
            )
            params += [category] * 4
        sql = (
            "SELECT * FROM outfits WHERE "
            + " AND ".join(where)
            + " ORDER BY id LIMIT ?"
        )
        params.append(limit)
        return [_outfit(r) for r in self._conn.execute(sql, params)]


# 기본 DB 경로: 패키지 내부 data/clothing.db. 환경변수로 재정의 가능.
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "clothing.db"

_repo: SQLiteOutfitRepository | None = None


def _db_path() -> Path:
    return Path(os.environ.get("CLOTHING_DB_PATH", str(_DEFAULT_DB)))


def get_repository() -> SQLiteOutfitRepository:
    """프로세스 단위 read-only 저장소 싱글턴을 돌려준다.

    DB 파일이 없으면 즉시 실패한다(fail-fast).
    """
    global _repo
    if _repo is None:
        path = _db_path()
        if not path.exists():
            raise FileNotFoundError(
                f"outfits DB 가 없습니다: {path}. "
                "`python -m playmcp_server.db.build_db --src ...` 로 생성하세요."
            )
        conn = sqlite3.connect(
            f"file:{path}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        _repo = SQLiteOutfitRepository(conn)
    return _repo


def reset_repository() -> None:
    """싱글턴을 초기화한다(테스트·재로딩용)."""
    global _repo
    if _repo is not None:
        _repo._conn.close()
    _repo = None
