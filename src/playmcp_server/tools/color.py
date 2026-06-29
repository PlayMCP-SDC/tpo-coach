"""색상 추출 도구 — 모델 없이(Pillow) 이미지 대표 색상을 뽑아 텍스트로 반환.

비전 모델·외부 API·키가 필요 없다(완전 모델 독립, 오프라인). 결과가 텍스트라
PlayMCP 등 텍스트 전용 호스트에서도 동작한다. TPO Coach 색상 매칭의 1단계
(이 색을 기준으로 어울리는 하의를 추천하는 흐름으로 확장).
"""

from __future__ import annotations

import io
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from playmcp_server.web.upload import get_image_bytes

_NOT_FOUND = (
    "이미지를 찾을 수 없습니다(만료되었거나 잘못된 링크). 다시 업로드해 주세요."
)

# 흔한 의류 색상 (이름, R, G, B) — 추출 색을 가장 가까운 이름으로 매핑
_NAMED: list[tuple[str, int, int, int]] = [
    ("검정", 0, 0, 0),
    ("흰색", 255, 255, 255),
    ("회색", 128, 128, 128),
    ("남색", 25, 35, 75),
    ("파랑", 30, 80, 200),
    ("하늘색", 120, 180, 230),
    ("청록", 0, 140, 140),
    ("초록", 40, 140, 60),
    ("카키", 110, 110, 70),
    ("노랑", 230, 200, 60),
    ("주황", 230, 130, 40),
    ("빨강", 200, 40, 40),
    ("분홍", 230, 150, 175),
    ("보라", 130, 70, 160),
    ("갈색", 110, 70, 45),
    ("베이지", 225, 210, 180),
]


def _name_of(r: int, g: int, b: int) -> str:
    """RGB 를 가장 가까운 의류 색 이름으로."""

    def dist(c: tuple[str, int, int, int]) -> int:
        return (r - c[1]) ** 2 + (g - c[2]) ** 2 + (b - c[3]) ** 2

    return min(_NAMED, key=dist)[0]


def extract_colors(data: bytes, n: int = 5) -> list[tuple[str, str, float]]:
    """대표 색상을 (hex, 이름, 비율) 목록으로 비율 내림차순 반환."""
    from PIL import Image

    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((128, 128))  # 속도용 축소
    q = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette() or []
    counts = q.getcolors() or []
    total = sum(c for c, _ in counts) or 1
    out: list[tuple[str, str, float]] = []
    for count, idx in sorted(counts, reverse=True):
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        out.append((f"#{r:02X}{g:02X}{b:02X}", _name_of(r, g, b), count / total))
    return out


def _extract_token(image_ref: str) -> str:
    """'.../i/<token>' 형태면 토큰만, 아니면 입력 자체를 토큰으로 본다."""
    path = urlparse(image_ref).path
    return path.rsplit("/", 1)[-1] if "/" in path else image_ref


def register_tools(mcp: FastMCP) -> None:
    """색상 추출 도구를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Extract clothing colors",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,  # 외부 API 호출 없음 — 로컬 계산만
        )
    )
    def extract_color(image_ref: str) -> str:
        """Extracts dominant colors of a clothing image for TPO Coach(티피오 코치).

        Runs locally with no external model or API key, so it is fast and offline.
        Returns the top colors as text (hex, Korean name, ratio) for outfit color
        matching. Provide the upload reference returned by the /upload page.

        Args:
            image_ref: Upload reference (e.g. ".../i/abc123" or the token itself).

        Returns:
            Markdown text listing the dominant colors.
        """
        data = get_image_bytes(_extract_token(image_ref))
        if data is None:
            return _NOT_FOUND
        colors = extract_colors(data)
        lines = ["**추출된 주요 색상 (TPO Coach):**"]
        for i, (hex_, name, ratio) in enumerate(colors, 1):
            lines.append(f"{i}. {hex_} {name} ({ratio * 100:.0f}%)")
        return "\n".join(lines)
