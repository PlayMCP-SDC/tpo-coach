# 의상 메타데이터 DB 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TPO Coach 의 `recommend_bottoms`(규칙 색 매칭)와 `recommend_outfits`(상황 코디) 추천을 뒷받침하는 내장 read-only SQLite 데이터 계층을 구축한다.

**Architecture:** 저장(repository)·규칙(color_rules)·도구(tool)를 분리한다. 도구는 `ClothingRepository` 인터페이스에만 의존해 백엔드 교체가 가능하다. 큐레이션 시드(CSV) → `build_db.py` → read-only `clothing.db`(컨테이너 동봉). 개별 아이템(`clothing_items`)과 셋업(`outfits`)은 출처·품질이 달라 독립 테이블로 둔다.

**Tech Stack:** Python 3.10+, sqlite3(표준 라이브러리), FastMCP(mcp SDK), pytest(in-memory MCP transport), uv.

---

## 설계 대비 통합 결정 (스펙에서의 의도된 조정)

스펙(`docs/superpowers/specs/2026-06-29-clothing-metadata-db-design.md`)을 기존 코드베이스에 맞추며 내린 결정:

1. **색 어휘 = 기존 한글 색 16종.** `src/playmcp_server/tools/color.py` 의 `_NAMED` 가 이미
   검정·흰색·회색·남색·파랑·하늘색·청록·초록·카키·노랑·주황·빨강·분홍·보라·갈색·베이지를 출력한다.
   `extract_color` 출력과 `recommend_bottoms` 입력을 일치시키기 위해 이 16종을 색 태그소니로 쓴다.
   (스펙의 영문 enum 예시 대체) `Color` enum 대신 Python 3.10 호환 문자열 상수 + frozenset 사용.
2. **색 어울림 = 규칙 함수 + 보색 맵.** 거대한 수기 룩업 테이블 대신 `harmony()` 함수로
   톤온톤(자기색)·무채색(항상)·보색(`COMPLEMENT` 맵)을 결정적으로 산출한다. 여전히 규칙 기반.
3. **build_db 위치 = 패키지 모듈.** 스펙은 `scripts/build_db.py` 였으나, 컨테이너(`src/` 만 복사)에
   동봉되고 테스트에서 import 하려면 패키지 안이어야 한다 → `src/playmcp_server/db/build_db.py`
   (`python -m playmcp_server.db.build_db`).
4. **데이터/DB 경로 = 패키지 내부** `src/playmcp_server/data/` (CSV + 생성된 clothing.db). 환경변수
   `CLOTHING_DB_PATH` 로 재정의 가능(테스트·배포 유연성).

## 파일 구조

생성:
- `src/playmcp_server/models.py` — 공유 타입 `ClothingItem`, `Outfit`
- `src/playmcp_server/db/__init__.py`
- `src/playmcp_server/db/vocab.py` — 통제 어휘(카테고리·시즌·상황태그·스타일태그)
- `src/playmcp_server/db/color_rules.py` — 색 어휘 + 어울림 규칙
- `src/playmcp_server/db/schema.py` — 스키마 SQL, `init_schema`, 태그 정규화
- `src/playmcp_server/db/repository.py` — `ClothingRepository` Protocol + SQLite 구현 + 싱글턴
- `src/playmcp_server/db/build_db.py` — 시드 CSV → DB 빌드 + 검증 (CLI)
- `src/playmcp_server/data/clothing_items.csv` — 아이템 시드
- `src/playmcp_server/data/outfits.csv` — 셋업 시드
- `src/playmcp_server/tools/recommend_bottoms.py` — F9 도구
- `src/playmcp_server/tools/recommend_outfits.py` — 신규 도구
- `tests/test_color_rules.py`, `tests/test_schema.py`, `tests/test_repository.py`,
  `tests/test_build_db.py`, `tests/test_recommend_bottoms.py`, `tests/test_recommend_outfits.py`

수정:
- `src/playmcp_server/tools/__init__.py` — 두 도구 등록
- `tests/conftest.py` — `clothing_db` 픽스처 추가
- `Dockerfile` — 빌드 단계에 DB 생성 추가

---

### Task 1: 색 어휘 + 어울림 규칙 (`color_rules.py`)

**Files:**
- Create: `src/playmcp_server/db/__init__.py`
- Create: `src/playmcp_server/db/color_rules.py`
- Test: `tests/test_color_rules.py`

- [ ] **Step 1: 빈 패키지 파일 생성**

`src/playmcp_server/db/__init__.py`:
```python
"""DB 데이터 계층 (저장·규칙·빌드)."""
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_color_rules.py`:
```python
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
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/test_color_rules.py -v`
Expected: FAIL (ModuleNotFoundError: playmcp_server.db.color_rules)

- [ ] **Step 4: 구현 작성**

`src/playmcp_server/db/color_rules.py`:
```python
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
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_color_rules.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/playmcp_server/db/__init__.py src/playmcp_server/db/color_rules.py tests/test_color_rules.py
git commit -m "feat(db): 색 어휘·규칙 기반 어울림(color_rules)"
```

---

### Task 2: 공유 타입 + 스키마 (`models.py`, `vocab.py`, `schema.py`)

