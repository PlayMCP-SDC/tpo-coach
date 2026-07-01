"""셋업(코디) 추천 도구 — 스타일/상황 기반 무작위 N건 추천.

DB 의 K-Fashion 셋업을 style 로 무작위 표본 추출해 이미지 URL 마크다운으로 낸다.
상황→스타일 매핑은 우리가 두지 않고 docstring 으로 호출 LLM 에 위임한다.
"""

from __future__ import annotations

from itertools import zip_longest
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from playmcp_server.db.repository import get_repository
from playmcp_server.db.vocab import STYLES
from playmcp_server.models import Outfit

_N_MIN = 1
_N_MAX = 10
_N_DEFAULT = 3


def _clamp_n(n: int) -> int:
    """추천 개수를 [1, 10] 범위로 보정한다."""
    return max(_N_MIN, min(_N_MAX, n))


_STYLE_LIST = sorted(STYLES)  # 23종 — 설명·스키마·안내 공용 단일 출처


def _normalize_styles(styles: list[str]) -> list[str]:
    """중복 제거(순서 보존) 후 STYLES 에 있는 유효 스타일만 남긴다."""
    seen: set[str] = set()
    out: list[str] = []
    for s in styles:
        if s in STYLES and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _no_valid_styles_msg(styles: list[str]) -> str:
    """유효 스타일이 하나도 없을 때 안내(입력 echo + 유효 목록)."""
    shown = ", ".join(styles) if styles else "(없음)"
    return (
        f"지원하는 스타일이 없습니다 (입력: {shown}). "
        f"가능한 스타일: {', '.join(_STYLE_LIST)}"
    )


def _interleave(pools: list[list[Outfit]]) -> list[Outfit]:
    """스타일별 풀을 라운드로빈으로 인터리브한다(각 풀 1개씩 우선, None 제외)."""
    return [o for group in zip_longest(*pools) for o in group if o is not None]


def _part(label: str, category: str | None, length: str | None) -> str | None:
    if not category:
        return None
    return f"{label} {category}" + (f"({length})" if length else "")


def _format_outfit(o: Outfit) -> str:
    """셋업 1건을 이미지 URL 마크다운 블록으로 만든다."""
    parts = [
        p
        for p in (
            _part("상의", o.top_category, o.top_length),
            _part("하의", o.bottom_category, o.bottom_length),
            _part("아우터", o.outer_category, o.outer_length),
            _part("원피스", o.dress_category, o.dress_length),
        )
        if p
    ]
    style_line = o.style + (f" / {o.substyle}" if o.substyle else "")
    return "\n".join(
        [
            f"![코디]({o.image_url})",
            f"- 스타일: {style_line}",
            f"- 구성: {' · '.join(parts) if parts else '정보 없음'}",
        ]
    )


def _recommend(styles: list[str], n: int, header: str | None) -> str:
    """styles 정규화 → 스타일별 무작위 표본 → 라운드로빈 → 마크다운.

    유효 스타일이 하나도 없으면 안내 문자열을 돌려준다(추천 안 함).
    header 가 있으면 결과 맨 위에 붙인다.
    """
    valid = _normalize_styles(styles)
    if not valid:
        return _no_valid_styles_msg(styles)
    k = _clamp_n(n)
    repo = get_repository()
    pools = [repo.sample_outfits(style=s, n=k) for s in valid]
    outfits = _interleave(pools)[:k]
    if not outfits:
        return "해당 스타일의 코디를 찾지 못했습니다. 다른 스타일로 시도해 보세요."
    body = "\n\n".join(_format_outfit(o) for o in outfits)
    return f"{header}\n\n{body}" if header else body


def register_tools(mcp: FastMCP) -> None:
    """추천 도구 2개를 등록한다."""

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend outfit sets by style",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,  # 랜덤 표본 — 매 호출 결과 다름
            openWorldHint=False,  # 로컬 DB·외부 호출 없음
        )
    )
    def recommend_outfits_by_style(style: str, n: int = _N_DEFAULT) -> str:
        """Recommends outfit sets (코디) of a given style for TPO Coach(티피오 코치).

        Samples up to n random outfit coordinations of the requested style from
        the K-Fashion reference set and returns them as image-URL markdown. If the
        style is not supported, the valid style list is returned instead.

        Args:
            style: One of the supported Korean styles (e.g. 클래식, 스트리트, 로맨틱).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.

        Returns:
            Markdown listing recommended outfits (image, style, composition).
        """
        return _recommend([style], n, header=f"**{style}** 스타일 코디 추천")

    @mcp.tool(
        annotations=ToolAnnotations(
            title="Recommend outfit sets for a situation",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def recommend_outfits_by_situation(
        situation: str,
        styles: Annotated[
            list[str],
            Field(
                description=(
                    "Styles that fit the situation, ordered by best fit first. "
                    "You MUST choose ONLY from these 23 supported Korean styles: "
                    + ", ".join(_STYLE_LIST)
                ),
                json_schema_extra={"items": {"type": "string", "enum": _STYLE_LIST}},
            ),
        ],
        n: int = _N_DEFAULT,
    ) -> str:
        """Recommends varied outfit sets (코디) for a situation for TPO Coach(티피오
        코치).

        Given a free-text situation, infer the Korean styles that fit it (ordered by
        best fit) and pass them as `styles`, choosing ONLY from the supported styles
        listed in the `styles` parameter. The tool samples random outfits across those
        styles (round-robin) so the results span different styles. The situation and the
        styles used are echoed in the heading. Unsupported styles are ignored; if none
        are valid, the valid style list is returned.

        Args:
            situation: User's situation in free text (e.g. "주말 소개팅"). Echoed only.
            styles: Supported styles fitting the situation, best fit first (1개 이상).
            n: Number of outfits to recommend. Clamped to 1-10, default 3.

        Returns:
            Markdown: situation/styles heading + recommended outfits across styles.
        """
        used = _normalize_styles(styles)
        label = " · ".join(used)
        suffix = f" ({label})" if label else ""
        header = f"**{situation}**에 어울리는 코디 추천" + suffix
        return _recommend(styles, n, header=header)
