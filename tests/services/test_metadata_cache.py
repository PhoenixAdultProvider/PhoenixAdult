from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from PIL import Image as PILImage

from phoenixadult.models.metadata import PlexData18, PlexImage, PlexMetadataResponse
from phoenixadult.utils import cache as mc
from phoenixadult.utils import db
from phoenixadult.utils.cache import text_rules as _text_rules  # noqa: F401
from phoenixadult.utils.helpers.helpers import b64url_encode, embed_subsite
from phoenixadult.utils.images import image_fetcher
from phoenixadult.utils.plex.rating_key import to_rating_key


@pytest.fixture(autouse=True)
def _unsigned_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc, 'sign_url', lambda url: url)


def test_rebased_urls_are_signed(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.auth.url_signing import sign_url

    monkeypatch.setattr(mc, 'sign_url', sign_url)
    out = mc._rebase(
        {'thumb': '/cache/ab/bundle/images/img-00.jpg', 'role': '/images/local/people/actor.jane_female.jpg?v=1'},
        'http://b',
        'http://p',
    )
    assert out['thumb'].startswith('http://b/cache/') and '?sig=' in out['thumb']
    assert out['role'].startswith('http://p/images/local/') and '&sig=' in out['role']


def test_reapply_text_rules_renormalizes_genres_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: [t.upper() for t in tags if t != 'Drop Me'])
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: 'Canonical' if name in ('Alias A', 'Alias B') else name)

    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'S',
                        'Genre': [{'tag': 'Keep'}, {'tag': 'Drop Me'}],
                        'Role': [{'tag': 'Alias A'}, {'tag': 'Alias B'}, {'tag': 'Solo'}],
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    md = resp.MediaContainer.Metadata[0]
    assert [g.tag for g in (md.Genre or [])] == ['KEEP']
    assert [r.tag for r in (md.Role or [])] == ['Canonical', 'Solo']


def test_reapply_text_rules_noop_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: name)
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'T', 'Genre': [{'tag': 'Anal'}]}],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is False


def test_reapply_text_rules_recases_studio_tagline_collections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_studio', lambda name, site_name='': name.title().replace('Of', 'of'))
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'word of the day',
                        'tagline': 'lady Of the manor',
                        'Collection': [{'tag': 'word of the day'}, {'tag': 'Word Of The Day'}],
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    md = resp.MediaContainer.Metadata[0]
    assert md.studio == 'Word of The Day'
    assert md.tagline == 'Lady of The Manor'
    assert [c.tag for c in md.Collection or []] == ['Word of The Day']


def test_reapply_text_rules_recases_title_and_titlesort() -> None:
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'the tale of two part 2', 'titleSort': 'stale'}],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    md = resp.MediaContainer.Metadata[0]
    assert md.title == 'The Tale of Two: Part 2'
    assert md.titleSort == 'Tale of Two: Part 2'


def _tagged_response(title: str) -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title}]}}
    )


@pytest.mark.parametrize(
    ('scraper', 'tagged', 'clean'),
    [
        ('nubiles', 'Stepmom Wants to Move In - S2:E1', 'Stepmom Wants to Move In'),
        ('reptyle', 'S1E3: Sneaky, Bratty Lil Stepsis', 'Sneaky, Bratty Lil Stepsis'),
    ],
)
def test_reapply_text_rules_strips_the_episode_tag(scraper: str, tagged: str, clean: str) -> None:
    resp = _tagged_response(tagged)
    assert mc.reapply_text_rules(resp, scraper) is True
    assert resp.MediaContainer.Metadata[0].title == clean
    assert mc.reapply_text_rules(resp, scraper) is False


def test_reapply_text_rules_restores_a_title_apostrophe_once() -> None:
    resp = _tagged_response('Lets Play')
    assert mc.reapply_text_rules(resp) is True
    assert resp.MediaContainer.Metadata[0].title == "Let's Play"
    assert mc.reapply_text_rules(resp) is False


def test_reapply_text_rules_leaves_a_third_person_lets_alone() -> None:
    resp = _tagged_response('Rachel Lets Her Hair Down')
    assert mc.reapply_text_rules(resp) is False
    assert resp.MediaContainer.Metadata[0].title == 'Rachel Lets Her Hair Down'


def test_reapply_text_rules_leaves_other_scrapers_tags_alone() -> None:
    untouched = _tagged_response('Stepmom Wants to Move In - S2:E1')
    assert mc.reapply_text_rules(untouched) is False
    assert untouched.MediaContainer.Metadata[0].title == 'Stepmom Wants to Move In - S2:E1'


def test_backfill_metadata_attrs_adds_new_fields() -> None:
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'The Cool Scene', 'Role': [{'tag': 'A'}, {'tag': 'B'}]}],
            }
        }
    )
    assert mc.backfill_metadata_attrs(resp) is True
    md = resp.MediaContainer.Metadata[0]
    assert md.contentRating == 'XXX'
    assert md.isAdult is True
    assert md.titleSort == 'Cool Scene'
    assert [r.order for r in md.Role or []] == [0, 1]
    assert mc.backfill_metadata_attrs(resp) is False


def _resp(
    *,
    title: str = 'Cool Scene',
    studio: str = '',
    tagline: str = '',
    thumb: str | None = None,
    role_thumb: str | None = None,
    images: list[str] | None = None,
    data18: dict[str, str] | None = None,
    source_url: str = '',
) -> PlexMetadataResponse:
    md: dict[str, Any] = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title}
    if source_url:
        md['sourceRef'] = {'url': source_url, 'kind': 'page'}
    if studio:
        md['studio'] = studio
    if tagline:
        md['tagline'] = tagline
    if thumb:
        md['thumb'] = thumb
    if role_thumb:
        md['Role'] = [{'tag': 'Jane Doe', 'thumb': role_thumb}]
    if images:
        md['Image'] = [{'url': u, 'type': 'coverPoster'} for u in images]
    if data18:
        md['data18'] = data18
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'id', 'size': 1, 'Metadata': [md]}})


