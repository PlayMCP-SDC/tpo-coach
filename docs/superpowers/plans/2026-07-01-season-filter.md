# 계절 하드 필터 (소매기장 + 소재 보온등급) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코디 추천에 계절(봄가을/여름/겨울)이 들어오면 그 계절에 안 맞는 코디를 하드 필터로 제외한다.

**Architecture:** 원천 라벨링에서 `소매기장`·`소재`를 새 컬럼으로 적재하고(원값 보존), 소재에서 `보온등급(따뜻/시원/중립)`을 빌드 시점에 파생 저장한다. 계절 필터는 쿼리 시점에 `warmth`·`sleeve`·`기장`·`카테고리`를 WHERE 로 걸어 계산한다(재빌드 없이 규칙 튜닝 가능). 코디는 세트라 한 부위라도 금지 조건에 걸리면 전체 제외한다.

**Tech Stack:** Python 3.10+, SQLite (stdlib `sqlite3`), FastMCP(`mcp[cli]`), pytest, ruff. 패키지/실행은 `uv`.

**설계 출처:** `docs/idea/weather_role.md` (매핑표·규칙표 확정본).

## Global Constraints

- Python 3.10+ · 실행/명령은 항상 `uv run <cmd>` (pip/poetry 금지).
- stdio transport 에서 `print`(stdout) 금지 — 로그는 `logging`/`sys.stderr`.
- 모든 MCP 도구는 타입 힌트 + docstring, `annotations` 5종 유지. 도구 개수 ≤ 20 (이번엔 새 도구 없음, 파라미터만 추가).
- 도구 응답 p99 ≤ 3,000ms (계절 필터가 추천 쿼리에 WHERE 추가 — 기존 성능 가드 테스트 유지).
- 통제 어휘(스타일/카테고리/기장/소매기장/소재)는 `vocab.py` 단일 출처. 미등록 값은 빌드에서 `ParseError`.
- 계절 3버킷 고정: `봄가을`·`여름`·`겨울` (요청당 하나).
- 컬럼 추가 대상: `sleeve`=상의·아우터·원피스(하의 없음), `material`·`warmth`=전 부위.

---

## File Structure

- `src/playmcp_server/db/vocab.py` (수정) — `SLEEVES`·`MATERIALS`·`WARMTH_LEVELS` 어휘, 소재→보온등급 매핑 `_MATERIAL_WARMTH`, `warmth_of()` 파생 함수.
- `src/playmcp_server/db/schema.py` (수정) — `outfits` 에 `{part}_sleeve`·`{part}_material`·`{part}_warmth` 컬럼 추가.
- `src/playmcp_server/models.py` (수정) — `Outfit` 에 새 필드 추가.
- `src/playmcp_server/db/build_db.py` (수정) — 소매기장·소재 추출 + 보온등급 파생, `_INSERT` 확장.
- `src/playmcp_server/db/season.py` (신규) — `SEASONS` + `season_where()` (계절→SQL WHERE 조각·params).
- `src/playmcp_server/db/repository.py` (수정) — `_outfit` 새 컬럼 매핑, `sample_outfits(..., season=)` 필터, Protocol 갱신.
- `src/playmcp_server/tools/recommend.py` (수정) — 두 도구에 `season` 파라미터 + `_recommend` 통과.
- 테스트: 각 모듈의 `tests/test_*.py` 에 추가.
- 마지막: 패키지 DB(`src/playmcp_server/data/clothing.db`) 재빌드.

---

## Task 1: 어휘 + 보온등급 파생 (vocab.py)

**Files:**
- Modify: `src/playmcp_server/db/vocab.py`
- Test: `tests/test_vocab.py` (신규)

**Interfaces:**
- Produces:
  - `SLEEVES: frozenset[str]` — 소매기장 6종.
  - `MATERIALS: frozenset[str]` — 소재 25종.
  - `WARMTH_LEVELS: frozenset[str]` — `{"따뜻","시원","중립"}`.
  - `warmth_of(materials: list[str] | None) -> str | None` — 소재 리스트→보온등급(따뜻>시원>중립), 빈/None→None.

- [ ] **Step 1: Write the failing test**

Create `tests/test_vocab.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vocab.py -v`
Expected: FAIL (`ImportError: cannot import name 'SLEEVES'`)

- [ ] **Step 3: Implement in `vocab.py`**

Append to `src/playmcp_server/db/vocab.py` (아래 `normalize_length` 뒤):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vocab.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/db/vocab.py tests/test_vocab.py
git commit -m "feat(vocab): add sleeve/material vocab + warmth derivation"
```

---

## Task 2: 스키마 컬럼 추가 (schema.py)

**Files:**
- Modify: `src/playmcp_server/db/schema.py`
- Test: `tests/test_schema.py` (기존에 추가)

**Interfaces:**
- Produces: `outfits` 테이블에 컬럼 —
  `top_sleeve`, `outer_sleeve`, `dress_sleeve`,
  `top_material`, `bottom_material`, `outer_material`, `dress_material`,
  `top_warmth`, `bottom_warmth`, `outer_warmth`, `dress_warmth` (모두 TEXT, nullable).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_schema.py`:

