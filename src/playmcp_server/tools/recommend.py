"""셋업(코디) 추천 도구 — 스타일/상황 기반 무작위 N건 추천.

DB 의 K-Fashion 셋업을 style 로 무작위 표본 추출해 이미지 URL 마크다운으로 낸다.
상황→스타일 매핑은 우리가 두지 않고 docstring 으로 호출 LLM 에 위임한다.
"""

from __future__ import annotations

from playmcp_server.db.vocab import STYLES
from playmcp_server.models import Outfit

_N_MIN = 1
_N_MAX = 10
_N_DEFAULT = 3


def _clamp_n(n: int) -> int:
    """추천 개수를 [1, 10] 범위로 보정한다."""
    return max(_N_MIN, min(_N_MAX, n))


def _invalid_style_msg(style: str) -> str:
    """무효 스타일 입력에 유효 스타일 목록을 안내한다."""
    return (
        f"'{style}' 은(는) 지원하지 않는 스타일입니다. "
        f"가능한 스타일: {', '.join(sorted(STYLES))}"
    )


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
