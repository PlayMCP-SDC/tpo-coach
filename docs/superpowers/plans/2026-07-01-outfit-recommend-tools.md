# 셋업(코디) 추천 도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스타일/상황을 받아 K-Fashion 셋업 DB에서 무작위 N건(기본 3)을 추천하는 MCP 도구 2개를 추가한다.

**Architecture:** 저장소에 무작위 표본 메서드 `sample_outfits`를 더하고, `tools/recommend.py`에 얇은 도구 2개(`recommend_outfits_by_style`·`recommend_outfits_by_situation`)를 둔다. 둘 다 `style`로 조회하며, 상황→스타일 매핑은 docstring으로 호출 LLM에 위임한다. 출력은 이미지 URL 마크다운.

**Tech Stack:** Python 3.10+, uv, mcp[cli] FastMCP, SQLite(sqlite3), pytest(in-memory transport), ruff.

## Global Constraints

이 절은 모든 태스크의 요구사항에 암묵적으로 포함된다. 출처: 설계 spec(`docs/superpowers/specs/2026-07-01-outfit-recommend-tools-design.md`) + `CLAUDE.md`.

- 실행/테스트는 **uv** 사용: `uv run pytest`, `uv run ruff check .`.
- **stdout(print) 금지** — 로그는 `sys.stderr`/`logging`만.
- 모든 도구는 **타입 힌트 + docstring** 작성(FastMCP 스키마 자동 생성).
- 모든 도구에 **`annotations` 5종 전부**: `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint`, `idempotentHint`.
- 추천 도구 annotations 고정값: `readOnlyHint=True`, `destructiveHint=False`, `openWorldHint=False`, **`idempotentHint=False`**(랜덤 표본).
- 도구 이름: `A-Za-z0-9_-`만, **`kakao` 금지**, 중복 금지, 1~128자.
- `description`(docstring 첫 줄): **"TPO Coach" 포함**, 1,024자 이내, 영문 권장.
- 도구 총수 ≤ 20(현재 `extract_color` + 신규 2 = 3개).
- 응답속도 평균 100ms / p99 3,000ms 이내.
- 추천 개수 `n`: 범위 **1~10, 기본 3**(범위 밖은 클램프).
- 스타일 통제 어휘 단일 출처: `playmcp_server.db.vocab.STYLES`(23종). 무효 스타일은 추천 대신 유효 목록 안내.
- 작업 종료 시 `uv run ruff check .`·`uv run pytest` 통과.

---

### Task 1: 저장소 `sample_outfits` 무작위 표본 메서드

**Files:**
- Modify: `src/playmcp_server/db/repository.py` (Protocol `OutfitRepository` + `SQLiteOutfitRepository`)
- Test: `tests/test_repository.py` (기존 `repo` 픽스처 재사용)

**Interfaces:**
- Consumes: `playmcp_server.models.Outfit`, 기존 `repo` 픽스처(스타일 "모던" 2건 활성 + 1건 soft-deleted, "스트리트" 1건).
- Produces: `SQLiteOutfitRepository.sample_outfits(self, *, style: str, n: int) -> list[Outfit]` — 해당 style 의 활성(`deleted_at IS NULL`) 행을 무작위 순서로 최대 n건 반환. Protocol 에도 동일 시그니처 추가.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_repository.py` 끝에 추가

```python
def test_sample_outfits_only_style_and_active(repo: SQLiteOutfitRepository) -> None:
    # "모던" 활성은 o1, o3 (o4 는 soft-deleted 라 제외)
    ids = {o.id for o in repo.sample_outfits(style="모던", n=10)}
    assert ids == {"o1", "o3"}


def test_sample_outfits_respects_n(repo: SQLiteOutfitRepository) -> None:
    assert len(repo.sample_outfits(style="모던", n=1)) == 1


def test_sample_outfits_unknown_style_empty(repo: SQLiteOutfitRepository) -> None:
    assert repo.sample_outfits(style="없는스타일", n=3) == []