```python
def test_schema_has_season_columns() -> None:
    import sqlite3

    from playmcp_server.db import schema

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(outfits)")}
    for c in (
        "top_sleeve", "outer_sleeve", "dress_sleeve",
        "top_material", "bottom_material", "outer_material", "dress_material",
        "top_warmth", "bottom_warmth", "outer_warmth", "dress_warmth",
    ):
        assert c in cols, f"컬럼 누락: {c}"
    assert "bottom_sleeve" not in cols  # 하의엔 소매기장 없음
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py::test_schema_has_season_columns -v`
Expected: FAIL (`컬럼 누락: top_sleeve`)

- [ ] **Step 3: Modify `schema.py`**

`SCHEMA` 안의 부위 구성 블록을 아래로 교체 (기존 `-- 구성:` 4줄):

```python
    -- 구성: 부위별 카테고리 + 기장 + 소매기장 + 소재(원값) + 보온등급(파생).
    -- sleeve 는 상의/아우터/원피스만(하의엔 소매기장 없음).
    top_category    TEXT, top_length    TEXT, top_sleeve  TEXT,
    top_material    TEXT, top_warmth    TEXT,
    bottom_category TEXT, bottom_length TEXT,
    bottom_material TEXT, bottom_warmth TEXT,
    outer_category  TEXT, outer_length  TEXT, outer_sleeve TEXT,
    outer_material  TEXT, outer_warmth  TEXT,
    dress_category  TEXT, dress_length  TEXT, dress_sleeve TEXT,
    dress_material  TEXT, dress_warmth  TEXT,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (기존 스키마 테스트 + 신규 통과)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/db/schema.py tests/test_schema.py
git commit -m "feat(schema): add sleeve/material/warmth columns to outfits"
```

---

## Task 3: 모델 필드 추가 (models.py)

**Files:**
- Modify: `src/playmcp_server/models.py`
- Test: `tests/test_repository.py` (기존에 추가) — 모델 필드 존재/기본값 확인

