from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from phoenixadult.models.metadata import PlexMetadataResponse
from phoenixadult.utils import cache as mc
from phoenixadult.utils.images import image_fetcher as fetcher
from phoenixadult.utils.images.image_fetcher import ImageEntry

SITE = 'Brazzers'
CUR = 'guard1'
IMG = 'https://cdn.example.com/a.jpg'


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    monkeypatch.setenv('METADATA_CACHE_DIR', str(tmp_path / 'snapshots'))
    fetcher._cache.clear()
    fetcher._cache_total_bytes = 0
    buf = io.BytesIO()
    Image.effect_noise((800, 1200), 90).convert('RGB').save(buf, format='JPEG', quality=95)
    fetcher._cache_put(IMG, ImageEntry(data=buf.getvalue(), content_type='image/jpeg', cached_at=9e9, width=800, height=1200))


def _response(**fields: Any) -> PlexMetadataResponse:
    md: dict[str, Any] = {'type': 'movie', 'ratingKey': 'rk', 'guid': 'g', 'title': 'Scene One', 'studio': SITE, **fields}
    return PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': 'i', 'size': 1, 'Metadata': [md]}})


def _rich() -> PlexMetadataResponse:
    return _response(
        Genre=[{'tag': 'Anal'}, {'tag': 'MILF'}],
        Collection=[{'tag': 'Real Wife Stories'}],
        Role=[{'tag': 'Jane Doe'}],
        Image=[{'url': IMG, 'type': 'coverPoster'}],
    )


def _stored() -> dict[str, Any]:
    from phoenixadult.utils.cache import scene_store

    loaded = scene_store.load(mc._hash(SITE, CUR))
    assert loaded is not None
    md: dict[str, Any] = loaded['MediaContainer']['Metadata'][0]
    return md


async def test_a_scrape_that_lost_everything_keeps_the_stored_values(caplog: pytest.LogCaptureFixture) -> None:
    assert await mc.write(SITE, CUR, _rich())
    with caplog.at_level('WARNING'):
        assert await mc.write(SITE, CUR, _response(summary='fresh summary'))
    assert 'kept the stored values' in caplog.text
    assert 'Genre(2)' in caplog.text

    md = _stored()
    assert [g['tag'] for g in md['Genre']] == ['Anal', 'MILF']
    assert [c['tag'] for c in md['Collection']] == ['Real Wife Stories']
    assert [r['tag'] for r in md['Role']] == ['Jane Doe']
    assert len(md['Image']) == 1
    assert md['summary'] == 'fresh summary'


async def test_the_kept_image_is_still_on_disk() -> None:
    assert await mc.write(SITE, CUR, _rich())
    before = sorted(p.name for p in Path(mc.cache_dir()).rglob('*.jpg'))
    assert before

    assert await mc.write(SITE, CUR, _response(summary='no images this time'))
    after = sorted(p.name for p in Path(mc.cache_dir()).rglob('*.jpg'))
    assert after == before


async def test_a_field_may_still_change_without_being_emptied() -> None:
    assert await mc.write(SITE, CUR, _rich())
    assert await mc.write(SITE, CUR, _response(Genre=[{'tag': 'Anal'}], Collection=[{'tag': 'Moms in Control'}]))

    md = _stored()
    assert [g['tag'] for g in md['Genre']] == ['Anal']
    assert [c['tag'] for c in md['Collection']] == ['Moms in Control']


async def test_the_first_write_is_never_guarded() -> None:
    assert await mc.write(SITE, CUR, _response(summary='brand new'))
    assert not _stored().get('Genre')


async def test_an_edit_may_deliberately_clear_a_field() -> None:
    assert await mc.write(SITE, CUR, _rich())
    assert await mc.write(SITE, CUR, _response(summary='cleared by hand'), allow_clear=True)
    assert not _stored().get('Genre')
