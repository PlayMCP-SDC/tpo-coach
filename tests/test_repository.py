"""SQLiteOutfitRepository 검증 (in-memory 연결)."""

import sqlite3

import pytest

from playmcp_server.db import schema
from playmcp_server.db.repository import SQLiteOutfitRepository

_COLS = (
    "id,image_url,style,substyle,"
    "top_category,top_length,bottom_category,bottom_length,"
    "dress_category,dress_length,deleted_at"
)


@pytest.fixture
def repo() -> SQLiteOutfitRepository:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        f"INSERT INTO outfits ({_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            # id, url, style, substyle, top_cat, top_len, bot_cat, bot_len,
            # dress_cat, dress_len, deleted_at
            ("o1", "u/o1", "모던", "톰보이", "블라우스", None,
             "팬츠", "롱", None, None, None),
            ("o2", "u/o2", "스트리트", "스트리트", "티셔츠", "노멀",
             "청바지", "발목", None, None, None),
            ("o3", "u/o3", "모던", "페미닌", None, None,
             None, None, "드레스", "미니", None),
            # soft-deleted → 모든 조회에서 제외돼야 함
            ("o4", "u/o4", "모던", "톰보이", "셔츠", None,
             None, None, None, None, "2026-07-01"),
        ],
    )
    conn.commit()
    return SQLiteOutfitRepository(conn)


def test_get_outfit_found(repo: SQLiteOutfitRepository) -> None:
    o = repo.get_outfit("o1")
    assert o is not None
    assert o.style == "모던"
    assert o.bottom_category == "팬츠"
    assert o.bottom_length == "롱"


def test_get_outfit_missing(repo: SQLiteOutfitRepository) -> None:
    assert repo.get_outfit("nope") is None


def test_get_outfit_excludes_soft_deleted(repo: SQLiteOutfitRepository) -> None:
    assert repo.get_outfit("o4") is None


def test_find_by_style(repo: SQLiteOutfitRepository) -> None:
    # o4 는 soft-deleted 라 모던이어도 제외
    assert {o.id for o in repo.find_outfits(style="모던")} == {"o1", "o3"}


def test_find_by_substyle(repo: SQLiteOutfitRepository) -> None:
    assert {o.id for o in repo.find_outfits(substyle="페미닌")} == {"o3"}


def test_find_by_category_across_parts(repo: SQLiteOutfitRepository) -> None:
    assert {o.id for o in repo.find_outfits(category="드레스")} == {"o3"}
    assert {o.id for o in repo.find_outfits(category="청바지")} == {"o2"}


def test_find_combined_filters(repo: SQLiteOutfitRepository) -> None:
    assert {o.id for o in repo.find_outfits(style="모던", category="팬츠")} == {
        "o1"
    }


def test_find_limit(repo: SQLiteOutfitRepository) -> None:
    assert len(repo.find_outfits(style="모던", limit=1)) == 1


