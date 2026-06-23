from __future__ import annotations

from app.mappers.metadata_mapper import MetadataMapper


def test_rating_key_roundtrip() -> None:
    mapper = MetadataMapper()
    rk = mapper.to_rating_key('YWJj', 'Some-Site', '2024-01-02')
    parsed = mapper.parse_rating_key(rk)
    assert parsed is not None
    assert parsed['site_name'] == 'somesite'
    assert parsed['cur_id'] == 'YWJj'
    assert parsed['release_date'] == '2024-01-02'
