## 변경 요약

<!-- 무엇을, 왜 바꿨는지 -->

## 테스트 방법

<!-- 리뷰어가 검증할 수 있는 단계 -->

- [ ] `uv run ruff check .` 통과
- [ ] `uv run pytest` 통과
- [ ] (도구 추가 시) `uv run mcp dev src/playmcp_server/server.py` 로 Inspector 확인

## 관련 이슈

<!-- 예: Closes #123 -->

## 체크리스트

- [ ] 브랜치 이름이 `feat/`·`fix/`·`docs/` prefix 를 따른다
- [ ] 커밋이 Conventional Commits 형식이다
- [ ] (버전 변경 시) `pyproject.toml` 과 `server.json` 의 version 을 함께 수정했다
- [ ] 새 도구는 타입 힌트 + docstring 을 포함한다