def test_sample_outfits_returns_outfit_objects(repo: SQLiteOutfitRepository) -> None:
    out = repo.sample_outfits(style="스트리트", n=3)
    assert len(out) == 1
    assert out[0].id == "o2"
    assert out[0].bottom_category == "청바지"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_repository.py -k sample_outfits -v`
Expected: FAIL — `AttributeError: 'SQLiteOutfitRepository' object has no attribute 'sample_outfits'`

- [ ] **Step 3: Protocol 에 시그니처 추가** — `repository.py` 의 `class OutfitRepository` 안, `find_outfits` 선언 아래

```python
    def sample_outfits(self, *, style: str, n: int) -> list[Outfit]: ...
```

- [ ] **Step 4: 구현 추가** — `class SQLiteOutfitRepository` 안, `find_outfits` 메서드 아래

```python
    def sample_outfits(self, *, style: str, n: int) -> list[Outfit]:
        rows = self._conn.execute(
            "SELECT * FROM outfits "
            "WHERE style = ? AND deleted_at IS NULL "
            "ORDER BY RANDOM() LIMIT ?",
            (style, n),
        )
        return [_outfit(r) for r in rows]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_repository.py -k sample_outfits -v`
Expected: PASS (4 passed)

- [ ] **Step 6: 커밋**

```bash
git add src/playmcp_server/db/repository.py tests/test_repository.py
git commit -m "feat(db): 스타일별 무작위 표본 조회 sample_outfits

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: 추천 모듈 순수 헬퍼(클램프·무효안내·셋업 포맷)

**Files:**
- Create: `src/playmcp_server/tools/recommend.py`
- Test: `tests/test_recommend.py`

**Interfaces:**
- Consumes: `playmcp_server.models.Outfit`, `playmcp_server.db.vocab.STYLES`.
- Produces (모듈 상수·함수):
  - `_N_MIN = 1`, `_N_MAX = 10`, `_N_DEFAULT = 3`
  - `_clamp_n(n: int) -> int`
  - `_invalid_style_msg(style: str) -> str` — 무효 스타일 안내(유효 목록 포함).
  - `_format_outfit(o: Outfit) -> str` — 셋업 1건을 이미지 URL 마크다운 블록으로.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_recommend.py` 신규

```python
"""셋업 추천 도구 — 순수 헬퍼 + 도구 동작 검증."""

from playmcp_server.db.vocab import STYLES
from playmcp_server.models import Outfit
from playmcp_server.tools.recommend import (
    _clamp_n,
    _format_outfit,
    _invalid_style_msg,
)


def test_clamp_n_bounds() -> None:
    assert _clamp_n(0) == 1
    assert _clamp_n(1) == 1
    assert _clamp_n(3) == 3
    assert _clamp_n(10) == 10
    assert _clamp_n(999) == 10


def test_invalid_style_msg_lists_valid_styles() -> None:
    msg = _invalid_style_msg("없는스타일")
    assert "없는스타일" in msg
    # 유효 스타일 목록을 안내한다
    assert "클래식" in msg and "스트리트" in msg


def test_format_outfit_has_image_and_parts() -> None:
    o = Outfit(
        id="a",
        image_url="https://img/a.jpg",
        style="로맨틱",
        substyle="페미닌",
        top_category="블라우스",
        top_length="크롭",
        bottom_category="스커트",
        bottom_length="미니",
    )
    block = _format_outfit(o)
    assert "![" in block and "https://img/a.jpg" in block
    assert "로맨틱" in block and "페미닌" in block
    assert "블라우스" in block and "스커트" in block


