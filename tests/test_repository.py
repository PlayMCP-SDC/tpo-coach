"""SQLiteClothingRepository 검증 (in-memory 연결)."""

import sqlite3

import pytest

from playmcp_server.db import schema
from playmcp_server.db.repository import SQLiteClothingRepository


@pytest.fixture
def repo() -> SQLiteClothingRepository:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO clothing_items "
        "(id,name,category,subcategory,color,image_url,seller_name,seller_url,"
        "price,formality,season,style_tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("b1", "베이지 슬랙스", "bottom", "slacks", "베이지",
             "http://img/b1", "무신사", "http://buy/b1", 39000, 3, "all", "미니멀"),
            ("b2", "흰 데님", "bottom", "jeans", "흰색",
             "http://img/b2", "무신사", "http://buy/b2", 49000, 2, "summer", None),
            ("b3", "검정 슬랙스", "bottom", "slacks", "검정",
             "http://img/b3", None, None, None, 5, "all", "포멀"),
            ("t1", "남색 셔츠", "top", "shirt", "남색",
             "http://img/t1", None, None, None, 3, "all", None),
        ],
    )
    conn.commit()
    return SQLiteClothingRepository(conn)


def test_get_item_found(repo: SQLiteClothingRepository) -> None:
    item = repo.get_item("b1")
    assert item is not None
    assert item.name == "베이지 슬랙스"
    assert item.color == "베이지"


def test_get_item_missing(repo: SQLiteClothingRepository) -> None:
    assert repo.get_item("nope") is None


def test_find_bottoms_only_bottoms(repo: SQLiteClothingRepository) -> None:
    items = repo.find_bottoms(["남색", "검정"])
    assert {i.id for i in items} == {"b3"}  # t1(남색)은 top 이라 제외


def test_find_bottoms_color_filter(repo: SQLiteClothingRepository) -> None:
    items = repo.find_bottoms(["베이지", "흰색"])
    assert {i.id for i in items} == {"b1", "b2"}


def test_find_bottoms_formality_window(repo: SQLiteClothingRepository) -> None:
    # formality=5 ± 1 → 4~6 → b3(5)만
    items = repo.find_bottoms(["베이지", "흰색", "검정"], formality=5)
    assert {i.id for i in items} == {"b3"}


def test_find_bottoms_season_filter(repo: SQLiteClothingRepository) -> None:
    # summer 요청 → b2(summer) + all 은 통과, b1(all) 포함
    items = repo.find_bottoms(["베이지", "흰색"], season="summer")
    assert {i.id for i in items} == {"b1", "b2"}


def test_find_bottoms_empty_colors(repo: SQLiteClothingRepository) -> None:
    assert repo.find_bottoms([]) == []
