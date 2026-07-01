"""outfits 스키마 검증."""

import sqlite3

from playmcp_server.db import schema


def test_init_schema_creates_outfits_table() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "outfits" in names


def test_outfits_has_expected_columns() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(outfits)")}
    expected = {
        "id", "image_url", "style", "substyle",
        "top_category", "top_length", "bottom_category", "bottom_length",
        "outer_category", "outer_length", "dress_category", "dress_length",
        "created_at", "updated_at", "deleted_at",
    }
    assert expected <= cols


def test_init_schema_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    schema.init_schema(conn)  # 두 번 호출해도 예외 없어야 한다
    n = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='outfits'"
    ).fetchone()[0]
    assert n == 1


def test_schema_has_season_columns() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(outfits)")}
    for c in (
        "top_sleeve", "outer_sleeve", "dress_sleeve",
        "top_material", "bottom_material", "outer_material", "dress_material",
        "top_warmth", "bottom_warmth", "outer_warmth", "dress_warmth",
    ):
        assert c in cols, f"컬럼 누락: {c}"
    assert "bottom_sleeve" not in cols  # 하의엔 소매기장 없음


def test_schema_has_is_complete_column() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(outfits)")}
    assert "is_complete" in cols
    assert cols["is_complete"] == "INTEGER"
