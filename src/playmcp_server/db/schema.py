"""SQLite 스키마와 태그 정규화 헬퍼."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS clothing_items (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    subcategory  TEXT,
    color        TEXT NOT NULL,
    image_url    TEXT NOT NULL,
    seller_name  TEXT,
    seller_url   TEXT,
    price        INTEGER,
    formality    INTEGER NOT NULL DEFAULT 3,
    season       TEXT,
    style_tags   TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_cat_color
  ON clothing_items(category, color);
CREATE INDEX IF NOT EXISTS idx_items_cat_formality
  ON clothing_items(category, formality);

CREATE TABLE IF NOT EXISTS outfits (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    image_url     TEXT NOT NULL,
    source        TEXT,
    source_url    TEXT,
    formality     INTEGER,
    season        TEXT,
    occasion_tags TEXT NOT NULL,
    style_tags    TEXT,
    items_note    TEXT
);
CREATE INDEX IF NOT EXISTS idx_outfits_formality
  ON outfits(formality);
CREATE INDEX IF NOT EXISTS idx_outfits_season
  ON outfits(season);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """주어진 연결에 테이블·인덱스를 생성한다(멱등)."""
    conn.executescript(SCHEMA)


def normalize_tags(raw: str) -> str:
    """'a, b' → ',a,b,' (정확 토큰 매칭용). 비면 ''."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return "," + ",".join(parts) + "," if parts else ""


def tags_to_list(normalized: str) -> list[str]:
    """',a,b,' → ['a','b']. 비면 []."""
    return [p for p in normalized.split(",") if p]
