"""SQLite 스키마 — K-Fashion 셋업(코디) 레퍼런스.

한 행 = 한 이미지(셋업). 부위(상의/하의/아우터/원피스)별 카테고리·기장을
고정 컬럼으로 담는다(부위당 의류 최대 1개). 개별 의류(garments)는 별도
독립 소스이며 이 스키마에 포함하지 않는다.

soft delete: deleted_at 이 NULL 이면 활성 행. 인덱스는 활성 행만 대상으로 한다.
"""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS outfits (
    id          TEXT PRIMARY KEY,   -- 이미지 식별자(= 버킷 객체 키 stem, 전역 고유)
    image_url   TEXT NOT NULL,      -- 버킷 공개 URL ("{base}/{id}.jpg")
    style       TEXT NOT NULL,      -- 스타일 (STYLES)
    substyle    TEXT,               -- 서브스타일 (SUBSTYLES)

    -- 구성: 부위별 카테고리 + 기장 + 소매기장 + 소재(원값) + 보온등급(파생).
    -- sleeve 는 상의/아우터/원피스만(하의엔 소매기장 없음).
    top_category    TEXT, top_length    TEXT, top_sleeve  TEXT,
    top_material    TEXT, top_warmth    TEXT,
    bottom_category TEXT, bottom_length TEXT,
    bottom_material TEXT, bottom_warmth TEXT,
    outer_category  TEXT, outer_length  TEXT, outer_sleeve TEXT,
    outer_material  TEXT, outer_warmth  TEXT,
    dress_category  TEXT, dress_length  TEXT, dress_sleeve TEXT,
    dress_material  TEXT, dress_warmth  TEXT,

    created_at  TEXT,               -- 파일 생성일자(JSON)
    updated_at  TEXT,               -- 마지막 변경 시각
    deleted_at  TEXT                -- soft delete (NULL = 활성)
);
CREATE INDEX IF NOT EXISTS idx_outfits_style
  ON outfits(style) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_outfits_substyle
  ON outfits(substyle) WHERE deleted_at IS NULL;
"""


def init_schema(conn: sqlite3.Connection) -> None:
    """주어진 연결에 테이블·인덱스를 생성한다(멱등)."""
    conn.executescript(SCHEMA)
