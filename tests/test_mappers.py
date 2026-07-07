from __future__ import annotations

from app.clients.base import SearchResult
from app.mappers.metadata_mapper import MetadataMapper
from app.registry import find_site, normalize_site_key
from app.utils.plex.rating_key import parse_rating_key, to_rating_key


def test_rating_key_roundtrip() -> None:
    rk = to_rating_key('YWJj', 'Some-Site', '2024-01-02')
    parsed = parse_rating_key(rk)
    assert parsed is not None
    assert parsed['site_name'] == 'somesite'
    assert parsed['cur_id'] == 'YWJj'
    assert parsed['release_date'] == '2024-01-02'


def test_rating_key_drops_non_iso_date() -> None:
    rk = to_rating_key('YWJj', 'Some-Site', 'Jan 2023')
    assert rk == 'scene-somesite-YWJj'
    assert parse_rating_key(rk) is not None


def test_normalize_site_key_strips_punctuation_and_accents() -> None:
    assert normalize_site_key("Ricky's Room") == 'rickysroom'
    assert normalize_site_key('Rickys Room') == 'rickysroom'
    assert normalize_site_key('Señorita Pépe') == 'senoritapepe'


def test_rating_key_site_resolves_back_through_registry() -> None:
    site = find_site("Ricky's Room")
    assert site is not None
    parsed = parse_rating_key(to_rating_key('YWJj', site.name))
    assert parsed is not None
    assert find_site(parsed['site_name'] or '') is site


def test_match_result_labels_with_subsite_when_present() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj', subsite='Big Tits at School')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x')
    assert result.title.endswith('[Big Tits at School]')


def test_match_result_falls_back_to_master_site_without_subsite() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x')
    assert result.title.endswith('[Brazzers]')


def test_match_result_falls_back_to_filename_site_when_client_has_no_subsite() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj')  # client supplied no sub-site
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Big Tits at School')
    assert result.title.endswith('[Big Tits at School]')


def test_match_result_client_subsite_beats_filename_site() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj', subsite='Real Wife Stories')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Big Tits at School')
    assert result.title.endswith('[Real Wife Stories]')
