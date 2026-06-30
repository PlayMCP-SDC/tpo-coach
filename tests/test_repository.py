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


@pytest.fixture
def outfit_repo() -> SQLiteClothingRepository:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO outfits "
        "(id,title,image_url,source,source_url,formality,season,"
        "occasion_tags,style_tags,items_note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                "f1", "놀이동산 캐주얼", "http://img/f1", "instagram",
                "http://ig/f1", 2, "spring", ",놀이동산,데이트,",
                ",캐주얼,", "흰 티, 데님"
            ),
            (
                "f2", "하객룩", "http://img/f2", "musinsa",
                "http://ms/f2", 4, "all", ",하객룩,", ",클래식,", None
            ),
            (
                "f3", "놀이동산 스트릿", "http://img/f3", "instagram",
                "http://ig/f3", 1, "summer", ",놀이동산,여행,",
                ",스트릿,", None
            ),
        ],
    )
    conn.commit()
    return SQLiteClothingRepository(conn)


def test_get_outfit_found(outfit_repo: SQLiteClothingRepository) -> None:
    fit = outfit_repo.get_outfit("f1")
    assert fit is not None
    assert fit.title == "놀이동산 캐주얼"


def test_get_outfit_missing(outfit_repo: SQLiteClothingRepository) -> None:
    assert outfit_repo.get_outfit("nope") is None


def test_find_outfits_by_occasion(outfit_repo: SQLiteClothingRepository) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산")
    assert {f.id for f in fits} == {"f1", "f3"}


def test_find_outfits_exact_token_match(
    outfit_repo: SQLiteClothingRepository,
) -> None:
    """부분일치 오탐 방지: '동산'은 '놀이동산'에 걸리면 안 된다."""
    assert outfit_repo.find_outfits(occasion="동산") == []


def test_find_outfits_style_filter(
    outfit_repo: SQLiteClothingRepository,
) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산", style="스트릿")
    assert {f.id for f in fits} == {"f3"}


def test_find_outfits_limit(outfit_repo: SQLiteClothingRepository) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산", limit=1)
    assert len(fits) == 1


def test_get_repository_reads_env_path(tmp_path, monkeypatch) -> None:
    """CLOTHING_DB_PATH 가 가리키는 read-only DB 를 연다."""
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.execute(
        "INSERT INTO clothing_items "
        "(id,name,category,color,image_url,formality) "
        "VALUES ('x','t','bottom','검정','http://i',3)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    repo = repository.get_repository()
    assert repo.get_item("x") is not None


def test_get_repository_is_read_only(tmp_path, monkeypatch) -> None:
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    repo = repository.get_repository()
    with pytest.raises(sqlite3.OperationalError):
        repo._conn.execute(
            "INSERT INTO clothing_items "
            "(id,name,category,color,image_url,formality) "
            "VALUES ('y','t','bottom','검정','http://i',3)"
        )
    repository.reset_repository()
