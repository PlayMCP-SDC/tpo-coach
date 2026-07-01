"""통제 어휘 + 보온등급 파생."""

from playmcp_server.db.vocab import (
    MATERIALS,
    SLEEVES,
    WARMTH_LEVELS,
    warmth_of,
)


def test_vocab_sizes() -> None:
    assert SLEEVES == {"긴팔", "반팔", "7부소매", "민소매", "없음", "캡"}
    assert len(MATERIALS) == 25
    assert WARMTH_LEVELS == {"따뜻", "시원", "중립"}


def test_warmth_priority_warm_wins() -> None:
    # 따뜻 > 시원 > 중립
    assert warmth_of(["우븐", "린넨"]) == "시원"
    assert warmth_of(["울/캐시미어", "린넨"]) == "따뜻"
    assert warmth_of(["우븐", "데님"]) == "중립"


def test_warmth_empty_is_none() -> None:
    assert warmth_of(None) is None
    assert warmth_of([]) is None


def test_material_warmth_examples() -> None:
    assert warmth_of(["헤어 니트"]) == "따뜻"
    assert warmth_of(["가죽"]) == "따뜻"
    assert warmth_of(["니트"]) == "중립"   # 소재 '니트' 는 두께 모호 → 중립
    assert warmth_of(["메시"]) == "시원"
