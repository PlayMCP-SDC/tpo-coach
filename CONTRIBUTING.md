# 기여 가이드

## 브랜치

- `main` 에 직접 push 금지. **항상 PR** 로 머지한다.
- 브랜치 이름 prefix:
  - `feat/...` 새 기능
  - `fix/...` 버그 수정
  - `docs/...` 문서

## 커밋 메시지 — Conventional Commits

```
feat: 새 도구 추가
fix: greet 인코딩 버그 수정
docs: README 설치 방법 보강
chore: 의존성 업데이트
test: add 도구 테스트 추가
```

## PR 규칙

- CI(`ruff` + `pytest`)를 **통과**해야 한다.
- 리뷰어 **최소 1명 승인**이 있어야 머지할 수 있다.
- 변경 요약 / 테스트 방법 / 관련 이슈를 PR 템플릿에 맞춰 작성한다.

## 새 도구 추가 방법

1. `src/playmcp_server/tools/` 아래에 새 모듈을 만든다 (예: `weather.py`).
2. 모듈 안에 `register_tools(mcp)` 를 정의하고, 그 안에서 `@mcp.tool()` 로 도구를 만든다.
   - 모든 도구는 **타입 힌트 + docstring** 필수 (스키마 자동 생성).
3. `src/playmcp_server/tools/__init__.py` 의 `register_tools` 에서 새 모듈을 등록한다.
4. `tests/` 에 in-memory transport 테스트를 추가한다.

## 버전 올리기

- `pyproject.toml` 의 `version` 과 `server.json` 의 `version` 을 **동시에** 수정한다 (항상 일치).
- `src/playmcp_server/__init__.py` 의 `__version__` 도 맞춘다.
