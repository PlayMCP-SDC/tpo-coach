# 이미지(사진) 입력 처리 — 결론·옵션·검증

> 상태: **설계 확정(텍스트 기본 · image_url 보조) + 잔여 미지수 1개(라이브 첨부버튼 유무)**. 원래 아이디어("각자 사진을 보내 비공개로 착장 검사")의
> 사진 입력을 MCP/PlayMCP 위에서 어떻게 실현하는지 정리한 팀 공통 문서.

## TL;DR (3줄)

1. 사진은 제품 핵심이 맞다.
2. MCP 도구는 **원본 이미지 바이트**는 못 받지만 **`image_url`/`image_base64` 문자열 파라미터**로는 받을 수 있고,
   이 방식은 **PlayMCP 등록작 다수가 실제로 쓰는 검증된 길**이다(아래 실측).
3. **잔여 미지수 거의 해소(2026-06-28 조사)**: PlayMCP AI Chat은 **텍스트 입출력 중심**이고, 기존 이미지 앱들은
   **사용자가 이미지 URL을 직접 붙여넣게** 한다(호스트 자동 업로드 증거 없음). → **PlayMCP에선 텍스트 설명이 기본,
   `image_url`은 보조**. 풍부한 사진 UX는 **외부 멀티모달 호스트(Claude/ChatGPT 도구함 연결)** 경유에서만.

## 왜 도구가 원본 이미지를 직접 못 받나 (MCP 구조)

