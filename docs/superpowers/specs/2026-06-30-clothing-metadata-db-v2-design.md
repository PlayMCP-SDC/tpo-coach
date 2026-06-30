# 의상 메타데이터 DB 설계 v2 (K-Fashion 소스 · LLM 상황해석)

> 작성일: 2026-06-30
> 상태: 설계 (브레인스토밍 결과 반영). 구현 계획·코드 변경은 별도.
> 이 문서는 [2026-06-29 설계](2026-06-29-clothing-metadata-db-design.md) 의
> **셋업/상황(occasion) 부분을 대체**한다. 아래는 그대로 유지된다:
> - 내장 read-only SQLite + 교체 가능한 repository 계층 (§7 동일)
> - 규칙 기반 색 어울림 `color_rules.py` (명명색 16 + 톤온톤/무채색/보색)
> - 응답 이미지 출력 규약 §5.3 (마크다운 `![](url)`)
>
> 개정 이력
> - v1 (06-29): 상황 태그(occasion_tags) 기반 셋업 추천 + 인스타/무신사 스냅 가정
> - **v2 (06-30): 실데이터 소스를 AI Hub K-Fashion 으로 확정. 데이터에 "상황"이
>   없고 "분위기(스타일)+색상"만 있어, 상황 해석을 호스트 LLM 에 위임. 성별 라벨이
>   없어 분류기로 파생. 스키마를 소스에 맞게 재정의.**

## 1. 무엇이 왜 바뀌었나 (핵심 피벗)

데이터 소스를 실제로 확보 가능한 **AI Hub K-Fashion 이미지 데이터셋**(dataSetSn=51)으로
확정하면서 두 가지 사실이 드러났다:

1. **데이터에 "상황(결혼식·놀이동산)"이 없다.** K-Fashion 라벨은 **스타일(분위기) 23종 +
   색상 + 카테고리 + 세부속성**뿐이다. 상황(TPO)은 라벨에 없다.
2. **성별 라벨이 없다.** 남녀 이미지가 섞여 있으나 `gender` 필드가 없다.

→ 그래서 설계를 이렇게 바꾼다:

| v1 (이전) | v2 (현재) | 이유 |
| --- | --- | --- |
| 셋업에 `occasion_tags` 저장, `recommend_outfits(occasion=...)` | **상황은 저장 안 함.** 호스트 LLM 이 상황 → **분위기(style)+색상** 으로 변환해 조회 | 데이터에 상황이 없음. LLM 의 자연어 추론에 맡기는 게 MCP 정석 |
| 성별 개념 없음 | **`gender`(남성/여성/공용) 1급 컬럼.** 임포트 시 이미지 분류기로 파생 | TPO 추천에 성별이 핵심인데 라벨이 없음 |
| 인스타/무신사 스냅(수기) | **K-Fashion(라이선스 확인 전제) + 버킷 이미지 호스팅** | 무신사는 robots.txt 상 자동수집 금지. K-Fashion 은 라벨 풍부 |

## 2. 핵심 설계 결정 #1 — "상황은 LLM 이 분위기·색상으로 변환한다"

사용자가 "결혼식 가는데 셋업 추천해줘"라고 하면, **우리 DB 는 '결혼식'을 모른다.**
대신 흐름은 다음과 같다:

```
사용자: "결혼식 갈 셋업 추천해줘" (남)
   │
   ▼  호스트 LLM 이 "우리가 가진 어휘 안에서" 변환
        결혼식 → style=[클래식], colors=[남색·회색·검정·흰색], gender=남성
   │
   ▼  도구 호출
        recommend_outfits(styles=["클래식"], colors=["남색","회색",...], gender="남성")
   │
   ▼  DB 는 분위기·색상·성별로 "조회"만 (상황은 모름)
   ▼  매칭 셋업 Top-N 반환 → LLM 이 사용자에게 정리
```

- **상황 해석 = 호스트 LLM(자연어 추론)**, **검색 = 우리 DB(속성 조회)**. 역할 분리.
- 무한히 많은 상황을 우리가 태깅할 필요가 없다. 스키마가 단순·안정적이다.

