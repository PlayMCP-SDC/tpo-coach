# 의상 메타데이터 DB 설계

> 작성일: 2026-06-29
> 대상 기능:
> - F8 `extract_color` → F9 `recommend_bottoms` (색상 기반 하의 추천, v1)
> - **`recommend_outfits` (상황 기반 코디 추천, 신규)**
> 상태: 설계 확정 (브레인스토밍 승인). 구현 계획은 별도 plan 문서로.
>
> 개정 이력
> - 2026-06-29 초안: clothing_items + 규칙 색 매칭
> - 2026-06-29 개정: **셋업(코디) 자기완결 단일 테이블 추가** — 인스타/무신사 스냅 출처,
>   개별 아이템 정보가 불완전하므로 정규화하지 않고 룩 단위로 안정 저장
> - 2026-06-29 개정: **응답 이미지 출력 규약(5.3) 추가** — 카톡/PlayMCP 실측 결과
>   마크다운 `![](url)` 만 인라인 렌더됨(ImageContent 불가) → 이미지는 URL로 출력

## 1. 배경과 범위

TPO Coach 는 두 가지 추천을 제공한다.

1. **하의 색 매칭** (`recommend_bottoms`): 기준 상의의 색에서 출발해 어울리는 하의 후보를
   **개별 아이템 카탈로그**에서 찾아 Top-N 추천. (규칙 기반 색 매칭)
2. **상황 기반 코디 추천** (`recommend_outfits`): "놀이동산에 어울리는 코디 5개" 처럼
   상황/스타일 태그로 **큐레이션된 셋업(완성 룩)** 을 조회해 추천.

이 두 기능은 **데이터 출처와 품질이 다르므로 독립된 데이터셋**으로 둔다.

```
clothing_items  ──► recommend_bottoms  (깨끗한 개별 아이템 + 규칙 색 매칭)
outfits(셋업)    ──► recommend_outfits  (인스타/무신사 스냅 룩 + 상황 태그)
```

이 문서의 범위는 **데이터 저장·접근 계층과 스키마**다. 도구의 입출력 스키마/annotations
최종 확정, 위젯 응답 포맷, extract_color 의 이미지 처리 UX 는 별도 과제다.

### 확정된 전제 (브레인스토밍 결정)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| DB 성격 | **큐레이션된 레퍼런스** (수백~수천 건, 거의 불변) | 라이브 카탈로그가 아니라 사람이 엄선한 참고 데이터 |
| 매칭 방식 | **규칙 기반 색 매칭** (하의 추천) | 결정적·설명가능·가벼움 → stateless/100ms 목표에 유리 |
| 저장소 | **내장 read-only SQLite + 교체 가능한 repository 계층** | 네트워크 0, 외부 의존 없음 → 안정성·속도. 미래 교체 여지 확보 |
| 아이템 단위 | **개별 의상 아이템** (한 행 = 옷 한 점) | 규칙 매칭과 정합, 정규화 용이 |
| 색 표현 | **명명된 색 태그소니(enum)** + 색×색 어울림 룩업 | 결정적·설명가능·쿼리 용이 |
| **셋업 단위** | **자기완결 단일 테이블** (조인 테이블 없음) | 스냅 출처라 개별 아이템 정보가 불완전 → 룩 단위 안정 저장 |
| 시드 형식 | **CSV** | 평면 스키마, 시트로 대량 편집·PR diff 명확 |

### 셋업을 단일 테이블로 두는 이유 (데이터 안정성)

셋업 데이터는 인스타그램·무신사 **스냅(완성 룩 사진 + 상황/스타일 태그)** 에서 온다.
스냅 안의 개별 아이템(정확한 상품명·색·판매 링크)은 **불완전하거나 없는 경우가 많다.**
따라서 아이템을 정규화(조인)하려 하면 식별·매칭이 자주 불가능해 데이터가 불안정해진다.

