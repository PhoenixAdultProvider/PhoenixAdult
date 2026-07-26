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
from phoenixadult.utils.helpers.helpers import b64url_encode, embed_subsite
from phoenixadult.utils.images import image_fetcher
from phoenixadult.utils.plex.rating_key import to_rating_key


def test_reapply_text_rules_renormalizes_genres_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: [t.upper() for t in tags if t != 'Drop Me'])
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: 'Canonical' if name in ('Alias A', 'Alias B') else name)

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
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: name)
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
    monkeypatch.setattr(mc, 'normalize_studio', lambda name, site_name='': name.title().replace('Of', 'of'))
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


def test_reapply_text_rules_strips_nubiles_episode_tag() -> None:
    def _resp_with_tag() -> PlexMetadataResponse:
        return PlexMetadataResponse.model_validate(
            {
                'MediaContainer': {
                    'identifier': 'i',
                    'size': 1,
                    'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Stepmom Wants to Move In - S2:E1'}],
                }
            }
        )

    resp = _resp_with_tag()
    assert mc.reapply_text_rules(resp, 'nubiles') is True
    md = resp.MediaContainer.Metadata[0]
    assert md.title == 'Stepmom Wants to Move In'
    assert mc.reapply_text_rules(resp, 'nubiles') is False

    untouched = _resp_with_tag()
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
) -> PlexMetadataResponse:
    md: dict[str, Any] = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title}
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
    assert '/cache/project1service/brazzers/baby-got-boobs/' in md['thumb'] and '/images/cache/' not in md['thumb']
    assert md['thumb'].endswith('/images/poster-00.jpg')
    assert md['Role'][0]['thumb'].endswith('/images/local/actor.jane_female.jpg')
    downloaded = list(tmp_path.glob('project1service/brazzers/baby-got-boobs/*/images/poster-00.jpg'))  # type: ignore[attr-defined]
    assert downloaded and downloaded[0].read_bytes() == b'POSTER'


@respx.mock
async def test_image_bases_are_reconfigurable(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Image URLs are stored host-relative and rebased on every read — metadata images (/cache/)
    onto base_url, people images (/images/local/) onto IMAGE_BASE_URL's base — so both survive a tunnel change."""
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


async def test_layout_per_registry_type(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    assert await mc.write('Brazzers', 'b1', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True
    assert list(tmp_path.glob('project1service/brazzers/baby-got-boobs/*'))  # type: ignore[attr-defined]

    assert await mc.write('Vixen', 'v1', _resp(studio='Vixen')) is True
    assert list(tmp_path.glob('strike3/vixen/*'))  # type: ignore[attr-defined]

    assert await mc.write('5Kporn', 'p1', _resp(studio='5Kporn')) is True
    assert list(tmp_path.glob('5kporn/5kporn/*'))  # type: ignore[attr-defined]

    assert await mc.write('5Kteens', 't1', _resp(studio='5Kporn', tagline='5Kteens')) is True
    assert list(tmp_path.glob('5kporn/5kteens/*'))  # type: ignore[attr-defined]

    assert await mc.write('DickDrainers', 'd1', _resp(studio='DickDrainers')) is True
    assert (tmp_path / 'dickdrainers').is_dir()  # type: ignore[operator]
    assert not (tmp_path / 'dickdrainers' / 'dickdrainers').exists()  # type: ignore[operator]

    for name, cur in (('Brazzers', 'b1'), ('Vixen', 'v1'), ('5Kporn', 'p1'), ('5Kteens', 't1'), ('DickDrainers', 'd1')):
        assert mc.read(name, cur) is not None


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
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    (Path(str(tmp_path)) / 'actor.kira-noir_female.jpg').write_bytes(b'x')

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
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    (Path(str(tmp_path)) / 'a.jpg').write_bytes(b'x')
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
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))

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
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: name)
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
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: name)
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
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: name)
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
    """A backfill rewrite must never re-download or renumber already-snapshotted images —
    renumbering is what scrambled kinds against files across rewrite generations."""
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
    scene_dir = next(tmp_path.glob('project1service/brazzers/brazzers/*'))
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
    monkeypatch.setattr(mc, 'normalize_genres', lambda tags, opts=None: list(tags))
    monkeypatch.setattr(mc, 'apply_name_aliases', lambda name, studio, site: 'Vanessa Cruz' if name == 'Vanessa' else name)
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
