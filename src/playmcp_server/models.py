"""도구·저장소가 공유하는 경량 타입."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClothingItem:
    """개별 의상 아이템 (색 매칭용)."""

    id: str
    name: str
    category: str
    color: str
    image_url: str
    formality: int
    subcategory: str | None = None
    seller_name: str | None = None
    seller_url: str | None = None
    price: int | None = None
    season: str | None = None
    style_tags: str | None = None


@dataclass(frozen=True)
class Outfit:
    """큐레이션된 셋업/코디 (상황 기반 추천용)."""

    id: str
    image_url: str
    occasion_tags: str
    title: str | None = None
    source: str | None = None
    source_url: str | None = None
    formality: int | None = None
    season: str | None = None
    style_tags: str | None = None
    items_note: str | None = None
