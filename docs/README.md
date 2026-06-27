# 설계 문서

이 폴더에는 TPO Coach MCP 서버의 아이디어/설계/아키텍처 문서를 둔다.

## 아이디어 / 기획

- [idea/README.md](idea/README.md) — **TPO Coach 아이디어 개요** (모드 구성·플로우·확장 포인트)
- [idea/host-mode.md](idea/host-mode.md) — 모임장 모드 (단톡방 가이드 카드, 개인 착장 검사)
- [idea/use-cases.md](idea/use-cases.md) — 활용 시나리오와 상황별 주의점
- [idea/matching-flow.md](idea/matching-flow.md) — 색상 기반 착장 추천 플로우

## 작성할 내용 (자리)

- 서버가 제공하는 도구/리소스/프롬프트 목록과 스키마
- 외부 API 연동 방식 (인증, rate limit, 에러 처리)
- 설정(.env) 항목 설명
- 배포 흐름 (PyPI → MCP 레지스트리)

> TODO: 아이디어가 도구 스펙으로 구체화되면 위 "작성할 내용"을 채운다.
