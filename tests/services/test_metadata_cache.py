from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.models.metadata import PlexMetadataResponse
from app.utils import cache as mc


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


async def test_snapshot_survives_base_url_change(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Image URLs are stored host-relative and rebased onto the live base_url, so a
    snapshot keeps working after a base_url/tunnel change on restart."""
    from types import SimpleNamespace

    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path))

    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://host-a:1'))
    resp = _resp(studio='DickDrainers', thumb='http://host-a:1/images/local/jane.jpg')
    assert await mc.write('DickDrainers', 's1', resp) is True

    # Restart under a brand-new tunnel host.
    monkeypatch.setattr(mc, 'config', SimpleNamespace(base_url='http://host-b:2'))
    cached = mc.read('DickDrainers', 's1')
    assert cached is not None
    assert cached['MediaContainer']['Metadata'][0]['thumb'] == 'http://host-b:2/images/local/jane.jpg'


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


async def test_backfill_actor_images_fills_missing_thumb(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.utils.people.types import PersonLookupContext, PhotoHit

    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'false')  # use the raw URL, skip local download
    monkeypatch.setenv('GENDER_DETECT_ENABLE', 'false')  # no IAFD lookup
    monkeypatch.setenv('GENDER_SKIP_MALE_ENABLE', 'false')  # keep male actors (don't skip Mandingo)

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


async def test_backfill_noop_when_all_thumbs_present(monkeypatch: pytest.MonkeyPatch) -> None:
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