### ⚠️ 이 설계의 단 하나의 필수 조건 — "어휘 노출"

LLM 이 *우리가 실제로 가진* 분위기·색상 안에서만 고르게 하려면, **도구가 가능한 값을
광고**해야 한다. 안 그러면 LLM 이 없는 값("웨딩룩")을 만들어 호출 → 빈 결과.

구현 방법:
1. **도구 파라미터를 enum 으로 정의** — `style`·`color`·`gender` 에 우리 어휘를 enum 으로
   명시 → FastMCP 가 입력 스키마에 노출 → LLM 이 그 안에서만 선택. (1순위)
2. **`list_style_vocabulary` 리소스/도구**(선택) — LLM 이 분위기·색 목록을 먼저 조회 후 매핑.
3. **도구 description 에 매핑 가이드** — 예: "격식 있는 행사면 클래식 분위기 + 무채색/어두운
   색을 우선." → 모델별 편차를 줄여 '안정성' 확보.

### 트레이드오프 (정직하게)

상황→분위기 변환 품질이 **호스트 LLM 에 의존**한다(모델마다 편차 가능). 보정책:
- 도구 description 의 매핑 가이드(위 3번)
- **결과 0건이면 "보유 분위기/색 목록"을 함께 반환** → LLM 이 다시 고르게 하는 폴백

## 3. 데이터 소스 — K-Fashion 라벨 매핑

K-Fashion 라벨 JSON (이미지 1장 = 사람이 입은 한 룩) 구조:

```
라벨링.스타일: [{"스타일":"리조트"}]                       ← 룩 1개당 분위기 1개
라벨링.상의:   [{"색상":"베이지","카테고리":"티셔츠", ...}]   ← 슬롯별 옷
라벨링.하의:   [{"색상":"화이트","카테고리":"팬츠", ...}]
라벨링.아우터/원피스: [{}]                                 ← 없으면 빈칸
렉트좌표/폴리곤좌표: 슬롯별 위치                            ← 옷별 크롭 가능
```

매핑 규칙:

| K-Fashion | 우리 스키마 | 처리 |
| --- | --- | --- |
| 스타일(23종: 리조트·로맨틱·클래식·스트리트…) | `outfits.style` | **우리 style 어휘로 그대로 채택**(23종) |
| 슬롯(상의/하의/아우터/원피스) | `category` (top/bottom/outer/dress) | 직접 매핑 |
| 세부 카테고리(팬츠·티셔츠·드레스) | `subcategory` | 그대로 |
| 색상(화이트·블랙·네이비…) | `color` | **CONVERSION 맵으로 우리 16색에 정규화** (화이트→흰색 등) |
| (없음) 상황 | — | 저장 안 함 (LLM 이 처리, §2) |
| (없음) 성별 | `gender` | **이미지 분류기로 파생** (§6) |
| (없음) 판매처/가격 | `seller_*`/`price` | NULL (K-Fashion 은 커머스 아님). 나중에 커머스 소스로 보강 |

**이미지 1장 → 양쪽 테이블에 적재**:
- `outfits` 1행 = 그 룩 전체 (style, gender, 룩의 색들, 룩 이미지)
- `clothing_items` N행 = 슬롯별 옷 (category, color, gender, 크롭 이미지)

## 4. 스키마 (v2)

### 4.1 outfits — 셋업(룩) 단위

```sql
CREATE TABLE outfits (
    id          TEXT PRIMARY KEY,     -- 'fit_000001'
    image_url   TEXT NOT NULL,        -- 룩 이미지 (버킷 공개 URL)
    style       TEXT NOT NULL,        -- 분위기 1개 (style 어휘) — 주 조회축
    gender      TEXT NOT NULL,        -- '남성' | '여성' | '공용' (파생)
    colors      TEXT NOT NULL,        -- 룩에 등장하는 색들, 정규화 ',흰색,베이지,'
    season      TEXT,                 -- 'spring'|...|'all' | NULL (K-Fashion 엔 없을 수 있음)
    title       TEXT,                 -- 선택
    items_note  TEXT,                 -- 선택: 구성 요약 '티셔츠+팬츠'
    source      TEXT,                 -- 'k-fashion'
    source_id   TEXT                  -- 원본 이미지 식별자
);
CREATE INDEX idx_outfits_style  ON outfits(style);
CREATE INDEX idx_outfits_gender ON outfits(gender);
```

