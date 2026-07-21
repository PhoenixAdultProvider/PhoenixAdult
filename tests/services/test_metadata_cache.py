from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.models.metadata import PlexData18, PlexMetadataResponse
from app.utils import cache as mc
from app.utils.helpers.helpers import b64url_encode, embed_subsite
from app.utils.images import image_fetcher
from app.utils.plex.rating_key import to_rating_key


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


def test_backfill_logo_fills_only_missing(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from app.utils.images import logo_cache

    root = Path(str(tmp_path))
    (root / 'brazzers').mkdir(parents=True)
    (root / 'brazzers' / 'logo.brazzers.png').write_bytes(b'png')
    monkeypatch.setenv('LOGO_CACHE_ENABLE', 'true')
    monkeypatch.setenv('LOGO_CACHE_DIR', str(root))
    logo_cache.invalidate()

    resp = _resp(studio='Brazzers')
    assert mc.backfill_logo(resp) is True
    md = resp.MediaContainer.Metadata[0]
    logos = [i for i in md.Image or [] if i.type == 'clearLogo']
    assert len(logos) == 1 and logos[0].url.endswith('/images/local/logos/brazzers/logo.brazzers.png')
    assert mc.backfill_logo(resp) is False

    monkeypatch.setenv('LOGO_CACHE_ENABLE', 'false')
    logo_cache.invalidate()
    assert mc.backfill_logo(_resp(studio='Brazzers')) is False


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
    onto base_url, people images (/images/local/) onto PEOPLE_IMAGE_URL's base — so both survive a tunnel change."""
    import json
    from pathlib import Path
    from types import SimpleNamespace

    image_fetcher._cache.clear()
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=b'POSTER', headers={'content-type': 'image/jpeg'}))

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-a:1'))
    monkeypatch.setattr(mc, 'people_image_base', lambda: 'http://10.0.0.5:3000')
    resp = _resp(
        studio='DickDrainers',
        thumb='https://host/images/proxy?url=https%3A%2F%2Fcdn.example%2Fp.jpg',
        role_thumb='https://tunnel-a:1/images/local/actor.jane_female.jpg',
    )
    assert await mc.write('DickDrainers', 's1', resp) is True

    raw = json.loads(next(Path(str(tmp_path)).rglob('meta.json')).read_text(encoding='utf-8'))
    rmd = raw['MediaContainer']['Metadata'][0]
    assert rmd['thumb'].startswith('/cache/')
    assert rmd['Role'][0]['thumb'] == '/images/local/actor.jane_female.jpg'

    md = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md['thumb'].startswith('http://tunnel-a:1/cache/')
    assert md['Role'][0]['thumb'] == 'http://10.0.0.5:3000/images/local/actor.jane_female.jpg'

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-b:2'))
    monkeypatch.setattr(mc, 'people_image_base', lambda: 'http://localhost:3000')
    md2 = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md2['thumb'].startswith('http://tunnel-b:2/cache/')
    assert md2['Role'][0]['thumb'] == 'http://localhost:3000/images/local/actor.jane_female.jpg'


async def test_layout_per_registry_type(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    assert await mc.write('Brazzers', 'b1', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True
    assert list(tmp_path.glob('project1service/brazzers/baby-got-boobs/*/meta.json'))  # type: ignore[attr-defined]

    assert await mc.write('Vixen', 'v1', _resp(studio='Vixen')) is True
    assert list(tmp_path.glob('strike3/vixen/*/meta.json'))  # type: ignore[attr-defined]

    assert await mc.write('5Kporn', 'p1', _resp(studio='5Kporn')) is True
    assert list(tmp_path.glob('5kporn/5kporn/*/meta.json'))  # type: ignore[attr-defined]

    assert await mc.write('5Kteens', 't1', _resp(studio='5Kporn', tagline='5Kteens')) is True
    assert list(tmp_path.glob('5kporn/5kteens/*/meta.json'))  # type: ignore[attr-defined]

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
    from app.utils.people.types import PersonLookupContext, PhotoHit

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

    monkeypatch.setattr('app.utils.people.find_photo', fake_find_photo)

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
    from app.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))

    async def fake_find_photo(name: str, ctx: PersonLookupContext) -> PhotoHit:
        return PhotoHit(url='https://cdn.example/greg-new.jpg', gender='male') if name == 'Greg Lansky' else PhotoHit(url='')

    monkeypatch.setattr('app.utils.people.find_photo', fake_find_photo)

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


def _snapshot(root: Path, rel: str, rating_key: str) -> None:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    meta = {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': rating_key, 'guid': 'g', 'title': 'Scene'}]}}
    (d / 'meta.json').write_text(json.dumps(meta), encoding='utf-8')


def test_duplicate_entries_reports_the_subless_twin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    old_cur = b64url_encode('3870731|scene|2015-09-24')
    new_cur = embed_subsite(old_cur, 'Teens Like It Big')
    old_rel = f'brazzers/brazzers/{mc._hash("Brazzers", old_cur)}'
    new_rel = f'brazzers/teens-like-it-big/{mc._hash("Brazzers", new_cur)}'
    _snapshot(tmp_path, old_rel, to_rating_key(old_cur, 'Brazzers'))
    _snapshot(tmp_path, new_rel, to_rating_key(new_cur, 'Brazzers'))

    assert mc.duplicate_entries() == [old_rel]
    assert mc.purge_duplicates() == 1
    assert not (tmp_path / old_rel).exists()
    assert (tmp_path / new_rel).exists()


def test_duplicate_entries_ignores_a_lone_subless_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    old_cur = b64url_encode('3870731|scene|2015-09-24')
    _snapshot(tmp_path, f'brazzers/brazzers/{mc._hash("Brazzers", old_cur)}', to_rating_key(old_cur, 'Brazzers'))
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
