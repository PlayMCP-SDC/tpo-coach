# 상황 추천 다중 스타일(태그) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `recommend_outfits_by_situation` 을 단일 `style` → `styles: list[str]` 로 바꿔, N개 추천을 여러 스타일에 라운드로빈 분산해 서로 다른 스타일의 코디로 다양화한다.

**Architecture:** `tools/recommend.py` 국소 변경. 순수 헬퍼(정규화·인터리브·안내)를 추가하고 공유 코어 `_recommend` 를 `styles: list[str]` 로 일반화한다. `by_style` 은 `_recommend([style], …)` 로 감싸 기존 동작을 보존한다. 저장소는 기존 `sample_outfits` 를 스타일별로 재사용(변경 없음). 23종 통제 어휘는 프롬프트 설명·런타임 필터·스키마 enum 3중으로 제약한다.

**Tech Stack:** Python 3.10+, uv, mcp[cli] FastMCP, pydantic, SQLite, pytest(in-memory transport), ruff.

## Global Constraints

출처: spec `docs/superpowers/specs/2026-07-01-multi-style-situation-recommend-design.md` + `CLAUDE.md`. 모든 태스크에 암묵 적용.

- 실행/테스트는 **uv**: `uv run pytest`, `uv run ruff check .` 통과.
- **stdout(print) 금지** — 로그는 stderr/logging.
- 모든 도구에 **`annotations` 5종**; 추천 도구는 `readOnlyHint=True`·`destructiveHint=False`·`openWorldHint=False`·**`idempotentHint=False`**.
- 도구 `description`(docstring 첫 줄): **"TPO Coach" 포함**, 영문, ≤1024자. 도구 이름: `A-Za-z0-9_-`만, `kakao` 금지.
- `n`: **1~10, 기본 3**, 클램프.
- 스타일 통제 어휘 단일 출처 **`playmcp_server.db.vocab.STYLES`(23종)**.
- **다중 태그는 `recommend_outfits_by_situation` 에만.** `recommend_outfits_by_style(style, n)` 시그니처·동작 불변.
- **분배:** 유효 스타일마다 무작위 표본 → 라운드로빈 인터리브 → 앞에서 n개(짧은 풀은 백필).
- **무효 스타일:** 걸러내고 진행. 유효 0개면 유효 목록 안내.
- **23종 강력 제약 불변식:** 파라미터 타입은 `list[str]` 유지(하드 리젝트 금지) + 스키마에 23종 enum 광고 + 런타임 필터. 광고 수단은 이 불변식을 만족하면 무엇이든 가능.

---

### Task 1: 순수 헬퍼 추가(정규화·인터리브·안내) — 가산

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py` (헬퍼·상수 추가, 기존 것 유지)
- Test: `tests/test_recommend.py` (순수 단위 테스트 추가)

**Interfaces:**
- Consumes: `playmcp_server.db.vocab.STYLES`, `playmcp_server.models.Outfit`.
- Produces:
  - `_STYLE_LIST: list[str]` = `sorted(STYLES)` (23종, 설명·스키마·안내 공용 단일 출처).
  - `_normalize_styles(styles: list[str]) -> list[str]` — 중복 제거(순서 보존) + STYLES 유효 필터.
  - `_no_valid_styles_msg(styles: list[str]) -> str` — 유효 0개 안내(입력 echo + 유효 목록).
  - `_interleave(pools: list[list[Outfit]]) -> list[Outfit]` — 라운드로빈 인터리브(None 제외).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_recommend.py` 의 기존 순수 테스트 아래에 추가

