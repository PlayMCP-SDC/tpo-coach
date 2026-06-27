<!-- mcp-name: io.github.PlayMCP-SDC/playmcp-server -->

# playmcp-server

**카카오 [PlayMCP](https://playmcp.kakao.com) 에 등록하기 위한 MCP(Model Context Protocol) 서버** 입니다.
FastMCP(공식 `mcp` SDK) 기반이며, 로컬에서는 `stdio` 로, 카카오 클라우드(KC) 배포 시에는
`streamable-http` 로 동작합니다.

> ⚠️ 이 프로젝트는 아직 **placeholder 값**(`playmcp-server` / `PlayMCP-SDC`)으로 만들어진 골격입니다.
> 실제 이름이 확정되면 [이름 변경](#이름-변경) 절차로 한 번에 바꾸세요.

---

## 이게 뭔가요? (처음 보는 사람용)

- **MCP 서버**는 ChatGPT·Claude 같은 AI 가 외부 도구/데이터를 쓸 수 있게 해주는 서버예요.
- 이 저장소는 그 MCP 서버를 **카카오 PlayMCP 플랫폼에 제출**하기 위한 코드입니다.
- 실제 기능(도구)은 `src/playmcp_server/tools/` 에 들어가며, 현재는 예시 도구
  (`greet`, `add`) 만 들어있는 **빈 골격** 상태입니다.

### 전송 방식 (중요)

| 환경 | 전송 방식 | 설명 |
| --- | --- | --- |
| 로컬 개발 | `stdio` (기본값) | 내 PC 에서 MCP Inspector 등으로 테스트 |
| 카카오 클라우드 배포 | `streamable-http` | **공개 URL 엔드포인트** 가 생김 (PlayMCP 등록용) |

전송 방식은 환경변수 `MCP_TRANSPORT` 로 정합니다. PlayMCP 는 `streamable-http` 만 지원합니다.

---

## 빠른 시작 (로컬 개발)

> 사전 준비: [uv](https://docs.astral.sh/uv/) 설치 (pip/poetry 아님)

```bash
# 가상환경 + 의존성 설치
uv venv
source .venv/bin/activate
uv sync --extra dev

# 도구를 MCP Inspector 로 테스트 (stdio)
uv run mcp dev src/playmcp_server/server.py

# 린트 / 테스트
uv run ruff check .
uv run pytest
```

### HTTP 서버로 직접 띄워보기

```bash
MCP_TRANSPORT=streamable-http uv run playmcp-server
# → http://localhost:8000/mcp 로 접속 가능
```

환경변수: `MCP_TRANSPORT`(stdio|streamable-http), `HOST`(기본 0.0.0.0), `PORT`(기본 8000),
`LOG_LEVEL`(DEBUG|INFO|WARNING|ERROR). 비밀키/토큰은 `.env` 로만 관리합니다
(`.env.example` 복사해서 `.env` 생성, `.env` 는 커밋 금지).

---

## 카카오 클라우드(KC) 배포

이 저장소에는 배포용 [`Dockerfile`](Dockerfile) 이 포함돼 있습니다.
컨테이너는 자동으로 `streamable-http` + stateless 모드로 기동되며,
엔드포인트 경로는 **`/mcp`** 입니다.

```bash
# 빌드
docker build -t playmcp-server .

# 실행 (로컬에서 컨테이너 테스트)
docker run -p 8000:8000 playmcp-server
# → http://localhost:8000/mcp
```

배포 후 발급된 공개 URL(`https://<도메인>/mcp`)을
**PlayMCP 개발자 콘솔 → 새로운 MCP 서버 등록** 에 등록하면 됩니다.

---

## PlayMCP 등록 필수 요건 (체크리스트)

서버를 제출하기 전 PlayMCP 서버 개발가이드 기준으로 확인하세요.

- [x] **Streamable HTTP** 전송 방식 (sse/stdio 불가)
- [x] **Stateless**(no session) 구성 — `stateless_http=True`
- [ ] 공개된 URL 로 접근 가능한 **Remote 서버**(도메인) — 배포 단계
- [ ] 모든 도구에 **필수 property**: `name`, `description`, `inputSchema`, `annotations`
- [ ] `annotations` 5종 전부 값 지정: `title`, `readOnlyHint`, `destructiveHint`,
      `openWorldHint`, `idempotentHint`
- [ ] 도구 개수 ≤ 20개 (3~10개 권장), 도구/서버 이름에 `kakao` 사용 금지
- [ ] `description` 1,024자 이내 + 서비스명 포함 (영문 권장)
- [ ] 도구 응답속도 평균 100ms 이내 / p99 3,000ms 이내
- [ ] **MCP Inspector** 로 표준 스펙 사전 점검

---

## 프로젝트 구조

```
playmcp-server/
├── src/playmcp_server/
│   ├── server.py        # FastMCP 인스턴스 + main() 진입점 (전송 방식 분기)
│   ├── config.py        # 환경변수/설정 로딩
│   ├── tools/           # 도구 모듈 (register_tools 로 등록) ← 여기에 기능 추가
│   ├── resources/       # 리소스 자리
│   └── prompts/         # 프롬프트 자리
├── tests/               # in-memory transport pytest
├── docs/                # 설계 문서
├── Dockerfile           # 카카오 클라우드 배포용 (streamable-http)
├── scripts/rename.sh    # placeholder 일괄 변경 스크립트
├── pyproject.toml       # 빌드/의존성 (uv + hatchling)
└── server.json          # MCP 레지스트리 메타데이터
```

### 새 도구 추가하는 법

1. `src/playmcp_server/tools/` 에 새 모듈 작성 (`example.py` 참고)
2. 각 도구는 **타입 힌트 + docstring + `annotations` 5종** 작성 (FastMCP 가 스키마 자동 생성)
3. `tools/__init__.py` 의 `register_tools` 에서 새 모듈 등록

> 자세한 절차·예시 코드·체크리스트는 [`tools/README.md`](src/playmcp_server/tools/README.md),
> 전체 코드 규칙은 [`CLAUDE.md`](CLAUDE.md) 참고.

---

## 이름 변경

조직명·패키지명·모듈명·설명이 확정되면 한 번에 치환합니다:

```bash
./scripts/rename.sh <new-org> <new-package-name> <new_module_name> "<한 줄 설명>"
# 예) ./scripts/rename.sh PlayMCP-SDC weather-mcp weather_mcp "날씨 정보 MCP 서버"
```

| 용도 | 형식 | 현재 값 |
| --- | --- | --- |
| PyPI / 명령어 | 소문자-하이픈 | `playmcp-server` |
| Python 패키지 | 소문자_밑줄 | `playmcp_server` |
| 레지스트리 네임스페이스 | `io.github.<ORG>/<PKG>` | `io.github.PlayMCP-SDC/playmcp-server` |

> 맨 위 `<!-- mcp-name: ... -->` 주석은 `server.json` 의 `name` 과 **정확히 일치**해야
> 레지스트리 소유권 검증을 통과합니다.

---

## 기여

[CONTRIBUTING.md](CONTRIBUTING.md) 를 참고하세요.
