from __future__ import annotations

from phoenixadult.utils.helpers.helpers import dict_values_from_key, format_duration, pack_cur_id, title_distance_score, unpack_cur_id


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
    assert title_distance_score('Big Tits in History: Part Three', 'Big Tits in History: Part 3') == 100
    assert title_distance_score('Big Tits in History: Episode Three', 'Big Tits in History: Episode 3') == 100
    assert title_distance_score('Big Tits in History: Episode 3', 'Big Tits in History: Episode 3') == 100


def test_title_distance_score_keeps_distinct_ordinals_apart() -> None:
    assert title_distance_score('Big Tits in History: Part Three', 'Big Tits in History: Part 4') < 100
    assert title_distance_score('Big Tits in History: Part 3', 'Big Tits in History: Part 4') < 100


def test_title_distance_score_rotates_trailing_articles() -> None:
    assert title_distance_score('The Big Movie', 'Big Movie, The') == 100
    assert title_distance_score('A Whore of Wall Street', 'Whore of Wall Street, A') == 100


def test_dict_values_from_key_matches_case_insensitively() -> None:
    table = {'40oz-zombie-booty': ('Vanessa', 'Vanessa Cruz')}
    assert dict_values_from_key(table, '40oz-zombie-booty') == ('Vanessa', 'Vanessa Cruz')
    assert dict_values_from_key(table, '40OZ-Zombie-Booty') == ('Vanessa', 'Vanessa Cruz')
    assert dict_values_from_key(table, 'other-scene') is None


def test_dict_values_from_key_accepts_a_tuple_of_equivalent_keys() -> None:
    table = {('one-title', 'other-title'): ('Vanessa', 'Vanessa Monet')}
    assert dict_values_from_key(table, 'other-title') == ('Vanessa', 'Vanessa Monet')