@respx.mock
async def test_write_then_read_localizes_images(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=b'POSTER', headers={'content-type': 'image/jpeg'}))

    resp = _resp(
        studio='Brazzers',
        tagline='Baby Got Boobs',
        thumb='https://host/images/proxy?url=https%3A%2F%2Fcdn.example%2Fp.jpg',
        role_thumb='https://host/images/local/actor.jane_female.jpg',
    )
    assert await mc.write('Brazzers', 'curid123', resp) is True

    cached = mc.read('Brazzers', 'curid123')
    assert cached is not None
    md = cached['MediaContainer']['Metadata'][0]
    assert f'/cache/{mc.bundle_path(mc._hash("Brazzers", "curid123"))}/' in md['thumb'] and '/images/cache/' not in md['thumb']
    assert md['thumb'].endswith('/images/poster-00.jpg')
    assert md['Role'][0]['thumb'].endswith('/images/local/actor.jane_female.jpg')
    downloaded = list(tmp_path.glob('scenes/*/*/images/poster-00.jpg'))  # type: ignore[attr-defined]
    assert downloaded and downloaded[0].read_bytes() == b'POSTER'


@respx.mock
async def test_image_bases_are_reconfigurable(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=b'POSTER', headers={'content-type': 'image/jpeg'}))

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-a:1'))
    monkeypatch.setattr(mc, 'image_base_url', lambda: 'http://10.0.0.5:3000')
    resp = _resp(
        studio='DickDrainers',
        thumb='https://host/images/proxy?url=https%3A%2F%2Fcdn.example%2Fp.jpg',
        role_thumb='https://tunnel-a:1/images/local/actor.jane_female.jpg',
    )
    assert await mc.write('DickDrainers', 's1', resp) is True

    stored = db.connect().execute('SELECT thumb FROM scenes').fetchone()
    assert stored['thumb'].startswith('/cache/')
    stored_role = db.connect().execute('SELECT photo_rel_path FROM scene_people').fetchone()
    assert stored_role['photo_rel_path'] == '/images/local/actor.jane_female.jpg'

    md = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md['thumb'].startswith('http://tunnel-a:1/cache/')
    assert md['Role'][0]['thumb'] == 'http://10.0.0.5:3000/images/local/actor.jane_female.jpg'

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-b:2'))
    monkeypatch.setattr(mc, 'image_base_url', lambda: 'http://localhost:3000')
    md2 = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md2['thumb'].startswith('http://tunnel-b:2/cache/')
    assert md2['Role'][0]['thumb'] == 'http://localhost:3000/images/local/actor.jane_female.jpg'


async def test_every_snapshot_lands_in_a_hash_bucket(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    written = [('Brazzers', 'b1', 'Brazzers', 'Baby Got Boobs'), ('Vixen', 'v1', 'Vixen', ''), ('5Kteens', 't1', '5Kporn', '5Kteens')]
    for site, cur, studio, tagline in written:
        assert await mc.write(site, cur, _resp(studio=studio, tagline=tagline or None)) is True

    for site, cur, _studio, _tagline in written:
        scene_hash = mc._hash(site, cur)
        assert (tmp_path / 'scenes' / scene_hash[:2] / scene_hash).is_dir()  # type: ignore[operator]
        assert mc.read(site, cur) is not None
    assert [p.name for p in sorted(tmp_path.iterdir()) if p.is_dir()] == ['scenes']  # type: ignore[attr-defined]


async def test_restudioing_a_scene_never_moves_its_folder(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    assert await mc.write('Brazzers', 'b1', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True
    scene_hash = mc._hash('Brazzers', 'b1')
    bundle = tmp_path / 'scenes' / scene_hash[:2] / scene_hash  # type: ignore[operator]
    assert bundle.is_dir()

    assert await mc.write('Brazzers', 'b1', _resp(studio='Renamed Studio', tagline='Renamed Sub')) is True

    assert bundle.is_dir()
    assert [p for p in tmp_path.glob('scenes/*/*')] == [bundle]  # type: ignore[attr-defined]
    assert mc.entries()[0]['key'] == mc.bundle_path(scene_hash)


async def test_each_snapshot_carries_a_self_contained_bundle(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Brazzers', 'b1', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True

    scene_hash = mc._hash('Brazzers', 'b1')
    payload = json.loads((tmp_path / mc.bundle_path(scene_hash) / mc.BUNDLE_FILE).read_text(encoding='utf-8'))  # type: ignore[operator]
    assert payload['version'] == mc.BUNDLE_VERSION
    assert (payload['site'], payload['cur_id'], payload['hash']) == ('Brazzers', 'b1', scene_hash)
    assert payload['response']['MediaContainer']['Metadata'][0]['studio'] == 'Brazzers'


async def test_error_title_not_frozen(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Site', 'c', _resp(title='404 Not Found')) is False
    assert mc.read('Site', 'c') is None


async def test_disabled_is_noop(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Site', 'c', _resp()) is False
    assert mc.read('Site', 'c') is None


async def test_entries_expose_data18_and_mapping_slug(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Brazzers', 'a1', _resp(studio='Brazzers', tagline='Baby Got Boobs', data18={'type': 'scene', 'id': '1209186'})) is True
    assert await mc.write('Vixen', 'b2', _resp(studio='Vixen')) is True

    by_studio = {e['studio']: e for e in mc.entries()}
    assert by_studio['Brazzers']['data18_id'] == '1209186'
    assert by_studio['Brazzers']['data18_type'] == 'scene'
    assert by_studio['Brazzers']['mapping_slug'] == 'cool-scene-babygotboobs'
    assert by_studio['Vixen']['data18_id'] == '' and by_studio['Vixen']['data18_type'] == ''
    assert by_studio['Vixen']['mapping_slug'] == 'cool-scene-vixen'


async def test_change_token_moves_on_write_and_purge(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    empty = mc.change_token()
    assert await mc.write('Brazzers', 'c1', _resp(studio='Brazzers')) is True
    written = mc.change_token()
    assert written != empty
    assert mc.change_token() == written
    assert mc.purge(mc.entries()[0]['key']) is True
    assert mc.change_token() != written


async def test_purge(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Brazzers', 'curid123', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True
    assert mc.read('Brazzers', 'curid123') is not None
    entry = mc.entries()[0]
    assert entry['title'] == 'Cool Scene'

    key = entry['key']
    assert mc.purge(key) is True
    assert mc.read('Brazzers', 'curid123') is None
    assert mc.purge(key) is False


async def test_backfill_actor_images_fills_missing_thumb(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    (Path(str(tmp_path)) / 'people').mkdir()
    (Path(str(tmp_path)) / 'people' / 'actor.kira-noir_female.jpg').write_bytes(b'x')

    photos = {
        'Mandingo': PhotoHit(url='https://cdn.example/mandingo.jpg', gender='male'),
        'Greg Lansky': PhotoHit(url='https://cdn.example/greg.jpg', gender='male'),
        'Jane Producer': PhotoHit(url='https://cdn.example/jane.jpg', gender='female'),
    }

    async def fake_find_photo(name: str, ctx: PersonLookupContext) -> PhotoHit:
        return photos.get(name, PhotoHit(url=''))

    monkeypatch.setattr('phoenixadult.utils.people.find_photo', fake_find_photo)

    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'id',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'Role': [
                            {'tag': 'Mandingo'},
                            {'tag': 'Kira Noir', 'thumb': '/images/local/actor.kira-noir_female.jpg'},
                        ],
                        'Director': [{'tag': 'Greg Lansky'}],
                        'Producer': [{'tag': 'Jane Producer'}],
                    },
                ],
            }
        }
    )
    changed = await mc.backfill_people_images(resp, 'TestSite')
    assert changed is True
    md = resp.MediaContainer.Metadata[0]
    assert md.Role is not None
    assert md.Role[0].tag == 'Mandingo' and md.Role[0].thumb and 'mandingo.jpg' in md.Role[0].thumb
    assert md.Role[1].thumb == '/images/local/actor.kira-noir_female.jpg'
    assert md.Director is not None and md.Director[0].thumb and 'greg.jpg' in md.Director[0].thumb
    assert md.Producer is not None and md.Producer[0].thumb and 'jane.jpg' in md.Producer[0].thumb


async def test_backfill_noop_when_all_thumbs_present(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    (Path(str(tmp_path)) / 'people').mkdir()
    (Path(str(tmp_path)) / 'people' / 'a.jpg').write_bytes(b'x')
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'id',
                'size': 1,
                'Metadata': [
                    {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'T', 'Role': [{'tag': 'A', 'thumb': '/images/local/a.jpg'}]},
                ],
            }
        }
    )
    assert await mc.backfill_people_images(resp, 'TestSite') is False


async def test_backfill_re_resolves_purged_local_thumb(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))

    async def fake_find_photo(name: str, ctx: PersonLookupContext) -> PhotoHit:
        return PhotoHit(url='https://cdn.example/greg-new.jpg', gender='male') if name == 'Greg Lansky' else PhotoHit(url='')

    monkeypatch.setattr('phoenixadult.utils.people.find_photo', fake_find_photo)

    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'id',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'Director': [{'tag': 'Greg Lansky', 'thumb': 'http://h/images/local/director.greg-lansky_male.jpg'}],
                    }
                ],
            }
        }
    )
    assert await mc.backfill_people_images(resp, 'TestSite') is True
    d = resp.MediaContainer.Metadata[0].Director
    assert d is not None and d[0].thumb and 'greg-new.jpg' in d[0].thumb