- **MCP 도구 입력 = JSON Schema(텍스트/구조화)뿐.** 이미지용 입력 타입이 스펙에 없다. `ImageContent`는 도구
  **결과(출력)**·sampling용이지 **입력**용이 아니다.
  ([MCP 스펙](https://modelcontextprotocol.io/specification/2025-06-18/server/tools),
  [디스커션 #1197](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1197))
- 그래서 이미지는 **JSON 본문 안의 문자열(`image_url` 또는 `image_base64`)** 로만 도구에 들어갈 수 있다.
- **PlayMCP = streamable-http + stateless = JSON 본문만**(멀티파트 업로드 불가). 입력 길이 제한(후기 기준
  ~20k자)이라 **큰 base64는 부적합 → `image_url` 선호**.

## 다른 등록작으로 실측 (2026-06-28 조사)

PlayMCP 갤러리는 JS 렌더링이라, **공개 카탈로그 API `https://playmcp.kakao.com/api/v1/mcps`** 를 직접 조회해
**승인된 작품 197개 전체 + 각 도구 스키마(파라미터)** 를 1차 출처로 확인.

**이미지를 입력으로 받는 승인 작품** (우리 `check_outfit`과 동일 패턴):

| 작품 | 하는 일 | 입력 파라미터 |
| --- | --- | --- |
| 나무의사 진단도구 | 나무 사진 → 병해충 진단 | `image_url` |
| 삶은 갓생 | 목표 인증 사진 → 달성 채점 | `image_url` |
| 싸인전에(계약 건강검진) | 계약서 사진/PDF → 독소조항 분석 | `image_url`, `image_base64`, `pdf_url`, … |
| 어린이ZIP | 아이 활동 사진 → 알림장 작성 | `images[]`(URL/base64) |

확인된 사실:
- ✅ **옵션 B(`image_url`/`image_base64` 문자열)는 실증됨** — 등록·승인되어 동작 중.
- ✅ **비전 처리 앱이 승인된다 = 100ms 규칙은 하드 블로커가 아님** (계약 분석·병해충 진단은 수초 소요).
  운영상 의미 있는 한도는 **p99 3s** 쪽.
- ✅ TalkGuard(OCR 사례)는 `ocr_text`(이미 추출된 텍스트) 파라미터도 둠 → 옵션 A 패턴도 공존 가능.
- 🟡 단, 이건 "도구가 받을 수 있다"는 증거지 "호스트가 사용자 업로드 사진을 그 파라미터에 넣어준다"는 별개.

**그럼 사용자 사진은 어떻게 `image_url`로 들어가나? (2차 조사)** — 호스트 자동 업로드가 아니라 **사용자가 URL을 직접 제공**하는 방식이다:
- **앱들의 안내가 일관**: 나무의사 docstring *"사용자가 실제 사진 URL을 직접 제공한 경우에만 사용 … 임의 URL 생성 금지"*,
  삶은갓생 예시 *"오늘 인증할게 [사진 url]"*, 쿠키샷 *"이 사진으로 9컷: [이미지 URL]"*. (출처: 카탈로그 API의 starter message·도구 docstring)
- **공식 가이드 FAQ가 쐐기**: *"AI 채팅은 응답 content가 **TextContent 타입만 허용**, 이미지는 URL을 마크다운으로 텍스트에 포함.
  TextContent 외 타입은 **도구함으로 Claude/ChatGPT 직접 연결**할 때만"*. FAQ 34항목에 이미지/사진/파일 **첨부 항목 0개**.
  (출처: PlayMCP 가이드 Notion FAQ)
  > ✅ **실측 확정(2026-06-29)**: KC 배포 후 PlayMCP AI Chat에서 도구가 `ImageContent` 를 반환하니 **작은 이미지도 "답변 생성 중 오류"** 로 실패.
  > 즉 **PlayMCP AI Chat은 도구 결과의 이미지를 모델에 넘기지 않는다**(문구 출처는 못 찾았지만 동작상 텍스트 결과가 사실상 강제). 카탈로그 API 조사에서도 등록작
  > 261개 도구 중 **이미지 입력/반환 도구 0개**. → 도구 결과는 **텍스트**로. (이미지 PoC는 모델 없는 색상 추출로 선회 — [image_poc.md](image_poc.md))
- → **PlayMCP AI Chat = 텍스트 입출력 중심**. 첨부 사진 자동 주입 증거 없음. 멀티모달 첨부는 외부 호스트(Claude/ChatGPT) 연결 경로에서만.

출처: [PlayMCP 카탈로그 API](https://playmcp.kakao.com/api/v1/mcps?page=0&size=100) ·
[TalkGuard OCR 서버](https://glama.ai/mcp/servers/Leejinhoe/kakao_mcp_secretary) · PlayMCP 가이드 FAQ(Notion)

## 사진을 다루는 옵션

| 옵션 | 방식 | PlayMCP |
| --- | --- | --- |
| **B. `image_url`/`image_base64` 파라미터 (실증·권장)** | 도구가 문자열로 받아 다운로드·처리(비전) | ✅ **등록작 다수가 실제 사용** |
| **A. 호스트가 사진 → 설명 변환** | 멀티모달 호스트가 사진→텍스트 변환해 도구에 텍스트 전달 | 🟡 PlayMCP 내장 지원 **미확인** |
| C. 큰 base64 직접 | 대용량 base64를 인자에 그대로 | ❌ ~20k 입력 한도 → 작은 이미지만, 일반적으로 `image_url` 권장 |

## 잔여 미지수 — 거의 해소

**도구가 `image_url`을 받는 것은 실증됨. 사용자 사진이 그 파라미터로 들어가는 방식 = "사용자가 공개 URL을 직접 붙여넣기"**
(공식 FAQ TextContent-only + 앱 docstring 근거, 신뢰도 높음). 옵션 A(호스트 자동 변환)는 PlayMCP AI Chat 네이티브 기능 아님.

**남은 단 하나 (5분 자가확인, 로그인 필요)**: PlayMCP AI Chat 라이브 UI에 **사진 첨부(클립/카메라) 버튼이 실제로 있는지**.
→ 나무의사를 도구함에 추가 → ① 첨부 버튼 유무 ② 사진 붙여서 되나 vs URL 붙여야 되나 시도. 버튼 없으면 URL 방식 확정.

## 검증 계획

### 1단계 (오늘, 배포 0) — 호스트 업로드 UI 확인
PlayMCP AI Chat(콘솔)/카카오톡 연동 채팅에 **이미지 첨부(클립/카메라) 버튼이 있는지** 본다.
- 있으면 → 사진 올리고 "이 사진 뭐 보여?"로 호스트가 보는지/텍스트화하는지 관찰
- 없으면 → 사용자 사진은 `image_url`을 직접 줘야 하는 구조일 가능성

### 2단계 (7/1 스켈레톤 등록과 합침) — 무엇이 도구로 오나
받은 인자를 그대로 돌려주는 **프로브 도구**로 확정:

```python
@mcp.tool(annotations=ToolAnnotations(
    title="Echo probe", readOnlyHint=True, destructiveHint=False,
    idempotentHint=True, openWorldHint=False))
def echo_probe(description: str = "", image_url: str = "", image_base64: str = "") -> str:
    """Echoes received args to verify what the PlayMCP host passes (TPO Coach debug)."""
    return f"description={description!r} image_url={image_url!r} base64_len={len(image_base64)}"
```

PlayMCP에서 **사진 올리고/URL 주고 "echo_probe로 확인해줘"** → 무엇이 채워지나 본다:
- `image_url`/`image_base64` 채워짐 → 옵션 B 완전 자동 ✓✓
- `description` 채워짐 → 옵션 A(호스트 텍스트 변환) ✓
- 아무것도 안 옴 → 사용자가 URL 수동 입력 필요

### ⚠️ 이걸로는 답이 안 나온다
- **MCP Inspector** — "내가 클라이언트"라 내가 넣는 대로 들어옴(호스트 행동 검증 ❌)
- **Claude Desktop** — 멀티모달이지만 PlayMCP 호스트 아님 → 일반화 금지

## 우리 도구 설계에 주는 의미

- **PlayMCP AI Chat(컨테스트 심사 surface)에선 `outfit_text`(텍스트 설명)가 기본 UX** — 사용자가 사진을 URL로
  만들어 붙이는 건 캐주얼 유저에게 불편하기 때문. ("검정 후드+청바지인데 졸업모임 괜찮아?" → 네이티브 동작)
- **`image_url`은 보조 경로로 함께 수용** (실증된 패턴, 나무의사/삶은갓생과 동일). `check_outfit`·`extract_color`(v1)가
  `outfit_text` | `image_url`(+선택 작은 `image_base64`)을 모두 받게.
- **진짜 사진 UX는 외부 멀티모달 호스트(Claude/ChatGPT 도구함 연결) 경유** 에서 빛난다 — 그 호스트가 사진을 텍스트로 변환.
- 입력 우선순위: `outfit_text` > `image_url` > `image_base64`(작은 것만).
- **프라이버시(F7)는 이제 실질 요건**: 옵션 B면 사진이 우리 서버(및 비전 API)에 도달 → **처리 후 즉시 폐기·미로깅·
  동의 고지** 강제. 비전 API 경유 시 `openWorldHint=true` 로 정직 신고.
- MVP 범위: `image_url` **파라미터 수용**은 넣되, 실제 비전 처리(외부 API)를 MVP에 넣을지는 7/1 검증·여력 보고 결정
  (텍스트 경로만으로도 핵심 루프는 성립).

## 업로드 구현 설계 (사용자 사진 → `image_url`)

> 적용 조건: **7/1 `echo_probe` 검증에서 "사용자 사진이 도구로 자동 주입되지 않음"이 확정될 때만 필요**.
> 첨부 버튼이 있고 호스트가 `image_url`을 자동으로 채워주면 이 절은 불필요.

사용자 손의 이미지를 `image_url`로 만드는 일은 **MCP 도구 호출 경로 바깥(out-of-band)** 에서 풀어야 한다
(도구 입력 = JSON 문자열뿐, 멀티파트 업로드 불가). 즉 **별도 HTTP 업로드 경로**를 두고, 도구는 그 결과 URL만 받는다.

### 전체 흐름

```
사용자 ──"착장 봐줘"──► [PlayMCP 채팅]  (도구/starter msg가 /upload 안내)
사용자 ──사진 업로드──► [브라우저 /upload] ──POST multipart──► [서버: 검증·EXIF제거·리사이즈·저장(TTL)]
                                          ◄── 짧은 URL /i/<token> ──┘
사용자 ──URL 붙여넣기──► check_outfit(image_url=...) ──다운로드·비전처리──► 결과(텍스트) ──► 처리 후 즉시 폐기
```

나무의사·삶은갓생 등 승인작이 쓰는 "사용자가 공개 URL을 직접 제공" 패턴과 동일하되, **그 URL을 우리가 발급**한다.

### 저장 방식 — 두 패턴

| 패턴 | 방식 | 평가 |
| --- | --- | --- |
| **A. 서버 버퍼링 (메모리/디스크)** | 업로드 바이트를 서버가 들고 `/i/<token>`로 서빙 | 👍 컨테이너 1개로 끝·TTL 통제 쉬움 / ⚠️ **멀티 인스턴스 함정**(replica 분산 시 store 미공유 → 404) |
| **B. presigned → 오브젝트 스토리지** | 브라우저가 카카오 클라우드 Object Storage(S3 호환)에 직접 PUT, 도구는 presigned GET으로 다운로드 | 👍 스케일아웃 안전·서버 메모리 0·자동 lifecycle 만료 / ⚠️ 버킷·CORS·서명 셋업 |

→ **MVP/컨테스트는 A(단일 인스턴스), 확장 시 B로 교체.** 도구 인터페이스(`image_url`)는 동일해 내부만 갈아끼우면 됨.

### 보안 (필수)

- **SSRF 차단(최우선)**: 도구가 임의 URL을 다운로드하면 내부 IP/메타데이터(`169.254.169.254`) 공격 가능.
  → 가능하면 **우리 도메인(`/i/<token>`)만 허용**. 외부 URL 허용 시 사설 IP 대역(10/8·172.16/12·192.168/16·127/8·169.254/16) 차단·`https`만·size/timeout 제한.
- **파일 검증**: 확장자 말고 **매직바이트**로 실제 이미지 확인(Pillow `verify`), **최대 크기 제한**(예: 10MB), 포맷 화이트리스트(jpg/png/webp/heic).
- **토큰**: `secrets.token_urlsafe()` (추측 불가, capability 기반 접근). one-time 조회 옵션.
- **남용 방지**: `/upload` rate limiting.

### 프라이버시 (F7 — 실질 요건)

옷 사진엔 얼굴·배경·**EXIF GPS**가 포함 → 더 민감.

- **EXIF/메타데이터 제거** 필수(재인코딩으로 스트립, 특히 GPS).
- **짧은 TTL(예: 10분) + 처리 후 즉시 폐기**, 디스크 사용 시 만료 청소 작업.
- **이미지 바이트 미로깅**(URL/토큰 로그도 주의).
- 도구 docstring에 **"사진은 분석 후 즉시 삭제됩니다" 동의 고지**.
- 비전 API 외부 호출 시 도구에 **`openWorldHint=true`** 정직 신고.

### 포맷·사이즈

- **HEIC**(아이폰 기본) 주의 → `pillow-heif`로 JPEG 변환.
- 비전 API 전 **긴 변 ~1024px 리사이즈**(비용·지연 ↓, p99 3s 한도에 유리).
- `ImageOps.exif_transpose`로 회전 보정 후 메타 제거.

### 구현 스케치 (패턴 A, FastMCP custom route)

```python
import secrets, time, io
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from PIL import Image, ImageOps

MAX_BYTES = 10 * 1024 * 1024
TTL = 600  # 10분
_store: dict[str, tuple[bytes, float]] = {}

def _sweep() -> None:  # 만료 청소
    now = time.time()
    for k in [k for k, (_, exp) in _store.items() if exp < now]:
        _store.pop(k, None)

@mcp.custom_route("/upload", methods=["GET"])
async def upload_page(request: Request):
    return HTMLResponse(
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<form method="post" enctype="multipart/form-data">'
        '<input type="file" name="f" accept="image/*" required><button>업로드</button></form>'
        '<p>사진은 분석 후 즉시 삭제됩니다.</p>'
    )

@mcp.custom_route("/upload", methods=["POST"])
async def upload(request: Request):
    _sweep()
    raw = await (await request.form())["f"].read()
    if len(raw) > MAX_BYTES:
        return HTMLResponse("파일이 너무 큽니다(최대 10MB).", status_code=413)
    try:  # 실제 이미지 검증 + EXIF 제거 + 리사이즈 + 재인코딩
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=85)
        clean = buf.getvalue()
    except Exception:
        return HTMLResponse("이미지 파일이 아닙니다.", status_code=400)
    token = secrets.token_urlsafe(12)
    _store[token] = (clean, time.time() + TTL)
    url = f"{request.base_url}i/{token}"
    return HTMLResponse(f'아래 링크를 복사해 채팅에 붙여넣으세요(10분 후 만료):<br><code>{url}</code>')

@mcp.custom_route("/i/{token}", methods=["GET"])
async def serve(request: Request):
    _sweep()
    item = _store.get(request.path_params["token"])
    if not item:
        return JSONResponse({"error": "expired or not found"}, status_code=404)
    return Response(item[0], media_type="image/jpeg")
```

도구 쪽(SSRF 차단):

```python
from urllib.parse import urlparse
ALLOWED_HOST = "your-domain"  # 배포 도메인

def _fetch_image(image_url: str) -> bytes:
    if (urlparse(image_url).hostname or "") != ALLOWED_HOST:
        raise ValueError("허용되지 않은 이미지 URL입니다.")
    # httpx로 timeout·size 제한 두고 다운로드
    ...
```

> 추가 의존성: 폼 파싱 **`python-multipart`**, 이미지 처리 **`Pillow`**, HEIC **`pillow-heif`** (`pyproject.toml`).

### 구성 요약

| 항목 | MVP(7/1~컨테스트) | 확장 시 |
| --- | --- | --- |
| 저장 | 메모리 store + TTL | 카카오 Object Storage + presigned |
| 검증 | Pillow verify + size 제한 | + 콘텐츠 검사 |
| 프라이버시 | EXIF 제거·즉시 폐기·미로깅 | + lifecycle 자동만료 |
| SSRF | 우리 도메인만 허용 | + IP 대역 차단(외부 URL 허용 시) |
| 포맷 | JPEG 재인코딩·리사이즈 | + HEIC 변환 |

## 일정 연결

[delivery-plan.md](delivery-plan.md)의 **7/1 배포·등록 조기 검증**에 합친다 — `echo_probe`로 1·2단계를 한 번에 돌려
**사진이 도구로 어떻게 도달하는지 7/1에 확정**하고, 그 결과로 `check_outfit` 입력 스키마와 v1 비전 처리 범위를 정한다.
