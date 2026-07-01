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
        add(_not_in("bottom_length", ("미니", "미디", "니렝스")))
        add(_not_in("dress_length", ("미니", "미디", "니렝스")))
        add(_ne("top_category", "브라탑"))
    elif season == "봄가을":
        add(_ne("outer_category", "패딩"))
    else:
        return "", []
    return " AND ".join(clauses), params


# --- 소프트 선호(가중 랜덤 정렬) — 설계 §8 ---
# 정렬키 = 정규화랜덤(0~1) − _SOFT_BIAS × 선호점수. 값이 작을수록 앞(선호 우선).
_SOFT_BIAS: float = 0.85

# SQLite RANDOM() 은 부호있는 int64. 부호비트를 마스킹해 [0,1) 로 정규화.
_RAND01 = "((RANDOM() & 9223372036854775807) / 9223372036854775807.0)"


def _summer_score() -> str:
    """여름 선호점수: 상의 소매가 반팔·민소매·캡 이면 1.0, 아니면 0.0."""
    return "CASE WHEN top_sleeve IN ('반팔','민소매','캡') THEN 1.0 ELSE 0.0 END"


def _winter_score() -> str:
    """겨울 선호점수: 상의·아우터 기장 중 큰 값. 롱=1.0, 노멀=0.5, 그 외 0.0."""
    top = "CASE top_length WHEN '롱' THEN 1.0 WHEN '노멀' THEN 0.5 ELSE 0.0 END"
    outer = "CASE outer_length WHEN '롱' THEN 1.0 WHEN '노멀' THEN 0.5 ELSE 0.0 END"
    return f"MAX({top}, {outer})"


def season_order_by(season: str) -> tuple[str, list[float]]:
    """계절 → (ORDER BY 키 식, params). 여름/겨울만 가중, 그 외는 ('', [])(랜덤)."""
    if season == "여름":
        score = _summer_score()
    elif season == "겨울":
        score = _winter_score()
    else:
        return "", []
    return f"{_RAND01} - ? * ({score})", [_SOFT_BIAS]
