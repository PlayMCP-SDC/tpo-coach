"""셋업 추천 도구 — 순수 헬퍼 + 도구 동작 검증."""

import sqlite3
import time
from pathlib import Path

import pytest

from playmcp_server.db import repository, schema
from playmcp_server.models import Outfit
from playmcp_server.tools.recommend import (
    _clamp_n,
    _format_outfit,
    _interleave,
    _no_valid_styles_msg,
    _normalize_styles,
    _recommend,
)


def test_clamp_n_bounds() -> None:
    assert _clamp_n(0) == 1
    assert _clamp_n(1) == 1
    assert _clamp_n(3) == 3
    assert _clamp_n(10) == 10
    assert _clamp_n(999) == 10


def test_format_outfit_has_image_and_parts() -> None:
    o = Outfit(
        id="a",
        image_url="https://img/a.jpg",
        style="로맨틱",
        substyle="페미닌",
        top_category="블라우스",
        top_length="크롭",
        bottom_category="스커트",
        bottom_length="미니",
    )
    block = _format_outfit(o)
    assert "![" in block and "https://img/a.jpg" in block
    assert "로맨틱" in block and "페미닌" in block
    assert "블라우스" in block and "스커트" in block


def test_format_outfit_skips_absent_parts() -> None:
    o = Outfit(id="b", image_url="u/b", style="페미닌", dress_category="드레스")
    block = _format_outfit(o)
    assert "드레스" in block
    assert "상의" not in block and "하의" not in block


@pytest.fixture
def small_db(tmp_path, monkeypatch):
    """style 로 조회 가능한 작은 read-write 임시 DB 를 싱글턴에 물린다."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO outfits "
        "(id,image_url,style,substyle,top_category,bottom_category) "
        "VALUES (?,?,?,?,?,?)",
        [
            ("a", "https://img/a.jpg", "로맨틱", "로맨틱", "블라우스", "스커트"),
            ("b", "https://img/b.jpg", "로맨틱", None, "니트웨어", "팬츠"),
            ("c", "https://img/c.jpg", "스트리트", None, "티셔츠", "청바지"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLOTHING_DB_PATH", str(db))
    repository.reset_repository()
    yield
    repository.reset_repository()


def test_recommend_two_styles_distributes(small_db) -> None:
    # small_db: 로맨틱 a·b(2건) + 스트리트 c(1건)
    out = _recommend(["로맨틱", "스트리트"], 3, header=None)
    assert out.count("![코디]") == 3  # 총 3개
    assert "https://img/c.jpg" in out  # 스트리트도 포함(단일이면 안 나옴)


def test_recommend_all_invalid_returns_guidance(small_db) -> None:
    out = _recommend(["xx", "yy"], 3, header=None)
    assert "지원하는 스타일이 없습니다" in out
    assert "스트리트" in out


@pytest.mark.asyncio
async def test_by_style_returns_only_that_style(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_style", {"style": "로맨틱", "n": 5}
        )
    text = res.content[0].text
    assert "https://img/a.jpg" in text or "https://img/b.jpg" in text
    assert "https://img/c.jpg" not in text  # 스트리트는 제외


@pytest.mark.asyncio
async def test_by_style_invalid_style_lists_options(
    small_db, client_session
) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_style", {"style": "없는스타일"}
        )
    text = res.content[0].text
    assert "없는스타일" in text and "스트리트" in text


@pytest.mark.asyncio
async def test_by_situation_echoes_situation_and_style(
    small_db, client_session
) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "주말 소개팅", "style": "로맨틱"},
        )
    text = res.content[0].text
    assert "주말 소개팅" in text and "로맨틱" in text


@pytest.mark.asyncio
async def test_tools_listed_with_honest_annotations(
    small_db, client_session
) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    by_name = {t.name: t for t in result.tools}
    assert "recommend_outfits_by_style" in by_name
    assert "recommend_outfits_by_situation" in by_name
    # 랜덤 표본이라 idempotent 가 아님을 정직하게 신고
    anno = by_name["recommend_outfits_by_style"].annotations
    assert anno.idempotentHint is False
    assert anno.readOnlyHint is True


def test_sample_perf_on_real_db(monkeypatch) -> None:
    """동봉 DB 가 있으면 최다 스타일 표본이 1초 내에 끝나는지 가드."""
    real = (
        Path(__file__).resolve().parent.parent
        / "src/playmcp_server/data/clothing.db"
    )
    if not real.exists():
        pytest.skip("packaged clothing.db 없음")
    monkeypatch.setenv("CLOTHING_DB_PATH", str(real))
    repository.reset_repository()
    try:
        repo = repository.get_repository()
        t0 = time.perf_counter()
        out = repo.sample_outfits(style="스트리트", n=3)
        elapsed = time.perf_counter() - t0
    finally:
        repository.reset_repository()
    assert len(out) == 3
    assert elapsed < 1.0, f"sample 너무 느림: {elapsed:.3f}s (p99 3s 위험)"


def test_normalize_styles_dedup_order_filter() -> None:
    assert _normalize_styles(["모던", "모던", "없는거", "로맨틱"]) == ["모던", "로맨틱"]


def test_normalize_styles_all_invalid_empty() -> None:
    assert _normalize_styles(["xx", "yy"]) == []


def test_no_valid_styles_msg_echoes_and_lists() -> None:
    msg = _no_valid_styles_msg(["xx"])
    assert "xx" in msg
    assert "스트리트" in msg and "클래식" in msg


def _mk(oid: str, style: str) -> Outfit:
    return Outfit(id=oid, image_url=f"u/{oid}", style=style)


def test_interleave_round_robin() -> None:
    a = [_mk("a0", "모던"), _mk("a1", "모던"), _mk("a2", "모던")]
    b = [_mk("b0", "로맨틱"), _mk("b1", "로맨틱")]
    assert [o.id for o in _interleave([a, b])] == ["a0", "b0", "a1", "b1", "a2"]


def test_interleave_skips_empty_pool() -> None:
    a = [_mk("a0", "모던")]
    assert [o.id for o in _interleave([[], a])] == ["a0"]
