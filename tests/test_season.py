"""계절 하드 필터 SQL 조각 — 실제 SQLite 로 배제 동작 검증."""

import sqlite3

import pytest

from playmcp_server.db import schema
from playmcp_server.db.season import SEASONS, season_where


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    yield conn
    conn.close()


def _insert(conn, oid, **cols):
    keys = ["id", "image_url", "style", *cols.keys()]
    ph = ",".join("?" * len(keys))
    conn.execute(
        f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
        [oid, f"u/{oid}", "모던", *cols.values()],
    )


def _kept(conn, season):
    frag, params = season_where(season)
    sql = "SELECT id FROM outfits WHERE deleted_at IS NULL"
    if frag:
        sql += " AND " + frag
    return {r[0] for r in conn.execute(sql, params)}


def test_seasons_set() -> None:
    assert SEASONS == {"봄가을", "여름", "겨울"}


def test_summer_excludes_warm_coat_maxi(db) -> None:
    _insert(db, "ok", top_warmth="시원", bottom_length="미디")
    _insert(db, "warm", outer_warmth="따뜻")          # 따뜻 → 탈락
    _insert(db, "coat", outer_category="코트")         # 코트 → 탈락
    _insert(db, "maxi", bottom_length="맥시")          # 맥시 → 탈락
    _insert(db, "null", top_warmth=None)               # 결측 → 통과
    db.commit()
    assert _kept(db, "여름") == {"ok", "null"}


def test_winter_excludes_cool_sleeveless_mini_bratop(db) -> None:
    _insert(db, "ok", top_warmth="따뜻", top_sleeve="긴팔")
    _insert(db, "cool", top_warmth="시원")             # 시원 → 탈락
    _insert(db, "sleeve", top_sleeve="반팔")           # 반팔 → 탈락
    _insert(db, "mini", dress_length="미니")           # 미니 → 탈락
    _insert(db, "bra", top_category="브라탑")          # 브라탑 → 탈락
    db.commit()
    assert _kept(db, "겨울") == {"ok"}


def test_springfall_only_excludes_padding(db) -> None:
    _insert(db, "wool", outer_warmth="따뜻", outer_category="코트")  # 통과
    _insert(db, "linen", top_warmth="시원")            # 통과
    _insert(db, "pad", outer_category="패딩")          # 패딩만 탈락
    db.commit()
    assert _kept(db, "봄가을") == {"wool", "linen"}


def test_unknown_season_no_filter(db) -> None:
    _insert(db, "a", outer_category="패딩")
    db.commit()
    assert season_where("겨울잠") == ("", [])
    assert _kept(db, "겨울잠") == {"a"}