**Files:**
- Create: `src/playmcp_server/models.py`
- Create: `src/playmcp_server/db/vocab.py`
- Create: `src/playmcp_server/db/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_schema.py`:
```python
"""스키마·태그 정규화 검증."""

import sqlite3

from playmcp_server.db import schema


def test_init_schema_creates_tables() -> None:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"clothing_items", "outfits"} <= names


def test_normalize_tags_wraps_with_delimiters() -> None:
    assert schema.normalize_tags("놀이동산, 데이트") == ",놀이동산,데이트,"


def test_normalize_tags_empty() -> None:
    assert schema.normalize_tags("") == ""
    assert schema.normalize_tags("  ") == ""


def test_tags_to_list_roundtrip() -> None:
    assert schema.tags_to_list(",놀이동산,데이트,") == ["놀이동산", "데이트"]
    assert schema.tags_to_list("") == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL (ModuleNotFoundError: playmcp_server.db.schema)

- [ ] **Step 3: 공유 타입 작성**

`src/playmcp_server/models.py`:
```python
"""도구·저장소가 공유하는 경량 타입."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClothingItem:
    """개별 의상 아이템 (색 매칭용)."""

    id: str
    name: str
    category: str
    color: str
    image_url: str
    formality: int
    subcategory: str | None = None
    seller_name: str | None = None
    seller_url: str | None = None
    price: int | None = None
    season: str | None = None
    style_tags: str | None = None


@dataclass(frozen=True)
class Outfit:
    """큐레이션된 셋업/코디 (상황 기반 추천용)."""

    id: str
    image_url: str
    occasion_tags: str
    title: str | None = None
    source: str | None = None
    source_url: str | None = None
    formality: int | None = None
    season: str | None = None
    style_tags: str | None = None
    items_note: str | None = None
```

- [ ] **Step 4: 통제 어휘 작성**

`src/playmcp_server/db/vocab.py`:
```python
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
```

- [ ] **Step 5: 스키마 작성**

`src/playmcp_server/db/schema.py`:
```python
"""SQLite 스키마와 태그 정규화 헬퍼."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS clothing_items (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    category     TEXT NOT NULL,
    subcategory  TEXT,
    color        TEXT NOT NULL,
    image_url    TEXT NOT NULL,
    seller_name  TEXT,
    seller_url   TEXT,
    price        INTEGER,
    formality    INTEGER NOT NULL DEFAULT 3,
    season       TEXT,
    style_tags   TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_cat_color ON clothing_items(category, color);
CREATE INDEX IF NOT EXISTS idx_items_cat_formality ON clothing_items(category, formality);

CREATE TABLE IF NOT EXISTS outfits (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    image_url     TEXT NOT NULL,
    source        TEXT,
    source_url    TEXT,
    formality     INTEGER,
    season        TEXT,
    occasion_tags TEXT NOT NULL,
    style_tags    TEXT,
    items_note    TEXT
);
CREATE INDEX IF NOT EXISTS idx_outfits_formality ON outfits(formality);
CREATE INDEX IF NOT EXISTS idx_outfits_season ON outfits(season);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """주어진 연결에 테이블·인덱스를 생성한다(멱등)."""
    conn.executescript(SCHEMA)


def normalize_tags(raw: str) -> str:
    """'a, b' → ',a,b,' (정확 토큰 매칭용). 비면 ''."""
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return "," + ",".join(parts) + "," if parts else ""


def tags_to_list(normalized: str) -> list[str]:
    """',a,b,' → ['a','b']. 비면 []."""
    return [p for p in normalized.split(",") if p]
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 커밋**

```bash
git add src/playmcp_server/models.py src/playmcp_server/db/vocab.py src/playmcp_server/db/schema.py tests/test_schema.py
git commit -m "feat(db): 공유 타입(models)·통제 어휘(vocab)·스키마(schema)"
```

---

### Task 3: Repository — 아이템 조회 (`find_bottoms`, `get_item`)

**Files:**
- Create: `src/playmcp_server/db/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_repository.py`:
```python
"""SQLiteClothingRepository 검증 (in-memory 연결)."""

import sqlite3

import pytest

from playmcp_server.db import schema
from playmcp_server.db.repository import SQLiteClothingRepository


@pytest.fixture
def repo() -> SQLiteClothingRepository:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO clothing_items "
        "(id,name,category,subcategory,color,image_url,seller_name,seller_url,"
        "price,formality,season,style_tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("b1", "베이지 슬랙스", "bottom", "slacks", "베이지",
             "http://img/b1", "무신사", "http://buy/b1", 39000, 3, "all", "미니멀"),
            ("b2", "흰 데님", "bottom", "jeans", "흰색",
             "http://img/b2", "무신사", "http://buy/b2", 49000, 2, "summer", None),
            ("b3", "검정 슬랙스", "bottom", "slacks", "검정",
             "http://img/b3", None, None, None, 5, "all", "포멀"),
            ("t1", "남색 셔츠", "top", "shirt", "남색",
             "http://img/t1", None, None, None, 3, "all", None),
        ],
    )
    conn.commit()
    return SQLiteClothingRepository(conn)


def test_get_item_found(repo: SQLiteClothingRepository) -> None:
    item = repo.get_item("b1")
    assert item is not None
    assert item.name == "베이지 슬랙스"
    assert item.color == "베이지"


def test_get_item_missing(repo: SQLiteClothingRepository) -> None:
    assert repo.get_item("nope") is None


def test_find_bottoms_only_bottoms(repo: SQLiteClothingRepository) -> None:
    items = repo.find_bottoms(["남색", "검정"])
    assert {i.id for i in items} == {"b3"}  # t1(남색)은 top 이라 제외


def test_find_bottoms_color_filter(repo: SQLiteClothingRepository) -> None:
    items = repo.find_bottoms(["베이지", "흰색"])
    assert {i.id for i in items} == {"b1", "b2"}


def test_find_bottoms_formality_window(repo: SQLiteClothingRepository) -> None:
    # formality=5 ± 1 → 4~6 → b3(5)만
    items = repo.find_bottoms(["베이지", "흰색", "검정"], formality=5)
    assert {i.id for i in items} == {"b3"}


def test_find_bottoms_season_filter(repo: SQLiteClothingRepository) -> None:
    # summer 요청 → b2(summer) + all 은 통과, b1(all) 포함
    items = repo.find_bottoms(["베이지", "흰색"], season="summer")
    assert {i.id for i in items} == {"b1", "b2"}


def test_find_bottoms_empty_colors(repo: SQLiteClothingRepository) -> None:
    assert repo.find_bottoms([]) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_repository.py -v`
Expected: FAIL (ModuleNotFoundError: playmcp_server.db.repository)

- [ ] **Step 3: 구현 작성**