def test_format_outfit_skips_absent_parts() -> None:
    o = Outfit(id="b", image_url="u/b", style="페미닌", dress_category="드레스")
    block = _format_outfit(o)
    assert "드레스" in block
    assert "상의" not in block and "하의" not in block
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'playmcp_server.tools.recommend'`

- [ ] **Step 3: 순수 헬퍼 구현** — `src/playmcp_server/tools/recommend.py` 신규(이 단계는 헬퍼까지만)

```python
"""셋업(코디) 추천 도구 — 스타일/상황 기반 무작위 N건 추천.

DB 의 K-Fashion 셋업을 style 로 무작위 표본 추출해 이미지 URL 마크다운으로 낸다.
상황→스타일 매핑은 우리가 두지 않고 docstring 으로 호출 LLM 에 위임한다.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from playmcp_server.db.repository import get_repository
from playmcp_server.db.vocab import STYLES
from playmcp_server.models import Outfit

_N_MIN = 1
_N_MAX = 10
_N_DEFAULT = 3


def _clamp_n(n: int) -> int:
    """추천 개수를 [1, 10] 범위로 보정한다."""
    return max(_N_MIN, min(_N_MAX, n))


def _invalid_style_msg(style: str) -> str:
    """무효 스타일 입력에 유효 스타일 목록을 안내한다."""
    return (
        f"'{style}' 은(는) 지원하지 않는 스타일입니다. "
        f"가능한 스타일: {', '.join(sorted(STYLES))}"
    )


def _part(label: str, category: str | None, length: str | None) -> str | None:
    if not category:
        return None
    return f"{label} {category}" + (f"({length})" if length else "")


def _format_outfit(o: Outfit) -> str:
    """셋업 1건을 이미지 URL 마크다운 블록으로 만든다."""
    parts = [
        p
        for p in (
            _part("상의", o.top_category, o.top_length),
            _part("하의", o.bottom_category, o.bottom_length),
            _part("아우터", o.outer_category, o.outer_length),
            _part("원피스", o.dress_category, o.dress_length),
        )
        if p
    ]
    style_line = o.style + (f" / {o.substyle}" if o.substyle else "")
    return "\n".join(
        [
            f"![코디]({o.image_url})",
            f"- 스타일: {style_line}",
            f"- 구성: {' · '.join(parts) if parts else '정보 없음'}",
        ]
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: 커밋**

```bash
git add src/playmcp_server/tools/recommend.py tests/test_recommend.py
git commit -m "feat(tools): 추천 모듈 순수 헬퍼(클램프·무효안내·셋업 포맷)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 추천 도구 2개 + 등록 + 통합 테스트

**Files:**
- Modify: `src/playmcp_server/tools/recommend.py` (`_recommend` 코어 + `register_tools`)
- Modify: `src/playmcp_server/tools/__init__.py` (recommend 등록)
- Test: `tests/test_recommend.py` (도구 통합 테스트 추가)

**Interfaces:**
- Consumes: Task 1 `get_repository().sample_outfits(style=..., n=...)`, Task 2 `_clamp_n`/`_invalid_style_msg`/`_format_outfit`/`STYLES`, conftest `client_session` 픽스처, `playmcp_server.db.repository`(`reset_repository`)·`schema`.
- Produces:
  - `_recommend(style: str, n: int, header: str | None) -> str` — 검증·표본·렌더 오케스트레이션.
  - MCP 도구 `recommend_outfits_by_style(style: str, n: int = 3) -> str`
  - MCP 도구 `recommend_outfits_by_situation(situation: str, style: str, n: int = 3) -> str`
  - `register_tools(mcp: FastMCP) -> None`

- [ ] **Step 1: 실패하는 통합 테스트 작성** — `tests/test_recommend.py` 끝에 추가

```python
import sqlite3

import pytest

from playmcp_server.db import repository, schema


@pytest.fixture
def small_db(tmp_path, monkeypatch):
    """style 로 조회 가능한 작은 read-write 임시 DB 를 싱글턴에 물린다."""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    schema.init_schema(conn)
    conn.executemany(
        "INSERT INTO outfits "
        "(id,image_url,style,substyle,top_category,bottom_category) "
        "VALUES (?,?,?,?,?,?)",
        [
            ("a", "https://img/a.jpg", "로맨틱", "로맨틱", "블라우스", "스커트"),
            ("b", "https://img/b.jpg", "로맨틱", None, "니트웨어", "팬츠"),
            ("c", "https://img/c.jpg", "스트리트", None, "티셔츠", "청바지"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CLOTHING_DB_PATH", str(db))
    repository.reset_repository()
    yield
    repository.reset_repository()


@pytest.mark.asyncio
async def test_by_style_returns_only_that_style(small_db, client_session) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_style", {"style": "로맨틱", "n": 5}
        )
    text = res.content[0].text
    assert "https://img/a.jpg" in text or "https://img/b.jpg" in text
    assert "https://img/c.jpg" not in text  # 스트리트는 제외


@pytest.mark.asyncio
async def test_by_style_invalid_style_lists_options(
    small_db, client_session
) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_style", {"style": "없는스타일"}
        )
    text = res.content[0].text
    assert "없는스타일" in text and "스트리트" in text


@pytest.mark.asyncio
async def test_by_situation_echoes_situation_and_style(
    small_db, client_session
) -> None:
    async with client_session() as client:
        res = await client.call_tool(
            "recommend_outfits_by_situation",
            {"situation": "주말 소개팅", "style": "로맨틱"},
        )
    text = res.content[0].text
    assert "주말 소개팅" in text and "로맨틱" in text


@pytest.mark.asyncio
async def test_tools_listed_with_honest_annotations(
    small_db, client_session
) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    by_name = {t.name: t for t in result.tools}
    assert "recommend_outfits_by_style" in by_name
    assert "recommend_outfits_by_situation" in by_name
    # 랜덤 표본이라 idempotent 가 아님을 정직하게 신고
    anno = by_name["recommend_outfits_by_style"].annotations
    assert anno.idempotentHint is False
    assert anno.readOnlyHint is True
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_recommend.py -k "by_style or by_situation or tools_listed" -v`
Expected: FAIL — 도구 미등록(`Unknown tool` 또는 list 에 없음)

- [ ] **Step 3: `_recommend` 코어 + 도구 + 등록 구현** — `recommend.py` 의 `_format_outfit` 아래에 추가

```python
def _recommend(style: str, n: int, header: str | None) -> str:
    """style 검증 → 무작위 표본 → 마크다운 렌더. header 있으면 맨 위에 붙인다."""
    if style not in STYLES:
        return _invalid_style_msg(style)
    outfits = get_repository().sample_outfits(style=style, n=_clamp_n(n))
    if not outfits:
        return (
            f"'{style}' 스타일의 코디를 찾지 못했습니다. "
            "다른 스타일로 시도해 보세요."
        )
    body = "\n\n".join(_format_outfit(o) for o in outfits)
    return f"{header}\n\n{body}" if header else body


def register_tools(mcp: FastMCP) -> None:
    """추천 도구 2개를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend outfit sets by style",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,  # 랜덤 표본 — 매 호출 결과 다름
            openWorldHint=False,  # 로컬 DB·외부 호출 없음
        )
    )
    def recommend_outfits_by_style(style: str, n: int = _N_DEFAULT) -> str:
        """Recommends outfit sets (코디) of a given style for TPO Coach(티피오 코치).

        Samples up to n random outfit coordinations of the requested style from
        the K-Fashion reference set and returns them as image-URL markdown. If the
        style is not supported, the valid style list is returned instead.

        Args:
            style: One of the supported Korean styles (e.g. 클래식, 스트리트, 로맨틱).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.

        Returns:
            Markdown listing recommended outfits (image, style, composition).
        """
        return _recommend(style, n, header=f"**{style}** 스타일 코디 추천")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend outfit sets for a situation",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def recommend_outfits_by_situation(
        situation: str, style: str, n: int = _N_DEFAULT
    ) -> str:
        """Recommends outfit sets (코디) for a situation for TPO Coach(티피오 코치).

        Given a free-text situation, infer the single most fitting style from the
        supported Korean styles and pass it as `style`; the tool then samples up to
        n random outfits of that style. The situation is echoed in the response
        heading. If the style is unsupported, the valid style list is returned.

        Args:
            situation: User's situation in free text (e.g. "주말 소개팅"). Echoed only.
            style: Supported style inferred from the situation (e.g. 로맨틱, 클래식).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.

        Returns:
            Markdown: situation/style heading + recommended outfits.
        """
        header = f"**{situation}**에 어울리는 **{style}** 코디 추천"
        return _recommend(style, n, header=header)