```python
from playmcp_server.tools.recommend import (
    _interleave,
    _no_valid_styles_msg,
    _normalize_styles,
)


def test_normalize_styles_dedup_order_filter() -> None:
    assert _normalize_styles(["모던", "모던", "없는거", "로맨틱"]) == ["모던", "로맨틱"]


def test_normalize_styles_all_invalid_empty() -> None:
    assert _normalize_styles(["xx", "yy"]) == []


def test_no_valid_styles_msg_echoes_and_lists() -> None:
    msg = _no_valid_styles_msg(["xx"])
    assert "xx" in msg
    assert "스트리트" in msg and "클래식" in msg


def _mk(oid: str, style: str) -> Outfit:
    return Outfit(id=oid, image_url=f"u/{oid}", style=style)


def test_interleave_round_robin() -> None:
    a = [_mk("a0", "모던"), _mk("a1", "모던"), _mk("a2", "모던")]
    b = [_mk("b0", "로맨틱"), _mk("b1", "로맨틱")]
    assert [o.id for o in _interleave([a, b])] == ["a0", "b0", "a1", "b1", "a2"]


def test_interleave_skips_empty_pool() -> None:
    a = [_mk("a0", "모던")]
    assert [o.id for o in _interleave([[], a])] == ["a0"]
```

> 참고: `Outfit` 은 파일 상단에서 이미 import 되어 있다(`from playmcp_server.models import Outfit`). 없으면 추가.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_recommend.py -k "normalize or interleave or no_valid" -v`
Expected: FAIL — `ImportError: cannot import name '_normalize_styles' ...`

- [ ] **Step 3: 헬퍼 구현** — `recommend.py` 상단 import 에 `zip_longest` 추가하고, `_invalid_style_msg` 정의 아래에 헬퍼 추가

`from __future__ import annotations` 아래 import 블록에 추가:
```python
from itertools import zip_longest
```

`_N_DEFAULT = 3` 아래(또는 `_invalid_style_msg` 아래)에 추가:
```python
_STYLE_LIST = sorted(STYLES)  # 23종 — 설명·스키마·안내 공용 단일 출처


def _normalize_styles(styles: list[str]) -> list[str]:
    """중복 제거(순서 보존) 후 STYLES 에 있는 유효 스타일만 남긴다."""
    seen: set[str] = set()
    out: list[str] = []
    for s in styles:
        if s in STYLES and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _no_valid_styles_msg(styles: list[str]) -> str:
    """유효 스타일이 하나도 없을 때 안내(입력 echo + 유효 목록)."""
    shown = ", ".join(styles) if styles else "(없음)"
    return (
        f"지원하는 스타일이 없습니다 (입력: {shown}). "
        f"가능한 스타일: {', '.join(_STYLE_LIST)}"
    )


def _interleave(pools: list[list[Outfit]]) -> list[Outfit]:
    """스타일별 풀을 라운드로빈으로 인터리브한다(각 풀 1개씩 우선, None 제외)."""
    return [o for group in zip_longest(*pools) for o in group if o is not None]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_recommend.py -k "normalize or interleave or no_valid" -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `uv run pytest -q && uv run ruff check .`
Expected: 전체 PASS, ruff clean (기존 `_invalid_style_msg` 는 아직 살아있어 회귀 없음)

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "feat(tools): 다중 스타일 순수 헬퍼(정규화·인터리브·안내)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 공유 코어 `_recommend` 를 styles 리스트로 일반화 + by_style 재배선

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py` (`_recommend` 재작성, `by_style` 호출부, `_invalid_style_msg` 제거)
- Test: `tests/test_recommend.py` (구 `_invalid_style_msg` 테스트 제거, `_recommend` 다중 스타일 테스트 추가)

**Interfaces:**
- Consumes: Task 1 `_normalize_styles`/`_no_valid_styles_msg`/`_interleave`, 기존 `_clamp_n`/`_format_outfit`, `get_repository().sample_outfits(style=..., n=...)`, 기존 `small_db` 픽스처(로맨틱 a·b, 스트리트 c).
- Produces:
  - `_recommend(styles: list[str], n: int, header: str | None) -> str` — 정규화→스타일별 표본→인터리브→렌더. 유효 0개면 안내.
  - `recommend_outfits_by_style` 은 `_recommend([style], n, header)` 로 위임(시그니처·출력 불변).
  - `_invalid_style_msg` 제거(더 이상 사용 안 함).

- [ ] **Step 1: 실패/갱신 테스트 작성**

(a) 기존 순수 테스트 `test_invalid_style_msg_lists_valid_styles` 와 그 함수 import 를 **삭제**한다(Task 2 에서 `_invalid_style_msg` 가 사라짐).

(b) `tests/test_recommend.py` 의 통합 테스트 구역(기존 `small_db` 픽스처 아래)에 `_recommend` 직접 테스트 추가:
```python
def test_recommend_two_styles_distributes(small_db) -> None:
    # small_db: 로맨틱 a·b(2건) + 스트리트 c(1건)
    out = _recommend(["로맨틱", "스트리트"], 3, header=None)
    assert out.count("![코디]") == 3           # 총 3개
    assert "https://img/c.jpg" in out          # 스트리트도 포함(단일이면 안 나옴)


