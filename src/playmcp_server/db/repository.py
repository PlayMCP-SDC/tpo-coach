"""의상 데이터 저장소.

도구는 ClothingRepository Protocol 에만 의존한다(백엔드 교체 가능).
지금은 SQLiteClothingRepository 하나만 구현한다(하나의 read-only db 파일).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Protocol

from playmcp_server.models import ClothingItem, Outfit


class ClothingRepository(Protocol):
    """의상 아이템·셋업 조회 인터페이스."""

    def get_item(self, item_id: str) -> ClothingItem | None: ...

    def find_bottoms(
        self,
        colors: list[str],
        *,
        formality: int | None = None,
        season: str | None = None,
    ) -> list[ClothingItem]: ...

    def get_outfit(self, outfit_id: str) -> Outfit | None: ...

    def find_outfits(
        self,
        *,
        occasion: str,
        style: str | None = None,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> list[Outfit]: ...


def _item(row: sqlite3.Row) -> ClothingItem:
    return ClothingItem(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        subcategory=row["subcategory"],
        color=row["color"],
        image_url=row["image_url"],
        seller_name=row["seller_name"],
        seller_url=row["seller_url"],
        price=row["price"],
        formality=row["formality"],
        season=row["season"],
        style_tags=row["style_tags"],
    )


def _outfit(row: sqlite3.Row) -> Outfit:
    return Outfit(
        id=row["id"],
        title=row["title"],
        image_url=row["image_url"],
        source=row["source"],
        source_url=row["source_url"],
        formality=row["formality"],
        season=row["season"],
        occasion_tags=row["occasion_tags"],
        style_tags=row["style_tags"],
        items_note=row["items_note"],
    )


class SQLiteClothingRepository:
    """SQLite 기반 구현. 주어진 연결을 그대로 쓴다."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        self._conn = conn

    def get_item(self, item_id: str) -> ClothingItem | None:
        row = self._conn.execute(
            "SELECT * FROM clothing_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _item(row) if row else None

    def find_bottoms(
        self,
        colors: list[str],
        *,
        formality: int | None = None,
        season: str | None = None,
    ) -> list[ClothingItem]:
        if not colors:
            return []
        placeholders = ",".join("?" * len(colors))
        where = ["category = 'bottom'", f"color IN ({placeholders})"]
        params: list[object] = list(colors)
        if formality is not None:
            where.append("formality BETWEEN ? AND ?")
            params += [formality - 1, formality + 1]
        if season is not None:
            where.append("(season IS NULL OR season IN (?, 'all'))")
            params.append(season)
        sql = (
            "SELECT * FROM clothing_items WHERE "
            + " AND ".join(where)
            + " ORDER BY id"
        )
        return [_item(r) for r in self._conn.execute(sql, params)]

    def get_outfit(self, outfit_id: str) -> Outfit | None:
        row = self._conn.execute(
            "SELECT * FROM outfits WHERE id = ?", (outfit_id,)
        ).fetchone()
        return _outfit(row) if row else None

    def find_outfits(
        self,
        *,
        occasion: str,
        style: str | None = None,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> list[Outfit]:
        where = ["occasion_tags LIKE '%,' || ? || ',%'"]
        params: list[object] = [occasion]
        if style is not None:
            where.append("style_tags LIKE '%,' || ? || ',%'")
            params.append(style)
        if formality is not None:
            where.append("(formality IS NULL OR formality BETWEEN ? AND ?)")
            params += [formality - 1, formality + 1]
        if season is not None:
            where.append("(season IS NULL OR season IN (?, 'all'))")
            params.append(season)
        sql = (
            "SELECT * FROM outfits WHERE "
            + " AND ".join(where)
            + " ORDER BY id LIMIT ?"
        )
        params.append(limit)
        return [_outfit(r) for r in self._conn.execute(sql, params)]


# 기본 DB 경로: 패키지 내부 data/clothing.db. 환경변수로 재정의 가능.
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "clothing.db"

_repo: SQLiteClothingRepository | None = None


def _db_path() -> Path:
    return Path(os.environ.get("CLOTHING_DB_PATH", str(_DEFAULT_DB)))


def get_repository() -> SQLiteClothingRepository:
    """프로세스 단위 read-only 저장소 싱글턴을 돌려준다.

    DB 파일이 없으면 즉시 실패한다(fail-fast).
    """
    global _repo
    if _repo is None:
        path = _db_path()
        if not path.exists():
            raise FileNotFoundError(
                f"clothing DB 가 없습니다: {path}. "
                "`python -m playmcp_server.db.build_db` 로 생성하세요."
            )
        conn = sqlite3.connect(
            f"file:{path}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        _repo = SQLiteClothingRepository(conn)
    return _repo


def reset_repository() -> None:
    """싱글턴을 초기화한다(테스트·재로딩용)."""
    global _repo
    if _repo is not None:
        _repo._conn.close()
    _repo = None
