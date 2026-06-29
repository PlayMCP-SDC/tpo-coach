"""이미지 업로드 라우트 + 메모리 store.

MCP 도구는 사용자 사진을 직접 못 받는다(입력은 JSON 문자열뿐). 그래서 사진은
별도 HTTP 경로(/upload)로 받아 메모리에 저장하고, 도구에는 그 참조(URL/토큰)만 준다.
근거: docs/idea/image-input.md

저장 방식은 단일 인스턴스 전제의 메모리 store + 짧은 TTL.
프라이버시: EXIF 제거 · 처리 후 짧은 TTL 로 폐기 · 바이트 미로깅.
"""

from __future__ import annotations

import io
import logging
import secrets
import time

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

logger = logging.getLogger("playmcp_server.web.upload")

MAX_BYTES = 10 * 1024 * 1024  # 10MB
TTL_SECONDS = 600  # 10분
MAX_EDGE = 1024  # 긴 변 리사이즈 한도(px)

# token -> (jpeg_bytes, expires_at)
_store: dict[str, tuple[bytes, float]] = {}


def _sweep() -> None:
    """만료된 항목을 store 에서 제거한다."""
    now = time.time()
    for token in [t for t, (_, exp) in _store.items() if exp < now]:
        _store.pop(token, None)


def store_image(data: bytes, ttl: float = TTL_SECONDS) -> str:
    """바이트를 저장하고 접근 토큰을 돌려준다."""
    _sweep()
    token = secrets.token_urlsafe(12)
    _store[token] = (data, time.time() + ttl)
    return token


def get_image_bytes(token: str) -> bytes | None:
    """토큰으로 바이트를 돌려준다. 만료/부재면 None."""
    _sweep()
    item = _store.get(token)
    if item is None or item[1] < time.time():
        _store.pop(token, None)
        return None
    return item[0]


def _process_image(raw: bytes) -> bytes:
    """검증 + EXIF 제거 + 리사이즈 + JPEG 재인코딩. 이미지가 아니면 ValueError."""
    from PIL import Image, ImageOps

    try:  # 선택: 아이폰 HEIC 지원
        import pillow_heif

        pillow_heif.register_heif_opener()
    except ImportError:
        pass

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise ValueError("not an image") from exc

    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)  # 재인코딩으로 메타데이터 자연 제거
    return buf.getvalue()


_UPLOAD_FORM = (
    '<!doctype html><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    "<h3>TPO Coach — 이미지 업로드</h3>"
    '<form method="post" enctype="multipart/form-data">'
    '<input type="file" name="f" accept="image/*" required> '
    "<button>업로드</button></form>"
    "<p>사진은 분석 후 즉시 삭제됩니다(약 10분 후 자동 만료).</p>"
)


def _result_html(url: str) -> str:
    return (
        '<!doctype html><meta charset="utf-8">'
        "<p>아래 링크를 복사해 채팅에 붙여넣으세요(약 10분 후 만료):</p>"
        f"<code>{url}</code>"
    )


def register_routes(mcp: FastMCP) -> None:
    """업로드 관련 HTTP 라우트를 FastMCP(Starlette) 앱에 붙인다.

    streamable-http 전송일 때만 실제로 마운트된다(stdio 에선 무해).
    """

    @mcp.custom_route("/upload", methods=["GET"])
    async def upload_page(request: Request) -> Response:
        return HTMLResponse(_UPLOAD_FORM)

    @mcp.custom_route("/upload", methods=["POST"])
    async def upload(request: Request) -> Response:
        form = await request.form()
        field = form.get("f")
        if field is None or not hasattr(field, "read"):
            return HTMLResponse("파일을 선택해 주세요.", status_code=400)
        raw = await field.read()
        if len(raw) > MAX_BYTES:
            return HTMLResponse("파일이 너무 큽니다(최대 10MB).", status_code=413)
        try:
            clean = _process_image(raw)
        except ValueError:
            return HTMLResponse("이미지 파일이 아닙니다.", status_code=400)
        token = store_image(clean)
        url = f"{request.base_url}i/{token}"
        logger.info("image uploaded: token=%s bytes=%d", token, len(clean))
        return HTMLResponse(_result_html(url))

    @mcp.custom_route("/i/{token}", methods=["GET"])
    async def serve_image(request: Request) -> Response:
        data = get_image_bytes(request.path_params["token"])
        if data is None:
            return JSONResponse({"error": "expired or not found"}, status_code=404)
        return Response(data, media_type="image/jpeg")