def _md_resp(title: str, tagline: str) -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'tagline': tagline}]}}
    )


def test_data18_remap_needed_flags_added_or_changed_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')

    assert mc.data18_remap_needed(resp, 'Brazzers') is True

    resp.MediaContainer.Metadata[0].data18 = PlexData18(type='scene', id='1301931')
    assert mc.data18_remap_needed(resp, 'Brazzers') is False

    unmapped = _md_resp('Some Unmapped Scene', 'Brazzers Exxtra')
    unmapped.MediaContainer.Metadata[0].data18 = PlexData18(type='scene', id='999')
    assert mc.data18_remap_needed(unmapped, 'Brazzers') is False


def test_data18_remap_needed_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')
    assert mc.data18_remap_needed(resp, 'Brazzers') is False


def test_data18_backfill_needed_flags_empty_ref_on_eligible_site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    resp = _md_resp('Some Scene', 'Brazzers Exxtra')

    assert mc.data18_backfill_needed(resp, 'Brazzers') is True

    resp.MediaContainer.Metadata[0].data18 = PlexData18(type='scene', id='999')
    assert mc.data18_backfill_needed(resp, 'Brazzers') is False

    untitled = _md_resp('', 'Brazzers Exxtra')
    assert mc.data18_backfill_needed(untitled, 'Brazzers') is False


def test_data18_backfill_needed_off_when_disabled_or_ineligible(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _md_resp('Some Scene', 'Brazzers Exxtra')
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    assert mc.data18_backfill_needed(resp, 'Brazzers') is False

    monkeypatch.setenv('DATA18_ENABLE', 'true')
    assert mc.data18_backfill_needed(resp, 'Nonexistent Site') is False


async def test_backfill_data18_records_manual_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')

    assert await mc.backfill_data18(resp, 'Brazzers') is True
    d = resp.MediaContainer.Metadata[0].data18
    assert d is not None and d.type == 'scene' and d.id == '1301931'

    assert await mc.backfill_data18(resp, 'Brazzers') is False


async def test_backfill_data18_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')
    assert await mc.backfill_data18(resp, 'Brazzers') is False
    assert resp.MediaContainer.Metadata[0].data18 is None


def _snapshot(root: Path, rel: str, site: str, cur: str) -> None:
    from phoenixadult.utils.cache import scene_store

    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    rating_key = to_rating_key(cur, site)
    meta = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': rating_key, 'guid': 'g', 'title': 'Scene'}]}}
    scene_store.upsert(site, cur, rel.rsplit('/', 1)[-1], rel, meta, {})


def test_duplicate_entries_reports_the_subless_twin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    old_cur = b64url_encode('3870731|scene|2015-09-24')
    new_cur = embed_subsite(old_cur, 'Teens Like It Big')
    old_rel = f'brazzers/brazzers/{mc._hash("Brazzers", old_cur)}'
    new_rel = f'brazzers/teens-like-it-big/{mc._hash("Brazzers", new_cur)}'
    _snapshot(tmp_path, old_rel, 'Brazzers', old_cur)
    _snapshot(tmp_path, new_rel, 'Brazzers', new_cur)

    assert mc.duplicate_entries() == [old_rel]
    assert mc.purge_duplicates() == 1
    assert not (tmp_path / old_rel).exists()
    assert (tmp_path / new_rel).exists()


def test_duplicate_entries_ignores_a_lone_subless_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    old_cur = b64url_encode('3870731|scene|2015-09-24')
    _snapshot(tmp_path, f'brazzers/brazzers/{mc._hash("Brazzers", old_cur)}', 'Brazzers', old_cur)
    assert mc.duplicate_entries() == []


def test_reapply_text_rules_normalizes_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: name)
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'S',
                        'summary': 'specs. . . his roommate’s girlfriend…\n\nSecond para.',
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    assert resp.MediaContainer.Metadata[0].summary == "specs... his roommate's girlfriend...\n\nSecond para."
    assert mc.reapply_text_rules(resp) is False