→ 셋업은 **그 자체로 1급 엔티티**로, 룩 이미지 + 태그 + 출처를 자기완결적으로 저장한다.
   개별 아이템 정보는 *있을 때만* 비정규 텍스트(`items_note`)로 보조 기록한다(관계 아님).

### 제약 (프로젝트 공통)

- stateless MCP, 카카오 클라우드 `streamable-http` 배포
- 응답 평균 100ms / p99 3,000ms
- stdout 금지 (로그는 stderr/logging)
- 도구 ≤ 20개 (3~10 권장), annotations 5종 정직 신고

## 2. 아키텍처 개요

```
LLM(host) ──tool call──► recommend_bottoms     recommend_outfits
                              │                       │
              ┌───────────────┘                       │
              ▼                                        ▼
       color_rules.py                          (상황/스타일 태그 필터)
   (명명색 enum + 어울림 룩업)                          │
              │                                        │
              └──────────────► ClothingRepository ◄────┘  (인터페이스/Protocol)
                                        │
                                        └─ SQLiteClothingRepository
                                           ← read-only clothing.db (컨테이너 동봉)
                                           (나중에 Postgres/Supabase 로 교체 가능)
```

핵심 원칙: **저장(repository)·규칙(color_rules)·도구(tool) 분리.** 도구는 SQLite 를
직접 알지 못하고 `ClothingRepository` 인터페이스에만 의존한다 → 백엔드 교체가 도구
코드에 영향을 주지 않는다.

## 3. 컴포넌트

각 컴포넌트는 하나의 책임을 가지며, 인터페이스로 통신하고, 독립적으로 테스트 가능하다.

| 모듈 | 책임 | 의존 |
| --- | --- | --- |
| `data/clothing_items.csv` | 개별 아이템 시드(카탈로그). git 버전관리 | — |
| `data/outfits.csv` | 셋업(코디) 시드. 스냅 룩 + 태그 + 출처 | — |
| `scripts/build_db.py` | 시드 CSV → read-only `clothing.db` 생성 (빌드·로컬·테스트) + 유효성 검증 | csv |
| `db/repository.py` | `ClothingRepository` Protocol + `SQLiteClothingRepository` 구현 | sqlite3 |
| `db/color_rules.py` | 명명색 enum + 색×색 어울림 룩업(보색/톤온톤/무채색) | — |
| `models.py` | 공유 타입 `ClothingItem`, `Outfit` (기존 공유타입 파일에 합류) | — |
| `tools/recommend_bottoms.py` | F9: 입력색 → 규칙 → repo 조회 → Top-N | repository, color_rules |
| `tools/recommend_outfits.py` | 신규: 상황/스타일 태그 → repo 조회 → Top-N | repository |

## 4. 스키마

### 4.1 clothing_items (개별 아이템 — 색 매칭용)

```sql
CREATE TABLE clothing_items (
    id           TEXT PRIMARY KEY,         -- 'itm_0001'
    name         TEXT NOT NULL,            -- '슬림 치노 팬츠'
    category     TEXT NOT NULL,            -- 'top' | 'bottom' | 'outer' | 'dress' | 'shoes'
    subcategory  TEXT,                     -- 'jeans' | 'slacks' | 'skirt' ...
    color        TEXT NOT NULL,            -- 명명색 enum 값 ('navy', 'beige' ...)
    image_url    TEXT NOT NULL,            -- 참고 이미지 링크 (바이너리 저장 X)
    seller_name  TEXT,                     -- '무신사'
    seller_url   TEXT,                     -- 구매 페이지 링크
    price        INTEGER,                  -- 원 단위, nullable
    formality    INTEGER NOT NULL DEFAULT 3, -- 1(캐주얼)~5(포멀) — F2 권장수준 연동
    season       TEXT,                     -- 'spring'|'summer'|'fall'|'winter'|'all'
    style_tags   TEXT                      -- 쉼표구분 'minimal,classic' (선택)
);
CREATE INDEX idx_items_cat_color ON clothing_items(category, color);
CREATE INDEX idx_items_cat_formality ON clothing_items(category, formality);
```

