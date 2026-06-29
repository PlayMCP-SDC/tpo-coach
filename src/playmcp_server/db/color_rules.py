"""색 어휘와 규칙 기반 어울림 판정.

색 태그소니는 tools/color.py 의 extract_color 가 내는 한글 색 이름과 일치한다
(test_named_colors_match_extractor 가 강제). 어울림은 룩업 테이블이 아니라
규칙 함수로 결정적으로 산출한다: 톤온톤(자기색)·무채색(항상)·보색(COMPLEMENT).
"""

from __future__ import annotations

# extract_color(_NAMED) 와 동일한 16색. 동기화는 테스트가 강제한다.
NAMED_COLORS: frozenset[str] = frozenset(
    {
        "검정", "흰색", "회색", "남색", "파랑", "하늘색", "청록", "초록",
        "카키", "노랑", "주황", "빨강", "분홍", "보라", "갈색", "베이지",
    }
)

# 무채색 — 거의 모든 색과 어울린다.
NEUTRALS: tuple[str, ...] = ("검정", "흰색", "회색")

# 유채색의 보색(대략적 색상환 대비). 무채색은 보색이 없다.
COMPLEMENT: dict[str, str] = {
    "남색": "주황",
    "파랑": "주황",
    "하늘색": "주황",
    "청록": "빨강",
    "초록": "분홍",
    "카키": "보라",
    "노랑": "보라",
    "주황": "파랑",
    "빨강": "청록",
    "분홍": "초록",
    "보라": "노랑",
    "갈색": "하늘색",
    "베이지": "남색",
}


def harmony(base: str) -> list[tuple[str, str, float]]:
    """기준색과 어울리는 (색, 종류, score) 목록을 score 내림차순으로 반환한다.

    종류: 'tone'(톤온톤) | 'neutral'(무채색) | 'complementary'(보색).

    Args:
        base: 기준 색 이름 (NAMED_COLORS 중 하나).

    Returns:
        (색, 종류, score) 튜플 목록. score 1.0(무채색) ~ 0.7.

    Raises:
        ValueError: base 가 NAMED_COLORS 에 없을 때.
    """
    if base not in NAMED_COLORS:
        raise ValueError(
            f"알 수 없는 색: {base}. 가능한 색: {sorted(NAMED_COLORS)}"
        )

    scored: dict[str, tuple[str, float]] = {}

    def add(color: str, htype: str, score: float) -> None:
        if color not in scored or scored[color][1] < score:
            scored[color] = (htype, score)

    add(base, "tone", 0.8)
    for n in NEUTRALS:
        add(n, "neutral", 1.0)

    if base in NEUTRALS:
        for c in NAMED_COLORS:
            if c not in NEUTRALS:
                add(c, "neutral", 0.7)
    else:
        comp = COMPLEMENT.get(base)
        if comp:
            add(comp, "complementary", 0.7)

    return sorted(
        ((c, h, s) for c, (h, s) in scored.items()),
        key=lambda x: (-x[2], x[0]),
    )
