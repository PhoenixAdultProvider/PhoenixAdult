from __future__ import annotations

from app.utils.helpers.helpers import format_duration, pack_cur_id, unpack_cur_id


def test_cur_id_roundtrip() -> None:
    encoded = pack_cur_id(['https://example.com/scene/123', '2024-01-02'])
    decoded = unpack_cur_id(encoded)
    assert decoded['head'] == 'https://example.com/scene/123'
    assert decoded['tail'] == '2024-01-02'


def test_cur_id_no_tail() -> None:
    decoded = unpack_cur_id(pack_cur_id(['https://example.com/scene/123']))
    assert decoded['head'] == 'https://example.com/scene/123'
    assert decoded['tail'] is None


def test_format_duration() -> None:
    assert format_duration(None) is None
    assert format_duration(90_000) == '1:30'
    assert format_duration(3_661_000) == '01:01:01'
