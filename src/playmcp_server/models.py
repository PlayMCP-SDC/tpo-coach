"""도구·저장소가 공유하는 경량 타입."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Outfit:
    """K-Fashion 셋업(코디) 한 건. 부위별 카테고리·기장은 없으면 None."""

    id: str
    image_url: str
    style: str
    substyle: str | None = None
    top_category: str | None = None
    top_length: str | None = None
    bottom_category: str | None = None
    bottom_length: str | None = None
    outer_category: str | None = None
    outer_length: str | None = None
    dress_category: str | None = None
    dress_length: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None