def test_recommend_all_invalid_returns_guidance(small_db) -> None:
    out = _recommend(["xx", "yy"], 3, header=None)
    assert "지원하는 스타일이 없습니다" in out
    assert "스트리트" in out
```

`_recommend` 를 파일 상단 import 에 추가한다(없으면):
```python
from playmcp_server.tools.recommend import _recommend
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_recommend.py -k "two_styles or all_invalid" -v`
Expected: FAIL — 현재 `_recommend(style: str, …)` 는 리스트를 받으면 `["로맨틱","스트리트"] not in STYLES` 로 안내 문자열을 반환 → `count("![코디]")==3` 실패.

- [ ] **Step 3: `_recommend` 재작성 + by_style 재배선 + 죽은 코드 제거**

`_recommend` 전체를 아래로 교체:
```python
def _recommend(styles: list[str], n: int, header: str | None) -> str:
    """styles 정규화 → 스타일별 무작위 표본 → 라운드로빈 → 마크다운.

    유효 스타일이 하나도 없으면 안내 문자열을 돌려준다(추천 안 함).
    header 가 있으면 결과 맨 위에 붙인다.
    """
    valid = _normalize_styles(styles)
    if not valid:
        return _no_valid_styles_msg(styles)
    k = _clamp_n(n)
    repo = get_repository()
    pools = [repo.sample_outfits(style=s, n=k) for s in valid]
    outfits = _interleave(pools)[:k]
    if not outfits:
        return "해당 스타일의 코디를 찾지 못했습니다. 다른 스타일로 시도해 보세요."
    body = "\n\n".join(_format_outfit(o) for o in outfits)
    return f"{header}\n\n{body}" if header else body
```

`recommend_outfits_by_style` 의 마지막 줄을 교체:
```python
        return _recommend([style], n, header=f"**{style}** 스타일 코디 추천")
```

`_invalid_style_msg` 함수 정의(및 그 docstring)를 **삭제**한다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: PASS. 기존 `test_by_style_returns_only_that_style`·`test_by_style_invalid_style_lists_options` 도 여전히 통과해야 한다(무효 단일 스타일 → `_no_valid_styles_msg(["없는스타일"])` 이 "없는스타일" 과 "스트리트" 를 포함).

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `uv run ruff check . && uv run pytest -q`
Expected: ruff clean(미사용 import 없음 — `_invalid_style_msg` 제거로 dangling 없음), 전체 PASS

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "refactor(tools): _recommend 를 styles 리스트로 일반화 + by_style 위임

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 상황 도구 다중 스타일 + 23종 프롬프트 제약 + 머리말

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py` (`recommend_outfits_by_situation` 시그니처·docstring·머리말; import 추가)
- Test: `tests/test_recommend.py` (구 상황 테스트 갱신 + 다중 스타일 통합 + 설명 동기화)

**Interfaces:**
- Consumes: Task 2 `_recommend`, Task 1 `_normalize_styles`/`_STYLE_LIST`, `STYLES`, `client_session`·`small_db` 픽스처, `pydantic.Field`, `typing.Annotated`.
- Produces:
  - `recommend_outfits_by_situation(situation: str, styles: list[str], n: int = _N_DEFAULT) -> str`
    — `styles` 는 `Annotated[list[str], Field(description=…23종 명시…)]`. 머리말에 상황 + 사용된 스타일.