`src/playmcp_server/db/repository.py`:
```python
"""의상 데이터 저장소.

도구는 ClothingRepository Protocol 에만 의존한다(백엔드 교체 가능).
지금은 SQLiteClothingRepository 하나만 구현한다(하나의 read-only db 파일).
"""

from __future__ import annotations

import sqlite3
from typing import Protocol

from playmcp_server.models import ClothingItem, Outfit


class ClothingRepository(Protocol):
    """의상 아이템·셋업 조회 인터페이스."""

    def get_item(self, item_id: str) -> ClothingItem | None: ...

    def find_bottoms(
        self,
        colors: list[str],
        *,
        formality: int | None = None,
        season: str | None = None,
    ) -> list[ClothingItem]: ...

    def get_outfit(self, outfit_id: str) -> Outfit | None: ...

    def find_outfits(
        self,
        *,
        occasion: str,
        style: str | None = None,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> list[Outfit]: ...


def _item(row: sqlite3.Row) -> ClothingItem:
    return ClothingItem(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        subcategory=row["subcategory"],
        color=row["color"],
        image_url=row["image_url"],
        seller_name=row["seller_name"],
        seller_url=row["seller_url"],
        price=row["price"],
        formality=row["formality"],
        season=row["season"],
        style_tags=row["style_tags"],
    )


class SQLiteClothingRepository:
    """SQLite 기반 구현. 주어진 연결을 그대로 쓴다."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        conn.row_factory = sqlite3.Row
        self._conn = conn

    def get_item(self, item_id: str) -> ClothingItem | None:
        row = self._conn.execute(
            "SELECT * FROM clothing_items WHERE id = ?", (item_id,)
        ).fetchone()
        return _item(row) if row else None

    def find_bottoms(
        self,
        colors: list[str],
        *,
        formality: int | None = None,
        season: str | None = None,
    ) -> list[ClothingItem]:
        if not colors:
            return []
        placeholders = ",".join("?" * len(colors))
        where = [f"category = 'bottom'", f"color IN ({placeholders})"]
        params: list[object] = list(colors)
        if formality is not None:
            where.append("formality BETWEEN ? AND ?")
            params += [formality - 1, formality + 1]
        if season is not None:
            where.append("(season IS NULL OR season IN (?, 'all'))")
            params.append(season)
        sql = (
            "SELECT * FROM clothing_items WHERE "
            + " AND ".join(where)
            + " ORDER BY id"
        )
        return [_item(r) for r in self._conn.execute(sql, params)]
```

> 참고: `get_outfit`/`find_outfits` 는 Task 4 에서 추가한다. Protocol 에는 이미 선언돼
> 있으나 SQLiteClothingRepository 에 메서드를 더한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(db): SQLite 저장소 — 아이템 조회(find_bottoms/get_item)"
```

---

### Task 4: Repository — 셋업 조회 (`find_outfits`, `get_outfit`)

**Files:**
- Modify: `src/playmcp_server/db/repository.py`
- Test: `tests/test_repository.py` (셋업 케이스 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_repository.py` 끝에 추가:
```python
@pytest.fixture
def outfit_repo() -> SQLiteClothingRepository:
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO outfits "
        "(id,title,image_url,source,source_url,formality,season,"
        "occasion_tags,style_tags,items_note) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("f1", "놀이동산 캐주얼", "http://img/f1", "instagram",
             "http://ig/f1", 2, "spring", ",놀이동산,데이트,", ",캐주얼,", "흰 티, 데님"),
            ("f2", "하객룩", "http://img/f2", "musinsa",
             "http://ms/f2", 4, "all", ",하객룩,", ",클래식,", None),
            ("f3", "놀이동산 스트릿", "http://img/f3", "instagram",
             "http://ig/f3", 1, "summer", ",놀이동산,여행,", ",스트릿,", None),
        ],
    )
    conn.commit()
    return SQLiteClothingRepository(conn)


def test_get_outfit_found(outfit_repo: SQLiteClothingRepository) -> None:
    fit = outfit_repo.get_outfit("f1")
    assert fit is not None
    assert fit.title == "놀이동산 캐주얼"


def test_get_outfit_missing(outfit_repo: SQLiteClothingRepository) -> None:
    assert outfit_repo.get_outfit("nope") is None


def test_find_outfits_by_occasion(outfit_repo: SQLiteClothingRepository) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산")
    assert {f.id for f in fits} == {"f1", "f3"}


def test_find_outfits_exact_token_match(
    outfit_repo: SQLiteClothingRepository,
) -> None:
    """부분일치 오탐 방지: '동산'은 '놀이동산'에 걸리면 안 된다."""
    assert outfit_repo.find_outfits(occasion="동산") == []


def test_find_outfits_style_filter(
    outfit_repo: SQLiteClothingRepository,
) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산", style="스트릿")
    assert {f.id for f in fits} == {"f3"}


def test_find_outfits_limit(outfit_repo: SQLiteClothingRepository) -> None:
    fits = outfit_repo.find_outfits(occasion="놀이동산", limit=1)
    assert len(fits) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_repository.py -k outfit -v`
Expected: FAIL (AttributeError: 'SQLiteClothingRepository' has no attribute 'get_outfit')

- [ ] **Step 3: 구현 추가**

`src/playmcp_server/db/repository.py` 상단 `_item` 아래에 `_outfit` 추가:
```python
def _outfit(row: sqlite3.Row) -> Outfit:
    return Outfit(
        id=row["id"],
        title=row["title"],
        image_url=row["image_url"],
        source=row["source"],
        source_url=row["source_url"],
        formality=row["formality"],
        season=row["season"],
        occasion_tags=row["occasion_tags"],
        style_tags=row["style_tags"],
        items_note=row["items_note"],
    )
```

