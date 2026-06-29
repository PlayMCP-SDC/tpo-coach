"""이미지 PoC 검증.

설계: MCP 도구는 업로드된 이미지를 **반환**만 하고(트리거), 설명은 호스트 모델이 한다.
그래서 비전 모델/키 없이 전 구간을 검증할 수 있다.

- 업로드 메모리 store 의 저장/조회/만료
- get_uploaded_image 도구가 ImageContent 를 반환하는지
- 잘못된/만료된 참조 처리
- 업로드 이미지 처리(EXIF 제거·리사이즈·JPEG 재인코딩)
"""

import time

import pytest

from playmcp_server.web import upload


# 모듈 전역 store 오염 방지: 각 테스트 후 비운다.
@pytest.fixture(autouse=True)
def _clear_store():
    yield
    upload._store.clear()


# --- 업로드 메모리 store --------------------------------------------------


def test_store_roundtrip() -> None:
    token = upload.store_image(b"hello-bytes")
    assert upload.get_image_bytes(token) == b"hello-bytes"


def test_store_unknown_token() -> None:
    assert upload.get_image_bytes("nope") is None


def test_store_expiry() -> None:
    token = upload.store_image(b"x", ttl=-1)  # 이미 만료
    assert upload.get_image_bytes(token) is None


def test_sweep_drops_only_expired() -> None:
    fresh = upload.store_image(b"keep")
    upload._store["stale"] = (b"gone", time.time() - 1)
    upload._sweep()
    assert fresh in upload._store
    assert "stale" not in upload._store


# --- get_uploaded_image 도구 (in-memory MCP) ------------------------------


async def test_image_tool_listed(client_session) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    assert "get_uploaded_image" in {t.name for t in result.tools}


async def test_get_uploaded_image_returns_image(client_session) -> None:
    # 진짜 JPEG 바이트를 store 에 넣는다.
    Image = pytest.importorskip("PIL.Image")
    import io

    buf = io.BytesIO()
    Image.new("RGB", (32, 24), (10, 20, 30)).save(buf, "JPEG")
    token = upload.store_image(buf.getvalue())

    async with client_session() as client:
        result = await client.call_tool("get_uploaded_image", {"image_ref": token})

    block = result.content[0]
    assert block.type == "image"
    assert block.mimeType == "image/jpeg"
    assert not result.isError


async def test_get_uploaded_image_accepts_url_ref(client_session) -> None:
    token = upload.store_image(b"\xff\xd8jpegish")
    image_ref = f"http://localhost:8000/i/{token}"  # 전체 URL 형태도 허용
    async with client_session() as client:
        result = await client.call_tool(
            "get_uploaded_image", {"image_ref": image_ref}
        )
    assert result.content[0].type == "image"


async def test_get_uploaded_image_not_found(client_session) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "get_uploaded_image", {"image_ref": "missing"}
        )
    assert result.isError
    assert "찾을 수 없습니다" in result.content[0].text


# --- 이미지 처리 파이프라인 (Pillow) --------------------------------------


def test_process_image_reencodes_to_jpeg() -> None:
    Image = pytest.importorskip("PIL.Image")
    import io

    buf = io.BytesIO()
    Image.new("RGB", (50, 40), (10, 20, 30)).save(buf, "PNG")
    out = upload._process_image(buf.getvalue())

    assert out[:2] == b"\xff\xd8"  # JPEG 매직바이트
    assert Image.open(io.BytesIO(out)).format == "JPEG"


def test_process_image_rejects_non_image() -> None:
    pytest.importorskip("PIL.Image")
    with pytest.raises(ValueError):
        upload._process_image(b"this is not an image")


def test_process_image_resizes_long_edge() -> None:
    Image = pytest.importorskip("PIL.Image")
    import io

    buf = io.BytesIO()
    Image.new("RGB", (3000, 1500)).save(buf, "PNG")
    out = upload._process_image(buf.getvalue())
    assert max(Image.open(io.BytesIO(out)).size) <= upload.MAX_EDGE
