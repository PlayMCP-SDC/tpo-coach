# 기능 카탈로그 & MCP 도구 매핑

> 상태: **기획 → 설계 전환 단계**. 아이디어 문서([README](README.md)·[host-mode](host-mode.md)·[use-cases](use-cases.md)·[matching-flow](matching-flow.md))에서
> 기능을 추출·통합하고 적대적 검증을 거친 결과다. 도구 스키마·annotations 확정은 다음 단계.

## 기능 ≠ MCP 도구

추출된 기능(feature)이 전부 `@mcp.tool` 이 되는 것은 아니다. 기능은 실제로 다음 5가지로 갈라진다:

| 유형 | 의미 | 들어갈 곳 |
| --- | --- | --- |
| ✅ **도구(tool)** | LLM 이 호출하는 함수 | `src/playmcp_server/tools/` |
| 📦 **리소스(resource)** | 정적 데이터·카피 | `src/playmcp_server/resources/` |
| ⚙️ **횡단 정책** | 모든 도구가 지켜야 할 코드 규칙 | 설계 원칙 (도구 아님) |
| 🔧 **입력 옵션 흡수** | 기존 도구의 인자로 합침 (도구 수 절감) | 기존 도구 |
| 🚫 **범위 밖** | 클라이언트/플랫폼 책임 또는 stateless MCP 불가 | — |

도구 수를 최소화하는 이유는 [CLAUDE.md](../../CLAUDE.md) 의 PlayMCP 규칙(도구 ≤ 20개, 권장 3~10개,
너무 많으면 LLM 툴콜 정확도 하락) 때문이다.

## 기능 카탈로그 (14개 / 7 에픽)

| ID | 기능 | 모드 | 우선순위 | 산출물 유형 | 도구 후보 |
| --- | --- | --- | --- | --- | --- |
| **F1** | 자연어 상황 입력 파서 (일시·장소·성격·제약 추출) | host/platform | **MVP** | ✅ 도구 | `parse_occasion` |
| **F2** | 드레스코드 규칙 엔진 (상황 → 권장수준 + 추천/금기) | platform | **MVP** | ✅ 도구 | `recommend_dresscode` |
| **F3** | 시나리오별 규칙 데이터셋 (하객룩·골프장·소개팅 …) | platform | **MVP**(데이터) | 📦 리소스 + ✅ 조회도구(v1) | `get_dresscode_rules` |
| **F4** | TPO 가이드 카드 생성 | host | **MVP** | ✅ 도구 | `create_tpo_guide` |
| F5 | 가이드 카드 단톡방 공유 | host | v1 | 🚫 클라이언트 책임 | — |
| **F6** | 개인 착장 비공개 검사 (부합/조정/부적합) | personal | **MVP** | ✅ 도구 | `check_outfit` |
| **F7** | 프라이버시 가드 (사진·결과 비공유/비저장) | platform | **MVP** | ⚙️ 횡단 정책 | — |
| F8 | 의상 대표 색상 추출 | personal | v1 *(원래 MVP)* | ✅ 도구 | `extract_color` |
| F9 | 어울리는 하의 추천 (매칭 + 유사도 정렬) | personal | v1 *(원래 MVP)* | ✅ 도구 | `recommend_bottoms` |
| F10 | 조정 시 착장 추천 연계 (검사 실패 → 대안) | matching | v1 | 🔗 오케스트레이션 | — |
| F11 | 개인 옷장 기반 조합 추천 | personal | later | 🔧 `recommend_bottoms` 옵션 흡수 | — |
| F12 | 톡캘린더 일정 기반 가이드 자동화 | host | later | 🔧 `create_tpo_guide` 옵션 흡수 | — |
| F13 | 일정 알림 시점 카드 사전 노출 | host | **제외** | 🚫 stateless MCP 범위 밖 | — |
| F14 | 다국어/카피 리소스 | platform | v1 | 📦 리소스 | — |

> 🔗 **오케스트레이션** = 별도 도구가 아니라 LLM 이 기존 도구들(F6 → F9)을 순서대로 호출해 구현.

## MVP — 엔드투엔드 가치 루프

적대적 검증에서 "F8/F9 는 MVP 인데 연결고리(F10)는 v1 → 고립된 도구" 모순이 잡혀,
**색상 매칭(F8/F9)을 v1 로 내리고** MVP 를 최소 루프로 좁혔다.

```
모임장 │ parse_occasion → recommend_dresscode → create_tpo_guide → [카드]
참석자 │ check_outfit(카드 기준 + 내 착장 텍스트) → 부합 / 조정 / 부적합 판정
       └ 전 구간 프라이버시 가드(F7) 강제
```

**MVP 기능**: F1 · F2 · F3(데이터) · F4 · F6 (+ F7 정책)
→ 이것만으로 TPO Coach 의 두 약속(모임장에게 적정 드레스코드 카드, 참석자에게 비공개 착장 코칭)이 작동한다.