### 4.2 outfits (셋업/코디 — 자기완결 단일 테이블)

```sql
CREATE TABLE outfits (
    id            TEXT PRIMARY KEY,        -- 'fit_0001'
    title         TEXT,                    -- '놀이동산 캐주얼 코디'
    image_url     TEXT NOT NULL,           -- 스냅 룩 이미지 (한 장)
    source        TEXT,                    -- 'instagram' | 'musinsa' ...
    source_url    TEXT,                    -- 원본 게시물 링크 (출처/구매 우회 + attribution)
    formality     INTEGER,                 -- 1(캐주얼)~5(포멀)
    season        TEXT,                    -- 'spring'|'summer'|'fall'|'winter'|'all'
    occasion_tags TEXT NOT NULL,           -- 상황 태그 (구분자 정규화, 아래 규약)
    style_tags    TEXT,                    -- 스타일 태그 '캐주얼,스트릿'
    items_note    TEXT                     -- (선택) 알려진 구성 아이템 자유기술 '흰 티, 데님 팬츠, 스니커즈'
);
CREATE INDEX idx_outfits_formality ON outfits(formality);
CREATE INDEX idx_outfits_season ON outfits(season);
```

- `items_note` 는 **관계가 아니라 메모**다. 스냅에서 알 수 있는 만큼만 자유 텍스트로
  기록해 LLM 이 룩을 설명하는 데 쓴다. 없으면 비워둔다 → 스냅 불완전성 흡수.
- 개별 아이템 구매 연결이 필요하면 `source_url`(원본 스냅)로 우회한다.

### 4.3 태그 표현·매칭 규약 (단일 테이블 일관성)

`occasion_tags`·`style_tags` 는 **통제 어휘(controlled vocabulary)** 의 쉼표 구분 문자열로
저장한다. 별도 태그 테이블 없이 단일 테이블을 유지하되, 매칭 정확도를 위해 다음 규약을 둔다.

- 저장 시 앞뒤 구분자를 포함해 정규화: `,놀이동산,데이트,` (부분일치 오탐 방지)
- 조회 시 정확 토큰 매칭: `occasion_tags LIKE '%,놀이동산,%'`
- 통제 어휘는 `build_db.py` 가 검증한다(미등록 태그 = 빌드 실패). 어휘 목록은 F3 드레스코드
  시나리오(하객룩·골프장·소개팅·놀이동산 …)와 정렬한다.

> 트레이드오프: 단일 테이블 + LIKE 토큰 매칭은 정규화 태그 테이블보다 인덱스 효율이
> 낮지만, 수백~수천 행 read-only 규모에선 풀스캔도 1ms 급이라 실질 문제 없다.
> 단순성·안정성 우선.

### 4.4 색 어울림 규칙 (코드, DB 아님)

색×색 어울림은 작고(수십 행) 로직성이라 `color_rules.py` 코드에 둔다(색 enum 과 함께
테스트·리뷰). DB 테이블로 두지 않는다.

```python
class Color(StrEnum):  # 12색상환 + 무채색
    RED = "red"; ORANGE = "orange"; YELLOW = "yellow"; GREEN = "green"
    BLUE = "blue"; NAVY = "navy"; PURPLE = "purple"; PINK = "pink"
    BROWN = "brown"; BEIGE = "beige"
    BLACK = "black"; WHITE = "white"; GRAY = "gray"  # 무채색은 거의 모든 색과 매칭

# base_color -> [(match_color, harmony_type, score)]
HARMONY: dict[Color, list[tuple[Color, str, float]]] = {
    Color.NAVY: [
        (Color.WHITE, "neutral", 1.0),
        (Color.BEIGE, "tone", 0.9),
        (Color.ORANGE, "complementary", 0.7),
    ],
    # ...
}

def harmony(base: Color) -> list[tuple[Color, str, float]]:
    """기준색과 어울리는 색 목록(+무채색)을 score 와 함께 반환."""
```

