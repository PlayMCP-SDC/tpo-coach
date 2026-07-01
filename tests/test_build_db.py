"""라벨링 JSON → outfits DB 빌드·검증."""

import json
import sqlite3

import pytest

from playmcp_server.db import build_db


def _doc(
    oid: int,
    *,
    style: str = "모던",
    substyle: str | None = "톰보이",
    top_cat: str | None = "블라우스",
    bottom_cat: str | None = "팬츠",
    bottom_len: str | None = "롱",
    top_sleeve: str | None = None,
    top_material: list[str] | None = None,
    bottom_material: list[str] | None = None,
) -> dict:
    """최소 유효 라벨링 JSON 문서를 만든다."""
    top: dict = {"카테고리": top_cat} if top_cat else {}
    if top_sleeve is not None:
        top["소매기장"] = top_sleeve
    if top_material is not None:
        top["소재"] = top_material
    bottom: dict = (
        {"카테고리": bottom_cat, "기장": bottom_len} if bottom_cat else {}
    )
    if bottom_material is not None:
        bottom["소재"] = bottom_material
    lab: dict = {
        "스타일": [{"스타일": style, "서브스타일": substyle}],
        "상의": [top],
        "하의": [bottom],
        "아우터": [{}],
        "원피스": [{}],
    }
    return {
        "이미지 정보": {"이미지 식별자": oid, "이미지 파일명": f"{oid}.jpg"},
        "데이터셋 정보": {
            "파일 생성일자": "2020-01-01 00:00:00",
            "데이터셋 상세설명": {"라벨링": lab},
        },
    }


def _write(root, style: str, oid: int, **kw) -> None:
    d = root / style
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{oid}.json").write_text(
        json.dumps(_doc(oid, style=style, **kw), ensure_ascii=False),
        encoding="utf-8",
    )


def test_image_url() -> None:
    assert build_db._image_url("123", "https://b/o") == "https://b/o/123.jpg"
    assert build_db._image_url("123", "https://b/o/") == "https://b/o/123.jpg"
    assert build_db._image_url("123", "") == "123.jpg"


def test_parse_outfit_basic() -> None:
    row = build_db.parse_outfit(_doc(7), now="t", url_base="https://b")
    assert row["id"] == "7"
    assert row["image_url"] == "https://b/7.jpg"
    assert row["style"] == "모던"
    assert row["substyle"] == "톰보이"
    assert row["bottom_category"] == "팬츠"
    assert row["bottom_length"] == "롱"
    assert row["top_category"] == "블라우스"
    assert "_sig" in row


def test_parse_normalizes_length() -> None:
    row = build_db.parse_outfit(_doc(1, bottom_len="노말"), now="t")
    assert row["bottom_length"] == "노멀"


def test_parse_rejects_unknown_style() -> None:
    with pytest.raises(build_db.ParseError, match="스타일"):
        build_db.parse_outfit(_doc(1, style="없는스타일"), now="t")


def test_parse_rejects_unknown_substyle() -> None:
    with pytest.raises(build_db.ParseError, match="서브스타일"):
        build_db.parse_outfit(_doc(1, substyle="없는서브"), now="t")


def test_parse_rejects_category_in_wrong_part() -> None:
    # 팬츠는 하의 카테고리 → 상의에 오면 미등록
    with pytest.raises(build_db.ParseError, match="카테고리"):
        build_db.parse_outfit(_doc(1, top_cat="팬츠"), now="t")


def test_parse_rejects_unknown_length() -> None:
    with pytest.raises(build_db.ParseError, match="기장"):
        build_db.parse_outfit(_doc(1, bottom_len="초롱"), now="t")


def test_build_loads_and_dedupes(tmp_path) -> None:
    root = tmp_path / "labels"
    _write(root, "모던", 1)  # 동일 라벨
    _write(root, "모던", 2)  # 1 과 라벨 동일 → dedupe
    _write(root, "모던", 3, bottom_cat="청바지")  # 라벨 다름 → 별도
    dest = tmp_path / "out.db"
    loaded, skipped, deduped = build_db.build(root, dest, url_base="https://b")
    assert (loaded, skipped, deduped) == (2, 0, 1)
    conn = sqlite3.connect(dest)
    assert conn.execute("SELECT COUNT(*) FROM outfits").fetchone()[0] == 2


def test_build_skips_missing_style(tmp_path) -> None:
    root = tmp_path / "labels"
    d = root / "기타"
    d.mkdir(parents=True)
    doc = _doc(1)
    doc["데이터셋 정보"]["데이터셋 상세설명"]["라벨링"]["스타일"] = [{}]
    (d / "1.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    loaded, skipped, deduped = build_db.build(root, tmp_path / "o.db")
    assert loaded == 0 and skipped == 1


def test_parse_extracts_sleeve_material_warmth() -> None:
    row = build_db.parse_outfit(
        _doc(9, top_sleeve="반팔", top_material=["우븐", "린넨"]),
        now="t",
    )
    assert row["top_sleeve"] == "반팔"
    assert row["top_material"] == "우븐,린넨"
    assert row["top_warmth"] == "시원"       # 린넨 → 시원
    assert "bottom_sleeve" not in row         # 하의엔 sleeve 없음
    assert row["bottom_material"] is None     # 소재 미지정
    assert row["bottom_warmth"] is None


def test_parse_bottom_warmth_from_material() -> None:
    row = build_db.parse_outfit(
        _doc(10, bottom_material=["코듀로이"]), now="t"
    )
    assert row["bottom_material"] == "코듀로이"
    assert row["bottom_warmth"] == "따뜻"


def test_parse_rejects_unknown_sleeve() -> None:
    with pytest.raises(build_db.ParseError, match="소매기장"):
        build_db.parse_outfit(_doc(1, top_sleeve="쓰리쿼터"), now="t")


def test_parse_rejects_unknown_material() -> None:
    with pytest.raises(build_db.ParseError, match="소재"):
        build_db.parse_outfit(_doc(1, top_material=["금속"]), now="t")


def test_build_persists_season_columns(tmp_path) -> None:
    root = tmp_path / "labels"
    _write(root, "모던", 1, top_sleeve="긴팔", top_material=["울/캐시미어"])
    dest = tmp_path / "out.db"
    build_db.build(root, dest, url_base="https://b")
    conn = sqlite3.connect(dest)
    r = conn.execute(
        "SELECT top_sleeve, top_material, top_warmth FROM outfits"
    ).fetchone()
    assert r == ("긴팔", "울/캐시미어", "따뜻")


def test_build_strict_raises(tmp_path) -> None:
    root = tmp_path / "labels"
    d = root / "모던"
    d.mkdir(parents=True)
    # 폴더명과 무관하게 JSON 의 스타일이 미등록이면 strict 에서 중단
    (d / "1.json").write_text(
        json.dumps(_doc(1, style="없는스타일"), ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(build_db.ParseError):
        build_db.build(root, tmp_path / "o.db", strict=True)
