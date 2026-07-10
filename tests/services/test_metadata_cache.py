from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from app.models.metadata import PlexMetadataResponse
from app.utils import cache as mc
from app.utils.helpers.helpers import b64url_encode, embed_subsite
from app.utils.plex.rating_key import to_rating_key


def test_reapply_text_rules_renormalizes_genres_and_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stand in for the current genres.json/actors.json: drop "Drop Me", upper-case the rest;
    # collapse "Alias A"/"Alias B" onto one canonical name.
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
    assert [g.tag for g in (md.Genre or [])] == ['KEEP']  # Drop Me removed, Keep upper-cased
    assert [r.tag for r in (md.Role or [])] == ['Canonical', 'Solo']  # A+B merged to one, deduped


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
    assert [c.tag for c in md.Collection or []] == ['Word of The Day']  # recased + deduped


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
    assert mc.backfill_metadata_attrs(resp) is False  # idempotent


def _resp(
    *,
    title: str = 'Cool Scene',
    studio: str = '',
    tagline: str = '',
    thumb: str | None = None,
    role_thumb: str | None = None,
    images: list[str] | None = None,
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
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'id', 'size': 1, 'Metadata': [md]}})


@respx.mock
async def test_write_then_read_localizes_images(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=b'POSTER'))

    resp = _resp(
        studio='Brazzers',
        tagline='Baby Got Boobs',
        thumb='https://host/images/proxy?url=https%3A%2F%2Fcdn.example%2Fp.jpg',
        role_thumb='https://host/images/local/actor.jane_female.jpg',  # cached actor -> keep
    )
    assert await mc.write('Brazzers', 'curid123', resp) is True

    cached = mc.read('Brazzers', 'curid123')
    assert cached is not None
    md = cached['MediaContainer']['Metadata'][0]
    # project1service is an 'aggregator' layout: <scraper>/<studio>/<sub-site>, served at /cache.
    assert '/cache/project1service/brazzers/baby-got-boobs/' in md['thumb'] and '/images/cache/' not in md['thumb']
    assert md['thumb'].endswith('/images/poster-00.jpg')  # images live in an images/ subdir
    assert md['Role'][0]['thumb'].endswith('/images/local/actor.jane_female.jpg')  # untouched
    downloaded = list(tmp_path.glob('project1service/brazzers/baby-got-boobs/*/images/poster-00.jpg'))  # type: ignore[attr-defined]
    assert downloaded and downloaded[0].read_bytes() == b'POSTER'


