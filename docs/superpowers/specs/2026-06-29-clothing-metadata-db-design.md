# 의상 메타데이터 DB 설계

> 작성일: 2026-06-29
> 대상 기능: F8 `extract_color` → F9 `recommend_bottoms` (색상 기반 착장 추천, v1)
> 상태: 설계 확정 (브레인스토밍 승인). 구현 계획은 별도 plan 문서로.

## 1. 배경과 범위

TPO Coach 의 색상 기반 착장 추천(F8/F9)을 뒷받침하는 **의상 메타데이터 저장소**를
설계한다. `recommend_bottoms` 는 기준 상의의 색에서 출발해, 어울리는 하의 후보를
이 저장소에서 찾아 Top-N 으로 추천한다.

이 문서의 범위는 **데이터 저장·접근 계층과 스키마**다. 도구의 입출력 스키마/annotations
최종 확정, 위젯 응답 포맷, extract_color 의 이미지 처리 UX 는 별도 과제다.

### 확정된 전제 (브레인스토밍 결정)

| 항목 | 결정 | 근거 |
| --- | --- | --- |
| DB 성격 | **큐레이션된 레퍼런스** (수백~수천 건, 거의 불변) | 라이브 카탈로그가 아니라 사람이 엄선한 참고 데이터 |
| 매칭 방식 | **규칙 기반 색 매칭** | 결정적·설명가능·가벼움 → stateless/100ms 목표에 유리 |
| 저장소 | **내장 read-only SQLite + 교체 가능한 repository 계층** | 네트워크 0, 외부 의존 없음 → 안정성·속도. 미래 교체 여지 확보 |
| 데이터 단위 | **개별 의상 아이템** (한 행 = 옷 한 점) | 규칙 매칭과 정합, 정규화 용이 |
| 색 표현 | **명명된 색 태그소니(enum)** + 색×색 어울림 룩업 | 결정적·설명가능·쿼리 용이 |
| 시드 형식 | **CSV** | 평면 스키마, 시트로 대량 편집·PR diff 명확 |

### 제약 (프로젝트 공통)

- stateless MCP, 카카오 클라우드 `streamable-http` 배포
- 응답 평균 100ms / p99 3,000ms
- stdout 금지 (로그는 stderr/logging)
- 도구 ≤ 20개 (3~10 권장), annotations 5종 정직 신고

## 2. 아키텍처 개요

```
LLM(host) ──tool call──► recommend_bottoms / extract_color
                              │
                              ├─► color_rules.py   (명명색 enum + 어울림 룩업, 순수 함수)
                              │
                              └─► ClothingRepository (인터페이스/Protocol)
                                        │
                                        └─ SQLiteClothingRepository  ← read-only clothing.db (컨테이너 동봉)
                                           (나중에 PostgresRepository / SupabaseRepository 로 교체 가능)
```

핵심 원칙: **저장(repository)·규칙(color_rules)·도구(tool) 분리.** 도구는 SQLite 를
직접 알지 못하고 `ClothingRepository` 인터페이스에만 의존한다 → 백엔드 교체가 도구
코드에 영향을 주지 않는다.

## 3. 컴포넌트

각 컴포넌트는 하나의 책임을 가지며, 인터페이스로 통신하고, 독립적으로 테스트 가능하다.

| 모듈 | 책임 | 의존 |
| --- | --- | --- |
| `data/clothing_items.csv` | 사람이 편집하는 시드(아이템 카탈로그). git 버전관리 | — |
| `scripts/build_db.py` | 시드 CSV → read-only `clothing.db` 생성 (빌드 시점·로컬·테스트) | csv |
| `db/repository.py` | `ClothingRepository` Protocol + `SQLiteClothingRepository` 구현 | sqlite3 |
| `db/color_rules.py` | 명명색 enum + 색×색 어울림 룩업(보색/톤온톤/무채색) | — |
| `models.py` | 공유 타입 `ClothingItem` (기존 공유타입 파일에 합류) | — |
| `tools/recommend_bottoms.py` | F9: 입력색 → 규칙 → repo 조회 → Top-N | repository, color_rules |

> 각 단위에 대해 답할 수 있어야 한다: 무엇을 하는가 / 어떻게 쓰는가 / 무엇에 의존하는가.
> repository 는 "데이터를 조회한다", color_rules 는 "색 어울림을 판정한다", tool 은
> "둘을 엮어 추천을 만든다" — 내부 구현을 몰라도 역할이 명확하다.

