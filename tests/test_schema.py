"""스키마·태그 정규화 검증."""

import sqlite3

from playmcp_server.db import schema


def test_init_schema_creates_tables() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"clothing_items", "outfits"} <= names


def test_normalize_tags_wraps_with_delimiters() -> None:
    assert schema.normalize_tags("놀이동산, 데이트") == ",놀이동산,데이트,"


def test_normalize_tags_empty() -> None:
    assert schema.normalize_tags("") == ""
    assert schema.normalize_tags("  ") == ""


def test_tags_to_list_roundtrip() -> None:
    assert schema.tags_to_list(",놀이동산,데이트,") == ["놀이동산", "데이트"]
    assert schema.tags_to_list("") == []