- [ ] **Step 1: 실패/갱신 테스트 작성**

(a) 기존 `test_by_situation_echoes_situation_and_style` 을 **아래로 교체**(파라미터가 `style`→`styles` 로 바뀜):
```python
@pytest.mark.asyncio
async def test_by_situation_multi_style_distributes(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "주말 소개팅", "styles": ["로맨틱", "스트리트"], "n": 3},
        )
    text = res.content[0].text
    assert "주말 소개팅" in text          # 상황 echo
    assert "로맨틱" in text and "스트리트" in text  # 사용 스타일 표기 + 코디 다양성
    assert text.count("![코디]") == 3
```

(b) 무효 필터 + 전부 무효 + 설명 동기화 테스트 추가:
```python
@pytest.mark.asyncio
async def test_by_situation_filters_invalid_styles(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "여행", "styles": ["로맨틱", "없는거"], "n": 3},
        )
    text = res.content[0].text
    assert "지원하는 스타일이 없습니다" not in text  # 유효분(로맨틱)으로 진행
    assert "![코디]" in text


@pytest.mark.asyncio
async def test_by_situation_all_invalid_guides(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "여행", "styles": ["xx", "yy"]},
        )
    text = res.content[0].text
    assert "지원하는 스타일이 없습니다" in text and "스트리트" in text


@pytest.mark.asyncio
async def test_by_situation_description_lists_all_styles(client_session) -> None:
    async with client_session() as client:
        tools = (await client.list_tools()).tools
    tool = next(t for t in tools if t.name == "recommend_outfits_by_situation")
    desc = tool.inputSchema["properties"]["styles"].get("description", "")
    for s in STYLES:
        assert s in desc, f"styles 설명에 '{s}' 누락"
```

> `STYLES` 를 테스트 파일 상단 import 에 추가한다(없으면): `from playmcp_server.db.vocab import STYLES`.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_recommend.py -k "by_situation" -v`
Expected: FAIL — 현재 상황 도구는 `style: str` 라 `styles` 인자를 모른다(호출 오류/검증 실패), 설명에 23종 없음.

- [ ] **Step 3: 상황 도구 구현**

`recommend.py` 상단 import 에 추가:
```python
from typing import Annotated

from pydantic import Field
```

`recommend_outfits_by_situation` 정의를 아래로 교체(annotations 데코레이터는 그대로 유지):
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
            ),
        ],
        n: int = _N_DEFAULT,
    ) -> str:
        """Recommends varied outfit sets (코디) for a situation for TPO Coach(티피오 코치).

        Given a free-text situation, infer the Korean styles that fit it (ordered by
        best fit) and pass them as `styles`, choosing ONLY from the supported styles
        listed in the `styles` parameter. The tool samples random outfits across those
        styles (round-robin) so the results span different styles. The situation and the
        styles used are echoed in the heading. Unsupported styles are ignored; if none
        are valid, the valid style list is returned.

        Args:
            situation: User's situation in free text (e.g. "주말 소개팅"). Echoed only.
            styles: Supported styles fitting the situation, best fit first (1개 이상).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.

        Returns:
            Markdown: situation/styles heading + recommended outfits across styles.
        """
        used = _normalize_styles(styles)
        label = " · ".join(used)
        header = f"**{situation}**에 어울리는 코디 추천" + (f" ({label})" if label else "")
        return _recommend(styles, n, header=header)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: PASS(전부). 특히 `by_situation` 4종 + 기존 `test_tools_listed_with_honest_annotations`(annotations 불변) 통과.

- [ ] **Step 5: 전체 회귀 + 커밋**

Run: `uv run ruff check . && uv run pytest -q`
Expected: ruff clean, 전체 PASS

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "feat(tools): 상황 추천 다중 스타일 + 23종 프롬프트 제약 + 사용 스타일 머리말

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 스키마 enum 광고(기계 제약) + 동기화 테스트

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py` (`styles` Field 에 `json_schema_extra`)
- Test: `tests/test_recommend.py` (inputSchema enum 동기화 테스트)

