from __future__ import annotations

from app.utils.helpers.helpers import format_duration, pack_cur_id, title_distance_score, unpack_cur_id


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


def test_title_distance_score_matches_spelled_out_ordinals() -> None:
    # Plex-safe "Part Three" filename must match upstream "Part 3".
    assert title_distance_score('Big Tits in History: Part Three', 'Big Tits in History: Part 3') == 100
    assert title_distance_score('Big Tits in History: Episode Three', 'Big Tits in History: Episode 3') == 100
    assert title_distance_score('Big Tits in History: Episode 3', 'Big Tits in History: Episode 3') == 100


def test_title_distance_score_keeps_distinct_ordinals_apart() -> None:
    # Normalizing ordinals must not collapse different episode numbers to a perfect match.
    assert title_distance_score('Big Tits in History: Part Three', 'Big Tits in History: Part 4') < 100
    assert title_distance_score('Big Tits in History: Part 3', 'Big Tits in History: Part 4') < 100