### 4.2 clothing_items — 개별 아이템(슬롯) 단위

```sql
CREATE TABLE clothing_items (
    id           TEXT PRIMARY KEY,    -- 'itm_000001'
    name         TEXT NOT NULL,       -- 파생 '베이지 팬츠'
    category     TEXT NOT NULL,       -- 'top'|'bottom'|'outer'|'dress'
    subcategory  TEXT,                -- '팬츠'|'티셔츠'|'드레스' ...
    color        TEXT NOT NULL,       -- 우리 16색 (정규화)
    gender       TEXT NOT NULL,       -- '남성'|'여성'|'공용'
    image_url    TEXT NOT NULL,       -- 크롭 이미지 or 룩 이미지 (버킷)
    season       TEXT,                -- nullable
    style        TEXT,                -- 출처 룩의 분위기(선택)
    seller_name  TEXT,                -- NULL(K-Fashion). 커머스 보강 시 채움
    seller_url   TEXT,                -- NULL / 구매 링크
    price        INTEGER,             -- NULL / 원
    source       TEXT,                -- 'k-fashion'
    source_outfit_id TEXT             -- 어느 룩에서 왔는지
);
CREATE INDEX idx_items_cat_color  ON clothing_items(category, color);
CREATE INDEX idx_items_gender     ON clothing_items(gender);
```

변경 요지(v1 대비): **`occasion_tags` 제거**, **`gender` 추가**(양 테이블), outfits 에
`style`·`colors` 를 1급 조회축으로, `formality` 는 제거(소스에 없음 — 필요하면 style 에서
파생). 색 매칭 규칙(`color_rules.py`)·repository 패턴은 v1 그대로 유지.

### 4.3 색·태그 매칭 규약 (v1 유지)

- `outfits.colors` 는 정규화 문자열 `,흰색,베이지,` 로 저장 → 정확 토큰 매칭
  `colors LIKE '%,흰색,%'` (부분일치 오탐 방지). 기존 `normalize_tags` 재사용.
- 단일 테이블 + LIKE 스캔은 수천~수만 행 read-only 규모에서 충분히 빠름.

## 5. 어휘 (controlled vocabulary, v2)

`vocab.py` / `color_rules.py` 가 단일 출처. **빌드 검증 + 도구 입력 enum** 에 동시 사용.

- **style (분위기)**: K-Fashion 23종 채택 — 레트로·로맨틱·리조트·매니시·모던·밀리터리·섹시·
  소피스트케이티드·스트리트·스포티·아방가르드·오리엔탈·웨스턴·젠더리스·컨트리·클래식·
  키치/키덜트·톰보이·펑크·페미닌·프레피·히피·힙합. (v1 의 STYLE_TAGS 6종을 대체)
- **color (색)**: 기존 16색 유지(검정·흰색·회색·남색·파랑·하늘색·청록·초록·카키·노랑·주황·
  빨강·분홍·보라·갈색·베이지). `extract_color` 와 동기화. K-Fashion 색은 이 16색으로 매핑.
- **gender**: 남성 · 여성 · 공용.
- **category**: top · bottom · outer · dress (K-Fashion 4슬롯). (shoes 는 소스에 없음)
- **season**: spring·summer·fall·winter·all (nullable, 소스에 없으면 NULL)
- **OCCASION_TAGS 는 제거** (상황은 LLM 이 처리).

## 6. 핵심 설계 결정 #2 — 성별은 임포트 시 분류기로 파생

K-Fashion 에 성별 라벨이 없고, 옷 구성으로 남성을 자동 판별하기 어렵다(남성의 티셔츠+팬츠는
남성 전용 의류가 아님). 따라서:

- 임포트 단계에서 **이미지 성별 분류기** 로 `gender` 를 파생한다.
  - 1순위: `touchtech/fashion-images-gender-age` (패션 이미지 학습, 얼굴 없어도 동작)
  - 대안: FashionCLIP 제로샷("menswear"/"womenswear")
- **애매하면 `공용`** 으로 둔다. 소량 **사람 스팟체크**로 보정.
- 조회 시 **`공용` 은 모든 성별 요청에 포함**(무채색이 모든 색과 매칭되는 것과 동일 논리):
  ```sql
  WHERE gender IN ('남성','공용')   -- 남성 요청 시
  ```
- 주의: 이미지 성별 분류는 오분류·편향 가능 → **런타임 기능이 아니라 임포트 전처리**로만
  사용. 바이어스 캐비엇 명시.

## 7. 데이터 플로우 (v2)

### 7.1 `recommend_outfits` (분위기·색상·성별 기반)

```
입력: styles[](style enum), colors[](16색 enum), gender(enum), season?, limit=5
 ① 입력값을 어휘로 검증 (미등록이면 유효 목록 반환)
 ② repo.find_outfits(styles, colors, gender, season, limit)
      → SELECT * FROM outfits
        WHERE style IN (:styles)
          AND (colors LIKE '%,c1,%' OR colors LIKE '%,c2,%' ...)   -- 색 교집합
          AND gender IN (:gender, '공용')
          [AND (season IS NULL OR season IN (:season,'all'))]
 ③ 정렬: 매칭된 색 수 ↓ → (그 외 동률은 id)
 ④ 반환: Top-N 카드 [{image(![](url)), style, colors, gender, items_note}]
```

### 7.2 `recommend_bottoms` (색 매칭, v1 유지 + gender 추가)

```
입력: top_color(16색), gender?, season?, limit=5
 ① color_rules.harmony(top_color) → 어울리는 색+score (+무채색)
 ② repo.find_bottoms(colors, gender=?, season=?)
      → category='bottom' AND color IN (...) [AND gender IN (:gender,'공용')] [AND season..]
 ③ 정렬: harmony score ↓ → id
 ④ 반환: Top-N 카드 [{name, color, image(![](url)), (seller/price 있으면)}]
```

### 7.3 응답 이미지 출력 규약 (§5.3 v1 유지 — 반드시 준수)

추천 카드 이미지는 **마크다운 `![](image_url)`** 로 응답 텍스트에 담는다(MCP `ImageContent`
base64 아님). 카톡/PlayMCP 실측상 마크다운만 인라인 렌더됨. `image_url` 은 **공개 접근 가능
버킷 URL**(presigned/만료 주의).

## 8. 이미지 호스팅

K-Fashion 이미지는 파일이라 우리 `image_url` 흐름(공개 URL + 마크다운 출력)에 맞추려면 호스팅이
필요하다.

- **S3 / Cloudflare R2 등 오브젝트 스토리지**에 업로드 → 공개 URL 을 `image_url` 에 저장.
- 슬롯별 크롭 이미지는 `렉트좌표`로 잘라 별도 업로드(개별 아이템용). 룩 전체 이미지는 outfit 용.
- ⚠️ **라이선스 게이트**: 버킷에 올려 공개 서빙 = 재배포. **K-Fashion(AI Hub) 이용약관에서
  이미지 재배포·서빙이 허용되는지 반드시 확인**(구축기관 문의). 불가 시 호스팅 대신 다른
  권리 확보 방안 필요. → §11 확인 항목.

## 9. 에러 처리 & 동작 규약

- **DB 파일 없음** → 기동 시 fail-fast, stderr 로그.
- **알 수 없는 style/color/gender** → 유효 목록을 담은 결정적 검증 응답.
- **매칭 0건** → 에러 아님. 빈 결과 + **보유 분위기/색 목록 안내**(LLM 재시도용).
- **read-only 강제** → `file:clothing.db?mode=ro&immutable=1`.
- **annotations**: 두 도구 모두 `readOnlyHint=true, destructiveHint=false,
  idempotentHint=true, openWorldHint=false`.

## 10. 교체 가능성 · 빌드 파이프라인 · 테스트