@respx.mock
async def test_image_bases_are_reconfigurable(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Image URLs are stored host-relative and rebased on every read: metadata images
    (/cache/) onto base_url, people images (/images/local/) onto PEOPLE_IMAGE_URL's base —
    so both survive a tunnel change and people images stay reconfigurable (and self-heal
    if a snapshot stored them absolute)."""
    import json
    from pathlib import Path
    from types import SimpleNamespace

    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    respx.get('https://cdn.example/p.jpg').mock(return_value=httpx.Response(200, content=b'POSTER'))

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-a:1'))
    monkeypatch.setattr(mc, 'people_image_base', lambda: 'http://10.0.0.5:3000')
    resp = _resp(
        studio='DickDrainers',
        thumb='https://host/images/proxy?url=https%3A%2F%2Fcdn.example%2Fp.jpg',
        role_thumb='https://tunnel-a:1/images/local/actor.jane_female.jpg',  # absolute, like an old snapshot
    )
    assert await mc.write('DickDrainers', 's1', resp) is True

    # On disk: metadata image -> /cache/ path; people image -> host-relative.
    raw = json.loads(next(Path(str(tmp_path)).rglob('meta.json')).read_text(encoding='utf-8'))
    rmd = raw['MediaContainer']['Metadata'][0]
    assert rmd['thumb'].startswith('/cache/')
    assert rmd['Role'][0]['thumb'] == '/images/local/actor.jane_female.jpg'

    # Read: metadata follows base_url, people follows the People base.
    md = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md['thumb'].startswith('http://tunnel-a:1/cache/')
    assert md['Role'][0]['thumb'] == 'http://10.0.0.5:3000/images/local/actor.jane_female.jpg'

    # Change both bases -> both re-point on the next read.
    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://tunnel-b:2'))
    monkeypatch.setattr(mc, 'people_image_base', lambda: 'http://localhost:3000')
    md2 = mc.read('DickDrainers', 's1')['MediaContainer']['Metadata'][0]
    assert md2['thumb'].startswith('http://tunnel-b:2/cache/')
    assert md2['Role'][0]['thumb'] == 'http://localhost:3000/images/local/actor.jane_female.jpg'


async def test_layout_per_registry_type(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    # 'aggregator' (project1service): <scraper>/<studio>/<sub-site>.
    assert await mc.write('Brazzers', 'b1', _resp(studio='Brazzers', tagline='Baby Got Boobs')) is True
    assert list(tmp_path.glob('project1service/brazzers/baby-got-boobs/*/meta.json'))  # type: ignore[attr-defined]

    # 'network' (Strike3): <scraper>/<studio>, no sub-site.
    assert await mc.write('Vixen', 'v1', _resp(studio='Vixen')) is True
    assert list(tmp_path.glob('strike3/vixen/*/meta.json'))  # type: ignore[attr-defined]

    # 'auto' multi-site scraper, sub-site == studio (5Kporn flagship) -> 5kporn/5kporn.
    assert await mc.write('5Kporn', 'p1', _resp(studio='5Kporn')) is True
    assert list(tmp_path.glob('5kporn/5kporn/*/meta.json'))  # type: ignore[attr-defined]

    # 'auto' multi-site scraper, distinct sub-site -> 5kporn/5kteens.
    assert await mc.write('5Kteens', 't1', _resp(studio='5Kporn', tagline='5Kteens')) is True
    assert list(tmp_path.glob('5kporn/5kteens/*/meta.json'))  # type: ignore[attr-defined]

    # 'auto' lone-site scraper -> flat, never dickdrainers/dickdrainers.
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
    assert mc.purge(key) is False  # already gone


async def test_backfill_actor_images_fills_missing_thumb(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')  # use the raw URL, skip local download
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')  # no IAFD lookup
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')  # keep male actors (don't skip Mandingo)
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    (Path(str(tmp_path)) / 'actor.kira-noir_female.jpg').write_bytes(b'x')  # present file -> thumb kept

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
                            {'tag': 'Mandingo'},  # missing thumb -> should backfill
                            {'tag': 'Kira Noir', 'thumb': '/images/local/actor.kira-noir_female.jpg'},  # has thumb -> untouched
                        ],
                        'Director': [{'tag': 'Greg Lansky'}],  # missing thumb -> should backfill
                        'Producer': [{'tag': 'Jane Producer'}],  # missing thumb -> should backfill
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
    (Path(str(tmp_path)) / 'a.jpg').write_bytes(b'x')  # the referenced cache file exists -> not stale
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
    # A present /images/local/ thumb whose file was purged is treated as missing and re-resolved.
    from app.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))  # empty -> the referenced file is absent

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
    assert d is not None and d[0].thumb and 'greg-new.jpg' in d[0].thumb  # re-downloaded, not the dead link


def _md_resp(title: str, tagline: str) -> PlexMetadataResponse:
    return PlexMetadataResponse.model_validate(
        {'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [{'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': title, 'tagline': tagline}]}}
    )


def test_data18_remap_needed_flags_added_or_changed_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'true')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')  # mapping_slug -> a mapped value

    monkeypatch.setattr(mc, '_read_enrich', lambda site_name, cur_id: '')  # nothing recorded yet
    assert mc.data18_remap_needed(resp, 'Brazzers', 'cur') is True

    monkeypatch.setattr(mc, '_read_enrich', lambda site_name, cur_id: 'https://www.data18.com/scenes/1301931')
    assert mc.data18_remap_needed(resp, 'Brazzers', 'cur') is False  # fingerprint already current

    unmapped = _md_resp('Some Unmapped Scene', 'Brazzers Exxtra')
    monkeypatch.setattr(mc, '_read_enrich', lambda site_name, cur_id: '')
    assert mc.data18_remap_needed(unmapped, 'Brazzers', 'cur') is False  # no mapping -> nothing to do


def test_data18_remap_needed_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DATA18_ENABLE', 'false')
    resp = _md_resp('Live and on Location', 'Brazzers Exxtra')
    monkeypatch.setattr(mc, '_read_enrich', lambda site_name, cur_id: '')
    assert mc.data18_remap_needed(resp, 'Brazzers', 'cur') is False


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

    assert mc.duplicate_entries() == [old_rel]  # only the superseded sub-site-less side
    assert mc.purge_duplicates() == 1
    assert not (tmp_path / old_rel).exists()
    assert (tmp_path / new_rel).exists()  # the sub-site entry is kept


def test_duplicate_entries_ignores_a_lone_subless_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))
    old_cur = b64url_encode('3870731|scene|2015-09-24')
    _snapshot(tmp_path, f'brazzers/brazzers/{mc._hash("Brazzers", old_cur)}', to_rating_key(old_cur, 'Brazzers'))
    assert mc.duplicate_entries() == []  # no twin -> not provably a duplicate


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
    assert mc.reapply_text_rules(resp) is False  # idempotent: second pass changes nothing


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
    assert mc.reapply_text_rules(resp) is False  # idempotent


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