def test_get_repository_reads_env_path(tmp_path, monkeypatch) -> None:
    """CLOTHING_DB_PATH 가 가리키는 read-only DB 를 연다."""
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.execute(
        "INSERT INTO outfits (id,image_url,style) VALUES ('x','u/x','모던')"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    try:
        repo = repository.get_repository()
        assert repo.get_outfit("x") is not None
    finally:
        repository.reset_repository()


def test_get_repository_is_read_only(tmp_path, monkeypatch) -> None:
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    try:
        repo = repository.get_repository()
        with pytest.raises(sqlite3.OperationalError):
            repo._conn.execute(
                "INSERT INTO outfits (id,image_url,style) "
                "VALUES ('y','u/y','모던')"
            )
    finally:
        repository.reset_repository()


def test_sample_outfits_only_style_and_active(repo: SQLiteOutfitRepository) -> None:
    # "모던" 활성은 o1, o3 (o4 는 soft-deleted 라 제외)
    ids = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert ids == {"o1", "o3"}


def test_sample_outfits_respects_n(repo: SQLiteOutfitRepository) -> None:
    assert len(repo.sample_outfits(style="모던", n=1)) == 1


def test_sample_outfits_unknown_style_empty(repo: SQLiteOutfitRepository) -> None:
    assert repo.sample_outfits(style="없는스타일", n=3) == []


def test_sample_outfits_returns_outfit_objects(repo: SQLiteOutfitRepository) -> None:
    out = repo.sample_outfits(style="스트리트", n=3)
    assert len(out) == 1
    assert out[0].id == "o2"
    assert out[0].bottom_category == "청바지"


def test_sample_outfits_negative_n_returns_empty(repo: SQLiteOutfitRepository) -> None:
    # 음수 n 은 SQLite 에서 무제한(LIMIT -1)이 되므로 0 으로 막아 빈 결과를 보장한다
    assert repo.sample_outfits(style="모던", n=-1) == []


def test_outfit_has_season_fields() -> None:
    from playmcp_server.models import Outfit

    o = Outfit(
        id="x", image_url="u", style="모던",
        top_sleeve="반팔", top_material="린넨", top_warmth="시원",
        bottom_warmth="중립",
    )
    assert o.top_sleeve == "반팔"
    assert o.top_material == "린넨"
    assert o.top_warmth == "시원"
    assert o.outer_sleeve is None  # 기본값 None
    assert o.dress_warmth is None


def _repo_with(rows):
    import sqlite3

    from playmcp_server.db import schema
    from playmcp_server.db.repository import SQLiteOutfitRepository

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    for r in rows:
        cols = {k: v for k, v in r.items() if k != "_id"}
        keys = ["id", "image_url", "style", *cols.keys()]
        ph = ",".join("?" * len(keys))
        conn.execute(
            f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
            [r["_id"], f"u/{r['_id']}", "모던", *cols.values()],
        )
    conn.commit()
    return SQLiteOutfitRepository(conn)


def test_sample_applies_season_filter() -> None:
    repo = _repo_with([
        {"_id": "keep", "bottom_length": "미디"},
        {"_id": "drop", "bottom_length": "맥시"},   # 여름 배제
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10, season="여름")}
    assert got == {"keep"}


def test_sample_no_season_returns_all() -> None:
    repo = _repo_with([
        {"_id": "a", "bottom_length": "맥시"},
        {"_id": "b", "bottom_length": "미디"},
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert got == {"a", "b"}


def test_sample_excludes_incomplete() -> None:
    repo = _repo_with([
        {"_id": "keep", "is_complete": 1},
        {"_id": "null_ok"},                 # is_complete 미지정(NULL) → 통과
        {"_id": "drop", "is_complete": 0},  # 불완전 → 제외
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert got == {"keep", "null_ok"}


def test_summer_prefers_short_sleeve_strongly() -> None:
    # 반팔(선호)·긴팔(비선호) 각 20건, 모두 완성. n=1 을 여러 번 뽑아 반팔이 지배적인지.
    rows = []
    for i in range(20):
        rows.append({"_id": f"s{i}", "top_sleeve": "반팔", "is_complete": 1})
        rows.append({"_id": f"l{i}", "top_sleeve": "긴팔", "is_complete": 1})
    repo = _repo_with(rows)
    short = sum(
        1
        for _ in range(100)
        if repo.sample_outfits(style="모던", n=1, season="여름")[0].top_sleeve
        == "반팔"
    )
    assert short >= 80, f"반팔 선택 {short}/100 — 편향 약함"


def test_outfit_maps_new_columns() -> None:
    repo = _repo_with([
        {"_id": "z", "top_sleeve": "반팔",
         "top_material": "린넨", "top_warmth": "시원"},
    ])
    o = repo.sample_outfits(style="모던", n=1)[0]
    assert o.top_sleeve == "반팔"
    assert o.top_material == "린넨"
    assert o.top_warmth == "시원"
