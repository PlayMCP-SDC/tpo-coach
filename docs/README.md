# 설계 문서

이 폴더에는 TPO Coach MCP 서버의 아이디어/설계/아키텍처 문서를 둔다.

## 현재 상태 / 결정 요약 (SSOT · last updated: 2026-06-28)

문서가 흩어져 있으므로 **확정 결정은 여기로 수렴**한다. 개별 문서가 이 요약과 다르면 이 요약 기준으로 정정.

- **제품**: TPO Coach — 카카오 PlayMCP MCP 서버(드레스코드 코칭). Python/uv/FastMCP, streamable-http·stateless.
- **도구 표면 ~7개**: MVP 4 (`parse_occasion`·`recommend_dresscode`·`create_tpo_guide`·`check_outfit`) / v1 3 (`get_dresscode_rules`·`extract_color`·`recommend_bottoms`).
- **범위 = 'C' 베이스라인**: 레포 DoD(타입힌트·docstring·annotations 5종·pytest·ruff·버전 동기화) + 경량 공유타입(`models.py` 1인 소유; SCHEMA_VERSION·게이트키퍼·fixtures 1급화 **제외**) + 얇은 테스트 + 결정적 엔진 + 품질 카피. ※ 무거운 '계약 동결/버전 거버넌스'는 채택 안 함.
- **이미지 입력**: `outfit_text` 기본 UX, `image_url` 보조(호스트 자동 업로드 없음). 진짜 사진 UX 는 외부 멀티모달 호스트 경유. 100ms 는 하드블로커 아님(p99 3s 실질).
- **시나리오**: F3 MVP 6종. 장례·종교는 v1 연기(복귀자 담당).
- **일정/역할**: 접수 6/15~7/14, 내부 데드라인 **7/9(목) 등록**(→ 7/10~7/14 빠꾸 버퍼). 7/1 배포·등록·이미지 도달방식 조기검증. 3인 — A(계약·코어)/B(배포·파이프라인, 임계경로)/C(v1·매칭 오너, 6/28~7/7 해외연수 부재·7/8 복귀).
- **출처(SSOT)**: 범위/일정 → [delivery-plan.md](idea/delivery-plan.md), 도구 매핑 → [features.md](idea/features.md), 이미지 결론 → [image-input.md](idea/image-input.md).

## 아이디어 / 기획

- [idea/README.md](idea/README.md) — **TPO Coach 아이디어 개요** (모드 구성·플로우·확장 포인트)
- [idea/host-mode.md](idea/host-mode.md) — 모임장 모드 (단톡방 가이드 카드, 개인 착장 검사)
- [idea/use-cases.md](idea/use-cases.md) — 활용 시나리오와 상황별 주의점
- [idea/matching-flow.md](idea/matching-flow.md) — 색상 기반 착장 추천 플로우
- [idea/features.md](idea/features.md) — **기능 카탈로그 & MCP 도구 매핑** (14기능 → 도구 ~7개, MVP 슬라이스)
- [idea/delivery-plan.md](idea/delivery-plan.md) — **구현 범위·역할·일정** (예선 7/9 등록 데드라인, 3인 분담, 범위 베이스라인)
- [idea/image-input.md](idea/image-input.md) — **이미지(사진) 입력 처리** (결론: outfit_text 기본 · image_url 보조 · 호스트 자동 업로드 없음 · 진짜 사진 UX는 외부 멀티모달 호스트 경유)

## 작성할 내용 (자리)

- 서버가 제공하는 도구/리소스/프롬프트 목록과 스키마
- 외부 API 연동 방식 (인증, rate limit, 에러 처리)
- 설정(.env) 항목 설명
- 배포 흐름 (PyPI → MCP 레지스트리)

> TODO: 아이디어가 도구 스펙으로 구체화되면 위 "작성할 내용"을 채운다.