```

- [ ] **Step 4: 도구 등록 배선** — `src/playmcp_server/tools/__init__.py` 수정

```python
from mcp.server.fastmcp import FastMCP

from playmcp_server.tools import color, recommend


def register_tools(mcp: FastMCP) -> None:
    """모든 도구 모듈을 FastMCP 인스턴스에 등록한다."""
    color.register_tools(mcp)
    recommend.register_tools(mcp)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_recommend.py -v`
Expected: PASS (8 passed — Task 2 헬퍼 4 + 통합 4)

- [ ] **Step 6: 전체 검증**

Run: `uv run ruff check . && uv run pytest -q`
Expected: ruff `All checks passed!`, pytest 전체 PASS

- [ ] **Step 7: 커밋**

```bash
git add src/playmcp_server/tools/recommend.py src/playmcp_server/tools/__init__.py tests/test_recommend.py
git commit -m "feat(tools): 셋업 추천 도구 by_style·by_situation 추가

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: 실제 DB 성능 스모크(ORDER BY RANDOM 검증)

**Files:**
- Test: `tests/test_recommend.py` (성능 스모크 1건 추가)

**Interfaces:**
- Consumes: 패키지 동봉 `data/clothing.db`(존재 시), `get_repository()`, 최다 스타일 "스트리트".

