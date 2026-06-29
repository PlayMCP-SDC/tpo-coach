"""렌더링 검증 더미 도구(render_check) 검사.

호스트가 이미지를 그리는지 '실측'하기 위한 도구이므로, 여기서는 도구가
의도한 콘텐츠 블록(텍스트/이미지)을 올바르게 내보내는지까지만 확인한다.
실제 카카오톡 렌더링 여부는 PlayMCP 에 올려 눈으로 확인해야 한다.
"""

from mcp.types import ImageContent, TextContent


async def test_render_check_listed(client_session) -> None:
    async with client_session() as client:
        result = await client.list_tools()
    assert "render_check" in {t.name for t in result.tools}


async def test_markdown_mode_returns_image_url_text(client_session) -> None:
    async with client_session() as client:
        result = await client.call_tool(
            "render_check", {"mode": "markdown", "image_url": "https://x.test/a.jpg"}
        )
    assert not result.isError
    assert all(isinstance(c, TextContent) for c in result.content)
    text = "".join(c.text for c in result.content)
    assert "![" in text and "https://x.test/a.jpg" in text


async def test_image_mode_returns_image_block(client_session) -> None:
    async with client_session() as client:
        result = await client.call_tool("render_check", {"mode": "image"})
    assert not result.isError
    imgs = [c for c in result.content if isinstance(c, ImageContent)]
    assert len(imgs) == 1
    assert imgs[0].mimeType == "image/png"
    assert imgs[0].data  # base64 페이로드 존재


async def test_both_mode_returns_text_and_image(client_session) -> None:
    async with client_session() as client:
        result = await client.call_tool("render_check", {"mode": "both"})
    assert not result.isError
    assert any(isinstance(c, TextContent) for c in result.content)
    assert any(isinstance(c, ImageContent) for c in result.content)
