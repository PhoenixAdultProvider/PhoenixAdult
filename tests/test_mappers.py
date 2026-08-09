from __future__ import annotations

import pytest

import phoenixadult.mappers.metadata_mapper as mapper_mod
from phoenixadult.clients.base import ActorResult, SceneDetail, SearchResult
from phoenixadult.mappers.metadata_mapper import MetadataMapper
from phoenixadult.registry import find_site, normalize_site_key
from phoenixadult.utils.helpers.helpers import b64url_decode, pack_cur_id, split_subsite
from phoenixadult.utils.plex.rating_key import parse_rating_key, to_rating_key

POSTER, BG, SQ, UNK = 'http://x/poster.jpg', 'http://x/bg.jpg', 'http://x/sq.jpg', 'http://x/unk.jpg'
POSTER_XL = 'http://x/poster-xl.jpg'
_DIMS = {POSTER: (1000, 1500), POSTER_XL: (1200, 1800), BG: (1920, 1080), SQ: (1000, 1000), UNK: (1000, 1300)}


async def _image_types(monkeypatch: pytest.MonkeyPatch, urls: list[str]) -> dict[str, list[str]]:
    async def fake_dims(url: str, referers: object = None, cookies: object = None) -> dict[str, int] | None:
        w, h = _DIMS[url]
        return {'width': w, 'height': h}

    monkeypatch.setattr(mapper_mod, 'fetch_dimensions', fake_dims)
    monkeypatch.setattr(mapper_mod, 'proxy_url', lambda url, *a, **k: url)
    detail = SceneDetail(title='A Scene', summary='', studio='X', genres=[], actors=[], art=urls)
    md = await MetadataMapper().to_metadata(detail, 'scene-x-YWJj', 'com.plexapp.agents.x')
    by_type: dict[str, list[str]] = {}
    for img in md.Image or []:
        by_type.setdefault(img.type, []).append(img.url)
    return by_type


def _detail(studio: str, tagline: str = '', collections: list[str] | None = None) -> SceneDetail:
    return SceneDetail(title='A Scene', summary='', studio=studio, genres=[], actors=[], art=[], tagline=tagline, collections=collections)


async def _to_meta(detail: SceneDetail, filename_site: str | None = None) -> tuple[str | None, list[str]]:
    md = await MetadataMapper().to_metadata(detail, 'scene-x-YWJj', 'com.plexapp.agents.x', None, None, filename_site=filename_site)
    return md.tagline, [c.tag for c in (md.Collection or [])]


async def test_no_logo_no_clear_logo_image() -> None:
    md = await MetadataMapper().to_metadata(SceneDetail(title='A Scene', studio='X'), 'scene-x-YWJj', 'com.plexapp.agents.x')
    assert all(img.type != 'clearLogo' for img in (md.Image or []))


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
    tagline, collections = await _to_meta(_detail('Brazzers'), filename_site='Big Tits at School')
    assert tagline == 'Big Tits at School' and collections == ['Big Tits at School']


async def test_metadata_tagline_chain_blank_when_no_subsite() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers'), filename_site='Brazzers')
    assert tagline is None and collections == ['Brazzers']


async def test_metadata_tagline_dropped_when_equal_to_studio() -> None:
    tagline, collections = await _to_meta(_detail('Brazzers', tagline='Brazzers'))
    assert tagline is None and collections == ['Brazzers']


async def test_images_emitted_by_class_without_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    by_type = await _image_types(monkeypatch, [POSTER, BG, SQ])
    assert by_type == {'coverPoster': [POSTER], 'background': [BG], 'backgroundSquare': [SQ]}


async def test_images_no_poster_promotes_background_not_square(monkeypatch: pytest.MonkeyPatch) -> None:
    by_type = await _image_types(monkeypatch, [BG, SQ])
    assert by_type['coverPoster'] == [BG]
    assert by_type['background'] == [BG] and by_type['backgroundSquare'] == [SQ]


async def test_images_square_is_last_resort_for_both_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    by_type = await _image_types(monkeypatch, [SQ])
    assert by_type == {'backgroundSquare': [SQ], 'coverPoster': [SQ], 'background': [SQ]}


async def test_images_unknown_promotes_to_poster_but_not_emitted_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    by_type = await _image_types(monkeypatch, [UNK])
    assert by_type == {'coverPoster': [UNK]}


async def test_images_sorted_high_to_low_within_each_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    by_type = await _image_types(monkeypatch, [POSTER, POSTER_XL, BG])
    assert by_type['coverPoster'] == [POSTER_XL, POSTER]
    assert by_type['background'] == [BG]


