"""셋업 추천 도구 — 순수 헬퍼 + 도구 동작 검증."""

from playmcp_server.models import Outfit
from playmcp_server.tools.recommend import (
    _clamp_n,
    _format_outfit,
    _invalid_style_msg,
)


def test_clamp_n_bounds() -> None:
    assert _clamp_n(0) == 1
    assert _clamp_n(1) == 1
    assert _clamp_n(3) == 3
    assert _clamp_n(10) == 10
    assert _clamp_n(999) == 10


def test_invalid_style_msg_lists_valid_styles() -> None:
    msg = _invalid_style_msg("없는스타일")
    assert "없는스타일" in msg
    # 유효 스타일 목록을 안내한다
    assert "클래식" in msg and "스트리트" in msg


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
