# 계절 추천 신뢰성 v2 (완성 필터 + 소프트 선호 + 겨울 기장) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 계절 추천의 신뢰성을 높인다 — 불완전 코디 제외(완성 필터), 계절감 강한 코디 우선(가중 랜덤 소프트 선호), 겨울 하의·원피스 기장 강화(발목/맥시만).

**Architecture:** 세 축. (1) 빌드 시점 `is_complete` 컬럼을 만들어 `sample_outfits` 기본 WHERE 에서 `is_complete=1`만 추천(항상). (2) `season.py`에 `season_order_by()`를 추가해 `ORDER BY RANDOM()`을 계절별 가중 랜덤(`정규화랜덤 − bias×선호점수`)으로 교체. (3) 겨울 `season_where` 기장 조건을 `발목/맥시만`으로 강화. 하드 필터와 소프트 선호는 별도 함수로 분리한다.

**Tech Stack:** Python 3.10+, SQLite(stdlib `sqlite3`), FastMCP(`mcp[cli]`), pytest, ruff. 실행은 `uv`.

**설계 출처:** `docs/idea/weather_role.md` — §4(겨울 기장 갱신)·§7(완성 필터)·§8(소프트 선호)·§9(코드 배치). 이 계획은 v1(PR #10) 위에 스택된 v2 증분이며, 브랜치 `feat/season-reliability`.

## Global Constraints

- Python 3.10+ · 실행/명령은 항상 `uv run <cmd>` (pip/poetry 금지).
- stdio transport 에서 `print`(stdout) 금지 — 로그는 `logging`/`sys.stderr`.
- 도구 응답 p99 ≤ 3,000ms (추천 쿼리에 `is_complete` 필터 + 가중 정렬 추가 — 기존 성능 가드 테스트 유지).
- 통제 어휘·규칙은 기존 모듈 단일 출처 유지(`vocab.py`, `season.py`).
- **완성 정의:** `is_complete = 1` ⟺ `dress_category 있음 OR (top_category 있음 AND bottom_category 있음)`, 아니면 `0`.
- **완성 필터:** 항상 적용(계절·스타일 무관). 추천 WHERE 에서 `(is_complete IS NULL OR is_complete = 1)` — 실 DB 는 항상 0/1 이고, NULL 통과는 코드베이스 관례(결측은 안 떨어뜨림) + 테스트 편의.
- **보존 정책:** 불완전 코디(`is_complete=0`)도 DB 에 남긴다(미래 스토리지 정리용). 빌드에서 제외하지 않는다.
- **소프트 선호:** `_SOFT_BIAS = 0.85`. 정렬키 = `정규화랜덤(0~1) − bias × 선호점수` 오름차순. 여름=소매(반팔/민소매/캡, 동급), 겨울=기장(롱 1.0 > 노멀 0.5, top·outer MAX). 봄가을·`season=None` → 순수 랜덤. **소재는 선호에 안 넣는다**(설계 §6 기각).
- **겨울 기장 하드:** `bottom_length`·`dress_length` ∈ {미니, 미디, 니렝스} 이면 탈락 → 발목/맥시/NULL 만 통과.
- `models.py` 의 `Outfit` 은 건드리지 않는다 — `is_complete` 는 SQL 필터 전용이라 `Outfit` 필드/`_outfit` 매핑에 추가하지 않는다(`SELECT *` 가 컬럼을 돌려줘도 `_outfit` 이 무시).

---

## File Structure

- `src/playmcp_server/db/season.py` (수정) — 겨울 `season_where` 기장 조건 강화 + 신규 `season_order_by()`·점수 빌더·`_SOFT_BIAS`.
- `src/playmcp_server/db/schema.py` (수정) — `is_complete INTEGER` 컬럼 추가.
- `src/playmcp_server/db/build_db.py` (수정) — `is_complete` 계산 + `_INSERT` 반영.
- `src/playmcp_server/db/repository.py` (수정) — `sample_outfits` 기본 WHERE 에 완성 필터, `ORDER BY` 를 `season_order_by` 로 조립.
- `src/playmcp_server/data/clothing.db` (재생성) — 새 컬럼 채워 재빌드.
- 테스트: `tests/test_season.py`·`tests/test_schema.py`·`tests/test_build_db.py`·`tests/test_repository.py`.

**태스크 순서(레드 방지):** 컬럼(2)·빌드(3)·재빌드(4)를 저장소 결선(6)보다 앞에 둬서, 저장소가 `is_complete` 를 참조할 때 실 DB 에 이미 컬럼이 있게 한다.

---

## Task 1: 겨울 기장 하드 규칙 강화 (season.py season_where)

**Files:**
- Modify: `src/playmcp_server/db/season.py`
- Test: `tests/test_season.py`

**Interfaces:**
- Consumes: 기존 `_not_in(col, values) -> tuple[str, list[str]]`.
- Produces: `season_where("겨울")` 이 `bottom_length`·`dress_length` 를 `NOT IN (미니, 미디, 니렝스)` 로 거른다(발목/맥시/NULL 통과).

- [ ] **Step 1: 실패 테스트 수정/추가**

`tests/test_season.py` 의 겨울 테스트를 아래로 교체(기존 `test_winter_excludes_cool_sleeveless_mini_bratop` 를 확장):

```python
def test_winter_excludes_cool_sleeveless_mini_bratop(db) -> None:
    _insert(db, "ok", top_warmth="따뜻", top_sleeve="긴팔", bottom_length="발목")
    _insert(db, "cool", top_warmth="시원")             # 시원 → 탈락
    _insert(db, "sleeve", top_sleeve="반팔")           # 반팔 → 탈락
    _insert(db, "mini", dress_length="미니")           # 미니 → 탈락
    _insert(db, "bra", top_category="브라탑")          # 브라탑 → 탈락
    _insert(db, "midi", bottom_length="미디")          # (v2) 미디 하의 → 탈락
    _insert(db, "knee", dress_length="니렝스")         # (v2) 니렝스 원피스 → 탈락
    _insert(db, "maxi", bottom_length="맥시")          # 맥시 하의 → 통과
    db.commit()
    assert _kept(db, "겨울") == {"ok", "maxi"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_season.py::test_winter_excludes_cool_sleeveless_mini_bratop -v`
Expected: FAIL (`midi`·`knee` 가 아직 통과해 `_kept` 집합에 포함됨)

- [ ] **Step 3: `season.py` 겨울 기장 조건 교체**

`season_where` 의 `elif season == "겨울":` 블록에서 아래 두 줄을 찾아:

```python
        add(_ne("bottom_length", "미니"))
        add(_ne("dress_length", "미니"))
```

다음으로 교체:

```python
        add(_not_in("bottom_length", ("미니", "미디", "니렝스")))
        add(_not_in("dress_length", ("미니", "미디", "니렝스")))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_season.py -v`
Expected: PASS (겨울 테스트 + 기존 여름/봄가을/미지원 테스트 전부)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/season.py tests/test_season.py
git commit -m "feat(season): winter allows only 발목/맥시 bottoms/dresses"
```

---

## Task 2: 완성 플래그 컬럼 (schema.py)

**Files:**
- Modify: `src/playmcp_server/db/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `outfits` 테이블에 `is_complete INTEGER`(nullable) 컬럼.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_schema.py` 에 추가:

```python
def test_schema_has_is_complete_column() -> None:
    import sqlite3

    from playmcp_server.db import schema

    conn = sqlite3.connect(":memory:")
    schema.init_schema(conn)
    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(outfits)")}
    assert "is_complete" in cols
    assert cols["is_complete"] == "INTEGER"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_schema.py::test_schema_has_is_complete_column -v`
Expected: FAIL (`assert "is_complete" in cols`)

- [ ] **Step 3: `schema.py` 에 컬럼 추가**

`SCHEMA` 문자열에서 원피스 컬럼 줄 바로 뒤(`dress_material  TEXT, dress_warmth  TEXT,` 다음 줄)에 추가:

```python
    dress_material  TEXT, dress_warmth  TEXT,

    is_complete INTEGER,   -- 완성 코디 여부(1/0). 원피스 有 or (상의 有 AND 하의 有)
```

(기존 `created_at TEXT, ...` 줄은 그대로 이어진다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (기존 스키마 테스트 + 신규)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/schema.py tests/test_schema.py
git commit -m "feat(schema): add is_complete column to outfits"
```

---

## Task 3: 완성 여부 적재 (build_db.py)

**Files:**
- Modify: `src/playmcp_server/db/build_db.py`
- Test: `tests/test_build_db.py`

**Interfaces:**
- Consumes: `parse_outfit` 가 이미 채우는 `{part}_category` 키.
- Produces: `parse_outfit(...)` 반환 row 에 `is_complete`(int 1/0) 키. `_INSERT` 가 컬럼 반영.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_build_db.py` 에 추가:

```python
def test_parse_is_complete_top_and_bottom() -> None:
    row = build_db.parse_outfit(_doc(20), now="t")  # 상의+하의 기본
    assert row["is_complete"] == 1


def test_parse_incomplete_top_only() -> None:
    row = build_db.parse_outfit(_doc(21, bottom_cat=None), now="t")  # 상의만
    assert row["is_complete"] == 0


def test_parse_complete_dress_only() -> None:
    # 상·하 없이 원피스만 있어도 완성
    doc = _doc(22, top_cat=None, bottom_cat=None)
    doc["데이터셋 정보"]["데이터셋 상세설명"]["라벨링"]["원피스"] = [
        {"카테고리": "드레스"}
    ]
    row = build_db.parse_outfit(doc, now="t")
    assert row["is_complete"] == 1


def test_build_persists_is_complete(tmp_path) -> None:
    root = tmp_path / "labels"
    _write(root, "모던", 1)                    # 상의+하의 → 완성
    _write(root, "모던", 2, bottom_cat=None)   # 상의만 → 불완전
    dest = tmp_path / "out.db"
    build_db.build(root, dest, url_base="https://b")
    conn = sqlite3.connect(dest)
    got = dict(conn.execute("SELECT id, is_complete FROM outfits").fetchall())
    assert got == {"1": 1, "2": 0}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_build_db.py::test_parse_is_complete_top_and_bottom -v`
Expected: FAIL (`KeyError: 'is_complete'`)

- [ ] **Step 3: `build_db.py` 수정**

(a) `_INSERT` 에 컬럼·플레이스홀더 추가 — `dress_warmth` 뒤, `created_at` 앞에 `is_complete` 삽입:

```python
_INSERT = (
    "INSERT INTO outfits ("
    "id,image_url,style,substyle,"
    "top_category,top_length,top_sleeve,top_material,top_warmth,"
    "bottom_category,bottom_length,bottom_material,bottom_warmth,"
    "outer_category,outer_length,outer_sleeve,outer_material,outer_warmth,"
    "dress_category,dress_length,dress_sleeve,dress_material,dress_warmth,"
    "is_complete,"
    "created_at,updated_at,deleted_at) "
    "VALUES (:id,:image_url,:style,:substyle,"
    ":top_category,:top_length,:top_sleeve,:top_material,:top_warmth,"
    ":bottom_category,:bottom_length,:bottom_material,:bottom_warmth,"
    ":outer_category,:outer_length,:outer_sleeve,:outer_material,:outer_warmth,"
    ":dress_category,:dress_length,:dress_sleeve,:dress_material,:dress_warmth,"
    ":is_complete,"
    ":created_at,:updated_at,NULL)"
)
```

(b) `parse_outfit` 에서 부위 루프가 끝난 뒤, `row["_sig"] = _label_signature(lab)` 바로 앞에 완성 여부 계산 추가:

```python
    # 완성 코디: 원피스 有 or (상의 有 AND 하의 有). 미래 스토리지 정리용으로도 저장.
    row["is_complete"] = int(
        row["dress_category"] is not None
        or (row["top_category"] is not None and row["bottom_category"] is not None)
    )
    # dedupe 키(INSERT 시 무시되는 부가 키). 전체 라벨 기준.
    row["_sig"] = _label_signature(lab)
    return row
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_build_db.py -v`
Expected: PASS (기존 + 신규 4개)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/build_db.py tests/test_build_db.py
git commit -m "feat(build_db): compute and persist is_complete"
```

---

## Task 4: DB 재빌드 (is_complete 채우기)

**Files:**
- Regenerate: `src/playmcp_server/data/clothing.db`
- (코드 변경 없음 — 운영 단계)

**Interfaces:**
- Consumes: Task 2·3. 원천 라벨링 루트 `../014.KFashion/01.데이터/1.Training/라벨링데이터_modify/라벨링데이터` (스타일 폴더들의 부모). URL 베이스는 v1 과 동일해야 이미지 URL 이 안 깨진다.

- [ ] **Step 1: 재빌드 전 전체 테스트·린트**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 전체 PASS + ruff 클린. (이 시점 저장소는 아직 `is_complete` 를 참조하지 않으므로 실 DB 로도 grün)

- [ ] **Step 2: 새 컬럼 포함 재빌드**

프로젝트 루트(`tpo-coach/`)에서:

Run:
```bash
uv run python -m playmcp_server.db.build_db \
  --src "../014.KFashion/01.데이터/1.Training/라벨링데이터_modify/라벨링데이터" \
  --url-base "https://pub-15ec30a1728645b1ae95276a40c698d4.r2.dev"
```
Expected(stderr): `outfits.db 생성: loaded=<N> deduped=<M> skipped=<K> → .../data/clothing.db` (loaded > 0)

- [ ] **Step 3: is_complete 채움·이미지 URL 스팟체크**

Run:
```bash
uv run python -c "
import sqlite3; c=sqlite3.connect('src/playmcp_server/data/clothing.db')
tot,comp = c.execute('SELECT COUNT(*), SUM(is_complete) FROM outfits').fetchone()
print('total',tot,'complete',comp)
print('distinct is_complete', c.execute('SELECT DISTINCT is_complete FROM outfits ORDER BY 1').fetchall())
print('url', c.execute('SELECT image_url FROM outfits LIMIT 1').fetchone())
assert comp and 0 < comp < tot
print('OK')
"
```
Expected: `distinct is_complete` == `[(0,), (1,)]`, complete 가 total 의 대략 절반대(≈56%), image_url 이 `https://pub-...r2.dev/<id>.jpg`, `OK`.

- [ ] **Step 4: 전체 테스트 재확인**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 전체 PASS + ruff 클린.

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/data/clothing.db
git commit -m "chore(data): rebuild clothing.db with is_complete"
```

---

## Task 5: 계절 가중 랜덤 정렬 (season.py season_order_by)

**Files:**
- Modify: `src/playmcp_server/db/season.py`
- Test: `tests/test_season.py`

**Interfaces:**
- Consumes: (없음 — 순수 SQL 조각 생성기)
- Produces:
  - `_SOFT_BIAS: float = 0.85`.
  - `season_order_by(season: str) -> tuple[str, list[float]]` — 계절 정렬키 식과 params. 여름/겨울은 `("<식> − ? × (<점수>)", [_SOFT_BIAS])`, 그 외(봄가을·None·미지원)는 `("", [])`.
  - 내부 헬퍼 `_summer_score() -> str`, `_winter_score() -> str` (SQL CASE 문자열, 파라미터 없음).

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_season.py` 에 추가(파일 상단 import 에 `season_order_by` 등 추가):

```python
from playmcp_server.db.season import (
    SEASONS,
    season_order_by,
    season_where,
    _summer_score,
    _winter_score,
)


def _score(db, expr, **cols):
    keys = ["id", "image_url", "style", *cols.keys()]
    ph = ",".join("?" * len(keys))
    db.execute(
        f"INSERT INTO outfits ({','.join(keys)}) VALUES ({ph})",
        ["s", "u/s", "모던", *cols.values()],
    )
    val = db.execute(f"SELECT {expr} FROM outfits WHERE id='s'").fetchone()[0]
    db.execute("DELETE FROM outfits WHERE id='s'")
    return val


def test_summer_score_values(db) -> None:
    e = _summer_score()
    assert _score(db, e, top_sleeve="반팔") == 1.0
    assert _score(db, e, top_sleeve="민소매") == 1.0
    assert _score(db, e, top_sleeve="캡") == 1.0
    assert _score(db, e, top_sleeve="긴팔") == 0.0
    assert _score(db, e, top_sleeve=None) == 0.0


def test_winter_score_values(db) -> None:
    e = _winter_score()
    assert _score(db, e, top_length="롱") == 1.0
    assert _score(db, e, top_length="노멀") == 0.5
    assert _score(db, e, outer_length="롱", top_length="노멀") == 1.0  # MAX
    assert _score(db, e, top_length="크롭") == 0.0
    assert _score(db, e) == 0.0


def test_order_by_only_summer_winter() -> None:
    assert season_order_by("봄가을") == ("", [])
    assert season_order_by("없는계절") == ("", [])
    sql, params = season_order_by("여름")
    assert params == [0.85] and "?" in sql
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_season.py::test_summer_score_values -v`
Expected: FAIL (`ImportError: cannot import name '_summer_score'`)

- [ ] **Step 3: `season.py` 에 정렬 로직 추가**

`season.py` 끝(파일 하단, `season_where` 뒤)에 추가:

```python
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
    """계절 → (ORDER BY 키 식, params). 여름/겨울만 가중, 그 외는 ('', [])(순수 랜덤)."""
    if season == "여름":
        score = _summer_score()
    elif season == "겨울":
        score = _winter_score()
    else:
        return "", []
    return f"{_RAND01} - ? * ({score})", [_SOFT_BIAS]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_season.py -v`
Expected: PASS (신규 3개 + 기존 전부)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/season.py tests/test_season.py
git commit -m "feat(season): weighted-random soft preference (season_order_by)"
```

---

## Task 6: 저장소 결선 — 완성 필터 + 가중 정렬 (repository.py)

**Files:**
- Modify: `src/playmcp_server/db/repository.py`
- Test: `tests/test_repository.py`

**Interfaces:**
- Consumes: `season.season_where`, `season.season_order_by`.
- Produces: `SQLiteOutfitRepository.sample_outfits(*, style, n, season=None)` 가 (1) 기본 WHERE 에 완성 필터 `(is_complete IS NULL OR is_complete = 1)` 를 항상 적용하고, (2) `ORDER BY` 를 `season_order_by` 결과(있으면)로, 없으면 `RANDOM()` 으로 조립. 최종 params 순서 `[style, <season_where params>, <season_order_by param>, n]`.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_repository.py` 에 추가(`_repo_with` 헬퍼는 기존 것 재사용):

```python
def test_sample_excludes_incomplete() -> None:
    repo = _repo_with([
        {"_id": "keep", "is_complete": 1},
        {"_id": "null_ok"},                 # is_complete 미지정(NULL) → 통과
        {"_id": "drop", "is_complete": 0},  # 불완전 → 제외
    ])
    got = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert got == {"keep", "null_ok"}


def test_summer_prefers_short_sleeve_strongly() -> None:
    # 반팔(선호)·긴팔(비선호) 각 20건, 모두 완성. n=1 을 여러 번 뽑아 반팔이 지배적인지.
    rows = []
    for i in range(20):
        rows.append({"_id": f"s{i}", "top_sleeve": "반팔", "is_complete": 1})
        rows.append({"_id": f"l{i}", "top_sleeve": "긴팔", "is_complete": 1})
    repo = _repo_with(rows)
    short = sum(
        1
        for _ in range(100)
        if repo.sample_outfits(style="모던", n=1, season="여름")[0].top_sleeve
        == "반팔"
    )
    assert short >= 80, f"반팔 선택 {short}/100 — 편향 약함"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_repository.py::test_sample_excludes_incomplete -v`
Expected: FAIL (`drop` 이 아직 결과에 포함됨 — 완성 필터 없음)

- [ ] **Step 3: `repository.py` 의 `sample_outfits` 교체**

(a) import 에 `season_order_by` 추가 — 기존 `from playmcp_server.db.season import season_where` 를 아래로:

```python
from playmcp_server.db.season import season_order_by, season_where
```

(b) `SQLiteOutfitRepository.sample_outfits` 를 아래로 교체:

```python
    def sample_outfits(
        self, *, style: str, n: int, season: str | None = None
    ) -> list[Outfit]:
        # 완성 코디만 추천(항상). NULL 은 통과 — 실 DB 는 0/1, 테스트 편의.
        where = (
            "style = ? AND deleted_at IS NULL "
            "AND (is_complete IS NULL OR is_complete = 1)"
        )
        params: list[object] = [style]
        order = "RANDOM()"
        if season:
            frag, sp = season_where(season)
            if frag:
                where += " AND " + frag
                params.extend(sp)
            order_expr, op = season_order_by(season)
            if order_expr:
                order = order_expr
                params.extend(op)
        # SQLite 는 음수 LIMIT 을 "무제한"으로 취급 → 방어적 클램프.
        params.append(max(0, n))
        rows = self._conn.execute(
            f"SELECT * FROM outfits WHERE {where} ORDER BY {order} LIMIT ?",
            params,
        )
        return [_outfit(r) for r in rows]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (신규 2개 + 기존 전부). 이어서 전체:

Run: `uv run pytest -q && uv run ruff check .`
Expected: 전체 PASS(실 DB perf 테스트 포함 — Task 4 재빌드로 `is_complete` 존재) + ruff 클린.

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(repository): completeness filter + weighted season ordering"
```

---

## Self-Review

**Spec coverage (docs/idea/weather_role.md v2):**
- §4 겨울 기장(발목/맥시만) → Task 1(`_not_in` 미니·미디·니렝스) + 테스트. ✅
- §2·§7 `is_complete` 컬럼·정의·보존 → Task 2(schema)·Task 3(build 계산·적재)·Task 4(재빌드). 보존: 불완전 행 삭제 안 함(빌드는 그대로 적재, 필터는 쿼리시점). ✅
- §7 완성 필터 항상 적용 → Task 6(`is_complete IS NULL OR = 1` 기본 WHERE). ✅
- §8 소프트 선호(가중 랜덤, bias 0.85, 여름 소매·겨울 기장 MAX, 봄가을/None 순수 랜덤) → Task 5(`season_order_by`) + Task 6(ORDER BY 조립). ✅
- §8 소재 선호 제외 → 계획에 소재 선호 없음. ✅
- §9 코드 배치 → Task 1·2·3·5·6 파일 매핑 일치. ✅

**Placeholder scan:** 모든 코드 스텝에 실제 코드 포함, TODO/TBD 없음. ✅

**Type consistency:**
- `season_order_by(str) -> tuple[str, list[float]]`(Task 5) ↔ repository 언팩 `order_expr, op`(Task 6) 일치.
- `_summer_score()/_winter_score() -> str`(Task 5) — 파라미터 없는 SQL, `season_order_by` 가 `? × (score)` 로 감싸 bias 파라미터 1개만 추가 → params 순서 `[style, where.., bias, n]`(Task 6) 일치.
- 완성 정의 문자열 SQL `(is_complete IS NULL OR is_complete = 1)`(Task 6) ↔ 컬럼명 `is_complete`(Task 2)·빌드 키 `is_complete`(Task 3) 동일.
- 겨울 기장 `_not_in("bottom_length"/"dress_length", ("미니","미디","니렝스"))`(Task 1) ↔ 기존 `_not_in` 시그니처 일치.
- Task 6 perf test 그린 전제: Task 4 재빌드가 Task 6 앞에 위치 → 실 DB 에 `is_complete` 존재. 순서 보장됨. ✅
