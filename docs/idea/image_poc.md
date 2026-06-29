# 이미지 색상 추출 PoC — 설계 & 구현

> 상태: **구현 완료 · 검증됨**(ruff/pytest/로컬). PoC = **"사용자가 옷 사진을 한 번 업로드 → MCP가 대표 색상을 텍스트로 반환"**.
> 외부 비전 모델/키 없이(Pillow) 처리하므로 **완전 모델 독립 + PlayMCP 텍스트 호스트 호환**. 근거: [image-input.md](image-input.md)

## 왜 "색상 추출"인가 (결정 경위)

이 PoC는 처음엔 "이미지 설명"이었고 두 방향을 시도했다:

1. **A — 도구가 이미지(ImageContent) 반환, 호스트 모델이 설명** → **PlayMCP AI Chat에서 실패**(작은 이미지도 "답변 생성 중 오류"). 즉 **PlayMCP는 도구 결과의 이미지를 모델에 안 넘긴다**(실측 확인). 카탈로그 API 조사에서도 등록작 261개 도구 중 **이미지 입력/반환 도구 0개** — 전부 텍스트 in/out.
2. **B — 도구가 비전 모델 호출해 텍스트 반환** → PlayMCP 동작 O. 단 **서버가 비전 모델·API 키 필요.**

그런데 우리 실제 목표는 **"옷 색 추출 → 유사 색 판단 → 어울리는 하의 추천"**. 여기서 **1단계(색 추출)는 비전 모델 없이 Pillow로 가능**하다. 그래서:

- **결론: 색상 추출은 로컬 계산(Pillow)으로 → 모델/키 0, 텍스트 반환 → PlayMCP 호환 + 완전 모델 독립.**
- (착장 "적절성 판단" 같이 모델이 꼭 필요한 기능은 나중에 B로 추가 결정.)

## 전체 흐름

```
[임의의 호스트]            [브라우저 /upload]        [MCP 서버 (/mcp + /upload)]
 Claude/ChatGPT/PlayMCP      │── POST multipart ──────►│ 검증·EXIF제거·리사이즈·메모리저장 │
   │  옷 사진 업로드 ────────►│                          │  (TTL 10분)                      │
   │                          │◄── 참조 URL /i/<token> ─┤                                  │
   │◄── URL 복사 ─────────────┤                          │                                  │
   │── "이 옷 색 뽑아줘 [URL]"────(MCP tool call)───────►│ extract_color(image_ref)         │
   │                          │                          │  token→bytes→Pillow 색 분석      │
   │◄──── 대표 색상(텍스트) ────────────────────────────┤  (외부 호출 없음)                │
```

핵심: 도구는 외부 URL을 다운로드하지 않고, 업로드 시 메모리에 들어간 바이트를 **로컬에서 분석**해 텍스트로 돌려준다. → SSRF 없음, 모델/키 없음, p99 여유(128px 썸네일 연산 수 ms).

## 구성 요소 (구현됨)

### 1) 업로드 엔드포인트 — `web/upload.py`
[image-input.md](image-input.md) 패턴 A(메모리 store). `/upload`(폼·검증·EXIF제거·긴변 1024px 리사이즈·JPEG 재인코딩·TTL 10분), `/i/{token}` 서빙, `store_image`/`get_image_bytes`, `register_routes`(FastMCP `custom_route`).

### 2) MCP 도구 — `extract_color` (`tools/color.py`)
| 항목 | 값 |
| --- | --- |
| 이름 | `extract_color` |
| 파라미터 | `image_ref: str` (업로드 URL 또는 token) |
| 반환 | `str` (마크다운: 대표 색 hex·한글 이름·비율) |
| 처리 | Pillow median-cut 양자화 → 상위 색 + 가장 가까운 의류 색 이름 매핑 |

annotations 5종: `title="Extract clothing colors"`, `readOnlyHint=True`, `destructiveHint=False`, `idempotentHint=True`, **`openWorldHint=False`**(외부 호출 없음).

> 이전의 `vision/` provider·`describe_image`·`get_uploaded_image`·`anthropic` 의존성은 **불필요해서 모두 제거**됨.

## 구현 (핵심)

```python
def extract_colors(data: bytes, n: int = 5) -> list[tuple[str, str, float]]:
    from PIL import Image
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((128, 128))
    q = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    palette, counts = q.getpalette() or [], q.getcolors() or []
    total = sum(c for c, _ in counts) or 1
    out = []
    for count, idx in sorted(counts, reverse=True):
        r, g, b = palette[idx*3: idx*3+3]
        out.append((f"#{r:02X}{g:02X}{b:02X}", _name_of(r, g, b), count/total))
    return out
```

`extract_color(image_ref)` = `get_image_bytes(token)` → 없으면 안내 텍스트, 있으면 `extract_colors` 결과를 마크다운으로. 출력 예:

```
**추출된 주요 색상 (TPO Coach):**
1. #19234B 남색 (50%)
2. #F5F5F5 흰색 (50%)
```

## 설정 / 환경변수
`.env.example`: `MCP_TRANSPORT`(stdio|streamable-http)만. **비전 API 키 불필요.**
의존성: `python-multipart`, `Pillow` (공통) / `pillow-heif`(선택 `--extra heic`). **anthropic 등 비전 SDK 없음.**

## 검증 결과
- `uv run ruff check .` 통과
- `uv run pytest` → **12 passed** (store, 색 추출 정확성[빨강/검정/hex], 도구 텍스트 반환, URL/토큰, not-found)
- 로컬 확인: 남색+흰색 2색 이미지 → `남색 50% / 흰색 50%` 정확 추출

## 성공 기준
- [x] `/upload` 가 만료되는 참조 URL 반환
- [x] `extract_color(URL)` 이 대표 색을 **텍스트(hex·이름·비율)** 로 반환
- [x] 외부 모델/키 없음(완전 모델 독립·오프라인)
- [x] 결과가 텍스트 → PlayMCP 텍스트 호스트 호환
- [ ] **PlayMCP AI Chat에서 "이 옷 색 뽑아줘 [URL]" → extract_color 호출 → 색 텍스트 표시** (재배포 후 확인)

## 한계 (PoC 범위)
- **배경 포함** — 옷만 분리(세그멘테이션) 안 함. 사진에 배경/피부가 크면 그 색도 섞임. (옷 분리는 이후 과제)
- 색 이름은 16색 근사 매핑. 단일 인스턴스(메모리 store).

## 이후 연결
이 색을 기준으로 **유사 색 판단 → 어울리는 하의 추천**([matching-flow.md](matching-flow.md))으로 확장. 이 경로 전체가 **모델 없이** 성립한다(데이터 기반 매칭).
"착장 적절성 판단"처럼 비전 모델이 필요한 기능을 추가할 때만 그 도구에 한해 B(모델-독립 provider) 도입을 검토.