harmony_type: `neutral`(무채색), `tone`(톤온톤), `complementary`(보색). 무채색은 항상 후보 포함.

## 5. 데이터 플로우

### 5.1 `recommend_bottoms` (색 매칭)

```
입력: top_color(명명색), formality?(1~5), season?, limit=5
 ① color_rules.harmony(top_color) → 어울리는 색 목록 + score (+ 무채색 항상 포함)
 ② repo.find_bottoms(colors=[...], formality=?, season=?, limit)
      → SELECT * FROM clothing_items
        WHERE category='bottom' AND color IN (:colors)
          [AND formality BETWEEN ...] [AND (season IN (:season,'all') OR season IS NULL)]
 ③ 정렬: harmony score ↓ → formality 적합 → (price ↑)
 ④ 반환: Top-N 카드 [{name, color, image_url, seller, price, why}]
```

### 5.2 `recommend_outfits` (상황 기반 코디)

```
입력: occasion(예 '놀이동산'), style?(예 '캐주얼'), formality?, season?, limit=5
 ① 입력 태그를 통제 어휘로 정규화/검증
 ② repo.find_outfits(occasion=, style=?, formality=?, season=?, limit)
      → SELECT * FROM outfits
        WHERE occasion_tags LIKE '%,'||:occasion||',%'
          [AND style_tags LIKE ...] [AND formality BETWEEN ...] [AND season ...]
 ③ 정렬: 태그 적합도 → formality 근접 → (최신/큐레이션 우선)
 ④ 반환: Top-N 코디 카드 [{title, image_url, source, source_url, items_note, why}]
```

두 도구 모두 `why`(추천 이유)와 출처를 포함해 **설명가능성·안정성(평가지표)** 을 확보한다.
카드 형태 출력은 위젯/리치 UI 와 친화적이다.

### 5.3 응답 이미지 출력 규약 (실측 확정 — 반드시 준수)

추천 카드의 `image_url` 은 **마크다운 이미지 문법 `![](image_url)` 으로 응답 텍스트에 담아**
출력한다. base64 이미지(MCP `ImageContent`) 방식은 쓰지 않는다.

근거 (2026-06-29 카톡/PlayMCP 실측):

| 출력 방식 | 카카오톡 결과 |
| --- | --- |
| 마크다운 `![](url)` | ✅ **채팅에 인라인 이미지로 렌더됨** (placehold.co 600×400 PNG로 확인) |
| MCP `ImageContent` (base64) | ❌ 카톡이 받지 못함(렌더 안 됨). PlayMCP 20k 글자 제한에도 불리 |

- 따라서 이미지 바이트를 응답에 직접 싣지 않는다 → DB(`image_url`)에 저장된 **URL을 그대로**
  마크다운으로 내보낸다. (응답 경량화 + p99 3,000ms 규칙에도 유리)
- 호스트가 마크다운을 안 그리는 경우라도 URL 텍스트로 식별 가능하므로 **결과 웹페이지 폴백은
  불필요**하다(현재 카톡 기준 확인됨).
- 외부 이미지 호스팅(S3 등)을 쓸 경우 URL은 **공개 접근 가능**해야 한다(presigned/만료 주의).

## 6. 에러 처리 & 동작 규약

- **DB 파일 없음** → 서버 기동 시 fail-fast, stderr 로그 (stdout 금지 규칙 준수)
- **알 수 없는 색/태그** → 유효 목록을 담은 결정적 검증 에러 반환
- **매칭 0건** → 에러 아님. 빈 결과 + "필터를 완화해 보세요" 안내
- **read-only 강제** → `sqlite3.connect("file:clothing.db?mode=ro&immutable=1", uri=True)`
  — 쓰기 차단 + 동시 읽기 안전
- **annotations**: `recommend_bottoms`·`recommend_outfits` 모두 `readOnlyHint=true,
  destructiveHint=false, idempotentHint=true, openWorldHint=false` (외부 호출 없음·결정적)

