"""이미지 도구 — 트리거 역할만.

MCP 도구는 사용자가 /upload 로 올린 이미지를 **반환**만 한다(설명/분석 X).
설명은 **호스트의 모델**(Claude·ChatGPT 등 멀티모달 호스트)이 직접 본 뒤 한다.
→ 도구는 특정 모델에 의존하지 않는다(모델 독립). 근거: docs/idea/image_poc.md

주의: PlayMCP AI Chat 처럼 TextContent 만 허용하는 텍스트 전용 호스트는
ImageContent 를 렌더링하지 못한다(docs/idea/image-input.md). 그런 호스트에서의
이미지 UX는 별도 과제다.
"""

from __future__ import annotations

from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

from playmcp_server.web.upload import get_image_bytes

_NOT_FOUND = (
    "이미지를 찾을 수 없습니다(만료되었거나 잘못된 링크). 다시 업로드해 주세요."
)


def _extract_token(image_ref: str) -> str:
    """'.../i/<token>' 형태면 토큰만, 아니면 입력 자체를 토큰으로 본다."""
    path = urlparse(image_ref).path
    return path.rsplit("/", 1)[-1] if "/" in path else image_ref


def register_tools(mcp: FastMCP) -> None:
    """이미지 도구를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Get uploaded image",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,  # 외부 API 호출 없음 — 저장된 바이트만 반환
        )
    )
    def get_uploaded_image(image_ref: str) -> Image:
        """Returns an image the user uploaded to TPO Coach for the host model to view.

        The host's own (multimodal) model looks at the returned image and answers
        the user — this tool does not run any vision model itself. Provide the
        upload reference (the URL/token returned by the /upload page).

        Args:
            image_ref: Upload reference (e.g. ".../i/abc123" or the token itself).

        Returns:
            The uploaded image (JPEG) as image content.
        """
        data = get_image_bytes(_extract_token(image_ref))
        if data is None:
            raise ValueError(_NOT_FOUND)
        return Image(data=data, format="jpeg")
