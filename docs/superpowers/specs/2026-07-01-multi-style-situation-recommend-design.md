# 상황 추천 다중 스타일(태그) 설계

> 상태: **설계 확정 (2026-07-01)**. 다음 단계는 구현 계획(writing-plans).
> 선행: [셋업 추천 도구 설계](2026-07-01-outfit-recommend-tools-design.md)(PR #8, 미머지).
> 이 문서는 그 설계의 `recommend_outfits_by_situation` 을 **단일 → 다중 스타일**로 확장한다.

## 배경 / 동기

현재 `recommend_outfits_by_situation(situation, style, n)` 은 상황에서 **스타일 1개**만 받아
N개 추천이 전부 같은 스타일로 나온다. 예: "일본 여행 코디 3개" → 모던 3개(단조로움).
호출 LLM 이 상황에 어울리는 **여러 스타일**을 넘기게 하고, N개를 그 스타일들에 분산해
**서로 다른 스타일의 코디**로 다양화한다.

## 결정 사항 (확정)

1. **다중 태그는 상황 도구에만.** `recommend_outfits_by_style(style, n)` 은 단일 유지(불변).
2. **분배 = 라운드로빈 + 백필.** 태그 수와 `n` 을 따로 둔다(선택지 B).
   - 3태그·n=3 → 1개씩(다 다른 태그) / 2태그·n=3 → 2+1 / 1태그·n=3 → 그 스타일 3개(하위호환) /
     빈·소진 스타일은 다른 스타일에서 자연 백필.
3. **무효 스타일은 걸러내고 진행.** 유효한 것만 사용. **전부 무효면** 추천 대신 유효 목록 안내(재시도 유도).
4. **23종 통제 어휘 강력 제약 — 3중 레이어.** (아래 §강력 제약)
5. 저장소 변경 없음 — 기존 `sample_outfits` 를 스타일별로 재사용.

## 인터페이스

```python
recommend_outfits_by_situation(situation: str, styles: list[str], n: int = 3) -> str
```

- `situation`: 사용자 상황 원문. 조회엔 쓰지 않고 응답 머리말에만 echo.
- `styles`: 호출 LLM 이 상황을 보고 **어울리는 스타일들을 적합도 순으로** 넘긴다.
  `vocab.STYLES`(23종) 중에서만. 파라미터 설명에 23종 전부 명시 + "이 목록에서만 고르라".
- `n`: 추천 개수. 1~10, 기본 3(클램프).

`recommend_outfits_by_style(style: str, n: int = 3)` 은 그대로.

## 동작 흐름

```
입력(situation, styles, n)
  │ ① styles 정규화: 중복 제거(순서 보존) → STYLES 로 유효 필터
  │     └ 유효 0개면: 유효 스타일 23종 안내 문자열 반환 (LLM 재시도 유도)
  │ ② n 클램프 [1, 10]
  │ ③ 유효 스타일마다 sample_outfits(style, n) → 스타일별 풀
  │ ④ 라운드로빈 인터리브(zip_longest, None 제외) → 앞에서 n개
  ▼
출력: 머리말(상황 + 사용된 스타일들) + 코디 n개 마크다운
```

인터리브 예: 풀 A=[a0,a1,a2], B=[b0,b1] → `[a0,b0,a1,b1,a2]` → n=3 이면 `[a0,b0,a1]`(=2A+1B).
각 스타일 1개씩 앞에 오므로 다양성이 앞쪽에 배치되고, 짧은 풀은 자동 백필된다.

## 강력 제약 (23종만) — 3중 레이어

한 곳만으로는 호스트가 무시할 수 있어 3중으로 건다.

1. **스키마(기계 제약):** `styles` 항목에 23종 `enum` 을 JSON 스키마로 광고한다.
   enum 을 존중하는 호스트는 LLM 이 목록 밖 값을 넣지 못한다.
   단 **파라미터 타입은 `list[str]` 유지** — 벗어난 값이 와도 호출이 통째로 실패(Pydantic 하드 리젝트)하지
   않고 §동작 흐름 ①의 "필터 후 진행"이 살아있게 한다.
2. **프롬프트(LLM 유도):** `styles` 파라미터 설명에 **23종 전부**를 나열하고 "반드시 이 목록에서만
   고르라"고 명시. 이 설명 문자열은 `sorted(STYLES)` 에서 생성 → 어휘 드리프트 없음(단일 출처).
3. **런타임(최종 보증):** 호스트와 무관하게 우리 코드가 `STYLES` 로 필터. 이게 실제 보증선이다.

**동기화 테스트:** 도구 inputSchema 가 광고하는 style enum 집합 == `vocab.STYLES`(23종) 임을 강제한다
(어휘 추가/변경 시 자동 감지). 색 어휘 동기화 테스트와 같은 패턴.

> 구현 메모: enum 광고 방식(예: `Annotated[list[str], Field(json_schema_extra=...)]` 또는 동적 Enum)은
> 플랜 단계에서 FastMCP/Pydantic 스키마 생성 실측으로 확정한다. **불변식은 "타입은 str 유지(하드 리젝트
> 금지) + 스키마엔 23종 enum 광고 + 런타임 필터"** 이며, 광고 수단은 이 불변식을 만족하면 무엇이든 좋다.
> 광고가 어려우면 프롬프트+런타임(레이어 2·3)만으로도 정합성은 보장된다(스키마 광고는 유도 강화용).

## 코드 영향 (작음, 상황 도구 국소)

- `tools/recommend.py`:
  - `_recommend` 를 **`styles: list[str]`** 받도록 일반화(현재는 `style: str`). 내부에 정규화·필터·
    스타일별 표본·인터리브 로직. `recommend_outfits_by_style` 은 `_recommend([style], n, header)` 로 감싼다
    (단일=길이 1 리스트 → 기존과 동일 동작).
  - `_invalid_style_msg` 를 리스트 입력도 안내할 수 있게 조정(또는 "유효 0개" 전용 메시지 추가).
  - 상황 도구 시그니처·docstring 갱신(styles 리스트 + 23종 제약 문구 + 머리말에 사용 스타일 표기).
- 저장소·`recommend_outfits_by_style` 시그니처·`_format_outfit`·`_clamp_n` 불변.

## annotations

기존과 동일: `readOnlyHint=True`, `destructiveHint=False`, `openWorldHint=False`,
**`idempotentHint=False`**(무작위 표본). description 에 "TPO Coach" 포함.

## 범위 밖 (YAGNI)

- `WHERE style IN (...)` 단일 쿼리 최적화(스타일 수 적어 불필요 — 스타일별 호출로 충분).
- 스타일별 가중치/비율 커스텀, by_style 다중화, 성별·계절 필터.

## 테스트 전략

- 정규화: 중복 제거·순서 보존, 무효 필터, 유효 0개 → 안내.
- 분배(핵심): 3태그·n=3 → 3개가 서로 다른 스타일 / 2태그·n=3 → 2+1 / 1태그 → 하위호환(그 스타일 n개) /
  한 스타일 소진 시 다른 스타일로 백필해 총 n개 유지(총 재고가 n 이상일 때).
- 강력 제약: inputSchema 의 style enum == STYLES(동기화). 무효 섞인 리스트 → 유효분만으로 추천.
- 하위호환: `recommend_outfits_by_style` 동작·시그니처 불변 회귀.
- 통합: in-memory MCP 클라이언트로 상황 도구 호출 → 머리말에 상황+스타일들, 코디 블록 스타일 다양성 확인.