**Interfaces:**
- Consumes: Task 3 의 `styles` Annotated Field, `_STYLE_LIST`/`STYLES`, `client_session`.
- Produces: 상황 도구 inputSchema 의 `properties.styles.items.enum` == 23종. **타입은 `list[str]` 유지**(Pydantic 하드 리젝트 없음).

- [ ] **Step 1: 실패하는 스키마 테스트 작성**

```python
@pytest.mark.asyncio
async def test_by_situation_schema_advertises_style_enum(client_session) -> None:
    async with client_session() as client:
        tools = (await client.list_tools()).tools
    tool = next(t for t in tools if t.name == "recommend_outfits_by_situation")
    items = tool.inputSchema["properties"]["styles"]["items"]
    assert set(items.get("enum", [])) == set(STYLES)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_recommend.py -k schema_advertises -v`
Expected: FAIL — 아직 items 에 enum 광고 없음(`enum` 키 부재).

- [ ] **Step 3: `json_schema_extra` 로 items enum 광고**

Task 3 의 `styles` Field 에 `json_schema_extra` 를 추가(description 은 그대로):
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_recommend.py -k schema_advertises -v`
Expected: PASS — inputSchema.properties.styles.items.enum == 23종.

> **폴백(Step 4 가 FAIL 로 못 맞출 때만):** 이 FastMCP/Pydantic 버전이 `json_schema_extra` 를 items 로
> 병합하지 못하면(생성 스키마 구조가 다르면), `json_schema_extra` 를 제거하고 이 `schema_advertises`
> 테스트도 제거한다. 강력 제약은 Task 3 의 설명(레이어 2)과 런타임 필터(레이어 3)로 이미 보장되므로
> 정합성에 문제 없다. 폴백을 쓰면 이 사실을 커밋 메시지에 남긴다.

- [ ] **Step 5: 불변식 회귀 확인 + 커밋**

Run: `uv run pytest tests/test_recommend.py -k "by_situation" -v && uv run ruff check . && uv run pytest -q`
Expected: 전부 PASS. 특히 `test_by_situation_filters_invalid_styles`·`test_by_situation_all_invalid_guides` 가 통과 = enum 광고가 Pydantic 하드 리젝트를 유발하지 않고(타입 `list[str]` 유지) 무효값이 런타임 필터로 흘러감을 확인.

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "feat(tools): 상황 styles 스키마에 23종 enum 광고(기계 제약)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** — spec 각 결정의 구현 위치:
- 다중 태그 상황 도구만 → Task 3(시그니처), by_style 불변 → Task 2(위임, 회귀 테스트).
- 라운드로빈+백필 분배 → Task 1(`_interleave`) + Task 2(`_recommend` pools/interleave).
- 무효 필터, 유효 0개 안내 → Task 1(`_normalize_styles`/`_no_valid_styles_msg`) + Task 2/3 테스트.
- 23종 3중 제약: 스키마 enum → Task 4, 프롬프트 설명 → Task 3, 런타임 필터 → Task 2. 동기화 테스트 → Task 3(설명)·Task 4(스키마).
- 타입 `list[str]` 유지(하드 리젝트 금지) 불변식 → Task 4 Step 5 회귀로 검증.
- 머리말에 상황+사용 스타일 → Task 3.
- 저장소 불변 → 전 태스크에서 `sample_outfits` 재사용, 스키마/저장소 미변경.

**2. Placeholder scan** — "TBD"/"적절히" 없음. 모든 코드 스텝에 실제 코드. Task 4 폴백은 조건부 대안(placeholder 아님, 구체 지시). ✅

**3. Type consistency** — `_recommend(styles: list[str], n, header)`(Task 2)와 호출부 `_recommend([style], …)`(Task 2 by_style)·`_recommend(styles, n, header)`(Task 3) 일치. `_normalize_styles`/`_interleave`/`_no_valid_styles_msg`/`_STYLE_LIST` 정의(Task 1)와 사용(Task 2·3) 일치. `styles` 파라미터명이 Task 3·4·테스트에서 동일. ✅
