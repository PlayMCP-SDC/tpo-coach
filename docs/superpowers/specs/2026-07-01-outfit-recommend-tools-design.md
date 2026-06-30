# 셋업(코디) 추천 도구 설계

> 상태: **설계 확정 (2026-07-01)**. 다음 단계는 구현 계획(writing-plans).
> 선행: K-Fashion 셋업 DB 재설계([2026-06-30 v2 design](2026-06-30-clothing-metadata-db-v2-design.md)),
> 기능 카탈로그([features.md](../../idea/features.md) F9 `recommend_bottoms`).

## 배경 / 동기

기획 단계의 추천 도구(F9 `recommend_bottoms`)는 **색상 기반 하의 추천**이 전제였다.
그러나 이후 DB가 K-Fashion **셋업(코디) 26만 건**으로 재설계되면서, 한 행 = 한 이미지이고
컬럼은 `style/substyle` + 부위별 `category/length`(상의·하의·아우터·원피스) + R2 `image_url` 뿐이다.
**색상 컬럼이 없다.** 따라서 추천 도구를 색 기반 하의 추천이 아니라 **스타일 기반 셋업 추천**으로
재정의한다.

## 결정 사항 (확정)

1. **추천 단위 = 셋업(코디)** 전체. 부위 단독(하의만)이 아니라 한 이미지(코디)를 추천한다.
2. **도구 2개, 둘 다 `style` 키.** 입구만 다르고 백엔드 조회는 동일하다.
   - `recommend_outfits_by_style` — 스타일을 직접 받는다.
   - `recommend_outfits_by_situation` — 상황을 받되, **상황→스타일 매핑을 우리가 데이터로
     정의하지 않는다.** docstring 이 호출 LLM 에게 "허용 스타일 23종 중에서 상황에 맞는 것을
     유추해 `style` 인자에 채우라"고 지시한다(매핑 책임을 호스트 LLM 에 위임).
3. **선별 = 무작위 표본 N건** (`ORDER BY RANDOM()`). 기본 3, 범위 1~10.
   - 같은 스타일이 12만 건에 달해 결정적 정렬은 단조롭다. 추천 경험을 위해 매 호출 다양화.
   - 비결정적이므로 `idempotentHint=false` 로 정직하게 신고한다.
4. **출력 = 이미지 URL 마크다운.** 카톡 등 텍스트 호스트는 `ImageContent` 를 못 받으므로
   이미지를 URL 로 출력한다(메모리: playmcp-kakao-image-output, [5.3 응답 이미지 규칙]).
5. **더미 도구 정리.** `tools/example.py`(greet/add)와 `tests/test_tools.py` 는 제거한다
   (이미 반영). 등록 도구는 `extract_color` + 신규 2개 = 3개.

## 도구 표면

### `recommend_outfits_by_style(style: str, n: int = 3) -> str`

- `style`: 추천 기준 스타일. `vocab.STYLES`(23종) 중 하나.
- `n`: 추천 개수. 1~10, 기본 3 (범위 밖은 클램프).
- 반환: 추천 셋업 목록 마크다운(아래 출력 형식).

docstring 요지(영문, "TPO Coach" 포함): 주어진 스타일의 셋업 코디를 무작위 N건 추천한다.
유효 스타일 목록을 함께 안내한다.

### `recommend_outfits_by_situation(situation: str, style: str, n: int = 3) -> str`

- `situation`: 사용자 상황 원문(예: "주말 소개팅"). **조회엔 쓰지 않고** 응답 머리말에만 echo.
- `style`: **LLM 이 `situation` 을 보고 `vocab.STYLES` 23종 중에서 유추해 채운다.**
- `n`: 위와 동일.
- 반환: 상황 머리말 + 추천 셋업 목록 마크다운.

docstring 요지(영문, "TPO Coach" 포함): 상황이 주어지면 허용 스타일 목록에서 가장 적절한
스타일을 유추해 `style` 에 넣어 호출하라. 도구는 그 스타일의 셋업을 무작위 N건 추천하고,
응답 머리말에 상황을 함께 보여준다.

