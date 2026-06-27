# CLAUDE.md

이 저장소에서 작업하는 Claude / 기여자를 위한 요약.

## 스택

- Python 3.10+, 패키지/실행 관리는 **uv** (pip/poetry 아님)
- MCP SDK: `mcp[cli]>=1.27,<2` (FastMCP 포함)
- 빌드 백엔드: hatchling
- 린트/포맷: ruff · 테스트: pytest (in-memory transport)
- 배포: git 소스 → PyPI 패키지 → MCP 레지스트리엔 `server.json` 메타데이터만 등록
  (registryType: pypi, runtimeHint: uvx)

## 코드 규칙

1. **stdio transport 에서 stdout(print) 금지.** 로그는 `sys.stderr` / `logging` 으로만.
2. 모든 도구(tool)는 **타입 힌트 + docstring** 작성 (스키마 자동 생성).
3. 도구는 `src/playmcp_server/tools/` 아래 모듈로 분리하고, `tools/__init__.py` 의
   `register_tools` 에서 등록한다. 새 카테고리(resources/prompts)도 같은 패턴.
4. 비밀키/토큰은 `.env` 로만 관리. `.env` 커밋 금지(`.gitignore` 포함), `.env.example` 만 커밋.

## 전송 방식 (transport)

- 전송 방식은 환경변수 `MCP_TRANSPORT` 로 분기한다 (`server.py`).
  - `stdio` (기본) — 로컬 개발 / uvx 실행
  - `streamable-http` — 컨테이너/카카오 클라우드 배포. 엔드포인트 `/<host>:<port>/mcp`
- PlayMCP(KC) 는 **`streamable-http` 만 지원**한다. `sse`/`stdio` 로는 등록 불가.
- FastMCP 인스턴스는 **stateless 로 구성**한다 (`stateless_http=True`, `json_response=True`).

## PlayMCP 등록 규칙 (필수 — 어기면 심사 반려)

도구를 추가/수정할 때 아래를 반드시 지킨다. 출처: PlayMCP 서버 개발가이드.

1. **모든 도구에 `annotations` 5종 값 전부 지정** (FastMCP `@mcp.tool(annotations=...)`):
   `title`, `readOnlyHint`, `destructiveHint`, `openWorldHint`, `idempotentHint`.
   → 실전 예시는 [`src/playmcp_server/tools/README.md`](src/playmcp_server/tools/README.md) 참고.
2. **도구 개수 ≤ 20개** (3~10개 권장). 너무 많으면 LLM 툴콜 정확도가 떨어진다.
3. **이름 규칙**: 도구/서버 이름에 `kakao` 사용 금지(대소문자·위치 무관).
   도구 이름은 1~128자, `A-Za-z0-9_-` 만, 중복 금지(대소문자 구분).
4. **`description`**: 1,024자 이내 + 서비스명 포함, 영문 작성 권장.
5. **성능**: 도구 응답속도 평균 100ms 이내 / p99 3,000ms 이내.
6. 제출 전 **MCP Inspector** 로 표준 스펙 준수 점검.

## 배포 체크리스트

- [ ] 버전 올릴 때 **`pyproject.toml` 의 `version` 과 `server.json` 의 `version` 을 동시에 수정**
      (두 값은 항상 일치해야 한다). `src/playmcp_server/__init__.py` 의 `__version__` 도 맞춘다.
- [ ] `uv run ruff check .` 통과
- [ ] `uv run pytest` 통과
- [ ] 태그 `v<version>` push → CI(`publish.yml`)가 PyPI Trusted Publishing 으로 업로드
- [ ] (조직 레포로 옮긴 뒤) `mcp-publisher` 로 레지스트리에 `server.json` 등록

## placeholder 주의

현재 조직/패키지/모듈/설명은 임시값이다. 확정 시 `./scripts/rename.sh` 로 일괄 변경한다.