def test_reapply_text_rules_normalizes_cast_name_punctuation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: name)
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'S',
                        'Role': [{'tag': 'Nikki D’Angelo'}],
                        'Director': [{'tag': 'Jean-Luc  O’Brien'}],
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    assert [r.tag for r in (resp.MediaContainer.Metadata[0].Role or [])] == ["Nikki D'Angelo"]
    assert [d.tag for d in (resp.MediaContainer.Metadata[0].Director or [])] == ["Jean-Luc O'Brien"]
    assert mc.reapply_text_rules(resp) is False


def test_reapply_text_rules_leaves_clean_cast_names_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: name)
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'S',
                        'Role': [{'tag': 'Danny D'}, {'tag': 'Gina Gerson'}, {'tag': 'Xander Corvus'}],
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is False
    assert [r.tag for r in (resp.MediaContainer.Metadata[0].Role or [])] == ['Danny D', 'Gina Gerson', 'Xander Corvus']


def _resp_with_actor(studio: str, actor: str) -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Cool Scene', 'studio': studio, 'Role': [{'tag': actor}]}],
            }
        }
    )


async def test_scoped_person_wins_for_its_studio(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    assert await mc.write('Brazzers', 'sp1', _resp_with_actor('Brazzers', 'Amanda')) is True
    conn = db.connect()
    assert conn.execute('SELECT COUNT(*) AS c FROM people WHERE name = ?', ('Amanda',)).fetchone()['c'] == 1

    studio_id = conn.execute('SELECT id FROM studios WHERE name = ?', ('Brazzers',)).fetchone()['id']
    with conn:
        conn.execute('INSERT INTO people(name, scope_studio_id, gender) VALUES(?, ?, ?)', ('Amanda', studio_id, 'female'))

    assert await mc.write('Brazzers', 'sp2', _resp_with_actor('Brazzers', 'Amanda')) is True
    assert await mc.write('Vixen', 'sp3', _resp_with_actor('Vixen', 'Amanda')) is True

    scoped = mc.read('Brazzers', 'sp2')['MediaContainer']['Metadata'][0]['Role'][0]
    assert scoped['gender'] == 'female'
    unscoped = mc.read('Vixen', 'sp3')['MediaContainer']['Metadata'][0]['Role'][0]
    assert 'gender' not in unscoped
    assert conn.execute('SELECT COUNT(*) AS c FROM people WHERE name = ?', ('Amanda',)).fetchone()['c'] == 2


def _jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    PILImage.effect_noise((width, height), 90).convert('RGB').save(buf, format='JPEG', quality=95)
    return buf.getvalue()


def _solid_jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    PILImage.new('RGB', (width, height)).save(buf, format='JPEG')
    return buf.getvalue()


@respx.mock
async def test_read_orders_each_image_kind_high_to_low(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/small.jpg').mock(return_value=httpx.Response(200, content=_jpeg(10, 20), headers={'content-type': 'image/jpeg'}))
    respx.get('https://cdn.example/large.jpg').mock(return_value=httpx.Response(200, content=_jpeg(20, 40), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', images=['https://cdn.example/small.jpg', 'https://cdn.example/large.jpg'])
    assert await mc.write('Brazzers', 'ord1', resp) is True

    md = mc.read('Brazzers', 'ord1')['MediaContainer']['Metadata'][0]
    posters = [img['url'] for img in md['Image'] if img['type'] == 'coverPoster']
    assert posters[0].endswith('img-01.jpg') and posters[1].endswith('img-00.jpg')


@respx.mock
async def test_rewrite_keeps_snapshot_images_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=_jpeg(30, 45), headers={'content-type': 'image/jpeg'}))
    respx.get('https://cdn.example/bg.jpg').mock(return_value=httpx.Response(200, content=_jpeg(40, 20), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', thumb='https://cdn.example/p.jpg')
    resp.MediaContainer.Metadata[0].Image = [
        PlexImage(url='https://cdn.example/p.jpg', type='coverPoster'),
        PlexImage(url='https://cdn.example/bg.jpg', type='background'),
    ]
    assert await mc.write('Brazzers', 'rw1', resp) is True

    cached = mc.read('Brazzers', 'rw1')
    assert cached is not None
    before = {img['url'].rsplit('/', 1)[-1]: img['type'] for img in cached['MediaContainer']['Metadata'][0]['Image']}
    scene_dir = tmp_path / mc.bundle_path(mc._hash('Brazzers', 'rw1'))
    poster_bytes = (scene_dir / 'images' / 'img-01.jpg').read_bytes()

    again = PlexMetadataResponse.model_validate(cached)
    again.MediaContainer.Metadata[0].summary = 'backfilled summary'
    respx.reset()
    assert await mc.write('Brazzers', 'rw1', again) is True

    after_md = mc.read('Brazzers', 'rw1')['MediaContainer']['Metadata'][0]
    after = {img['url'].rsplit('/', 1)[-1]: img['type'] for img in after_md['Image']}
    assert after == before
    assert after_md['summary'] == 'backfilled summary'
    assert after_md['thumb'].endswith('/images/poster-00.jpg')
    assert (scene_dir / 'images' / 'img-01.jpg').read_bytes() == poster_bytes
    rows = db.connect().execute('SELECT kind, width, height FROM scene_images ORDER BY pos').fetchall()
    assert {(r['kind'], r['width'], r['height']) for r in rows} == {('coverPoster', 30, 45), ('background', 40, 20)}


def test_tags_for_matches_the_seeded_scene() -> None:
    from phoenixadult.utils.cache import scene_store

    md: dict[str, Any] = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': 'T',
        'studio': 'Brazzers',
        'Genre': [{'tag': 'Anal'}, {'tag': 'Blonde'}],
        'Collection': [{'tag': 'Baby Got Boobs'}, {'tag': 'Brazzers Exxtra'}],
        'Role': [{'tag': 'Jane Doe', 'gender': 'female'}, {'tag': 'John Doe'}],
        'Director': [{'tag': 'Greg Lansky'}],
        'Producer': [{'tag': 'Jane Producer'}],
        'Writer': [{'tag': 'Ghost Writer'}],
        'Country': [{'tag': 'United States'}],
    }
    data = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}}
    scene_store.upsert('Brazzers', 'tf1', mc._hash('Brazzers', 'tf1'), 'brazzers/x', data)

    assert scene_store.tags_for('Brazzers', 'tf1') == {
        'Collection': ['Baby Got Boobs', 'Brazzers Exxtra'],
        'Genre': ['Anal', 'Blonde'],
        'Role': ['Jane Doe', 'John Doe'],
        'Director': ['Greg Lansky'],
        'Producer': ['Jane Producer'],
    }
    assert scene_store.tags_for('Brazzers', 'missing') is None


def test_backfill_recomputes_guid_after_an_identifier_change() -> None:
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'scene-brazzers-abc123.20200101',
                        'guid': 'tv.plex.agents.custom.myprovider.phoenixadult://movie/scene-brazzers-abc123.20200101',
                        'title': 'T',
                        'studio': 'S',
                    }
                ],
            }
        }
    )
    assert mc.backfill_metadata_attrs(resp) is True
    assert resp.MediaContainer.Metadata[0].guid == 'tv.plex.agents.custom.phoenixadult://movie/scene-brazzers-abc123.20200101'
    assert mc.backfill_metadata_attrs(resp) is False