> 두 도구의 DB 조회는 동일(style 로 랜덤 표본). 차이는 (a) 입구/시그니처, (b) docstring 지시문,
> (c) 상황 도구의 응답 머리말뿐이다. 의도 라우팅을 호스트 LLM 이 쉽게 하도록 2개로 분리한다.

## 동작 흐름

```
입력(style[, situation], n)
  │ ① style ∈ vocab.STYLES 검증
  │     └ 아니면: 추천 대신 "유효 스타일 23종" 안내 문자열 반환 (LLM 재시도 유도)
  │ ② n 을 [1, 10] 으로 클램프
  │ ③ repo.sample_outfits(style=style, n=n)  → 무작위 N건
  ▼
출력: (상황 머리말?) + 셋업 N건 마크다운
```

## 저장소 변경 (`db/repository.py`)

`OutfitRepository` Protocol 과 `SQLiteOutfitRepository` 에 표본 메서드 추가:

```python
def sample_outfits(self, *, style: str, n: int) -> list[Outfit]:
    # SELECT * FROM outfits
    # WHERE style = ? AND deleted_at IS NULL
    # ORDER BY RANDOM() LIMIT ?
```

- 기존 `find_outfits`(결정적, `ORDER BY id`)·`get_outfit` 은 변경하지 않는다.
- 성능: 262k 행에서 단일 style 필터(인덱스 `idx_outfits_style`) 후 `ORDER BY RANDOM()`.
  구현 시 최다 스타일(스트리트 ~12만)로 실측해 **p99 3s / 권장 100ms** 충족을 확인한다.
  미달 시 rowid 기반 무작위 선택 등으로 대체(플랜에서 판단).

## 출력 형식

셋업 1건당:

```
![코디](image_url)
- 스타일: {style}{ / substyle 있으면 표기}
- 구성: {있는 부위만} 상의 {top_category}({top_length}) · 하의 ... · 아우터 ... · 원피스 ...
```

- 상황 도구는 맨 위에 머리말: 예) "**주말 소개팅**에 어울리는 **로맨틱** 코디 3선".
- 결과 0건(데이터에 해당 style 없음)일 때: 없음 안내 + 다른 스타일 제안 문구.

## annotations (정직 신고)

| 필드 | 값 | 근거 |
| --- | --- | --- |
| `title` | "Recommend outfit sets by style/situation" | 사람용 제목 |
| `readOnlyHint` | `True` | 읽기 전용 조회 |
| `destructiveHint` | `False` | 파괴적 동작 없음 |
| `openWorldHint` | `False` | 로컬 DB·외부 호출 없음 |
| `idempotentHint` | **`False`** | `ORDER BY RANDOM()` — 매 호출 결과 다름 |

`description`(docstring 첫 줄): "TPO Coach" 포함, 1,024자 이내, 영문 권장.
도구 이름: `A-Za-z0-9_-` 만, `kakao` 금지, 중복 금지 — 둘 다 충족.

## 파일 / 등록

- 신규: `src/playmcp_server/tools/recommend.py` (도구 2개 + `register_tools`).
- `tools/__init__.py:register_tools` 에 `recommend.register_tools(mcp)` 추가.
- 테스트: `tests/test_recommend.py`(도구 동작·검증·클램프), `tests/test_repository.py`
  에 `sample_outfits` 케이스 추가.

## 범위 밖 (YAGNI)

- 색상 기반 매칭/하의 단독 추천(원 F9) — 색 컬럼 부재로 이번 범위에서 제외.
- substyle·부위 category·기장·성별·계절 등 추가 필터 — v1 이후. 지금은 `style` + `n` 만.
- 상황→스타일 결정적 룩업 테이블 — 의도적으로 두지 않음(LLM 위임).
- 옷장 연계(F11)·다중 스타일 동시 조회.

## 테스트 전략

- `sample_outfits`: 지정 style 만 반환 / `deleted_at` 활성만 / `n` 만큼(데이터 충분 시) /
  반환 건이 매 호출 동일하지 않을 수 있음(무작위성은 약하게 검증).
- 도구: 유효 style → N건 마크다운에 `image_url` 포함 / 무효 style → 유효 목록 안내 /
  `n` 범위 클램프 / 상황 도구 머리말에 `situation` echo.
- annotations 5종 노출 확인(list_tools).
```