## 4. 스키마

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
    season       TEXT,                     -- 'spring'|'summer'|'fall'|'winter'|'all' — 날씨 슬롯
    style_tags   TEXT                      -- 쉼표구분 'minimal,classic' (선택)
);
CREATE INDEX idx_items_cat_color ON clothing_items(category, color);
CREATE INDEX idx_items_cat_formality ON clothing_items(category, formality);
```

### 색 어울림 규칙

색×색 어울림(`color_harmony`)은 **DB 테이블이 아니라 `color_rules.py` 코드에 둔다.**
작고(수십 행) 로직성이며, 색 enum 과 함께 테스트·리뷰하는 게 자연스럽기 때문이다.

```python
# color_rules.py 개념
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

harmony_type 종류: `neutral`(무채색 매칭), `tone`(톤온톤), `complementary`(보색).
무채색(black/white/gray)은 거의 모든 색과 어울리므로 항상 후보에 포함한다.

## 5. 데이터 플로우 (`recommend_bottoms`)

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

`why`(추천 이유: "네이비 상의에 베이지는 톤온톤으로 어울려요")를 포함해 **설명가능성
(안정성 평가지표)** 을 확보한다. 카드 형태 출력은 위젯/리치 UI 와 친화적이다.

## 6. 에러 처리 & 동작 규약

- **DB 파일 없음** → 서버 기동 시 fail-fast, stderr 로그 (stdout 금지 규칙 준수)
- **알 수 없는 색** → 유효 색 목록을 담은 결정적 검증 에러 반환
- **매칭 0건** → 에러 아님. 빈 결과 + "필터를 완화해 보세요" 안내
- **read-only 강제** → `sqlite3.connect("file:clothing.db?mode=ro&immutable=1", uri=True)`
  — 쓰기 차단 + 동시 읽기 안전
- **annotations**: `recommend_bottoms` → `readOnlyHint=true, destructiveHint=false,
  idempotentHint=true, openWorldHint=false` (외부 호출 없음·결정적 = 정직한 신고)

## 7. 교체 가능성 (설계 핵심)

```python
class ClothingRepository(Protocol):
    def get_item(self, item_id: str) -> ClothingItem | None: ...
    def find_bottoms(self, colors: list[str], *, formality: int | None,
                     season: str | None, limit: int) -> list[ClothingItem]: ...
    def find_by_category(self, category: str, **filters) -> list[ClothingItem]: ...
```

지금은 `SQLiteClothingRepository` 만 구현한다. 나중에 라이브 편집/대규모 카탈로그가
필요해지면 **같은 Protocol 을 구현하는** `PostgresClothingRepository` 를 추가하고,
주입 지점(서버 기동 시 1곳)만 교체한다. 도구·규칙 코드는 변경하지 않는다.

### 언제 백엔드를 교체하나 (재평가 트리거)

- 비개발 팀원이 데이터를 수시로 **라이브 편집**해야 할 때
- 이미지를 직접 **호스팅**해야 할 때
- **라이브 카탈로그**(수만 건, 잦은 갱신)로 확장할 때
- 사용자 **쓰기**(찜·옷장)를 추가할 때 (현재 stateless 라 범위 밖)

## 8. 테스트 & 성능

- **테스트**: 작은 fixture 시드로 `:memory:` DB 를 빌드해 repository·color_rules·tool 을
  결정적으로 검증한다. 기존 in-memory MCP transport 패턴을 재사용한다.
  - color_rules: 어울림 룩업의 대칭성/무채색 포함/score 범위 단위 테스트
  - repository: 색·카테고리·formality·season 필터 조회 검증
  - tool: 입력색 → Top-N 정렬·카드 형태·0건 처리 검증
- **성능**: read-only·인덱스·인메모리급 → 쿼리 1ms 미만, 100ms 목표 충분. 외부
  네트워크 없음 → p99 안정.
- **동시성**: stateless streamable-http 다중 요청 ↔ SQLite read-only 는 동시 읽기
  문제 없음.

## 9. 데이터 빌드 파이프라인

1. `data/clothing_items.csv` 를 사람이 편집(엑셀/시트 → CSV export, git 커밋)
2. 컨테이너 빌드 시 `scripts/build_db.py` 가 CSV → `clothing.db`(read-only) 생성
3. 로컬·테스트도 동일 스크립트로 생성 → 환경 간 일관성
4. 데이터 갱신 = 시드 수정 + 재배포 (거의 불변 데이터라 빈도 낮음)

빌드 스크립트는 시드 유효성(색 enum·카테고리 enum·필수 컬럼)을 검증해 잘못된 데이터가
DB 에 들어가지 않게 한다.

## 10. 향후 확장 (범위 밖, 메모)

- HSL 보조 컬럼 추가 → 톤 세분화 (현재는 명명색만)
- 임베딩 기반 스타일 유사도(하이브리드) — 비용/복잡도 트레이드오프
- 개별 아이템 외 큐레이션 셋업(상+하 쌍) 보강 테이블
- extract_color 의 이미지 색 추출 정확도 향상