## 7. 교체 가능성 (설계 핵심)

```python
class ClothingRepository(Protocol):
    # 개별 아이템 (색 매칭)
    def get_item(self, item_id: str) -> ClothingItem | None: ...
    def find_bottoms(self, colors: list[str], *, formality: int | None,
                     season: str | None, limit: int) -> list[ClothingItem]: ...
    # 셋업 (상황 코디)
    def get_outfit(self, outfit_id: str) -> Outfit | None: ...
    def find_outfits(self, *, occasion: str, style: str | None,
                     formality: int | None, season: str | None,
                     limit: int) -> list[Outfit]: ...
```

지금은 `SQLiteClothingRepository` 만 구현(하나의 db 파일에 두 테이블). 나중에 라이브
편집/대규모가 필요해지면 **같은 Protocol 을 구현하는** `PostgresClothingRepository` 를
추가하고 주입 지점(서버 기동 시 1곳)만 교체한다. 도구·규칙 코드는 변경하지 않는다.

### 언제 백엔드를 교체하나 (재평가 트리거)

- 비개발 팀원이 데이터를 수시로 **라이브 편집**해야 할 때
- 이미지를 직접 **호스팅**해야 할 때
- **라이브 카탈로그**(수만 건, 잦은 갱신)로 확장할 때
- 사용자 **쓰기**(찜·옷장)를 추가할 때 (현재 stateless 라 범위 밖)

## 8. 테스트 & 성능

- **테스트**: 작은 fixture 시드로 `:memory:` DB 를 빌드해 결정적으로 검증.
  - color_rules: 어울림 룩업의 무채색 포함/score 범위 단위 테스트
  - repository: `find_bottoms`(색·카테고리·formality·season), `find_outfits`(태그 토큰
    매칭 정확성·필터) 검증
  - tools: Top-N 정렬·카드 형태·0건 처리·잘못된 색/태그 검증
  - 기존 in-memory MCP transport 패턴 재사용
- **성능**: read-only·인덱스·인메모리급 → 쿼리 1ms 미만, 100ms 목표 충분. 외부
  네트워크 없음 → p99 안정.
- **동시성**: stateless streamable-http 다중 요청 ↔ SQLite read-only 는 동시 읽기 문제 없음.

## 9. 데이터 빌드 파이프라인

1. `data/clothing_items.csv`, `data/outfits.csv` 를 사람이 편집(시트 → CSV, git 커밋)
2. 컨테이너 빌드 시 `scripts/build_db.py` 가 두 CSV → `clothing.db`(read-only) 생성
3. 로컬·테스트도 동일 스크립트로 생성 → 환경 간 일관성
4. 데이터 갱신 = 시드 수정 + 재배포 (거의 불변 데이터라 빈도 낮음)

`build_db.py` 는 시드 유효성을 검증해 잘못된 데이터의 유입을 막는다:
- 필수 컬럼 존재, 색 enum·카테고리 enum 값 검증
- `occasion_tags`·`style_tags` 가 통제 어휘에 속하는지 검증
- 태그 저장 시 앞뒤 구분자 정규화(`,a,b,`) 적용

## 10. 데이터 안정성·저작권 메모

- 인스타/무신사 이미지는 **복사 저장보다 `source_url` 출처 링크 + attribution** 우선
  (이용약관·저작권 리스크 회피, 공모전 안정성). 이미지 직접 호스팅은 백엔드 교체
  트리거에 해당.
- 셋업의 개별 아이템 구매 연결은 원본 스냅(`source_url`)으로 우회한다.

## 11. 향후 확장 (범위 밖, 메모)

- HSL 보조 컬럼 추가 → 톤 세분화 (현재는 명명색만)
- 임베딩 기반 스타일 유사도(하이브리드) — 비용/복잡도 트레이드오프
- 셋업 ↔ 아이템 선택적 연결 테이블(`outfit_items`) — 아이템 정보가 충분히 쌓일 때 도입
- extract_color 의 이미지 색 추출 정확도 향상
