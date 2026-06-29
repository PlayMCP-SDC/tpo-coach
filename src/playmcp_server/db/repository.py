"""의상 데이터 저장소.

도구는 ClothingRepository Protocol 에만 의존한다(백엔드 교체 가능).
지금은 SQLiteClothingRepository 하나만 구현한다(하나의 read-only db 파일).
"""

from __future__ import annotations

import sqlite3
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
