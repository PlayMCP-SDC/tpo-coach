# tools/ — 도구(tool) 추가 가이드

여기에 MCP **도구**를 모듈로 추가한다. 도구 = AI 가 호출하는 함수.

> 전체 코드 규칙은 [`/CLAUDE.md`](../../../CLAUDE.md) 가 단일 출처다.
> 이 문서는 "도구를 어떻게 올바르게 짜는가"의 실전 안내 + 예시다.

## 추가 절차

1. 이 폴더에 새 모듈을 만든다 (예: `weather.py`). `example.py` 를 복사해 시작해도 된다.
2. 모듈 안에 `register_tools(mcp)` 함수를 만들고 그 안에서 `@mcp.tool(...)` 로 도구를 정의한다.
3. [`__init__.py`](__init__.py) 의 `register_tools` 에서 새 모듈을 호출한다.

```python
# tools/__init__.py
from playmcp_server.tools import example, weather   # ← 추가

def register_tools(mcp: FastMCP) -> None:
    example.register_tools(mcp)
    weather.register_tools(mcp)                      # ← 추가
```

## 올바른 도구 예시 (PlayMCP 규칙 충족)

**핵심: PlayMCP 는 모든 도구에 `annotations` 5종 값을 전부 요구한다.** 빠뜨리면 심사 반려.

```python
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Greet user",      # 사람이 읽는 짧은 제목
            readOnlyHint=True,       # 외부 상태를 바꾸지 않음(읽기 전용)이면 True
            destructiveHint=False,   # 데이터 삭제/파괴적 동작이면 True
            idempotentHint=True,     # 같은 입력 → 같은 결과면 True
            openWorldHint=False,     # 외부 세계(웹/외부 API)에 접근하면 True
        )
    )
    def greet(name: str) -> str:
        """Returns a greeting from playmcp-server(플레이엠씨피).

        Args:
            name: 인사할 대상의 이름.

        Returns:
            "Hello, {name}!" 형태의 인사말.
        """
        return f"Hello, {name}!"
```

## 체크리스트 (도구 하나 추가할 때마다)

- [ ] **타입 힌트 + docstring** 작성 (FastMCP 가 `inputSchema` 자동 생성)
- [ ] **`annotations` 5종 전부 지정**: `title`, `readOnlyHint`, `destructiveHint`,
      `openWorldHint`, `idempotentHint`
- [ ] `description`(= docstring 첫 줄): **서비스명 포함**, 1,024자 이내, 영문 권장
- [ ] 도구 이름: `A-Za-z0-9_-` 만, `kakao` 금지, 서버 내 중복 금지
- [ ] 서버 전체 도구 개수 ≤ 20개 (3~10개 권장)
- [ ] 응답속도 평균 100ms / p99 3,000ms 이내
- [ ] `tools/__init__.py` 에 등록했는지 확인
- [ ] `uv run pytest`, `uv run ruff check .` 통과

## annotations 의미 (빠르게)

| 필드 | True 로 두는 경우 |
| --- | --- |
| `readOnlyHint` | 외부 상태를 **읽기만** 하고 바꾸지 않음 |
| `destructiveHint` | 삭제·덮어쓰기 등 **파괴적** 동작 (보통 readOnly=False 일 때만 의미) |
| `idempotentHint` | 같은 인자로 여러 번 호출해도 **결과/효과가 동일** |
| `openWorldHint` | 웹·외부 API 등 **열린 외부 세계**와 상호작용 |