def test_recredited_actor_drops_its_now_wrong_headshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc.text_rules, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc.text_rules, 'apply_name_aliases', lambda name, studio, site: 'Vanessa Cruz' if name == 'Vanessa' else name)
    resp = PlexMetadataResponse.model_validate(
        {
            'MediaContainer': {
                'identifier': 'i',
                'size': 1,
                'Metadata': [
                    {
                        'type': 'movie',
                        'ratingKey': 'rk',
                        'guid': 'g',
                        'title': 'T',
                        'studio': 'Porn Pros',
                        'Role': [
                            {'tag': 'Vanessa', 'thumb': 'http://host/images/local/actor/vanessa.jpg'},
                            {'tag': 'Kept Name', 'thumb': 'http://host/images/local/actor/kept-name.jpg'},
                        ],
                    }
                ],
            }
        }
    )
    assert mc.reapply_text_rules(resp) is True
    roles = resp.MediaContainer.Metadata[0].Role or []
    assert [(r.tag, r.thumb) for r in roles] == [('Vanessa Cruz', None), ('Kept Name', 'http://host/images/local/actor/kept-name.jpg')]


@respx.mock
async def test_a_url_used_twice_is_fetched_and_stored_once(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    route = respx.get('https://cdn.example/shared.jpg').mock(return_value=httpx.Response(200, content=b'SHARED', headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', thumb='https://cdn.example/shared.jpg', images=['https://cdn.example/shared.jpg'])
    assert await mc.write('Brazzers', 'shared1', resp) is True

    assert route.call_count == 1
    stored = list(tmp_path.glob('**/images/*.jpg'))  # type: ignore[attr-defined]
    assert len(stored) == 1

    cached = mc.read('Brazzers', 'shared1')
    assert cached is not None
    md = cached['MediaContainer']['Metadata'][0]
    assert md['thumb'] == md['Image'][0]['url']


@respx.mock
async def test_rewrite_reuses_a_kept_image_referenced_twice(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/keep.jpg').mock(return_value=httpx.Response(200, content=b'KEEP', headers={'content-type': 'image/jpeg'}))

    first = _resp(studio='Brazzers', thumb='https://cdn.example/keep.jpg', images=['https://cdn.example/keep.jpg'])
    assert await mc.write('Brazzers', 'keep1', first) is True
    cached = mc.read('Brazzers', 'keep1')
    assert cached is not None
    local = cached['MediaContainer']['Metadata'][0]['thumb']

    again = _resp(studio='Brazzers', thumb=local, images=[local])
    assert await mc.write('Brazzers', 'keep1', again) is True

    stored = list(tmp_path.glob('**/images/*.jpg'))  # type: ignore[attr-defined]
    assert len(stored) == 1 and stored[0].read_bytes() == b'KEEP'


@respx.mock
async def test_a_solid_colour_image_is_never_stored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/black.jpg').mock(return_value=httpx.Response(200, content=_solid_jpeg(600, 900), headers={'content-type': 'image/jpeg'}))
    respx.get('https://cdn.example/real.jpg').mock(return_value=httpx.Response(200, content=_jpeg(600, 900), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', thumb='https://cdn.example/black.jpg', images=['https://cdn.example/black.jpg', 'https://cdn.example/real.jpg'])
    assert await mc.write('Brazzers', 'solid1', resp) is True

    md = mc.read('Brazzers', 'solid1')['MediaContainer']['Metadata'][0]
    assert [img['url'].rsplit('/', 1)[-1] for img in md['Image']] == ['img-01.jpg']
    assert md['thumb'].endswith('/images/img-01.jpg')
    stored = sorted(p.name for p in (tmp_path / mc.bundle_path(mc._hash('Brazzers', 'solid1')) / 'images').iterdir())
    assert stored == ['img-01.jpg']


@respx.mock
async def test_a_scene_whose_every_image_is_solid_still_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/blank.jpg').mock(return_value=httpx.Response(200, content=_solid_jpeg(600, 900), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', thumb='https://cdn.example/blank.jpg', images=['https://cdn.example/blank.jpg'])
    assert await mc.write('Brazzers', 'solid2', resp) is True

    md = mc.read('Brazzers', 'solid2')['MediaContainer']['Metadata'][0]
    assert md['title'] == 'Cool Scene'
    assert md.get('Image') == []
    assert 'thumb' not in md


async def test_a_solid_image_already_in_a_snapshot_is_dropped_on_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    scene_dir = tmp_path / mc.bundle_path(mc._hash('Brazzers', 'solid3')) / 'images'
    scene_dir.mkdir(parents=True)
    (scene_dir / 'poster-00.jpg').write_bytes(_solid_jpeg(600, 900))
    (scene_dir / 'img-01.jpg').write_bytes(_jpeg(600, 900))
    kept = f'/cache/{mc.bundle_path(mc._hash("Brazzers", "solid3"))}/images/img-01.jpg'
    blank = f'/cache/{mc.bundle_path(mc._hash("Brazzers", "solid3"))}/images/poster-00.jpg'

    resp = _resp(studio='Brazzers', thumb=blank, images=[blank, kept])
    assert await mc.write('Brazzers', 'solid3', resp) is True

    md = mc.read('Brazzers', 'solid3')['MediaContainer']['Metadata'][0]
    assert [img['url'].rsplit('/', 1)[-1] for img in md['Image']] == ['img-01.jpg']
    assert md['thumb'].endswith('/images/img-01.jpg')
    assert sorted(p.name for p in scene_dir.iterdir()) == ['img-01.jpg']


@respx.mock
async def test_the_largest_survivor_of_each_kind_replaces_a_dropped_thumb_and_art(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    for name, content in (
        ('blank', _solid_jpeg(970, 545)),
        ('small', _jpeg(475, 268)),
        ('big', _jpeg(960, 540)),
    ):
        respx.get(f'https://cdn.example/{name}.jpg').mock(return_value=httpx.Response(200, content=content, headers={'content-type': 'image/jpeg'}))

    md: dict[str, Any] = {
        'type': 'movie',
        'ratingKey': 'rk',
        'guid': 'g',
        'title': 'Cool Scene',
        'studio': 'Brazzers',
        'thumb': 'https://cdn.example/blank.jpg',
        'art': 'https://cdn.example/blank.jpg',
        'Image': [
            {'url': 'https://cdn.example/blank.jpg', 'type': 'coverPoster'},
            {'url': 'https://cdn.example/small.jpg', 'type': 'coverPoster'},
            {'url': 'https://cdn.example/big.jpg', 'type': 'coverPoster'},
            {'url': 'https://cdn.example/blank.jpg', 'type': 'background'},
            {'url': 'https://cdn.example/small.jpg', 'type': 'background'},
        ],
    }
    resp = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}})
    assert await mc.write('Brazzers', 'promote1', resp) is True

    stored = mc.read('Brazzers', 'promote1')['MediaContainer']['Metadata'][0]
    by_url = {img['url'].rsplit('/', 1)[-1] for img in stored['Image']}
    assert 'img-00.jpg' not in by_url
    assert stored['thumb'].endswith('/images/img-02.jpg')
    assert stored['art'].endswith('/images/img-01.jpg')


@respx.mock
async def test_a_scene_that_never_had_a_thumb_does_not_gain_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/only.jpg').mock(return_value=httpx.Response(200, content=_jpeg(600, 900), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', images=['https://cdn.example/only.jpg'])
    assert await mc.write('Brazzers', 'nothumb1', resp) is True

    stored = mc.read('Brazzers', 'nothumb1')['MediaContainer']['Metadata'][0]
    assert len(stored['Image']) == 1
    assert 'thumb' not in stored


async def test_data18_also_survives_the_store_roundtrip(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    d18 = {'type': 'movie', 'id': '1341861', 'also': ['1341863', '1377300']}
    assert await mc.write('MYLF', 'm1', _resp(studio='MYLF', tagline='MYLF Features', data18=d18)) is True

    loaded = mc.read('MYLF', 'm1')
    assert loaded is not None
    stored = loaded['MediaContainer']['Metadata'][0]['data18']
    assert stored['id'] == '1341861'
    assert stored['also'] == ['1341863', '1377300']

    entry = next(e for e in mc.entries() if e['studio'] == 'MYLF')
    assert entry['data18_also'] == '1341863,1377300'


def test_data18_remap_needed_sees_added_extra_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    resp = _md_resp('Everyone Cums Everywhere All at Once', 'MYLF Features')

    resp.MediaContainer.Metadata[0].data18 = PlexData18(type='scene', id='1341861')
    assert mc.data18_remap_needed(resp, 'MYLF') is True

    resp.MediaContainer.Metadata[0].data18 = PlexData18(type='scene', id='1341861', also=['1341863', '1377300'])
    assert mc.data18_remap_needed(resp, 'MYLF') is False


def test_data18_edit_accepts_multiple_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    md = _resp(studio='MYLF').MediaContainer.Metadata[0]
    mc._apply_data18_edit(md, {'data18_id': '1341861 1341863, 1377300', 'data18_type': 'movie'})
    assert md.data18 is not None
    assert (md.data18.id, md.data18.also, md.data18.manual) == ('1341861', ['1341863', '1377300'], True)

    mc._apply_data18_edit(md, {'data18_id': '1341861', 'data18_type': 'movie'})
    assert md.data18 is not None and md.data18.also is None

    mc._apply_data18_edit(md, {'data18_id': ''})
    assert md.data18 is None


@respx.mock
async def test_image_priority_survives_the_store_and_outranks_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/cover.jpg').mock(return_value=httpx.Response(200, content=_jpeg(30, 45), headers={'content-type': 'image/jpeg'}))
    respx.get('https://cdn.example/still.jpg').mock(return_value=httpx.Response(200, content=_jpeg(60, 90), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='MYLF')
    resp.MediaContainer.Metadata[0].Image = [
        PlexImage(url='https://cdn.example/cover.jpg', type='coverPoster', priority=True),
        PlexImage(url='https://cdn.example/still.jpg', type='coverPoster'),
    ]
    assert await mc.write('MYLF', 'p1', resp) is True

    loaded = mc.read('MYLF', 'p1')
    assert loaded is not None
    stored = loaded['MediaContainer']['Metadata'][0]['Image']
    assert [i.get('priority') for i in stored] == [True, None]
    assert stored[0]['url'].endswith('img-00.jpg')

    again = PlexMetadataResponse.model_validate(loaded)
    respx.reset()
    assert await mc.write('MYLF', 'p1', again) is True
    rewritten = mc.read('MYLF', 'p1')['MediaContainer']['Metadata'][0]['Image']
    assert [i.get('priority') for i in rewritten] == [True, None]


async def test_content_duplicates_match_on_normalized_quad(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    a = _resp(title="Mother's Day!", studio='Team Skeet', tagline='Mom Swap')
    a.MediaContainer.Metadata[0].originallyAvailableAt = '2024-05-12'
    b = _resp(title='mothers day', studio='TeamSkeet', tagline='MomSwap')
    b.MediaContainer.Metadata[0].originallyAvailableAt = '2024-05-12'
    c = _resp(title='mothers day', studio='TeamSkeet', tagline='Sis Swap')
    c.MediaContainer.Metadata[0].originallyAvailableAt = '2024-05-12'
    d = _resp(title='mothers day', studio='TeamSkeet', tagline='MomSwap')
    d.MediaContainer.Metadata[0].originallyAvailableAt = '2024-06-01'

    for cur, resp in (('d1', a), ('d2', b), ('d3', c), ('d4', d)):
        assert await mc.write('TeamSkeet', cur, resp) is True

    dupes = mc.content_duplicate_entries()
    by_cur = {e['key']: e for e in mc.entries()}
    flagged = {k for k in by_cur if by_cur[k]['key'] in dupes}
    assert len(dupes) == 2
    titles = {by_cur[k]['tagline'] for k in flagged}
    assert titles == {'Mom Swap', 'MomSwap'}


async def test_two_scenes_sharing_a_title_are_not_duplicates_when_the_site_ids_differ(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    for cur, url in (
        ('s1', 'https://www.scoreland.com/big-boob-videos/Danielle-Derek/45336/'),
        ('s2', 'https://www.scoreland.com/big-boob-videos/Shyla-Stylez/45339/'),
    ):
        resp = _resp(title='Funbag Fuckers', studio='Score Group', tagline='Scoreland', source_url=url)
        resp.MediaContainer.Metadata[0].originallyAvailableAt = '2015-02-25'
        assert await mc.write('Scoreland', cur, resp) is True

    assert mc.content_duplicate_entries() == []
    assert mc.stale_duplicate_entries() == []


async def test_one_scene_published_under_two_slugs_is_still_a_duplicate(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    for cur, url in (
        ('p1', 'https://www.pornmegaload.com/hd-porn-scenes/lila-lovely/71161/'),
        ('p2', 'https://www.pornmegaload.com/hd-porn-scenes/lila-lovely-drop-your-loads/71161/'),
    ):
        resp = _resp(title='Drop Your Loads', studio='Score Group', tagline='Porn Mega Load', source_url=url)
        resp.MediaContainer.Metadata[0].originallyAvailableAt = '2022-07-29'
        assert await mc.write('Porn Mega Load', cur, resp) is True

    assert len(mc.content_duplicate_entries()) == 2
    assert len(mc.stale_duplicate_entries()) == 1


async def test_stale_duplicates_keep_the_newest_copy(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    older = _resp(title='Same Scene', studio='Bad Oink VR', tagline='')
    newer = _resp(title='same scene!', studio='BadOinkVR', tagline='')
    assert await mc.write('BadOinkVR Old', 's1', older) is True
    assert await mc.write('BadOinkVR', 's2', newer) is True

    conn = db.connect()
    with conn:
        conn.execute('UPDATE scenes SET updated_at = ? WHERE site = ?', (100.0, 'BadOinkVR Old'))
        conn.execute('UPDATE scenes SET updated_at = ? WHERE site = ?', (200.0, 'BadOinkVR'))

    by_site = {e['provider']: e['key'] for e in mc.entries()}
    assert mc.content_duplicate_entries() == sorted(by_site.values())
    assert mc.stale_duplicate_entries() == [by_site['BadOinkVR Old']]

    assert mc.purge_duplicates() == 1
    assert {e['provider'] for e in mc.entries()} == {'BaDoink VR'}


@respx.mock
async def test_saving_a_rotation_rewrites_the_cached_image(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=_jpeg(30, 45), headers={'content-type': 'image/jpeg'}))

    resp = _resp(studio='Brazzers', title='Sideways Scene')
    resp.MediaContainer.Metadata[0].Image = [PlexImage(url='https://cdn.example/p.jpg', type='coverPoster')]
    assert await mc.write('Brazzers', 'rot1', resp) is True

    key = mc.entries()[0]['key']
    loaded = mc.read('Brazzers', 'rot1')
    entry = loaded['MediaContainer']['Metadata'][0]['Image'][0]
    rows = db.connect().execute('SELECT width, height FROM scene_images').fetchall()
    assert (rows[0]['width'], rows[0]['height']) == (30, 45)

    respx.reset()
    fields = {'title': 'Sideways Scene', 'Image': [{'url': entry['url'], 'type': entry['type'], 'rotate': 90}]}
    assert await mc.save_edits(key, fields) == key

    rows = db.connect().execute('SELECT width, height FROM scene_images').fetchall()
    assert (rows[0]['width'], rows[0]['height']) == (45, 30)
    after = mc.read('Brazzers', 'rot1')['MediaContainer']['Metadata'][0]['Image'][0]
    assert 'rotate' not in after


def test_an_edit_save_keeps_the_image_priority_flag() -> None:
    md = _resp(studio='MYLF').MediaContainer.Metadata[0]
    mc._apply_edits(md, {'title': 'Cool Scene', 'Image': [{'url': '/cache/x/images/a.jpg', 'type': 'coverPoster', 'priority': True}]})
    assert md.Image is not None
    assert md.Image[0].priority is True
    mc._apply_edits(md, {'title': 'Cool Scene', 'Image': [{'url': '/cache/x/images/a.jpg', 'type': 'coverPoster'}]})
    assert md.Image[0].priority is None


def _summary_resp(title: str, summary: str) -> PlexMetadataResponse:
    md = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'studio': 'Score Group', 'summary': summary}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}})


@pytest.mark.parametrize(
    ('title', 'summary', 'expected'),
    [
        ('Funbag Fuckers', 'Funbag Fuckers In the SCORE movie, Shyla is needy.', 'In the SCORE movie, Shyla is needy.'),
        ('A Diamond in the Buff', 'A Diamond In The Buff Roxanne makes a good case.', 'Roxanne makes a good case.'),
        ('Funbag Fuckers - Shyla Stylez', 'Funbag Fuckers In the SCORE movie, Shyla is needy.', 'In the SCORE movie, Shyla is needy.'),
        ('Teens in Need', 'Cutie pie Kelsey loves sucking on things.', 'Cutie pie Kelsey loves sucking on things.'),
        ('Funbag Fuckers', 'Funbag Fuckers', 'Funbag Fuckers'),
    ],
)
def test_a_cached_score_group_summary_sheds_the_title_glued_to_its_front(title: str, summary: str, expected: str) -> None:
    resp = _summary_resp(title, summary)
    mc.reapply_text_rules(resp, 'scoregroup')
    assert resp.MediaContainer.Metadata[0].summary == expected


def test_only_score_group_summaries_shed_their_leading_title() -> None:
    resp = _summary_resp('Funbag Fuckers', 'Funbag Fuckers In the SCORE movie, Shyla is needy.')
    mc.reapply_text_rules(resp, 'brazzers')
    assert resp.MediaContainer.Metadata[0].summary == 'Funbag Fuckers In the SCORE movie, Shyla is needy.'


def test_a_locked_summary_keeps_its_leading_title() -> None:
    resp = _summary_resp('Funbag Fuckers', 'Funbag Fuckers In the SCORE movie, Shyla is needy.')
    mc.reapply_text_rules(resp, 'scoregroup', locked={'summary'})
    assert resp.MediaContainer.Metadata[0].summary == 'Funbag Fuckers In the SCORE movie, Shyla is needy.'


async def test_a_thumb_whose_file_vanished_is_dropped_rather_than_left_pointing_at_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    rel = mc.bundle_path(mc._hash('Brazzers', 'gone1'))
    scene_dir = tmp_path / rel / 'images'
    scene_dir.mkdir(parents=True)
    (scene_dir / 'img-01.jpg').write_bytes(_jpeg(600, 900))
    survivor = f'/cache/{rel}/images/img-01.jpg'
    vanished = f'/cache/{rel}/images/poster-00.jpg'

    assert await mc.write('Brazzers', 'gone1', _resp(studio='Brazzers', thumb=vanished, images=[vanished, survivor])) is True

    md = mc.read('Brazzers', 'gone1')['MediaContainer']['Metadata'][0]
    assert [img['url'].rsplit('/', 1)[-1] for img in md['Image']] == ['img-01.jpg']
    assert md['thumb'].endswith('/images/img-01.jpg'), 'the surviving image should be promoted into the empty thumb'


async def test_a_scene_whose_only_image_vanished_reports_no_thumb_at_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    rel = mc.bundle_path(mc._hash('Brazzers', 'gone2'))
    (tmp_path / rel / 'images').mkdir(parents=True)
    vanished = f'/cache/{rel}/images/poster-00.jpg'

    assert await mc.write('Brazzers', 'gone2', _resp(studio='Brazzers', thumb=vanished, images=[vanished])) is True

    md = mc.read('Brazzers', 'gone2')['MediaContainer']['Metadata'][0]
    assert not md.get('thumb'), 'an empty thumb is what makes the cache list render "No image" instead of a broken one'
    assert not md.get('Image')


async def test_the_scan_finds_snapshots_whose_thumb_file_is_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    intact_rel = mc.bundle_path(mc._hash('Brazzers', 'intact'))
    (tmp_path / intact_rel / 'images').mkdir(parents=True)
    (tmp_path / intact_rel / 'images' / 'img-01.jpg').write_bytes(_jpeg(600, 900))
    assert await mc.write('Brazzers', 'intact', _resp(studio='Brazzers', thumb=f'/cache/{intact_rel}/images/img-01.jpg')) is True

    broken_rel = mc.bundle_path(mc._hash('Brazzers', 'broken'))
    (tmp_path / broken_rel / 'images').mkdir(parents=True)
    (tmp_path / broken_rel / 'images' / 'img-01.jpg').write_bytes(_jpeg(600, 900))
    assert await mc.write('Brazzers', 'broken', _resp(studio='Brazzers', thumb=f'/cache/{broken_rel}/images/img-01.jpg')) is True

    assert mc.missing_image_entries() == []

    (tmp_path / broken_rel / 'images' / 'img-01.jpg').unlink()
    conn = db.connect()
    with conn:
        conn.execute('UPDATE scenes SET updated_at = updated_at + 1 WHERE rel_path = ?', (broken_rel,))

    assert mc.missing_image_entries() == [broken_rel]


def test_only_a_snapshot_path_resolves_to_a_file_on_disk() -> None:
    from phoenixadult.utils.cache.integrity import snapshot_image_path

    assert snapshot_image_path('https://cdn.example/p.jpg') is None
    assert snapshot_image_path('/images/local/actors/female/actor.jane_female.jpg') is None
    assert snapshot_image_path('') is None
    assert snapshot_image_path('/cache/scenes/../../etc/passwd/images/x.jpg') is None
    assert snapshot_image_path('/cache/scenes/d2/d2f973d18fb4/images/poster-00.jpg') is not None
    assert snapshot_image_path('/cache/scenes/d2/d2f973d18fb4/images/poster-00.jpg?v=123') is not None


def test_an_image_the_scrape_never_localized_counts_as_broken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.utils.cache.integrity import unrenderable

    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    proxied = '/images/proxy?url=https%3A%2F%2Fcdn77.example%2Fscoreland%2Fgallys%2Fi.jpg'
    assert unrenderable(proxied), 'a proxy url means the download failed at scrape time — a re-scrape is the fix'
    assert unrenderable('https://cdn.example/p.jpg')
    assert not unrenderable(''), 'an empty thumb renders the "No image" placeholder, which is not broken'
    assert not unrenderable(None)
    assert not unrenderable('/images/local/actors/female/actor.jane_female.jpg')
