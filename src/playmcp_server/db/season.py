"""계절 하드 필터 — 코디(세트) 단위 배제 규칙을 SQL WHERE 조각으로.

한 부위라도 계절 금지 조건에 걸리면 코디 전체 제외. 그래서 '유지' 조건은 각
배제 조건의 부정을 AND 로 결합한다. NULL/결측 값은 통과(제외하지 않음).
규칙 근거·매핑표: docs/idea/weather_role.md
"""

from __future__ import annotations

SEASONS: frozenset[str] = frozenset({"봄가을", "여름", "겨울"})

# 보온등급 컬럼(전 부위) / 소매기장 컬럼(하의 제외).
_WARMTH_COLS = ("top_warmth", "bottom_warmth", "outer_warmth", "dress_warmth")
_SLEEVE_COLS = ("top_sleeve", "outer_sleeve", "dress_sleeve")


def _ne(col: str, value: str) -> tuple[str, list[str]]:
    """col 이 value 가 아님(또는 NULL). 배제조건 col=value 의 부정."""
    return f"({col} IS NULL OR {col} <> ?)", [value]


def _not_in(col: str, values: tuple[str, ...]) -> tuple[str, list[str]]:
    """col 이 values 중 아무것도 아님(또는 NULL)."""
    ph = ",".join("?" * len(values))
    return f"({col} IS NULL OR {col} NOT IN ({ph}))", list(values)


def season_where(season: str) -> tuple[str, list[str]]:
    """계절 → (유지조건 SQL 조각, params). 미지원 계절이면 ('', [])."""
    clauses: list[str] = []
    params: list[str] = []

    def add(pair: tuple[str, list[str]]) -> None:
        clauses.append(pair[0])
        params.extend(pair[1])

    if season == "여름":
        for c in _WARMTH_COLS:
            add(_ne(c, "따뜻"))
        add(_not_in("outer_category", ("코트", "패딩")))
        add(_ne("bottom_length", "맥시"))
        add(_ne("dress_length", "맥시"))
    elif season == "겨울":
        for c in _WARMTH_COLS:
            add(_ne(c, "시원"))
        for c in _SLEEVE_COLS:
            add(_not_in(c, ("민소매", "반팔", "캡")))
        add(_ne("bottom_length", "미니"))
        add(_ne("dress_length", "미니"))
        add(_ne("top_category", "브라탑"))
    elif season == "봄가을":
        add(_ne("outer_category", "패딩"))
    else:
        return "", []
    return " AND ".join(clauses), params
