# 이미지 PoC — 설계 & 구현

> 상태: **구현 완료 · 검증됨**(ruff/pytest/라이브 E2E). 목표는 **"사용자가 이미지를 한 번 업로드 → MCP가 그 이미지를
> 반환 → 호스트의 모델이 보고 설명"** 루프를 MCP 위에서 끝까지 동작시키는 것. TPO 로직은 범위 밖.
> 이미지 입력 제약·업로드 방식의 근거는 [image-input.md](image-input.md) 참고.

## 핵심 설계 결정: MCP는 "트리거"만, 설명은 호스트 모델이

`describe_image` 처럼 **도구가 직접 비전 모델을 호출**하면 서버가 특정 모델에 묶인다. 그래서 방향을 바꿨다:

- **도구는 비전을 하지 않는다.** 업로드된 이미지를 `ImageContent` 로 **반환만** 한다(트리거).
- **설명은 호스트의 멀티모달 모델**(Claude·ChatGPT 등)이 반환된 이미지를 직접 보고 한다.
- 따라서 **도구는 어떤 모델에도 의존하지 않는다.** 서버에 비전 SDK·API 키가 없다. → 진짜 모델 독립.

> ⚠️ **미검증 사항(중요)**: PlayMCP AI Chat 이 도구가 반환한 `ImageContent` 를 호스트 모델에 넘겨 "보게" 하는지는 **아직 확인되지 않았다**.
> 예전엔 "PlayMCP는 TextContent-only"라고 적었으나, **서버 개발가이드 본문·Notion 개발가이드에서 그 문구를 확인하지 못했다**(가이드는
> 오히려 `widget json` 등 비-텍스트 result 타입을 시사). → 이 PoC는 **멀티모달 호스트(Claude/ChatGPT 커넥터)에서는 동작이 검증**됐고,
> **PlayMCP AI Chat 에서의 동작은 배포 후 직접 호출로 검증해야 한다**(됨/안됨에 따라 "도구가 직접 비전" 방식 재검토). 이번 결정은 **모델 독립 우선**.

## 목표 / 비목표

증명하는 것:
1. 사용자가 이미지를 **한 번** 업로드하고 **공유 가능한 참조(URL/토큰)** 를 받는다.
2. 채팅에서 그 참조를 주면 MCP 도구가 **그 이미지를 반환**하고, **호스트 모델이 보고 설명**한다.
3. 위 흐름이 로컬(Inspector) → Claude 커넥터에서 동작한다.

하지 않는 것: TPO 코칭 로직 · 인증/DB/영구저장/멀티인스턴스 · 비전 품질 튜닝 · 서버 측 비전 모델.

## 전체 흐름

```
[멀티모달 호스트]          [브라우저 /upload]        [MCP 서버 (/mcp + /upload)]
 Claude / ChatGPT            │── POST multipart ──────►│ 검증·EXIF제거·리사이즈·메모리저장 │
   │  사진 업로드 ───────────►│                          │  (TTL 10분)                      │
   │                          │◄── 참조 URL /i/<token> ─┤                                  │
   │◄── URL 복사 ─────────────┤                          │                                  │
   │── "이거 설명해줘 [URL]" ─────(MCP tool call)───────►│ get_uploaded_image(image_ref)    │
   │                          │                          │  token→메모리 bytes              │
   │◄──── 이미지(ImageContent) ─────────────────────────┤  → Image(jpeg) 반환              │
   │                                                                                        │
   └─ 호스트의 모델이 반환된 이미지를 직접 보고 사용자에게 설명 (서버는 관여 안 함)
```

핵심: 도구는 외부 URL을 다운로드하지 않는다. 업로드 시 메모리에 들어간 바이트를 그대로 `ImageContent` 로 반환한다.
→ SSRF 없음, 서버에 비전 모델 없음, 구현 단순.

## 구성 요소 (구현됨)