`SQLiteClothingRepository` 클래스 끝에 메서드 추가:
```python
    def get_outfit(self, outfit_id: str) -> Outfit | None:
        row = self._conn.execute(
            "SELECT * FROM outfits WHERE id = ?", (outfit_id,)
        ).fetchone()
        return _outfit(row) if row else None

    def find_outfits(
        self,
        *,
        occasion: str,
        style: str | None = None,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> list[Outfit]:
        where = ["occasion_tags LIKE '%,' || ? || ',%'"]
        params: list[object] = [occasion]
        if style is not None:
            where.append("style_tags LIKE '%,' || ? || ',%'")
            params.append(style)
        if formality is not None:
            where.append("(formality IS NULL OR formality BETWEEN ? AND ?)")
            params += [formality - 1, formality + 1]
        if season is not None:
            where.append("(season IS NULL OR season IN (?, 'all'))")
            params.append(season)
        sql = (
            "SELECT * FROM outfits WHERE "
            + " AND ".join(where)
            + " ORDER BY id LIMIT ?"
        )
        params.append(limit)
        return [_outfit(r) for r in self._conn.execute(sql, params)]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (13 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(db): SQLite 저장소 — 셋업 조회(find_outfits/get_outfit)"
```

---

### Task 5: Repository 싱글턴 + read-only 열기 (`get_repository`)