**Interfaces:**
- Consumes: (없음)
- Produces: `Outfit` dataclass 에 `top_sleeve`, `outer_sleeve`, `dress_sleeve`, `top_material`, `bottom_material`, `outer_material`, `dress_material`, `top_warmth`, `bottom_warmth`, `outer_warmth`, `dress_warmth` (모두 `str | None = None`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_repository.py`:

```python
def test_outfit_has_season_fields() -> None:
    from playmcp_server.models import Outfit

    o = Outfit(
        id="x", image_url="u", style="모던",
        top_sleeve="반팔", top_material="린넨", top_warmth="시원",
        bottom_warmth="중립",
    )
    assert o.top_sleeve == "반팔"
    assert o.top_material == "린넨"
    assert o.top_warmth == "시원"
    assert o.outer_sleeve is None  # 기본값 None
    assert o.dress_warmth is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py::test_outfit_has_season_fields -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'top_sleeve'`)

- [ ] **Step 3: Modify `models.py`**

`Outfit` 의 부위 필드들을 아래로 교체 (기존 `top_category`~`dress_length` 블록):

```python
    top_category: str | None = None
    top_length: str | None = None
    top_sleeve: str | None = None
    top_material: str | None = None
    top_warmth: str | None = None
    bottom_category: str | None = None
    bottom_length: str | None = None
    bottom_material: str | None = None
    bottom_warmth: str | None = None
    outer_category: str | None = None
    outer_length: str | None = None
    outer_sleeve: str | None = None
    outer_material: str | None = None
    outer_warmth: str | None = None
    dress_category: str | None = None
    dress_length: str | None = None
    dress_sleeve: str | None = None
    dress_material: str | None = None
    dress_warmth: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repository.py::test_outfit_has_season_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/models.py tests/test_repository.py
git commit -m "feat(models): add sleeve/material/warmth fields to Outfit"
```

---

## Task 4: 빌드 시 소매기장·소재·보온등급 적재 (build_db.py)

**Files:**
- Modify: `src/playmcp_server/db/build_db.py`
- Test: `tests/test_build_db.py` (기존에 추가/수정)

**Interfaces:**
- Consumes: `vocab.SLEEVES`, `vocab.MATERIALS`, `vocab.warmth_of`.
- Produces: `parse_outfit(...)` 반환 row 에 `{part}_sleeve`(top/outer/dress), `{part}_material`(전부위), `{part}_warmth`(전부위) 키 포함. `_INSERT` 가 새 컬럼 반영.

- [ ] **Step 1: Write the failing test**

`tests/test_build_db.py` 의 `_doc` 헬퍼에 선택 속성을 주입하도록 수정하고 테스트를 추가한다.

`_doc` 시그니처와 본문을 아래로 교체:

```python
def _doc(
    oid: int,
    *,
    style: str = "모던",
    substyle: str | None = "톰보이",
    top_cat: str | None = "블라우스",
    bottom_cat: str | None = "팬츠",
    bottom_len: str | None = "롱",
    top_sleeve: str | None = None,
    top_material: list[str] | None = None,
    bottom_material: list[str] | None = None,
) -> dict:
    """최소 유효 라벨링 JSON 문서를 만든다."""
    top: dict = {"카테고리": top_cat} if top_cat else {}
    if top_sleeve is not None:
        top["소매기장"] = top_sleeve
    if top_material is not None:
        top["소재"] = top_material
    bottom: dict = (
        {"카테고리": bottom_cat, "기장": bottom_len} if bottom_cat else {}
    )
    if bottom_material is not None:
        bottom["소재"] = bottom_material
    lab: dict = {
        "스타일": [{"스타일": style, "서브스타일": substyle}],
        "상의": [top],
        "하의": [bottom],
        "아우터": [{}],
        "원피스": [{}],
    }
    return {
        "이미지 정보": {"이미지 식별자": oid, "이미지 파일명": f"{oid}.jpg"},
        "데이터셋 정보": {
            "파일 생성일자": "2020-01-01 00:00:00",
            "데이터셋 상세설명": {"라벨링": lab},
        },
    }
```

새 테스트 추가:

```python
def test_parse_extracts_sleeve_material_warmth() -> None:
    row = build_db.parse_outfit(
        _doc(9, top_sleeve="반팔", top_material=["우븐", "린넨"]),
        now="t",
    )
    assert row["top_sleeve"] == "반팔"
    assert row["top_material"] == "우븐,린넨"
    assert row["top_warmth"] == "시원"       # 린넨 → 시원
    assert row["bottom_sleeve"] not in row   # 하의엔 sleeve 없음
    assert row["bottom_material"] is None     # 소재 미지정
    assert row["bottom_warmth"] is None


def test_parse_bottom_warmth_from_material() -> None:
    row = build_db.parse_outfit(
        _doc(10, bottom_material=["코듀로이"]), now="t"
    )
    assert row["bottom_material"] == "코듀로이"
    assert row["bottom_warmth"] == "따뜻"


def test_parse_rejects_unknown_sleeve() -> None:
    with pytest.raises(build_db.ParseError, match="소매기장"):
        build_db.parse_outfit(_doc(1, top_sleeve="쓰리쿼터"), now="t")


def test_parse_rejects_unknown_material() -> None:
    with pytest.raises(build_db.ParseError, match="소재"):
        build_db.parse_outfit(_doc(1, top_material=["금속"]), now="t")


def test_build_persists_season_columns(tmp_path) -> None:
    root = tmp_path / "labels"
    _write(root, "모던", 1, top_sleeve="긴팔", top_material=["울/캐시미어"])
    dest = tmp_path / "out.db"
    build_db.build(root, dest, url_base="https://b")
    conn = sqlite3.connect(dest)
    r = conn.execute(
        "SELECT top_sleeve, top_material, top_warmth FROM outfits"
    ).fetchone()
    assert r == ("긴팔", "울/캐시미어", "따뜻")
```

주의: `test_parse_extracts_sleeve_material_warmth` 의 `assert row["bottom_sleeve"] not in row` 는
`"bottom_sleeve" not in row` 의 의도 — 아래처럼 명확히 작성:

```python
    assert "bottom_sleeve" not in row
```

(위 블록에서 해당 줄을 이 형태로 쓴다.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build_db.py::test_parse_extracts_sleeve_material_warmth -v`
Expected: FAIL (`KeyError: 'top_sleeve'`)

- [ ] **Step 3: Modify `build_db.py`**

(a) import 확장 — `from playmcp_server.db.vocab import (...)` 에 `MATERIALS`, `SLEEVES`, `warmth_of` 추가:

```python
from playmcp_server.db.vocab import (
    CATEGORIES_BY_PART,
    LENGTHS,
    MATERIALS,
    SLEEVES,
    STYLES,
    SUBSTYLES,
    normalize_length,
    warmth_of,
)
```

(b) `_PART_PREFIX` 아래에 소매기장 보유 부위 집합 추가:

```python
# 소매기장이 있는 부위(하의 제외).
_SLEEVE_PARTS: frozenset[str] = frozenset({"상의", "아우터", "원피스"})
```

(c) `_INSERT` 를 새 컬럼 포함해 교체:

```python
_INSERT = (
    "INSERT INTO outfits ("
    "id,image_url,style,substyle,"
    "top_category,top_length,top_sleeve,top_material,top_warmth,"
    "bottom_category,bottom_length,bottom_material,bottom_warmth,"
    "outer_category,outer_length,outer_sleeve,outer_material,outer_warmth,"
    "dress_category,dress_length,dress_sleeve,dress_material,dress_warmth,"
    "created_at,updated_at,deleted_at) "
    "VALUES (:id,:image_url,:style,:substyle,"
    ":top_category,:top_length,:top_sleeve,:top_material,:top_warmth,"
    ":bottom_category,:bottom_length,:bottom_material,:bottom_warmth,"
    ":outer_category,:outer_length,:outer_sleeve,:outer_material,:outer_warmth,"
    ":dress_category,:dress_length,:dress_sleeve,:dress_material,:dress_warmth,"
    ":created_at,:updated_at,NULL)"
)
```

(d) `parse_outfit` 의 부위 루프를 아래로 교체 (기존 `for part, prefix in _PART_PREFIX.items():` 블록 전체):

```python
    for part, prefix in _PART_PREFIX.items():
        item = _first(lab.get(part))
        category = item.get("카테고리") or None
        if category is not None and category not in CATEGORIES_BY_PART[part]:
            raise ParseError(f"{part} 카테고리 미등록: {category!r}")
        length = normalize_length(item.get("기장"))
        if length is not None and length not in LENGTHS:
            raise ParseError(f"{part} 기장 미등록: {length!r}")
        row[f"{prefix}_category"] = category
        row[f"{prefix}_length"] = length

        # 소재: 원값(리스트) 보존 + 보온등급 파생.
        materials = item.get("소재") or []
        if not isinstance(materials, list):
            materials = [materials]
        for m in materials:
            if m not in MATERIALS:
                raise ParseError(f"{part} 소재 미등록: {m!r}")
        row[f"{prefix}_material"] = ",".join(materials) or None
        row[f"{prefix}_warmth"] = warmth_of(materials)

        # 소매기장: 상의/아우터/원피스만.
        if part in _SLEEVE_PARTS:
            sleeve = item.get("소매기장") or None
            if sleeve is not None and sleeve not in SLEEVES:
                raise ParseError(f"{part} 소매기장 미등록: {sleeve!r}")
            row[f"{prefix}_sleeve"] = sleeve
```

(e) 모듈 docstring 의 "카테고리·기장만 추출하고, 좌표·색상·소재 등 나머지는 버린다." 문장을 현실에 맞게 수정:

```python
카테고리·기장·소매기장·소재를 추출하고(소재→보온등급 파생), 좌표·색상 등
나머지는 버린다.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_build_db.py -v`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/db/build_db.py tests/test_build_db.py
git commit -m "feat(build_db): extract sleeve/material and derive warmth"
```

---

## Task 5: 계절 → SQL 필터 (season.py 신규)

**Files:**
- Create: `src/playmcp_server/db/season.py`
- Test: `tests/test_season.py` (신규)

**Interfaces:**
- Consumes: (없음 — 순수 SQL 조각 생성기)
- Produces:
  - `SEASONS: frozenset[str]` — `{"봄가을","여름","겨울"}`.
  - `season_where(season: str) -> tuple[str, list[str]]` — 유지(keep) 조건 SQL 조각과 파라미터. 유효하지 않은 계절이면 `("", [])`. 반환 SQL 은 앞에 `AND` 없이 `cond AND cond ...` 형태(호출자가 `AND` 로 이어붙임).

- [ ] **Step 1: Write the failing test**

Create `tests/test_season.py`:

```python
"""계절 하드 필터 SQL 조각 — 실제 SQLite 로 배제 동작 검증."""

import sqlite3

import pytest

from playmcp_server.db import schema
from playmcp_server.db.season import SEASONS, season_where


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    yield conn
    conn.close()


def _insert(conn, oid, **cols):
    keys = ["id", "image_url", "style", *cols.keys()]
    ph = ",".join("?" * len(keys))
    conn.execute(
        f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
        [oid, f"u/{oid}", "모던", *cols.values()],
    )


def _kept(conn, season):
    frag, params = season_where(season)
    sql = "SELECT id FROM outfits WHERE deleted_at IS NULL"
    if frag:
        sql += " AND " + frag
    return {r[0] for r in conn.execute(sql, params)}


def test_seasons_set() -> None:
    assert SEASONS == {"봄가을", "여름", "겨울"}


def test_summer_excludes_warm_coat_maxi(db) -> None:
    _insert(db, "ok", top_warmth="시원", bottom_length="미디")
    _insert(db, "warm", outer_warmth="따뜻")          # 따뜻 → 탈락
    _insert(db, "coat", outer_category="코트")         # 코트 → 탈락
    _insert(db, "maxi", bottom_length="맥시")          # 맥시 → 탈락
    _insert(db, "null", top_warmth=None)               # 결측 → 통과
    db.commit()
    assert _kept(db, "여름") == {"ok", "null"}


def test_winter_excludes_cool_sleeveless_mini_bratop(db) -> None:
    _insert(db, "ok", top_warmth="따뜻", top_sleeve="긴팔")
    _insert(db, "cool", top_warmth="시원")             # 시원 → 탈락
    _insert(db, "sleeve", top_sleeve="반팔")           # 반팔 → 탈락
    _insert(db, "mini", dress_length="미니")           # 미니 → 탈락
    _insert(db, "bra", top_category="브라탑")          # 브라탑 → 탈락
    db.commit()
    assert _kept(db, "겨울") == {"ok"}


def test_springfall_only_excludes_padding(db) -> None:
    _insert(db, "wool", outer_warmth="따뜻", outer_category="코트")  # 통과
    _insert(db, "linen", top_warmth="시원")            # 통과
    _insert(db, "pad", outer_category="패딩")          # 패딩만 탈락
    db.commit()
    assert _kept(db, "봄가을") == {"wool", "linen"}


def test_unknown_season_no_filter(db) -> None:
    _insert(db, "a", outer_category="패딩")
    db.commit()
    assert season_where("겨울잠") == ("", [])
    assert _kept(db, "겨울잠") == {"a"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_season.py -v`
Expected: FAIL (`ModuleNotFoundError: ... season`)

- [ ] **Step 3: Create `season.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_season.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/db/season.py tests/test_season.py
git commit -m "feat(season): season->SQL hard-filter builder"
```

---

## Task 6: 저장소 조회에 계절 필터 결선 (repository.py)

**Files:**
- Modify: `src/playmcp_server/db/repository.py`
- Test: `tests/test_repository.py` (기존에 추가)

**Interfaces:**
- Consumes: `season.season_where`.
- Produces: `SQLiteOutfitRepository.sample_outfits(*, style: str, n: int, season: str | None = None) -> list[Outfit]` — season 지정 시 계절 필터 적용. `OutfitRepository` Protocol 도 동일 시그니처. `_outfit` 이 새 컬럼을 `Outfit` 필드로 매핑.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_repository.py`:

```python
def _repo_with(rows):
    import sqlite3

    from playmcp_server.db import schema
    from playmcp_server.db.repository import SQLiteOutfitRepository

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    for r in rows:
        keys = ["id", "image_url", "style", *r.keys()]
        ph = ",".join("?" * len(keys))
        conn.execute(
            f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
            [r["_id"], f"u/{r['_id']}", "모던",
             *[v for k, v in r.items()]],
        )
    conn.commit()
    return SQLiteOutfitRepository(conn)


def test_sample_applies_season_filter() -> None:
    repo = _repo_with([
        {"_id": "keep", "bottom_length": "미디"},
        {"_id": "drop", "bottom_length": "맥시"},   # 여름 배제
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10, season="여름")}
    assert got == {"keep"}


def test_sample_no_season_returns_all() -> None:
    repo = _repo_with([
        {"_id": "a", "bottom_length": "맥시"},
        {"_id": "b", "bottom_length": "미디"},
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert got == {"a", "b"}


def test_outfit_maps_new_columns() -> None:
    repo = _repo_with([
        {"_id": "z", "top_sleeve": "반팔",
         "top_material": "린넨", "top_warmth": "시원"},
    ])
    o = repo.sample_outfits(style="모던", n=1)[0]
    assert o.top_sleeve == "반팔"
    assert o.top_material == "린넨"
    assert o.top_warmth == "시원"
```

주의: `_repo_with` 의 INSERT 는 `_id` 키를 컬럼명으로 쓰면 안 되므로, row dict 에서 `_id` 를 분리해 실제 컬럼만 넣도록 아래처럼 작성한다(위 스텁을 이 정확한 형태로):

```python
def _repo_with(rows):
    import sqlite3

    from playmcp_server.db import schema
    from playmcp_server.db.repository import SQLiteOutfitRepository

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    for r in rows:
        cols = {k: v for k, v in r.items() if k != "_id"}
        keys = ["id", "image_url", "style", *cols.keys()]
        ph = ",".join("?" * len(keys))
        conn.execute(
            f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
            [r["_id"], f"u/{r['_id']}", "모던", *cols.values()],
        )
    conn.commit()
    return SQLiteOutfitRepository(conn)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py::test_sample_applies_season_filter -v`
Expected: FAIL (`TypeError: sample_outfits() got an unexpected keyword argument 'season'`)

- [ ] **Step 3: Modify `repository.py`**

(a) import 추가 (파일 상단 import 블록):

```python
from playmcp_server.db.season import season_where
```

(b) `_outfit` 에 새 컬럼 매핑 추가 — 기존 `top_length=...` 등 사이에 삽입해 아래 형태로:

```python
def _outfit(row: sqlite3.Row) -> Outfit:
    return Outfit(
        id=row["id"],
        image_url=row["image_url"],
        style=row["style"],
        substyle=row["substyle"],
        top_category=row["top_category"],
        top_length=row["top_length"],
        top_sleeve=row["top_sleeve"],
        top_material=row["top_material"],
        top_warmth=row["top_warmth"],
        bottom_category=row["bottom_category"],
        bottom_length=row["bottom_length"],
        bottom_material=row["bottom_material"],
        bottom_warmth=row["bottom_warmth"],
        outer_category=row["outer_category"],
        outer_length=row["outer_length"],
        outer_sleeve=row["outer_sleeve"],
        outer_material=row["outer_material"],
        outer_warmth=row["outer_warmth"],
        dress_category=row["dress_category"],
        dress_length=row["dress_length"],
        dress_sleeve=row["dress_sleeve"],
        dress_material=row["dress_material"],
        dress_warmth=row["dress_warmth"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        deleted_at=row["deleted_at"],
    )
```

(c) Protocol 의 `sample_outfits` 시그니처 갱신:

```python
    def sample_outfits(
        self, *, style: str, n: int, season: str | None = None
    ) -> list[Outfit]: ...
```

(d) `SQLiteOutfitRepository.sample_outfits` 를 아래로 교체:

```python
    def sample_outfits(
        self, *, style: str, n: int, season: str | None = None
    ) -> list[Outfit]:
        # SQLite 는 음수 LIMIT 을 "무제한"으로 취급하므로 방어적 클램프.
        where = "style = ? AND deleted_at IS NULL"
        params: list[object] = [style]
        if season:
            frag, sp = season_where(season)
            if frag:
                where += " AND " + frag
                params.extend(sp)
        params.append(max(0, n))
        rows = self._conn.execute(
            f"SELECT * FROM outfits WHERE {where} ORDER BY RANDOM() LIMIT ?",
            params,
        )
        return [_outfit(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(repository): season filter in sample_outfits + map new columns"
```

---

## Task 7: 추천 도구에 season 파라미터 (recommend.py)

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py`
- Test: `tests/test_recommend.py` (기존에 추가)

**Interfaces:**
- Consumes: `repository.sample_outfits(..., season=)`, `season.SEASONS`.
- Produces:
  - `_recommend(styles, n, *, title, label_styles, season=None)` — season 을 표본 추출에 전달.
  - `recommend_outfits_by_style(style, n=3, season=None)` 및 `recommend_outfits_by_situation(situation, styles, n=3, season=None)` — season 옵션(`봄가을`/`여름`/`겨울`/미지정).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_recommend.py`:

```python
def test_recommend_passes_season(monkeypatch) -> None:
    # _recommend 가 season 을 sample_outfits 로 그대로 넘기는지 확인
    from playmcp_server.tools import recommend as rec

    seen = {}

    class _Fake:
        def sample_outfits(self, *, style, n, season=None):
            seen["season"] = season
            return [Outfit(id="a", image_url="u/a", style=style)]

    monkeypatch.setattr(rec, "get_repository", lambda: _Fake())
    out = rec._recommend(
        ["모던"], 1, title="", label_styles=False, season="여름"
    )
    assert seen["season"] == "여름"
    assert "![코디]" in out


@pytest.mark.asyncio
async def test_by_situation_accepts_season(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "여름 소개팅", "styles": ["로맨틱"],
             "n": 2, "season": "여름"},
        )
    text = res.content[0].text
    assert "![코디]" in text  # 여름 필터로도 결과가 나옴(small_db 는 기장/보온 결측→통과)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_recommend.py::test_recommend_passes_season -v`
Expected: FAIL (`_recommend() got an unexpected keyword argument 'season'`)

- [ ] **Step 3: Modify `recommend.py`**

(a) import 에 SEASONS 추가:

```python
from playmcp_server.db.season import SEASONS
```

그리고 정렬 목록 상수 근처에 추가:

```python
_SEASON_LIST = ["봄가을", "여름", "겨울"]  # enum·설명 공용 단일 출처
```

(b) `_recommend` 시그니처·본문의 표본 호출을 season 반영으로 교체:

```python
def _recommend(
    styles: list[str],
    n: int,
    *,
    title: str,
    label_styles: bool,
    season: str | None = None,
) -> str:
    """styles 정규화 → 스타일별 무작위 표본 → 라운드로빈 → 마크다운.

    season 이 지정되면 계절 하드 필터를 적용한다(미지원 값은 무시). 유효 스타일이
    하나도 없으면 안내 문자열을 돌려준다(추천 안 함). label_styles=True 면 실제
    결과에 등장한 스타일들만 머리말에 덧붙인다.
    """
    valid = _normalize_styles(styles)
    if not valid:
        return _no_valid_styles_msg(styles)
    k = _clamp_n(n)
    repo = get_repository()
    pools = [
        repo.sample_outfits(style=s, n=k, season=season) for s in valid
    ]
    outfits = _interleave(pools)[:k]
    if not outfits:
        return "해당 조건의 코디를 찾지 못했습니다. 다른 스타일/계절로 시도해 보세요."
    header = title
    if label_styles:
        used = list(dict.fromkeys(o.style for o in outfits))
        header = f"{title} ({' · '.join(used)})"
    body = "\n\n".join(_format_outfit(o) for o in outfits)
    return f"{header}\n\n{body}" if header else body
```

(c) `recommend_outfits_by_style` 에 season 파라미터 추가 (시그니처·docstring·호출):

```python
    def recommend_outfits_by_style(
        style: str, n: int = _N_DEFAULT, season: str | None = None
    ) -> str:
        """Recommends outfit sets (코디) of a given style for TPO Coach(티피오 코치).

        Samples up to n random outfit coordinations of the requested style from
        the K-Fashion reference set and returns them as image-URL markdown. If a
        season is given, coordinations unsuitable for it are hard-filtered out. If
        the style is not supported, the valid style list is returned instead.

        Args:
            style: One of the supported Korean styles (e.g. 클래식, 스트리트, 로맨틱).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.
            season: Optional Korean season, one of 봄가을·여름·겨울. Others ignored.

        Returns:
            Markdown listing recommended outfits (image, style, composition).
        """
        return _recommend(
            [style], n, title=f"**{style}** 스타일 코디 추천",
            label_styles=False, season=season,
        )
```

(d) `recommend_outfits_by_situation` 에 season 파라미터 추가 (`styles` 파라미터 뒤, `n` 앞 또는 뒤 — 아래처럼 n 뒤):

```python
    def recommend_outfits_by_situation(
        situation: str,
        styles: Annotated[
            list[str],
            Field(
                description=(
                    "Styles that fit the situation, ordered by best fit first. "
                    "You MUST choose ONLY from these 23 supported Korean styles: "
                    + ", ".join(_STYLE_LIST)
                ),
                json_schema_extra={"items": {"type": "string", "enum": _STYLE_LIST}},
            ),
        ],
        n: int = _N_DEFAULT,
        season: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Season inferred from the situation, if any. Choose ONLY from: "
                    + ", ".join(_SEASON_LIST)
                    + ". Omit if the situation implies no particular season."
                ),
                json_schema_extra={"enum": [*_SEASON_LIST, None]},
            ),
        ] = None,
    ) -> str:
        """Recommends varied outfit sets (코디) for a situation for TPO Coach(티피오
        코치).

        Given a free-text situation, infer the Korean styles that fit it (ordered by
        best fit) and pass them as `styles`, choosing ONLY from the supported styles.
        If the situation implies a season, pass `season` (봄가을·여름·겨울) so
        season-inappropriate coordinations are hard-filtered out. The tool samples
        random outfits across the styles (round-robin). Unsupported styles are
        ignored; if none are valid, the valid style list is returned.

        Args:
            situation: User's situation in free text (e.g. "여름 소개팅"). Echoed only.
            styles: Supported styles fitting the situation, best fit first (1개 이상).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.
            season: Optional Korean season (봄가을·여름·겨울) to hard-filter by.

        Returns:
            Markdown: situation/styles heading + recommended outfits across styles.
        """
        title = f"**{situation}**에 어울리는 코디 추천"
        return _recommend(
            styles, n, title=title, label_styles=True, season=season
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: PASS (기존 + 신규 전부)

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "feat(recommend): add optional season hard-filter to both tools"
```

---

## Task 8: 패키지 DB 재빌드 + 전체 검증

**Files:**
- Regenerate: `src/playmcp_server/data/clothing.db`
- (코드 변경 없음 — 운영 단계)

**Interfaces:**
- Consumes: Task 1–7 전부. 원천 라벨링 루트 `014.KFashion/01.데이터/1.Training/라벨링데이터_modify` (스타일 폴더들의 부모).

- [ ] **Step 1: 전체 테스트·린트 (재빌드 전 코드 그린 확인)**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 전체 PASS + ruff 클린. (이 시점 `test_sample_perf_on_real_db` 는 구(舊) DB 로도 통과 — 새 컬럼은 `SELECT *` 로 무해)

- [ ] **Step 2: 새 스키마로 DB 재빌드**

원천 라벨링 루트를 환경변수로 지정하고 빌드(이미지 base URL 은 기존 값 사용). 약 97만 JSON 이라 수 분~수십 분 소요될 수 있음. 프로젝트 루트(`tpo-coach/`)에서:

Run:
```bash
uv run python -m playmcp_server.db.build_db \
  --src "../014.KFashion/01.데이터/1.Training/라벨링데이터_modify" \
  --url-base "$IMAGE_URL_BASE"
```
Expected(stderr 로그): `outfits.db 생성: loaded=<N> deduped=<M> skipped=<K> → .../data/clothing.db` (loaded > 0)

주의: `IMAGE_URL_BASE` 가 `.env` 에만 있고 셸에 없으면 `--url-base "$(grep ^IMAGE_URL_BASE .env | cut -d= -f2-)"` 로 주입하거나 값을 직접 넘긴다. base 를 비우면 image_url 에 객체 키만 저장되므로 반드시 기존 값과 동일하게 넣을 것.

- [ ] **Step 3: 재빌드 DB 에 계절 컬럼이 채워졌는지 스팟체크**

Run:
```bash
uv run python -c "import sqlite3; c=sqlite3.connect('src/playmcp_server/data/clothing.db'); print(c.execute(\"SELECT COUNT(*), COUNT(top_warmth), COUNT(top_sleeve) FROM outfits\").fetchone()); print(c.execute(\"SELECT DISTINCT top_warmth FROM outfits WHERE top_warmth IS NOT NULL\").fetchall())"
```
Expected: 총건수 > 0, `top_warmth`·`top_sleeve` 채워진 행 존재, distinct 보온등급이 `따뜻/시원/중립` 부분집합.

- [ ] **Step 4: 실 DB 로 계절 필터 왕복 확인 + 전체 테스트**

Run:
```bash
uv run python -c "
import os; os.environ.setdefault('CLOTHING_DB_PATH','src/playmcp_server/data/clothing.db')
from playmcp_server.db.repository import get_repository, reset_repository
reset_repository(); r=get_repository()
s=r.sample_outfits(style='스트리트', n=200, season='여름')
bad=[o.id for o in s if o.outer_category in ('코트','패딩') or o.bottom_length=='맥시' or o.dress_length=='맥시' or '따뜻' in (o.top_warmth,o.bottom_warmth,o.outer_warmth,o.dress_warmth)]
print('표본', len(s), '위반', len(bad)); assert not bad, bad
print('OK')
"
uv run pytest -q && uv run ruff check .
```
Expected: `위반 0` + `OK`, 그리고 전체 테스트 PASS + ruff 클린.

- [ ] **Step 5: Commit**

```bash
git add src/playmcp_server/data/clothing.db
git commit -m "chore(data): rebuild clothing.db with sleeve/material/warmth"
```

---

## Self-Review

**Spec coverage (docs/idea/weather_role.md):**
- §1 결정요약(3버킷·하드필터·쿼리시점) → Task 5(season.py)·Task 6(쿼리 결선). ✅
- §2 스키마 컬럼(sleeve/material/warmth, 하의 sleeve 없음) → Task 2(schema)·Task 3(models). ✅
- §3 소재→보온등급 매핑 + 다중값 우선순위 → Task 1(`_MATERIAL_WARMTH`·`warmth_of`). ✅
- §4 계절별 규칙표(여름 따뜻/코트·패딩/맥시, 겨울 시원/민소매·반팔·캡/미니/브라탑, 봄가을 패딩) → Task 5 `season_where` + Task 5 테스트. ✅
- §5 엣지(NULL 통과·다중소재 축약·세트 OR·후보고갈 안내) → Task 5(`_ne`/`_not_in` 의 `IS NULL OR`)·Task 1(우선순위)·Task 7(고갈 안내문). ✅
- §2 원값 보존(material 저장) → Task 4(`{prefix}_material`). ✅
- §6 out-of-scope(디테일/넥라인/핏, 하이브리드 완화, 빌드시점 태깅) → 계획에 미포함. ✅

**Placeholder scan:** 모든 코드 스텝에 실제 코드 포함, TODO/TBD 없음. ✅

**Type consistency:** `warmth_of(list|None)->str|None`(Task1) ↔ build_db 호출(Task4) ↔ warmth 컬럼 문자열(Task2) 일치. `sample_outfits(*, style, n, season=None)` 시그니처가 Protocol(Task6)·구현(Task6)·recommend 호출(Task7) 3곳 동일. `season_where(str)->tuple[str,list[str]]`(Task5) ↔ repository 언팩(Task6) 일치. `Outfit` 새 필드명(Task3) ↔ `_outfit` 매핑(Task6) ↔ build_db row 키(Task4) 동일 prefix 규칙. ✅
