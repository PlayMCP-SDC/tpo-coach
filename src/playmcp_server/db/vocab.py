"""통제 어휘 — 빌드 검증과 도구 입력 검증의 단일 출처.

K-Fashion 라벨링 데이터의 셋업(코디) 스키마에 맞춘다.
스타일/서브스타일/카테고리/기장은 라벨링 JSON 의 실제 값에서 도출했다.
"""

from __future__ import annotations

# 라벨링 부위(대분류). 한 셋업은 부위별 의류를 최대 1개씩 가진다.
PARTS: frozenset[str] = frozenset({"상의", "하의", "아우터", "원피스"})

# 스타일 23종 (라벨링.스타일.스타일).
STYLES: frozenset[str] = frozenset(
    {
        "레트로", "로맨틱", "리조트", "매니시", "모던", "밀리터리", "섹시",
        "소피스트케이티드", "스트리트", "스포티", "아방가르드", "오리엔탈",
        "웨스턴", "젠더리스", "컨트리", "클래식", "키치", "톰보이", "펑크",
        "페미닌", "프레피", "히피", "힙합",
    }
)

# 서브스타일 (라벨링.스타일.서브스타일). 전체 데이터 기준 STYLES 와 동일한 23종.
SUBSTYLES: frozenset[str] = STYLES

# 부위별 카테고리 (라벨링.{부위}.카테고리).
CATEGORIES_BY_PART: dict[str, frozenset[str]] = {
    "상의": frozenset(
        {"니트웨어", "브라탑", "블라우스", "셔츠", "탑", "티셔츠", "후드티"}
    ),
    "하의": frozenset({"래깅스", "스커트", "조거팬츠", "청바지", "팬츠"}),
    "아우터": frozenset(
        {"가디건", "베스트", "재킷", "점퍼", "짚업", "코트", "패딩"}
    ),
    "원피스": frozenset({"드레스", "점프수트"}),
}

# 전체 카테고리(부위 합집합) 21종.
CATEGORIES: frozenset[str] = frozenset().union(*CATEGORIES_BY_PART.values())

# 기장 정규 어휘 9종 (라벨링.{부위}.기장).
LENGTHS: frozenset[str] = frozenset(
    {"노멀", "니렝스", "롱", "맥시", "미니", "미디", "발목", "크롭", "하프"}
)

# 표기 흔들림 정규화(원천 → 정규).
LENGTH_ALIASES: dict[str, str] = {"노말": "노멀"}


def normalize_length(raw: str | None) -> str | None:
    """기장 표기를 정규 어휘로 통일한다. 비면 None."""
    if not raw:
        return None
    v = raw.strip()
    return LENGTH_ALIASES.get(v, v) or None


# 소매기장 정규 어휘 6종 (라벨링.{부위}.소매기장). 하의엔 없음.
SLEEVES: frozenset[str] = frozenset(
    {"긴팔", "반팔", "7부소매", "민소매", "없음", "캡"}
)

# 소재 정규 어휘 25종 (라벨링.{부위}.소재). 리스트(다중값)로 라벨됨.
MATERIALS: frozenset[str] = frozenset(
    {
        "우븐", "울/캐시미어", "니트", "저지", "데님", "트위드", "린넨", "시폰",
        "퍼", "실크", "자카드", "가죽", "스판덱스", "플리스", "코듀로이", "패딩",
        "레이스", "스웨이드", "헤어 니트", "벨벳", "네오프렌", "메시", "무스탕",
        "비닐/PVC", "시퀸/글리터",
    }
)

# 보온등급 3종.
WARMTH_LEVELS: frozenset[str] = frozenset({"따뜻", "시원", "중립"})

# 소재 → 보온등급. 근거: docs/idea/weather_role.md 매핑표.
_MATERIAL_WARMTH: dict[str, str] = {
    # 따뜻 (겨울/가을)
    "울/캐시미어": "따뜻", "트위드": "따뜻", "퍼": "따뜻", "무스탕": "따뜻",
    "플리스": "따뜻", "패딩": "따뜻", "코듀로이": "따뜻", "스웨이드": "따뜻",
    "헤어 니트": "따뜻", "벨벳": "따뜻", "네오프렌": "따뜻", "가죽": "따뜻",
    # 시원 (여름)
    "린넨": "시원", "시폰": "시원", "메시": "시원", "레이스": "시원", "실크": "시원",
    # 중립 (사계절)
    "우븐": "중립", "니트": "중립", "저지": "중립", "데님": "중립",
    "스판덱스": "중립", "자카드": "중립", "시퀸/글리터": "중립", "비닐/PVC": "중립",
}


def warmth_of(materials: list[str] | None) -> str | None:
    """소재 리스트 → 보온등급. 우선순위 따뜻 > 시원 > 중립. 빈/None 이면 None.

    미등록 소재는 등급이 없어 무시된다(빌드에서 별도 검증). 알려진 소재가
    하나도 안 남으면 '중립'.
    """
    if not materials:
        return None
    grades = {_MATERIAL_WARMTH.get(m) for m in materials}
    if "따뜻" in grades:
        return "따뜻"
    if "시원" in grades:
        return "시원"
    return "중립"