성능은 spec 의 미해결 리스크다(262k 행 `ORDER BY RANDOM()`). 실측해 p99 3s 안에 드는지 가드한다. DB 가 없는 CI 환경을 위해 없으면 skip.

- [ ] **Step 1: 성능 스모크 테스트 작성** — `tests/test_recommend.py` 끝에 추가

```python
import time
from pathlib import Path


def test_sample_perf_on_real_db(monkeypatch) -> None:
    """동봉 DB 가 있으면 최다 스타일 표본이 1초 내에 끝나는지 가드."""
    real = (
        Path(__file__).resolve().parent.parent
        / "src/playmcp_server/data/clothing.db"
    )
    if not real.exists():
        pytest.skip("packaged clothing.db 없음")
    monkeypatch.setenv("CLOTHING_DB_PATH", str(real))
    repository.reset_repository()
    try:
        repo = repository.get_repository()
        t0 = time.perf_counter()
        out = repo.sample_outfits(style="스트리트", n=3)
        elapsed = time.perf_counter() - t0
    finally:
        repository.reset_repository()
    assert len(out) == 3
    assert elapsed < 1.0, f"sample 너무 느림: {elapsed:.3f}s (p99 3s 위험)"
```

- [ ] **Step 2: 실측 실행**

Run: `uv run pytest tests/test_recommend.py -k perf -v`
Expected: PASS. 만약 FAIL(1s 초과)이면 STOP — 저장소 구현을 rowid 기반 무작위 선택으로 교체해야 한다(아래 폴백 참고). 통과하면 다음 단계.

> **폴백(테스트 FAIL 시에만):** `sample_outfits` 를 2-쿼리 방식으로 — ① 해당 style 활성 `id` 목록을 인덱스로 가져와 파이썬 `random.sample` 로 n개 뽑고 ② `WHERE id IN (...)` 로 조회. 12만 id 로드도 보통 100ms 내. 이 폴백을 쓰면 Task 1 테스트가 그대로 통과하는지 재확인.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_recommend.py
git commit -m "test(tools): 실 DB 무작위 표본 성능 스모크(p99 가드)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** — spec 각 결정의 구현 위치:
- 추천 단위=셋업 / 도구 2개 둘 다 style 키 → Task 3.
- 상황→스타일 LLM 위임(docstring) → Task 3 `recommend_outfits_by_situation` docstring.
- 무작위 표본 N건(1~10, 기본 3) → Task 1(`sample_outfits` RANDOM) + Task 2(`_clamp_n`).
- 이미지 URL 마크다운 출력 → Task 2 `_format_outfit`.
- 무효 style → 유효 목록 안내 → Task 2 `_invalid_style_msg` + Task 3 통합 테스트.
- 저장소 `sample_outfits` 추가, 기존 메서드 불변 → Task 1.
- annotations 정직(idempotent=false 등) → Task 3 도구 정의 + 통합 테스트.
- 파일/등록(`recommend.py`, `__init__` 배선) → Task 3.
- 성능 p99 3s 확인 → Task 4(폴백 포함).
- 더미 정리 → spec 단계에서 이미 반영(커밋 `b0c45c4`).

**2. Placeholder scan** — "TBD"/"적절히 처리" 류 없음. 모든 코드 스텝에 실제 코드 포함. ✅

**3. Type consistency** — `sample_outfits(*, style: str, n: int) -> list[Outfit]`(Task 1)와 Task 3 호출(`sample_outfits(style=..., n=_clamp_n(n))`) 일치. `_recommend`/`_clamp_n`/`_format_outfit`/`_invalid_style_msg` 시그니처가 정의(Task 2)와 사용(Task 3) 일치. `_N_DEFAULT=3` 이 도구 기본값과 일치. ✅
