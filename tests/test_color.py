"""색상 추출 PoC 검증.

설계: 도구는 로컬(Pillow)로 대표 색상을 뽑아 텍스트로 반환 — 외부 모델/키 불필요,
PlayMCP 텍스트 전용 호스트에서도 동작. 그래서 네트워크/키 없이 전 구간 검증된다.
"""

import io

import pytest

from playmcp_server.tools import color
from playmcp_server.web import upload


@pytest.fixture(autouse=True)
def _clear_store():
    yield
    upload._store.clear()


def _png(rgb: tuple[int, int, int], size: tuple[int, int] = (80, 60)) -> bytes:
    Image = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "PNG")
    return buf.getvalue()


def _png_on_bg(
    fg: tuple[int, int, int],
    bg: tuple[int, int, int],
    size: tuple[int, int] = (100, 100),
) -> bytes:
    """배경(bg) 위에 가운데 의상 사각형(fg)을 그린 PNG. 배경이 면적상 더 넓다."""
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")
    img = Image.new("RGB", size, bg)
    w, h = size
    draw = ImageDraw.Draw(img)
    # 가운데 약 36% 면적 — 테두리(배경)가 더 넓어 단순 최빈색이면 배경이 1순위가 된다.
    draw.rectangle((w * 3 // 10, h * 3 // 10, w * 7 // 10, h * 7 // 10), fill=fg)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --- 업로드 메모리 store --------------------------------------------------


def test_store_roundtrip() -> None:
    token = upload.store_image(b"hello")
    assert upload.get_image_bytes(token) == b"hello"


def test_store_expiry() -> None:
    token = upload.store_image(b"x", ttl=-1)
    assert upload.get_image_bytes(token) is None


# --- 색상 추출 (Pillow, 모델 없음) ----------------------------------------


def test_extract_colors_solid_red() -> None:
    colors = color.extract_colors(_png((220, 30, 30)))
    assert colors
    hex_, name, ratio = colors[0]
    assert name == "빨강"
    assert ratio > 0.9


def test_extract_colors_solid_black() -> None:
    colors = color.extract_colors(_png((0, 0, 0)))
    assert colors[0][1] == "검정"


def test_extract_colors_returns_hex() -> None:
    colors = color.extract_colors(_png((10, 20, 200)))
    assert colors[0][0].startswith("#")
    assert len(colors[0][0]) == 7


# --- 배경 제외 휴리스틱 (테두리=배경) -------------------------------------


def test_excludes_white_background() -> None:
    """흰 배경 + 검은 의상: 배경(흰색)을 빼고 의상색(검정)이 1순위여야 한다."""
    colors = color.extract_colors(_png_on_bg(fg=(0, 0, 0), bg=(255, 255, 255)))
    assert colors[0][1] == "검정"
    assert "흰색" not in {name for _, name, _ in colors}


def test_excludes_colored_background() -> None:
    """파란 배경 + 빨간 의상: 의상색(빨강)이 1순위, 배경(파랑 계열)은 제외."""
    colors = color.extract_colors(_png_on_bg(fg=(220, 30, 30), bg=(30, 80, 200)))
    assert colors[0][1] == "빨강"


def test_solid_image_falls_back() -> None:
    """단색 이미지는 테두리=전체라 모두 배경이지만, 폴백으로 그 색을 반환한다."""
    colors = color.extract_colors(_png((220, 30, 30)))
    assert colors[0][1] == "빨강"
    assert colors[0][2] > 0.9


# --- extract_color 도구 (in-memory MCP) -----------------------------------


async def test_color_tool_listed(client_session) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    assert "extract_color" in {t.name for t in result.tools}


async def test_extract_color_tool_returns_text(client_session) -> None:
    token = upload.store_image(_png((0, 0, 0)))
    async with client_session() as client:
        result = await client.call_tool("extract_color", {"image_ref": token})
    text = result.content[0].text
    assert not result.isError
    assert "검정" in text
    assert "#" in text


async def test_extract_color_accepts_url_ref(client_session) -> None:
    token = upload.store_image(_png((220, 30, 30)))
    ref = f"http://test-mcp.example.io/i/{token}"
    async with client_session() as client:
        result = await client.call_tool("extract_color", {"image_ref": ref})
    assert "빨강" in result.content[0].text


async def test_extract_color_not_found(client_session) -> None:
    async with client_session() as client:
        result = await client.call_tool("extract_color", {"image_ref": "missing"})
    assert "찾을 수 없습니다" in result.content[0].text