### 1) 업로드 엔드포인트 — `src/playmcp_server/web/upload.py`
[image-input.md](image-input.md) "업로드 구현 설계" 패턴 A(메모리 store).
- `GET /upload` — 파일 input 한 개짜리 HTML 폼
- `POST /upload` — 검증(이미지·≤10MB) → EXIF 제거·긴 변 1024px 리사이즈·JPEG 재인코딩 → `token` 발급, `{token: (bytes, expires_at)}` 메모리 저장(TTL 10분) → 참조 URL 반환
- `GET /i/{token}` — 사람이 브라우저로 확인용(참조가 진짜 URL로 보이게)
- 노출 헬퍼: `store_image(bytes) -> token`, `get_image_bytes(token) -> bytes|None`
- `register_routes(mcp)` 가 FastMCP `custom_route` 로 위 라우트를 단다 (streamable-http 일 때 마운트)

> 단일 인스턴스 전제(메모리 store). 멀티 인스턴스 확장은 PoC 이후(오브젝트 스토리지 등).

### 2) MCP 도구 — `get_uploaded_image` (`src/playmcp_server/tools/image.py`)
유일한 신규 도구. 업로드 참조를 받아 **이미지를 반환**(트리거).

| 항목 | 값 |
| --- | --- |
| 이름 | `get_uploaded_image` (`kakao` 미포함, `A-Za-z0-9_-`) |
| 파라미터 | `image_ref: str` (업로드 URL 또는 token) |
| 반환 | `Image` → `ImageContent`(mimeType `image/jpeg`) |
| 없는/만료 참조 | `ValueError` → 도구 에러(isError) + 안내 메시지 |

annotations 5종 (PlayMCP 필수):

| 필드 | 값 | 이유 |
| --- | --- | --- |
| `title` | "Get uploaded image" | 사람용 제목 |
| `readOnlyHint` | `True` | 외부 상태 변경 없음 |
| `destructiveHint` | `False` | 파괴적 동작 없음 |
| `idempotentHint` | `True` | 같은 참조 → 같은 이미지 |
| `openWorldHint` | **`False`** | **외부 API 호출 없음**(저장 바이트만 반환) — 정직 신고 |

> 이전 설계의 `vision/` provider 추상화·`VISION_PROVIDER`·비전 SDK 의존성은 **전부 제거**됐다(설명을 호스트가 하므로 불필요).

## 구현 (실제 코드)

### 도구 (`tools/image.py`)

```python
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

from playmcp_server.web.upload import get_image_bytes

_NOT_FOUND = (
    "이미지를 찾을 수 없습니다(만료되었거나 잘못된 링크). 다시 업로드해 주세요."
)


def _extract_token(image_ref: str) -> str:
    path = urlparse(image_ref).path
    return path.rsplit("/", 1)[-1] if "/" in path else image_ref


def register_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get uploaded image",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def get_uploaded_image(image_ref: str) -> Image:
        """Returns an image the user uploaded to TPO Coach for the host model to view.

        The host's own (multimodal) model looks at the returned image and answers —
        this tool does not run any vision model itself.

        Args:
            image_ref: Upload reference (".../i/abc123" or the token itself).

        Returns:
            The uploaded image (JPEG) as image content.
        """
        data = get_image_bytes(_extract_token(image_ref))
        if data is None:
            raise ValueError(_NOT_FOUND)
        return Image(data=data, format="jpeg")
```

### 업로드 (`web/upload.py`) — 요지
- `_store: dict[str, tuple[bytes, float]]` + `_sweep()`(만료 청소)
- `_process_image(raw)`: Pillow 로 검증 + `exif_transpose` + `convert("RGB")` + `thumbnail(1024)` + JPEG 재인코딩(메타 제거). 선택적 `pillow-heif` 로 HEIC 지원
- `store_image` / `get_image_bytes` / `register_routes(mcp)`(`/upload`, `/i/{token}`)

