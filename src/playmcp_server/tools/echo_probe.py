"""echo_probe — 배포/등록 검증용 디버그 프로브 도구.

목적(7/1 조기 검증): PlayMCP 호스트가 도구에 **무엇을** 전달하는지 그대로 돌려준다.
사용자 사진이 어떤 형태로 도달하는지(outfit_text / image_url / image_base64) 확정용.
이미지 입력 도달 방식은 docs/idea/image-input.md 참고. 검증이 끝나면 제거 예정.

새 도구를 짤 때의 올바른 패턴(타입힌트 + docstring + annotations 5종) 예시이기도 하다.
"""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


def register_tools(mcp: FastMCP) -> None:
    """프로브 도구를 FastMCP 인스턴스에 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Echo probe",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def echo_probe(
        outfit_text: str = "",
        image_url: str = "",
        image_base64: str = "",
    ) -> str:
        """Echo args to verify what the PlayMCP host passes to a TPO Coach tool.

        Debug-only probe for deployment/registration checks. It does not process
        images; it only reports which inputs the host populated, so we can confirm
        whether a user's outfit photo arrives as text, an image URL, or base64.

        Args:
            outfit_text: Free-text outfit description (host may convert a photo).
            image_url: Image URL (if the host or user supplied one).
            image_base64: Base64 image data (only its length is reported).

        Returns:
            A summary of which fields were received.
        """
        return (
            f"outfit_text={outfit_text!r} "
            f"image_url={image_url!r} "
            f"image_base64_len={len(image_base64)}"
        )
