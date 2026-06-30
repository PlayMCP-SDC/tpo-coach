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