async def test_thumb_prefers_highest_resolution_poster(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_dims(url: str, referers: object = None, cookies: object = None) -> dict[str, int] | None:
        w, h = _DIMS[url]
        return {'width': w, 'height': h}

    monkeypatch.setattr(mapper_mod, 'fetch_dimensions', fake_dims)
    monkeypatch.setattr(mapper_mod, 'proxy_url', lambda url, *a, **k: url)
    detail = SceneDetail(title='A Scene', summary='', studio='X', genres=[], actors=[], art=[POSTER, POSTER_XL])
    md = await MetadataMapper().to_metadata(detail, 'scene-x-YWJj', 'com.plexapp.agents.x')
    assert md.thumb == POSTER_XL


async def test_actor_names_are_dropped_from_genres(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENERIC_IMAGE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    detail = SceneDetail(
        title='A Scene',
        studio='X',
        genres=['Hardcore', 'Jane Doe', 'Amateur'],
        actors=[ActorResult(name='Jane Doe'), ActorResult(name='Amateur')],
    )
    md = await MetadataMapper().to_metadata(detail, 'scene-x-YWJj', 'com.plexapp.agents.x')

    tags = [g.tag for g in md.Genre or []]
    assert 'Jane Doe' not in tags
    assert 'Hardcore' in tags
    assert 'Amateur' in tags


def test_priority_artwork_outranks_larger_images_within_a_kind() -> None:
    from phoenixadult.mappers.metadata_mapper import build_artwork

    def probed(url: str, w: int, h: int, cls: str) -> dict[str, object]:
        return {'url': url, 'dims': {'width': w, 'height': h}, 'image_class': cls}

    valid = [
        probed('https://d18/cover-front.jpg', 530, 759, 'coverPoster'),
        probed('https://d18/still-huge.jpg', 1200, 1800, 'coverPoster'),
        probed('https://d18/back-cover.jpg', 1000, 1500, 'background'),
        probed('https://d18/wide-huge.jpg', 1920, 1080, 'background'),
    ]
    images = build_artwork(valid, priority={'https://d18/cover-front.jpg'})

    posters = [img.url for img in images if img.type == 'coverPoster']
    assert posters[0] == 'https://d18/cover-front.jpg'
    assert posters[1] == 'https://d18/still-huge.jpg'
    assert [img.url for img in images if img.type == 'background'][0] == 'https://d18/wide-huge.jpg'
    assert next(img for img in images if img.url == 'https://d18/cover-front.jpg').priority is True

    unranked = build_artwork(valid)
    assert [img.url for img in unranked if img.type == 'coverPoster'][0] == 'https://d18/still-huge.jpg'


def test_a_registered_series_reconciles_to_one_rating_key() -> None:
    from phoenixadult.clients.base import SearchResult
    from phoenixadult.mappers.metadata_mapper import MetadataMapper
    from phoenixadult.utils.helpers.helpers import pack_cur_id

    mapper = MetadataMapper()
    cur = pack_cur_id(['183626', '2024-01-18'])
    shared = {'title': 'Stepsister Needs An Orgasm', 'scene_url': 'https://stepsiblingscaught.com/video/watch/183626', 'cur_id': cur}

    via_own_site = mapper.to_match_result(
        SearchResult(**shared, subsite='Step Siblings Caught'), 'Step Siblings Caught', 100, 'tv.plex.test', '2024-01-18', scraper_type='nubiles'
    )
    via_network = mapper.to_match_result(
        SearchResult(**shared, subsite='Step Siblings Caught'), 'Nubiles Porn', 100, 'tv.plex.test', '2024-01-18', scraper_type='nubiles'
    )
    assert via_own_site.ratingKey == via_network.ratingKey, 'the same scene must reconcile no matter which network domain the filename named'
    assert 'stepsiblingscaught' in via_network.ratingKey


def test_an_unregistered_series_still_embeds_the_subsite() -> None:
    from phoenixadult.clients.base import SearchResult
    from phoenixadult.mappers.metadata_mapper import MetadataMapper
    from phoenixadult.utils.helpers.helpers import b64url_decode, pack_cur_id
    from phoenixadult.utils.plex.rating_key import parse_rating_key

    mapper = MetadataMapper()
    cur = pack_cur_id(['5', '2024-01-18'])
    result = SearchResult(title='X', scene_url='https://nubiles-porn.com/video/watch/5', cur_id=cur, subsite='Some Unlisted Series')
    mapped = mapper.to_match_result(result, 'Nubiles Porn', 100, 'tv.plex.test', '2024-01-18', scraper_type='nubiles')
    assert 'nubilesporn' in mapped.ratingKey
    parsed = parse_rating_key(mapped.ratingKey)
    assert parsed is not None and '\x1f' in b64url_decode(parsed['cur_id'] or '')


def test_a_same_named_site_of_another_scraper_never_hijacks_the_key() -> None:
    from phoenixadult.clients.base import SearchResult
    from phoenixadult.mappers.metadata_mapper import MetadataMapper
    from phoenixadult.utils.helpers.helpers import pack_cur_id

    mapper = MetadataMapper()
    cur = pack_cur_id(['6', '2024-01-18'])
    result = SearchResult(title='X', scene_url='https://example.com/6', cur_id=cur, subsite='Step Siblings Caught')
    mapped = mapper.to_match_result(result, 'Some Other Site', 100, 'tv.plex.test', '2024-01-18', scraper_type='not-nubiles')
    assert 'someothersite' in mapped.ratingKey, 'a type mismatch keeps the key on the searched site'
