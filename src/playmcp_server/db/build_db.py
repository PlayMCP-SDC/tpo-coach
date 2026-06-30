"""큐레이션 시드 CSV → read-only clothing.db 생성 + 유효성 검증.

CLI:  python -m playmcp_server.db.build_db
기본 입력: data/clothing_items.csv, data/outfits.csv → 출력: data/clothing.db
"""

from __future__ import annotations

import csv
import logging
import sqlite3
import sys
from pathlib import Path

from playmcp_server.db import schema
from playmcp_server.db.color_rules import NAMED_COLORS
from playmcp_server.db.vocab import (
    CATEGORIES,
    OCCASION_TAGS,
    SEASONS,
    STYLE_TAGS,
)

logger = logging.getLogger("playmcp_server.db.build_db")

_DATA = Path(__file__).resolve().parent.parent / "data"


def _int_or_none(v: str | None) -> int | None:
    v = (v or "").strip()
    return int(v) if v else None


def _check_tags(raw: str, allowed: frozenset[str], field: str) -> None:
    for t in (p.strip() for p in raw.split(",") if p.strip()):
        if t not in allowed:
            raise ValueError(f"{field} 태그 미등록: {t} (허용: {sorted(allowed)})")


def _check_season(v: str | None) -> None:
    if v and v.strip() and v.strip() not in SEASONS:
        raise ValueError(f"season 미등록: {v} (허용: {sorted(SEASONS)})")


def build(items: list[dict], outfits: list[dict], dest: Path) -> None:
    """검증 후 dest 에 새 DB 를 만든다(기존 파일 덮어씀)."""
    dest = Path(dest)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    try:
        schema.init_schema(conn)
        for it in items:
            if it["color"] not in NAMED_COLORS:
                raise ValueError(f"color 미등록: {it['color']}")
            if it["category"] not in CATEGORIES:
                raise ValueError(f"category 미등록: {it['category']}")
            _check_season(it.get("season"))
            conn.execute(
                "INSERT INTO clothing_items (id,name,category,subcategory,color,"
                "image_url,seller_name,seller_url,price,formality,season,"
                "style_tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    it["id"], it["name"], it["category"],
                    it.get("subcategory") or None, it["color"], it["image_url"],
                    it.get("seller_name") or None, it.get("seller_url") or None,
                    _int_or_none(it.get("price")),
                    int(it.get("formality") or 3),
                    it.get("season") or None, it.get("style_tags") or None,
                ),
            )
        for ft in outfits:
            _check_tags(ft["occasion_tags"], OCCASION_TAGS, "occasion")
            _check_tags(ft.get("style_tags") or "", STYLE_TAGS, "style")
            _check_season(ft.get("season"))
            conn.execute(
                "INSERT INTO outfits (id,title,image_url,source,source_url,"
                "formality,season,occasion_tags,style_tags,items_note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    ft["id"], ft.get("title") or None, ft["image_url"],
                    ft.get("source") or None, ft.get("source_url") or None,
                    _int_or_none(ft.get("formality")), ft.get("season") or None,
                    schema.normalize_tags(ft["occasion_tags"]),
                    schema.normalize_tags(ft.get("style_tags") or "") or None,
                    ft.get("items_note") or None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    items = _read_csv(_DATA / "clothing_items.csv")
    outfits = _read_csv(_DATA / "outfits.csv")
    dest = _DATA / "clothing.db"
    build(items, outfits, dest)
    logger.info(
        "clothing.db 생성: items=%d outfits=%d → %s",
        len(items), len(outfits), dest,
    )


if __name__ == "__main__":
    main()