### 배선
- `tools/__init__.py`: `image.register_tools(mcp)` 등록
- `server.py`: FastMCP 구성 뒤 `register_routes(mcp)` 호출

## 설정 / 환경변수

`.env.example`:
```
# MCP_TRANSPORT=stdio              # stdio(로컬/Inspector) | streamable-http(배포/PlayMCP)
# 설명은 호스트 모델이 한다 — 서버엔 비전 API 키가 필요 없다.
```
의존성(`pyproject.toml`): `python-multipart`, `Pillow` (공통) / `pillow-heif`(선택 `--extra heic`). **비전 SDK 없음.**

## 검증 결과 (완료)

- `uv run ruff check .` → **통과**
- `uv run pytest` → **14 passed** (store 저장/조회/만료/sweep, 도구가 `ImageContent` 반환, URL/토큰 참조, not-found isError, Pillow 재인코딩/리사이즈/거부)
- **라이브 E2E**(streamable-http, 한 프로세스): `GET /upload` 폼 → PNG `POST` → 발급 URL → MCP 클라이언트로 `get_uploaded_image(URL)` 호출 → **`type=image`, `mimeType=image/jpeg`, isError=False** 반환 확인. 잘못된 ref → `isError=True`.

## 성공 기준

- [x] `/upload` 가 이미지를 받아 **만료되는 참조 URL** 을 돌려준다.
- [x] `get_uploaded_image(URL)` 이 업로드 이미지를 **`ImageContent` 로 반환**한다(isError=False).
- [x] 잘못된/만료 참조는 도구 에러로 안내된다.
- [x] 도구가 **어떤 모델에도 의존하지 않는다**(서버에 비전 SDK/키 없음).
- [ ] **Claude 커넥터**에서 "이거 설명해줘 [URL]" → 도구 자동 호출 → 호스트 모델이 이미지를 보고 설명 (배포 후 확인).
- [x] annotations 5종·이름 규칙 등 PlayMCP 기본 규칙 위반 없음.

## 다음으로 돌려보기

```bash
# 로컬 Inspector (stdio)
uv run mcp dev src/playmcp_server/server.py

# HTTP 서버 (배포와 동일 전송) — /upload 에서 업로드, /mcp 가 MCP 엔드포인트
MCP_TRANSPORT=streamable-http uv run playmcp-server
```

## 테스트 surface 단계

| 단계 | 확인 | 상태 |
| --- | --- | --- |
| 로컬 직접/pytest | 업로드·도구·이미지 처리 | ✅ 완료 |
| MCP Inspector | 도구 노출·이미지 반환 | 수동 |
| Claude 커넥터 | "설명해줘 [URL]" → 호스트 모델이 이미지 보고 설명 (E2E) | 배포 후 |
| PlayMCP AI Chat | ImageContent 호스트 처리 여부 **미검증** → 배포 후 직접 호출로 확인 | 미검증 |

## 프라이버시 / 한계

- 업로드 이미지는 **메모리 + 단기 TTL(10분)**, 만료 자동 폐기. EXIF 제거. 바이트 미로깅.
- 이미지를 보는 주체는 **호스트 모델** → 우리 서버는 외부 비전 API로 이미지를 내보내지 않음(서버 측 외부 전송 0).
- 멀티 인스턴스/대용량/영구저장은 범위 밖.

## 이후 연결

이미지 입력·반환 파이프라인은 그대로 두고, **호스트 모델에게 줄 지시(프롬프트)** 를 TPO 관점으로 바꾸면 된다 —
즉 "이 착장 드레스코드 맞아?" 같은 질문을 호스트가 반환된 이미지와 함께 처리. [features.md](features.md) 의 `check_outfit`·
`extract_color` 로 확장 시, **서버가 텍스트 결과를 직접 만들어야 하는 기능**(PlayMCP에서 ImageContent가 안 통하는 것으로 확인될 경우 포함)이라면
그때 "도구가 직접 비전" 경로를 모델 독립 추상화로 다시 도입할지 결정한다.
