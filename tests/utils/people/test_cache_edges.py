from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from phoenixadult.utils.images import face_crop_log
from phoenixadult.utils.people import cache


@pytest.fixture
def people_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_FACE_ENABLE', 'false')
    monkeypatch.setattr(cache, 'impersonate_get_bytes', _no_bytes, raising=False)
    d = tmp_path / 'people'
    d.mkdir()
    return d


async def _no_bytes(*_args: object, **_kw: object) -> None:
    return None


@pytest.mark.parametrize(
    'response',
    [
        httpx.Response(404),
        httpx.Response(200, content=b'x' * 64, headers={'content-type': 'text/html'}),
    ],
    ids=['download-fails', 'not-an-image'],
)
@respx.mock
async def test_an_unusable_download_caches_nothing(people_dir: Path, response: httpx.Response) -> None:
    respx.get('https://cdn.example/jane').mock(return_value=response)
    assert await cache.cache_photo('https://cdn.example/jane', 'Jane Doe', 'actor', 'female') is None
    assert not any(people_dir.rglob('*.jpg'))


@respx.mock
async def test_an_oversized_download_caches_nothing(people_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, 'max_image_bytes', lambda: 10)
    respx.get('https://cdn.example/jane.jpg').mock(return_value=httpx.Response(200, content=b'x' * 64, headers={'content-type': 'image/jpeg'}))
    assert await cache.cache_photo('https://cdn.example/jane.jpg', 'Jane Doe', 'actor', 'female') is None


async def test_restore_needs_a_crop_log_entry(people_dir: Path) -> None:
    assert await cache.restore_original('actor.jane-doe_female.jpg') is False


def _logged_crop(people_dir: Path, upstream_url: str) -> Path:
    sub = people_dir / 'actors' / 'female'
    sub.mkdir(parents=True)
    (sub / 'actor.jane-doe_female.jpg').write_bytes(b'CROPPED')
    face_crop_log.record(
        str(sub), name='Jane Doe', filename='actor.jane-doe_female.jpg', base='actor.jane-doe_female', orig_ext='.png', upstream_url=upstream_url, cropped=True
    )
    return sub


@respx.mock
async def test_restore_downloads_the_original_when_no_local_copy_survives(people_dir: Path) -> None:
    sub = _logged_crop(people_dir, 'https://cdn.example/jane.png')
    respx.get('https://cdn.example/jane.png').mock(return_value=httpx.Response(200, content=b'UPSTREAM', headers={'content-type': 'image/png'}))
    assert await cache.restore_original('actor.jane-doe_female.jpg') is True
    assert (sub / 'actor.jane-doe_female.png').read_bytes() == b'UPSTREAM'
    assert not (sub / 'actor.jane-doe_female.jpg').exists()
    entry = face_crop_log.entry_for(str(sub), 'actor.jane-doe_female.png')
    assert entry is not None and entry['cropped'] is False


async def test_restore_fails_without_a_local_or_upstream_original(people_dir: Path) -> None:
    _logged_crop(people_dir, '')
    assert await cache.restore_original('actor.jane-doe_female.jpg') is False


@pytest.mark.parametrize(('filename', 'gender'), [('actor.jane-doe_female.jpg', 'robot'), ('actor.ghost_female.jpg', 'male'), ('.jpg', 'male')])
def test_set_gender_refuses_bad_input(people_dir: Path, filename: str, gender: str) -> None:
    assert cache.set_gender(filename, gender) is None


def test_set_gender_carries_the_saved_original_along(people_dir: Path) -> None:
    _logged_crop(people_dir, 'https://cdn.example/jane.png')
    originals = people_dir / 'originals'
    originals.mkdir()
    (originals / 'actor.jane-doe_female.png').write_bytes(b'ORIG')
    (originals / 'actor.jane-doe_male.png').write_bytes(b'STALE')
    assert cache.set_gender('actor.jane-doe_female.jpg', 'male') == 'actor.jane-doe_male.jpg'
    assert (originals / 'actor.jane-doe_male.png').read_bytes() == b'ORIG'
    assert not (originals / 'actor.jane-doe_female.png').exists()
    entry = face_crop_log.entry_for(str(people_dir / 'actors' / 'male'), 'actor.jane-doe_male.jpg')
    assert entry is not None and entry['base'] == 'actor.jane-doe_male' and entry['cropped'] is True
