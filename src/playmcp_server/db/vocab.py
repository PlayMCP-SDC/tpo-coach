"""통제 어휘 — 빌드 검증과 도구 입력 검증의 단일 출처.

상황 태그는 F3 드레스코드 시나리오와 정렬한다.
"""

from __future__ import annotations

CATEGORIES: frozenset[str] = frozenset(
    {"top", "bottom", "outer", "dress", "shoes"}
)

SEASONS: frozenset[str] = frozenset(
    {"spring", "summer", "fall", "winter", "all"}
)

OCCASION_TAGS: frozenset[str] = frozenset(
    {"놀이동산", "데이트", "하객룩", "소개팅", "골프장", "오피스", "캐주얼모임", "여행"}
)

STYLE_TAGS: frozenset[str] = frozenset(
    {"캐주얼", "스트릿", "미니멀", "클래식", "포멀", "스포티"}
)
