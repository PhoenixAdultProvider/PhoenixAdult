from __future__ import annotations

from app.clients.base import SceneDetail, SearchResult
from app.mappers.metadata_mapper import MetadataMapper
from app.registry import find_site, normalize_site_key
from app.utils.helpers.helpers import b64url_decode, pack_cur_id, split_subsite
from app.utils.plex.rating_key import parse_rating_key, to_rating_key


def _detail(studio: str, tagline: str | None = None, collections: list[str] | None = None) -> SceneDetail:
    return SceneDetail(title='A Scene', summary='', studio=studio, genres=[], actors=[], art=[], tagline=tagline, collections=collections)


async def _to_meta(detail: SceneDetail, filename_site: str | None = None) -> tuple[str | None, list[str]]:
    md = await MetadataMapper().to_metadata(detail, 'scene-x-YWJj', 'com.plexapp.agents.x', None, None, filename_site=filename_site)
    return md.tagline, [c.tag for c in (md.Collection or [])]


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
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Big Tits at School')
    assert result.title.endswith('[Big Tits at School]')


def test_match_result_client_subsite_beats_filename_site() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id='YWJj', subsite='Real Wife Stories')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Big Tits at School')
    assert result.title.endswith('[Real Wife Stories]')


def test_match_result_folds_filename_subsite_into_cur_id() -> None:
    raw = SearchResult(title='A Scene', scene_url='https://x/1', cur_id=pack_cur_id(['3870731|scene']))
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Big Tits at School')
    payload, sub = split_subsite(b64url_decode(parse_rating_key(result.ratingKey)['cur_id']))  # type: ignore[arg-type]
    assert payload == '3870731|scene' and sub == 'Big Tits at School'
    same = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x', filename_site='Brazzers')
    assert split_subsite(b64url_decode(parse_rating_key(same.ratingKey)['cur_id']))[1] is None  # type: ignore[arg-type]


def test_match_result_label_uses_registry_casing() -> None:
    raw = SearchResult(title='Horny MILF', scene_url='https://x/1', cur_id=pack_cur_id(['4655051|scene']), subsite='Moms in control')
    result = MetadataMapper().to_match_result(raw, 'Brazzers', 100.0, 'com.plexapp.agents.x')
    assert '[Moms in Control]' in result.title


async def test_metadata_tagline_chain_scrape_wins() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers', tagline='Real Wife Stories'), filename_site='Big Tits at School')
    assert tagline == 'Real Wife Stories' and collections == ['Real Wife Stories']


async def test_metadata_tagline_chain_falls_back_to_filename_subsite() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers', tagline=None), filename_site='Big Tits at School')
    assert tagline == 'Big Tits at School' and collections == ['Big Tits at School']


async def test_metadata_tagline_chain_blank_when_no_subsite() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers', tagline=None), filename_site='Brazzers')
    assert tagline is None and collections == ['Brazzers']


async def test_metadata_tagline_dropped_when_equal_to_studio() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers', tagline='Brazzers'))
    assert tagline is None and collections == ['Brazzers']
