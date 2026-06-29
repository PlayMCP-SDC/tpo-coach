"""색 어휘·어울림 규칙 검증."""

import pytest

from playmcp_server.db import color_rules
from playmcp_server.tools import color


def test_named_colors_match_extractor() -> None:
    """색 태그소니는 extract_color(_NAMED) 어휘와 정확히 일치해야 한다."""
    names = {n for n, *_ in color._NAMED}
    assert color_rules.NAMED_COLORS == names


def test_harmony_includes_neutrals() -> None:
    matches = {c for c, _, _ in color_rules.harmony("남색")}
    assert {"검정", "흰색", "회색"} <= matches


def test_harmony_includes_tone_on_tone() -> None:
    pairs = {(c, h) for c, h, _ in color_rules.harmony("남색")}
    assert ("남색", "tone") in pairs


def test_harmony_includes_complement() -> None:
    pairs = {(c, h) for c, h, _ in color_rules.harmony("남색")}
    assert ("주황", "complementary") in pairs


def test_harmony_neutral_base_pairs_chromatic() -> None:
    """무채색 상의(검정)는 유채색 하의와도 어울린다."""
    matches = {c for c, _, _ in color_rules.harmony("검정")}
    assert "빨강" in matches


def test_harmony_unknown_color_raises() -> None:
    with pytest.raises(ValueError):
        color_rules.harmony("형광연두")


def test_harmony_sorted_by_score_desc() -> None:
    scores = [s for _, _, s in color_rules.harmony("남색")]
    assert scores == sorted(scores, reverse=True)


def test_complement_keys_are_known_colors() -> None:
    assert set(color_rules.COMPLEMENT) <= color_rules.NAMED_COLORS
    assert set(color_rules.COMPLEMENT.values()) <= color_rules.NAMED_COLORS