## 실제 MCP 도구 표면

| 단계 | 도구 | 기능 | 비고 |
| --- | --- | --- | --- |
| **MVP** | `parse_occasion` | F1 | 자연어 → 구조화 슬롯 |
| **MVP** | `recommend_dresscode` | F2 | 100% 규칙 테이블 결정적 (LLM 폴백 금지) |
| **MVP** | `create_tpo_guide` | F4 | 출력에 자기완결적 `check_criteria` 블록 포함 |
| **MVP** | `check_outfit` | F6 | MVP 는 텍스트 묘사 입력만 (이미지 X) |
| v1 | `get_dresscode_rules` | F3 | 규칙 데이터 직접 조회 |
| v1 | `extract_color` | F8 | 이미지 색추출 (직접 색 입력은 `recommend_bottoms` 로 흡수) |
| v1 | `recommend_bottoms` | F9 | 색 매칭 + Top-N. 옷장(F11) 입력 옵션 흡수 |

→ 최종 **약 7개** (MVP 4 + v1 3). PlayMCP 권장(3~10개)·상한(≤20)을 모두 만족.

## 검증에서 나온 핵심 결정사항

다음 단계(도구 스키마 설계) 전에 반드시 못박아야 할 항목들.

### 실현 불가 / 재설계 (high)

- **이미지 경로(F6·F8)** — 비전 추론은 응답 평균 100ms 한계와 정면충돌 + 사진 외부 전송은 F7 위반.
  → MVP 는 **텍스트 묘사 입력만**. 이미지는 멀티모달 클라이언트가 사전 텍스트화 후 전달.
- **능동 푸시(F13)** — stateless MCP 는 타이머/푸시 불가 → 도구화 대상에서 제외, 외부 스케줄러 영역.
- **외부 캘린더 OAuth(F12)·옷장 저장(F11)** — stateless 라 토큰/상태 저장 불가
  → 별도 도구 X, **데이터를 매 요청 인자로 전달**받는 옵션으로 흡수.
- **F2 LLM 폴백** — 비결정성이라 `idempotentHint=true` 주장과 충돌(심사 반려 소지)
  → **규칙 테이블 100% 결정적** 고정. 자연어 해석은 F1(클라이언트 LLM)에서만.

### 데이터 계약 (high — 가장 load-bearing)

stateless 라 `F1 → F2 → F4 → F6` 의 값 전달이 전부 "클라이언트가 직렬화 결과를 다음 도구에 넘김"에
의존한다. 이 **공유 스키마의 주인이 없으면 MVP 도구 전부가 깨진다.** 4종 JSON 스키마를 버전 포함해 고정한다:

1. `occasion_struct` — F1 출력
2. `dresscode_result` — F2 출력
3. `guide_card` — F4 출력
4. `check_criteria` — F6 입력 (= `guide_card` 안에 self-contained 로 포함)

→ `[내 옷 확인하기]` 는 클릭 액션이 아니라 "이 기준 JSON 을 `check_outfit` 에 넣으세요" 형태로 현실화.

### 결정성·정직한 annotations (high)

- `parse_occasion` 은 상대 날짜('이번 주 토요일') 해석을 위해 `reference_time`·`timezone` 을
  **명시적 인자**로 받는다 (없으면 미해석 + 플래그). → 동일 입력에 결정적 = `idempotentHint=true` 정직.
- 정적 데이터 전용 도구는 `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=false`.
  외부 호출/LLM 이 끼면 `openWorldHint=true·idempotentHint=false` 로 정직하게 신고.

## 추가로 발굴된 누락 기능 (반영 권장)

- 🔴 **날씨/계절 슬롯** — 착장 1차 변수인데 누락. F1 에 5번째 슬롯 + F2 계절 레이어(아우터/소재/반팔 가용).
- 🔴 **면책·신뢰도 문구** — 카드/검사결과에 `disclaimer` + `confidence` 필드 (골프장·문화 편차 caveat 전달).
- 🔴 **장례·종교 시나리오** — 가장 치명적이고 규칙화는 오히려 쉬움 → F3 데이터셋에 추가.
- 🟡 액세서리·아우터 가이드 / 카드 재생성(override 입력) / 성별·스타일 선호 입력 / 로케일별 규칙 분기.

## 다음 단계

- [ ] MVP 도구 4개의 **입력/출력 스키마 + `annotations` 5종** 설계 (위 데이터 계약 4종 먼저 확정)
- [ ] F3 시나리오 규칙 데이터셋 초안 (장례·종교 포함, '보수적 기본값 + caveat' 패턴)
- [ ] 누락 기능(계절·면책) 반영해 F1/F2/F4 스키마에 필드 선반영
