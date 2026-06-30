"""시드 CSV → DB 빌드·검증."""

import sqlite3

import pytest

from playmcp_server.db import build_db

GOOD_ITEM = {
    "id": "b1", "name": "베이지 슬랙스", "category": "bottom",
    "subcategory": "slacks", "color": "베이지", "image_url": "http://i",
    "seller_name": "무신사", "seller_url": "http://buy", "price": "39000",
    "formality": "3", "season": "all", "style_tags": "미니멀",
}
GOOD_OUTFIT = {
    "id": "f1", "title": "놀이동산 캐주얼", "image_url": "http://i",
    "source": "instagram", "source_url": "http://ig", "formality": "2",
    "season": "spring", "occasion_tags": "놀이동산,데이트",
    "style_tags": "캐주얼", "items_note": "흰 티, 데님",
}


def test_build_inserts_rows(tmp_path) -> None:
    dest = tmp_path / "out.db"
    build_db.build([GOOD_ITEM], [GOOD_OUTFIT], dest)
    conn = sqlite3.connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM clothing_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM outfits").fetchone()[0] == 1


def test_build_normalizes_tags(tmp_path) -> None:
    dest = tmp_path / "out.db"
    build_db.build([GOOD_ITEM], [GOOD_OUTFIT], dest)
    conn = sqlite3.connect(dest)
    tags = conn.execute(
        "SELECT occasion_tags FROM outfits WHERE id='f1'"
    ).fetchone()[0]
    assert tags == ",놀이동산,데이트,"


def test_build_rejects_unknown_color(tmp_path) -> None:
    bad = {**GOOD_ITEM, "color": "형광연두"}
    with pytest.raises(ValueError, match="color"):
        build_db.build([bad], [], tmp_path / "out.db")


def test_build_rejects_unknown_category(tmp_path) -> None:
    bad = {**GOOD_ITEM, "category": "모자류"}
    with pytest.raises(ValueError, match="category"):
        build_db.build([bad], [], tmp_path / "out.db")


def test_build_rejects_unknown_occasion_tag(tmp_path) -> None:
    bad = {**GOOD_OUTFIT, "occasion_tags": "달나라"}
    with pytest.raises(ValueError, match="occasion"):
        build_db.build([], [bad], tmp_path / "out.db")
