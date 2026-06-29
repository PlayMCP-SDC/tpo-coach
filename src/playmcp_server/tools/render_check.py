"""렌더링 검증용 더미 도구 — 호스트가 응답 이미지를 실제로 그리는지 실측한다.

공모전 최종 타깃은 카카오톡(PlayMCP 경유)이고, 거기서 '이미지 출력'이 되는지가
설계의 핵심 불확실성이다. 호스트가 이미지를 그리는 방식은 둘로 나뉘는데, 이 도구는
둘을 분리해서 보내 어느 쪽이 채팅창에 사진으로 뜨는지 눈으로 확인하게 한다.

- markdown : 텍스트 안의 ``![](url)`` 마크다운 이미지
             (URL 방식, S3 등 실제 링크도 인자로 테스트 가능)
- image    : MCP ``ImageContent`` 블록 (base64, 로컬 생성한 작은 PNG)

결과 해석:
- 마크다운 URL이 사진으로 뜨면 → 추천 결과를 URL로 주는 설계가 안전.
- 초록 사각형(ImageContent)이 사진으로 뜨면 → base64 블록도 사용 가능
  (단 PlayMCP 20k 글자 제한 유의).
- 둘 다 텍스트/링크로만 보이면 → 호스트 인라인 렌더링 불가
  → 결과 웹페이지 링크 방식으로 폴백.
"""

from __future__ import annotations

import io

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import ToolAnnotations

# 마크다운 모드 기본 이미지(고정 seed 라 매번 같은 사진). 실제 링크는 인자로 덮어쓴다.
_DEFAULT_IMAGE_URL = "https://picsum.photos/seed/tpo-coach/240/240"


def _sample_png() -> bytes:
    """식별용 작은 PNG(초록 배경 + 흰 사각형)를 만든다.

    96x96 이라 base64 가 작아 PlayMCP 20k 글자 제한에 안전하다. '초록 사각형'이
    보이면 그게 ImageContent 경로로 렌더된 것이라고 판별할 수 있다.
    """
    from PIL import Image as PILImage
    from PIL import ImageDraw

    img = PILImage.new("RGB", (96, 96), (40, 140, 60))
    ImageDraw.Draw(img).rectangle((28, 28, 68, 68), fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def register_tools(mcp: FastMCP) -> None:
    """렌더링 검증 도구를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Render check (image vs markdown)",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,  # 외부 호출 없음 — 문자열/로컬 생성만
        ),
        # 텍스트+이미지 혼합 콘텐츠를 그대로 내보내기 위해 구조화 출력은 끈다.
        structured_output=False,
    )
    def render_check(mode: str = "both", image_url: str = "") -> object:
        """Probes how the chat host renders images for TPO Coach(티피오 코치).

        Use this to verify whether the host (e.g. KakaoTalk via PlayMCP) shows
        images returned by an MCP tool. It can return a markdown image link, an
        MCP ImageContent block, or both, so you can see which one appears as a
        real picture in the chat.

        Args:
            mode: "markdown" (text with ![](url)), "image" (an MCP ImageContent
                block: a green square generated locally), or "both" (default).
            image_url: URL used by the markdown mode. Defaults to a sample image;
                pass your own (e.g. an S3 presigned URL) to test a real link.

        Returns:
            Text and/or image content, depending on mode.
        """
        url = image_url.strip() or _DEFAULT_IMAGE_URL
        md = (
            "**[render_check] 마크다운 URL 테스트**\n"
            "아래가 사진으로 보이면 URL 방식 OK:\n\n"
            f"![tpo-coach test]({url})"
        )
        green = (
            "**[render_check] ImageContent 테스트** — "
            "초록 사각형이 사진으로 보이면 OK."
        )

        if mode == "markdown":
            return md
        if mode == "image":
            return [green, Image(data=_sample_png(), format="png")]
        # both: 두 방식을 한 응답에 같이 보내 비교한다.
        return [md, "\n" + green, Image(data=_sample_png(), format="png")]