### 10.1 repository (v1 유지, 시그니처만 갱신)

```python
class ClothingRepository(Protocol):
    def get_item(self, item_id: str) -> ClothingItem | None: ...
    def find_bottoms(self, colors: list[str], *, gender: str | None,
                     season: str | None) -> list[ClothingItem]: ...
    def get_outfit(self, outfit_id: str) -> Outfit | None: ...
    def find_outfits(self, *, styles: list[str], colors: list[str],
                     gender: str | None, season: str | None,
                     limit: int) -> list[Outfit]: ...
```

지금은 `SQLiteClothingRepository` 만. 라이브 편집/대규모/사용자 쓰기 필요 시 같은 Protocol
구현체(Postgres 등)로 교체.

### 10.2 빌드 파이프라인 (v2)

```
K-Fashion (이미지 + 라벨 JSON)
  │ ① 라벨 파싱 (슬롯별 색/카테고리/스타일)
  │ ② 색·카테고리·스타일 → 우리 어휘 매핑 (CONVERSION 맵)
  │ ③ 성별 파생 (이미지 분류기) + 스팟체크
  │ ④ 이미지 버킷 업로드(룩 + 슬롯 크롭) → 공개 URL
  ▼
 중간 CSV (clothing_items.csv / outfits.csv)
  │ ⑤ build_db.py: 어휘 검증 + 색/태그 정규화 → read-only clothing.db
  ▼
 컨테이너 동봉 clothing.db
```

- 중간 산출물을 CSV 로 두면 사람이 검수·수정 가능(스팟체크 결과 반영).
- `build_db.py` 가 style/color/gender/category 어휘를 검증(미등록 = 빌드 실패).

### 10.3 테스트 & 성능

- fixture 시드로 `:memory:` DB 빌드 → repository·color_rules·tool 결정적 검증.
- find_outfits: style·gender(+공용)·색 토큰 매칭·0건 폴백 검증.
- 성능: read-only·인덱스·인메모리급 → 100ms 목표 충분. 외부 네트워크 없음.

## 11. 확인·미해결 항목 (구현 전 결정 필요)

- [ ] **AI Hub K-Fashion 라이선스** — 이미지 버킷 공개 서빙(재배포) 허용 여부. 불가 시 대안.
- [ ] **남성 데이터 분량** — 어떤 스타일 폴더에 남성이 충분한지(스트리트/힙합/스포티 등) 확인.
- [ ] **season 확보** — K-Fashion 라벨에 계절이 없으면 NULL 로 둘지, 다른 단서로 파생할지.
- [ ] **성별 분류기 정확도** — 스팟체크 표본으로 오분류율 확인, `공용` 기준 정의.
- [ ] **K-Fashion 색 어휘 → 16색 매핑표** 확정(실제 색 라벨 목록 확인 후).

## 12. 기존 구현(Task 1–7)에 대한 영향 (메모, 코드 변경은 별도)

이미 구현된 데이터 계층은 v1 기준이라 v2 적용 시 다음 변경이 필요하다(이번엔 문서만):
- `vocab.py`: OCCASION_TAGS 제거, STYLE 23종으로 확장, gender 어휘 추가
- `models.py`: `Outfit`/`ClothingItem` 에 `gender` 추가, occasion 제거, outfits 필드 재정의
- `schema.py`: 두 테이블 v2 스키마로
- `repository.py`: `find_outfits(styles, colors, gender, ...)`, `find_bottoms(+gender)`
- `build_db.py`: 어휘 검증 갱신 + 색/스타일 매핑
- 시드/도구(Task 8·9): v2 시그니처·어휘 노출로 재정의

## 13. 향후 확장 (범위 밖)

- 커머스 소스(네이버 쇼핑 API 등)로 **판매처·가격·구매링크** 보강 → 실구매 연결
- HSL 보조 컬럼으로 톤 세분화
- 셋업↔아이템 명시적 연결 테이블(현재는 `source_outfit_id` 로 느슨히 연결)
- 성별 분류 사람 검수 비율 상향 / 능동 학습