**Files:**
- Modify: `src/playmcp_server/db/repository.py`
- Test: `tests/test_repository.py` (싱글턴 케이스 추가)

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_repository.py` 끝에 추가:
```python
def test_get_repository_reads_env_path(tmp_path, monkeypatch) -> None:
    """CLOTHING_DB_PATH 가 가리키는 read-only DB 를 연다."""
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.execute(
        "INSERT INTO clothing_items "
        "(id,name,category,color,image_url,formality) "
        "VALUES ('x','t','bottom','검정','http://i',3)"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    repo = repository.get_repository()
    assert repo.get_item("x") is not None


def test_get_repository_is_read_only(tmp_path, monkeypatch) -> None:
    from playmcp_server.db import repository

    db_path = tmp_path / "t.db"
    conn = sqlite3.connect(db_path)
    schema.init_schema(conn)
    conn.commit()
    conn.close()

    monkeypatch.setenv("CLOTHING_DB_PATH", str(db_path))
    repository.reset_repository()
    repo = repository.get_repository()
    with pytest.raises(sqlite3.OperationalError):
        repo._conn.execute(
            "INSERT INTO clothing_items "
            "(id,name,category,color,image_url,formality) "
            "VALUES ('y','t','bottom','검정','http://i',3)"
        )
    repository.reset_repository()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_repository.py -k get_repository -v`
Expected: FAIL (AttributeError: module has no attribute 'get_repository')

- [ ] **Step 3: 구현 추가**

`src/playmcp_server/db/repository.py` 상단 import 에 추가:
```python
import os
from pathlib import Path
```

파일 끝에 싱글턴 추가:
```python
# 기본 DB 경로: 패키지 내부 data/clothing.db. 환경변수로 재정의 가능.
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "clothing.db"

_repo: SQLiteClothingRepository | None = None


def _db_path() -> Path:
    return Path(os.environ.get("CLOTHING_DB_PATH", str(_DEFAULT_DB)))


def get_repository() -> SQLiteClothingRepository:
    """프로세스 단위 read-only 저장소 싱글턴을 돌려준다.

    DB 파일이 없으면 즉시 실패한다(fail-fast).
    """
    global _repo
    if _repo is None:
        path = _db_path()
        if not path.exists():
            raise FileNotFoundError(
                f"clothing DB 가 없습니다: {path}. "
                "`python -m playmcp_server.db.build_db` 로 생성하세요."
            )
        conn = sqlite3.connect(
            f"file:{path}?mode=ro&immutable=1",
            uri=True,
            check_same_thread=False,
        )
        _repo = SQLiteClothingRepository(conn)
    return _repo


def reset_repository() -> None:
    """싱글턴을 초기화한다(테스트·재로딩용)."""
    global _repo
    if _repo is not None:
        _repo._conn.close()
    _repo = None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(db): read-only 저장소 싱글턴(get_repository/reset_repository)"
```

---

### Task 6: 시드 빌드 + 검증 (`build_db.py`)

**Files:**
- Create: `src/playmcp_server/db/build_db.py`
- Test: `tests/test_build_db.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_build_db.py`:
```python
"""시드 CSV → DB 빌드·검증."""

import sqlite3

import pytest

from playmcp_server.db import build_db

GOOD_ITEM = {
    "id": "b1", "name": "베이지 슬랙스", "category": "bottom",
    "subcategory": "slacks", "color": "베이지", "image_url": "http://i",
    "seller_name": "무신사", "seller_url": "http://buy", "price": "39000",
    "formality": "3", "season": "all", "style_tags": "미니멀",
}
GOOD_OUTFIT = {
    "id": "f1", "title": "놀이동산 캐주얼", "image_url": "http://i",
    "source": "instagram", "source_url": "http://ig", "formality": "2",
    "season": "spring", "occasion_tags": "놀이동산,데이트",
    "style_tags": "캐주얼", "items_note": "흰 티, 데님",
}


def test_build_inserts_rows(tmp_path) -> None:
    dest = tmp_path / "out.db"
    build_db.build([GOOD_ITEM], [GOOD_OUTFIT], dest)
    conn = sqlite3.connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM clothing_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM outfits").fetchone()[0] == 1


def test_build_normalizes_tags(tmp_path) -> None:
    dest = tmp_path / "out.db"
    build_db.build([GOOD_ITEM], [GOOD_OUTFIT], dest)
    conn = sqlite3.connect(dest)
    tags = conn.execute(
        "SELECT occasion_tags FROM outfits WHERE id='f1'"
    ).fetchone()[0]
    assert tags == ",놀이동산,데이트,"


def test_build_rejects_unknown_color(tmp_path) -> None:
    bad = {**GOOD_ITEM, "color": "형광연두"}
    with pytest.raises(ValueError, match="color"):
        build_db.build([bad], [], tmp_path / "out.db")


def test_build_rejects_unknown_category(tmp_path) -> None:
    bad = {**GOOD_ITEM, "category": "모자류"}
    with pytest.raises(ValueError, match="category"):
        build_db.build([bad], [], tmp_path / "out.db")


def test_build_rejects_unknown_occasion_tag(tmp_path) -> None:
    bad = {**GOOD_OUTFIT, "occasion_tags": "달나라"}
    with pytest.raises(ValueError, match="occasion"):
        build_db.build([], [bad], tmp_path / "out.db")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_build_db.py -v`
Expected: FAIL (ModuleNotFoundError: playmcp_server.db.build_db)

- [ ] **Step 3: 구현 작성**

`src/playmcp_server/db/build_db.py`:
```python
"""큐레이션 시드 CSV → read-only clothing.db 생성 + 유효성 검증.

CLI:  python -m playmcp_server.db.build_db
기본 입력: data/clothing_items.csv, data/outfits.csv → 출력: data/clothing.db
"""

from __future__ import annotations

import csv
import logging
import sqlite3
import sys
from pathlib import Path

from playmcp_server.db import schema
from playmcp_server.db.color_rules import NAMED_COLORS
from playmcp_server.db.vocab import (
    CATEGORIES,
    OCCASION_TAGS,
    SEASONS,
    STYLE_TAGS,
)

logger = logging.getLogger("playmcp_server.db.build_db")

_DATA = Path(__file__).resolve().parent.parent / "data"


def _int_or_none(v: str | None) -> int | None:
    v = (v or "").strip()
    return int(v) if v else None


def _check_tags(raw: str, allowed: frozenset[str], field: str) -> None:
    for t in (p.strip() for p in raw.split(",") if p.strip()):
        if t not in allowed:
            raise ValueError(f"{field} 태그 미등록: {t} (허용: {sorted(allowed)})")


def _check_season(v: str | None) -> None:
    if v and v.strip() and v.strip() not in SEASONS:
        raise ValueError(f"season 미등록: {v} (허용: {sorted(SEASONS)})")


def build(items: list[dict], outfits: list[dict], dest: Path) -> None:
    """검증 후 dest 에 새 DB 를 만든다(기존 파일 덮어씀)."""
    dest = Path(dest)
    if dest.exists():
        dest.unlink()
    conn = sqlite3.connect(dest)
    try:
        schema.init_schema(conn)
        for it in items:
            if it["color"] not in NAMED_COLORS:
                raise ValueError(f"color 미등록: {it['color']}")
            if it["category"] not in CATEGORIES:
                raise ValueError(f"category 미등록: {it['category']}")
            _check_season(it.get("season"))
            conn.execute(
                "INSERT INTO clothing_items (id,name,category,subcategory,color,"
                "image_url,seller_name,seller_url,price,formality,season,"
                "style_tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    it["id"], it["name"], it["category"],
                    it.get("subcategory") or None, it["color"], it["image_url"],
                    it.get("seller_name") or None, it.get("seller_url") or None,
                    _int_or_none(it.get("price")),
                    int(it.get("formality") or 3),
                    it.get("season") or None, it.get("style_tags") or None,
                ),
            )
        for ft in outfits:
            _check_tags(ft["occasion_tags"], OCCASION_TAGS, "occasion")
            _check_tags(ft.get("style_tags") or "", STYLE_TAGS, "style")
            _check_season(ft.get("season"))
            conn.execute(
                "INSERT INTO outfits (id,title,image_url,source,source_url,"
                "formality,season,occasion_tags,style_tags,items_note) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    ft["id"], ft.get("title") or None, ft["image_url"],
                    ft.get("source") or None, ft.get("source_url") or None,
                    _int_or_none(ft.get("formality")), ft.get("season") or None,
                    schema.normalize_tags(ft["occasion_tags"]),
                    schema.normalize_tags(ft.get("style_tags") or "") or None,
                    ft.get("items_note") or None,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    items = _read_csv(_DATA / "clothing_items.csv")
    outfits = _read_csv(_DATA / "outfits.csv")
    dest = _DATA / "clothing.db"
    build(items, outfits, dest)
    logger.info(
        "clothing.db 생성: items=%d outfits=%d → %s",
        len(items), len(outfits), dest,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_build_db.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/build_db.py tests/test_build_db.py
git commit -m "feat(db): 시드 CSV → DB 빌드·검증(build_db)"
```

---

### Task 7: 시드 데이터 + 실DB 빌드 스모크 테스트

**Files:**
- Create: `src/playmcp_server/data/clothing_items.csv`
- Create: `src/playmcp_server/data/outfits.csv`
- Test: `tests/test_build_db.py` (실파일 빌드 케이스 추가)

- [ ] **Step 1: 아이템 시드 작성**

`src/playmcp_server/data/clothing_items.csv`:
```csv
id,name,category,subcategory,color,image_url,seller_name,seller_url,price,formality,season,style_tags
itm_0001,베이지 코튼 치노,bottom,chino,베이지,https://example.com/img/itm_0001,무신사,https://example.com/buy/itm_0001,39000,3,all,미니멀
itm_0002,인디고 스트레이트 데님,bottom,jeans,남색,https://example.com/img/itm_0002,무신사,https://example.com/buy/itm_0002,59000,2,all,캐주얼
itm_0003,차콜 울 슬랙스,bottom,slacks,회색,https://example.com/img/itm_0003,무신사,https://example.com/buy/itm_0003,79000,5,fall,클래식
itm_0004,검정 와이드 슬랙스,bottom,slacks,검정,https://example.com/img/itm_0004,무신사,https://example.com/buy/itm_0004,69000,4,all,미니멀
itm_0005,흰색 코튼 팬츠,bottom,cotton,흰색,https://example.com/img/itm_0005,무신사,https://example.com/buy/itm_0005,45000,3,summer,캐주얼
itm_0006,카키 카고 팬츠,bottom,cargo,카키,https://example.com/img/itm_0006,무신사,https://example.com/buy/itm_0006,55000,2,fall,스트릿
itm_0007,남색 옥스퍼드 셔츠,top,shirt,남색,https://example.com/img/itm_0007,무신사,https://example.com/buy/itm_0007,49000,3,all,클래식
itm_0008,흰색 라운드 티셔츠,top,tshirt,흰색,https://example.com/img/itm_0008,무신사,https://example.com/buy/itm_0008,19000,2,summer,캐주얼
```

- [ ] **Step 2: 셋업 시드 작성**

`src/playmcp_server/data/outfits.csv`:
```csv
id,title,image_url,source,source_url,formality,season,occasion_tags,style_tags,items_note
fit_0001,놀이동산 캐주얼 코디,https://example.com/img/fit_0001,instagram,https://instagram.com/p/fit_0001,2,spring,"놀이동산,데이트","캐주얼",흰 티셔츠+데님 팬츠+스니커즈
fit_0002,놀이동산 스트릿 코디,https://example.com/img/fit_0002,instagram,https://instagram.com/p/fit_0002,1,summer,"놀이동산,여행","스트릿",오버핏 티+카고팬츠
fit_0003,하객룩 클래식,https://example.com/img/fit_0003,musinsa,https://musinsa.com/fit_0003,4,all,"하객룩","클래식",셔츠+슬랙스+로퍼
fit_0004,소개팅 미니멀,https://example.com/img/fit_0004,instagram,https://instagram.com/p/fit_0004,3,fall,"소개팅,데이트","미니멀",니트+슬랙스
fit_0005,오피스 캐주얼,https://example.com/img/fit_0005,musinsa,https://musinsa.com/fit_0005,4,all,"오피스","클래식",셔츠+치노
```

- [ ] **Step 3: 실파일 빌드 스모크 테스트 추가**

`tests/test_build_db.py` 끝에 추가:
```python
def test_real_seed_files_build(tmp_path) -> None:
    """동봉 시드 CSV 가 검증을 통과해 빌드된다."""
    from playmcp_server.db.build_db import _DATA, _read_csv, build

    items = _read_csv(_DATA / "clothing_items.csv")
    outfits = _read_csv(_DATA / "outfits.csv")
    assert items and outfits
    dest = tmp_path / "real.db"
    build(items, outfits, dest)  # 미등록 색/태그면 ValueError 로 실패
    assert dest.exists()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_build_db.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 로컬 DB 생성 후 커밋**

```bash
uv run python -m playmcp_server.db.build_db
git add src/playmcp_server/data/clothing_items.csv src/playmcp_server/data/outfits.csv tests/test_build_db.py
git commit -m "feat(db): 큐레이션 시드 데이터(아이템 8·셋업 5)"
```

> 참고: 생성된 `clothing.db` 는 `.gitignore` 에 추가한다(빌드 산출물). 다음 단계에서 처리.

---

### Task 8: `recommend_bottoms` 도구

**Files:**
- Create: `src/playmcp_server/tools/recommend_bottoms.py`
- Modify: `src/playmcp_server/tools/__init__.py`
- Modify: `tests/conftest.py` (clothing_db 픽스처)
- Test: `tests/test_recommend_bottoms.py`

- [ ] **Step 1: conftest 에 clothing_db 픽스처 추가**

`tests/conftest.py` 끝에 추가:
```python
@pytest.fixture
def clothing_db(tmp_path, monkeypatch):
    """임시 clothing.db 를 빌드하고 저장소 싱글턴을 그쪽으로 돌린다."""
    from playmcp_server.db import build_db, repository

    items = [
        {"id": "itm_0001", "name": "베이지 치노", "category": "bottom",
         "subcategory": "chino", "color": "베이지", "image_url": "http://i/1",
         "seller_name": "무신사", "seller_url": "http://buy/1", "price": "39000",
         "formality": "3", "season": "all", "style_tags": "미니멀"},
        {"id": "itm_0004", "name": "검정 슬랙스", "category": "bottom",
         "subcategory": "slacks", "color": "검정", "image_url": "http://i/4",
         "seller_name": "무신사", "seller_url": "http://buy/4", "price": "69000",
         "formality": "4", "season": "all", "style_tags": "미니멀"},
        {"id": "itm_0008", "name": "흰 티셔츠", "category": "top",
         "subcategory": "tshirt", "color": "흰색", "image_url": "http://i/8",
         "seller_name": "무신사", "seller_url": "http://buy/8", "price": "19000",
         "formality": "2", "season": "summer", "style_tags": "캐주얼"},
    ]
    outfits = [
        {"id": "fit_0001", "title": "놀이동산 캐주얼", "image_url": "http://i/f1",
         "source": "instagram", "source_url": "http://ig/f1", "formality": "2",
         "season": "spring", "occasion_tags": "놀이동산,데이트",
         "style_tags": "캐주얼", "items_note": "흰 티+데님"},
        {"id": "fit_0003", "title": "하객룩", "image_url": "http://i/f3",
         "source": "musinsa", "source_url": "http://ms/f3", "formality": "4",
         "season": "all", "occasion_tags": "하객룩", "style_tags": "클래식",
         "items_note": None},
    ]
    dest = tmp_path / "clothing.db"
    build_db.build(items, outfits, dest)
    monkeypatch.setenv("CLOTHING_DB_PATH", str(dest))
    repository.reset_repository()
    yield dest
    repository.reset_repository()
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_recommend_bottoms.py`:
```python
"""recommend_bottoms 도구 검증 (in-memory MCP)."""

import pytest


async def test_tool_listed(client_session, clothing_db) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    assert "recommend_bottoms" in {t.name for t in result.tools}


async def test_recommends_matching_bottoms(client_session, clothing_db) -> None:
    """남색 상의 → 무채색(검정/흰색) 하의가 후보에 든다."""
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_bottoms", {"top_color": "남색"}
        )
    text = result.content[0].text
    assert not result.isError
    assert "검정 슬랙스" in text


async def test_unknown_color_returns_valid_list(
    client_session, clothing_db
) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_bottoms", {"top_color": "형광연두"}
        )
    assert "가능한 색" in result.content[0].text


async def test_no_match_is_not_error(client_session, clothing_db) -> None:
    """카키 하의가 없으니 빈 결과 안내(에러 아님)."""
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_bottoms", {"top_color": "카키", "formality": 1}
        )
    assert not result.isError
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `uv run pytest tests/test_recommend_bottoms.py -v`
Expected: FAIL (recommend_bottoms not in tool list / tool 미등록)

- [ ] **Step 4: 도구 구현 작성**

`src/playmcp_server/tools/recommend_bottoms.py`:
```python
"""recommend_bottoms (F9) — 규칙 색 매칭으로 어울리는 하의 Top-N 추천.

기준 상의 색(extract_color 가 내는 한글 색 이름)에서 출발해 color_rules 로
어울리는 색을 구하고, 저장소에서 해당 색 하의를 찾아 score 순으로 정렬한다.
외부 호출 없음·결정적 → annotations 정직.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from playmcp_server.db import color_rules
from playmcp_server.db.repository import get_repository


def register_tools(mcp: FastMCP) -> None:
    """recommend_bottoms 도구를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend matching bottoms",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def recommend_bottoms(
        top_color: str,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> str:
        """Recommends bottoms that match a top's color for TPO Coach(티피오 코치).

        Uses deterministic color rules (tone-on-tone, neutral, complementary).
        Provide the top's color name in Korean (e.g. '남색', '베이지') such as the
        name returned by extract_color.

        Args:
            top_color: 기준 상의 색 이름 (한글).
            formality: 격식 수준 1~5 (선택, ±1 범위로 필터).
            season: 'spring'|'summer'|'fall'|'winter'|'all' (선택).
            limit: 추천 개수 (기본 5).

        Returns:
            추천 하의 목록 마크다운. 매칭이 없으면 안내 문구.
        """
        try:
            ranked = color_rules.harmony(top_color)
        except ValueError as e:
            return str(e)

        score_of = {c: s for c, _, s in ranked}
        type_of = {c: h for c, h, _ in ranked}
        colors = list(score_of)

        items = get_repository().find_bottoms(
            colors, formality=formality, season=season
        )
        items.sort(
            key=lambda it: (-score_of.get(it.color, 0.0), -it.formality, it.id)
        )
        items = items[:limit]

        if not items:
            return (
                f"'{top_color}' 에 맞는 하의를 찾지 못했어요. "
                "격식/계절 조건을 완화해 보세요."
            )

        lines = [f"**'{top_color}' 상의에 어울리는 하의 추천 (TPO Coach):**"]
        for i, it in enumerate(items, 1):
            why = {
                "neutral": "무채색이라 깔끔하게",
                "tone": "톤온톤으로",
                "complementary": "보색으로 포인트",
            }.get(type_of.get(it.color, ""), "")
            price = f" · {it.price:,}원" if it.price else ""
            seller = f" · {it.seller_name}" if it.seller_name else ""
            lines.append(
                f"{i}. {it.name} ({it.color}){price}{seller} — {it.color}은 {why} 어울려요"
            )
        return "\n".join(lines)
```

- [ ] **Step 5: 도구 등록**

`src/playmcp_server/tools/__init__.py` 수정 — import 와 register 에 추가:
```python
from playmcp_server.tools import (
    color,
    example,
    recommend_bottoms,
    render_check,
)


def register_tools(mcp: FastMCP) -> None:
    """모든 도구 모듈을 FastMCP 인스턴스에 등록한다."""
    example.register_tools(mcp)
    color.register_tools(mcp)
    render_check.register_tools(mcp)
    recommend_bottoms.register_tools(mcp)
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_recommend_bottoms.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 커밋**

```bash
git add src/playmcp_server/tools/recommend_bottoms.py src/playmcp_server/tools/__init__.py tests/conftest.py tests/test_recommend_bottoms.py
git commit -m "feat(tools): recommend_bottoms — 규칙 색 매칭 하의 추천"
```

---

### Task 9: `recommend_outfits` 도구

**Files:**
- Create: `src/playmcp_server/tools/recommend_outfits.py`
- Modify: `src/playmcp_server/tools/__init__.py`
- Test: `tests/test_recommend_outfits.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_recommend_outfits.py`:
```python
"""recommend_outfits 도구 검증 (in-memory MCP)."""

import pytest


async def test_tool_listed(client_session, clothing_db) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    assert "recommend_outfits" in {t.name for t in result.tools}


async def test_recommends_by_occasion(client_session, clothing_db) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_outfits", {"occasion": "놀이동산"}
        )
    text = result.content[0].text
    assert not result.isError
    assert "놀이동산 캐주얼" in text
    assert "instagram" in text or "ig/" in text  # 출처 노출


async def test_unknown_occasion_returns_valid_list(
    client_session, clothing_db
) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_outfits", {"occasion": "달나라"}
        )
    assert "가능한 상황" in result.content[0].text


async def test_no_match_is_not_error(client_session, clothing_db) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "recommend_outfits", {"occasion": "소개팅"}
        )
    assert not result.isError
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_recommend_outfits.py -v`
Expected: FAIL (recommend_outfits 미등록)

- [ ] **Step 3: 도구 구현 작성**

`src/playmcp_server/tools/recommend_outfits.py`:
```python
"""recommend_outfits — 상황(놀이동산 등) 기반 큐레이션 코디 Top-N 추천.

큐레이션 셋업(인스타/무신사 스냅)을 상황·스타일 태그로 조회한다. 개별 아이템
구매는 원본 스냅(source_url)으로 우회한다. 외부 호출 없음·결정적.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from playmcp_server.db.repository import get_repository
from playmcp_server.db.schema import tags_to_list
from playmcp_server.db.vocab import OCCASION_TAGS, STYLE_TAGS


def register_tools(mcp: FastMCP) -> None:
    """recommend_outfits 도구를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend outfits by occasion",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def recommend_outfits(
        occasion: str,
        style: str | None = None,
        formality: int | None = None,
        season: str | None = None,
        limit: int = 5,
    ) -> str:
        """Recommends curated outfits for an occasion for TPO Coach(티피오 코치).

        Looks up curated looks tagged by occasion/style. Provide the occasion in
        Korean (e.g. '놀이동산', '하객룩').

        Args:
            occasion: 상황 태그 (한글).
            style: 스타일 태그 (선택, 예 '캐주얼').
            formality: 격식 1~5 (선택, ±1 범위).
            season: 'spring'|'summer'|'fall'|'winter'|'all' (선택).
            limit: 추천 개수 (기본 5).

        Returns:
            추천 코디 목록 마크다운(출처 포함). 없으면 안내 문구.
        """
        if occasion not in OCCASION_TAGS:
            return f"알 수 없는 상황: {occasion}. 가능한 상황: {sorted(OCCASION_TAGS)}"
        if style is not None and style not in STYLE_TAGS:
            return f"알 수 없는 스타일: {style}. 가능한 스타일: {sorted(STYLE_TAGS)}"

        fits = get_repository().find_outfits(
            occasion=occasion,
            style=style,
            formality=formality,
            season=season,
            limit=limit,
        )
        if not fits:
            return (
                f"'{occasion}' 에 맞는 코디를 찾지 못했어요. "
                "스타일/격식 조건을 완화해 보세요."
            )

        lines = [f"**'{occasion}' 코디 추천 (TPO Coach):**"]
        for i, f in enumerate(fits, 1):
            title = f.title or "코디"
            tags = " ".join(f"#{t}" for t in tags_to_list(f.style_tags or ""))
            src = f" · 출처:{f.source}({f.source_url})" if f.source_url else ""
            note = f" — {f.items_note}" if f.items_note else ""
            lines.append(f"{i}. {title} {tags}{src}{note}")
        return "\n".join(lines)
```

- [ ] **Step 4: 도구 등록**

`src/playmcp_server/tools/__init__.py` 수정 — import 와 register 에 추가:
```python
from playmcp_server.tools import (
    color,
    example,
    recommend_bottoms,
    recommend_outfits,
    render_check,
)


def register_tools(mcp: FastMCP) -> None:
    """모든 도구 모듈을 FastMCP 인스턴스에 등록한다."""
    example.register_tools(mcp)
    color.register_tools(mcp)
    render_check.register_tools(mcp)
    recommend_bottoms.register_tools(mcp)
    recommend_outfits.register_tools(mcp)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_recommend_outfits.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/playmcp_server/tools/recommend_outfits.py src/playmcp_server/tools/__init__.py tests/test_recommend_outfits.py
git commit -m "feat(tools): recommend_outfits — 상황 기반 코디 추천"
```

---

### Task 10: 배포 와이어링 + 전체 검증

**Files:**
- Modify: `Dockerfile`
- Modify: `.gitignore`
- Test: 전체 스위트 + ruff

- [ ] **Step 1: 빌드 산출물 gitignore**

`.gitignore` 끝에 추가:
```
# 빌드 산출물 (시드 CSV 에서 생성)
src/playmcp_server/data/clothing.db
```

- [ ] **Step 2: Dockerfile 에 DB 빌드 단계 추가**

`Dockerfile` 의 `RUN uv pip install --system -e .` 줄 바로 아래에 추가:
```dockerfile
# 시드 CSV → read-only clothing.db 생성 (런타임에 저장소가 로드)
RUN python -m playmcp_server.db.build_db
```

- [ ] **Step 3: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: PASS (기존 + 신규 전부 통과)

- [ ] **Step 4: 린트 통과 확인**

Run: `uv run ruff check .`
Expected: All checks passed

- [ ] **Step 5: 도구 개수 확인 (PlayMCP ≤ 20)**

Run: `uv run python -c "from playmcp_server.server import mcp; import asyncio; print(len(asyncio.run(mcp.list_tools())))"`
Expected: 7 이하 출력 (greet, add, extract_color, get_uploaded_image?, render_check, recommend_bottoms, recommend_outfits — PlayMCP 권장 3~10 충족)

- [ ] **Step 6: 커밋**

```bash
git add Dockerfile .gitignore
git commit -m "build: 컨테이너 빌드 시 clothing.db 생성 + 산출물 gitignore"
```

---

## Self-Review

**1. Spec coverage** (스펙 각 절 → 태스크):
- §2 아키텍처(분리) → Task 1·3·8·9 (repository/color_rules/tool 분리) ✅
- §3 컴포넌트 전부 → models(T2)·vocab(T2)·color_rules(T1)·schema(T2)·repository(T3-5)·build_db(T6)·도구(T8-9) ✅
- §4.1 clothing_items 스키마 → Task 2 ✅
- §4.2 outfits 단일 테이블(items_note 포함) → Task 2 ✅
- §4.3 태그 정규화·정확 토큰 매칭 → normalize_tags(T2)·find_outfits LIKE(T4)·test_find_outfits_exact_token_match ✅
- §4.4 색 규칙 코드(DB 아님) → Task 1 ✅
- §5.1 recommend_bottoms 플로우 → Task 8 ✅
- §5.2 recommend_outfits 플로우 → Task 9 ✅
- §6 에러: DB없음 fail-fast(T5)·알수없는 색/태그(T8/T9)·0건 비에러(T8/T9)·read-only(T5)·annotations(T8/T9) ✅
- §7 교체가능 Protocol → Task 3(Protocol 정의) ✅
- §8 테스트·성능·동시성 → 각 태스크 TDD, read-only 동시읽기(T5) ✅
- §9 빌드 파이프라인·검증 → Task 6·7·10 ✅
- §10 저작권(source_url) → Outfit.source_url(T2)·recommend_outfits 출처 노출(T9) ✅

**2. Placeholder scan:** "TODO/TBD/적절히" 없음. 모든 코드 단계에 완전한 코드 수록. ✅

**3. Type consistency:**
- `find_bottoms(colors, *, formality, season)` (limit 없음) — Protocol(T3)·구현(T3)·도구 호출(T8) 일치 ✅
- `find_outfits(*, occasion, style, formality, season, limit)` — Protocol(T3)·구현(T4)·도구(T9) 일치 ✅
- `ClothingItem`/`Outfit` 필드명 — models(T2)·_item/_outfit(T3/T4)·도구 사용(T8/T9) 일치 ✅
- `harmony()` 반환 `(색, 종류, score)` — color_rules(T1)·도구 unpack(T8) 일치 ✅
- `normalize_tags`/`tags_to_list` — schema(T2)·build_db(T6)·repository(T4)·도구(T9) 일치 ✅
- `get_repository`/`reset_repository` — repository(T5)·conftest(T8)·도구(T8/T9) 일치 ✅
