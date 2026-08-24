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


def test_title_distance_score_ignores_restored_apostrophes() -> None:
    assert title_distance_score('Lets Play', "Let's Play") == 100
    assert title_distance_score('Its Been a While', "It's Been a While") == 100
    assert title_distance_score('Lets Her Hair Down', 'Rachel Lets Her Hair Down') == title_distance_score("Let's Her Hair Down", 'Rachel Lets Her Hair Down')


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


def test_meta_content_pins_one_attribute_when_asked() -> None:
    from parsel import Selector

    from phoenixadult.utils.helpers.html_helpers import meta_content

    both = Selector(text='<meta property="twitter:title" content="OG"><meta name="twitter:title" content="CARD">')
    assert meta_content(both, 'twitter:title') == 'OG'
    assert meta_content(both, 'twitter:title', 'name') == 'CARD'
    assert meta_content(both, 'twitter:title', 'property') == 'OG'

    only_property = Selector(text='<meta property="description" content="FROM PROPERTY">')
    assert meta_content(only_property, 'description') == 'FROM PROPERTY'
    assert meta_content(only_property, 'description', 'name') == ''

    assert meta_content(Selector(text='<meta name="k" content="  padded  ">'), 'k', 'name') == 'padded'
    assert meta_content(Selector(text='<meta name="k">'), 'k', 'name') == ''


def test_scene_url_id_reads_the_site_id_from_a_path_or_a_query() -> None:
    from phoenixadult.utils.helpers.helpers import scene_url_id

    assert scene_url_id('https://www.scoreland.com/big-boob-videos/Danielle-Derek/45336/') == '45336'
    assert scene_url_id('https://www.scoreland.com/big-boob-videos/Danielle-Derek/45336') == '45336'
    assert scene_url_id('https://site-api.project1service.com/v2/releases?type=scene&id=3816751') == '3816751'
    assert scene_url_id('https://lubed.com/api/releases/soapy-wet-threesome') == ''
    assert scene_url_id('https://example.com/2024/some-scene/') == ''
    assert scene_url_id(None) == ''
