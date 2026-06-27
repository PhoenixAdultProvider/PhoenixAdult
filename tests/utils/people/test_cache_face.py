from __future__ import annotations

import httpx
import pytest
import respx

from app.utils.images import face_crop, face_crop_log
from app.utils.people import cache
from app.utils.people.generic import generic_image_url


@respx.mock
async def test_crop_applied_and_logged(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_FACE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_REPLACE_ENABLE', 'true')
    monkeypatch.setattr(face_crop, 'crop_to_headshot', lambda _data: b'CROPPEDJPEGBYTES')

    url = 'https://cdn.example/jane.webp'
    respx.get(url).mock(return_value=httpx.Response(200, content=b'origwebp', headers={'content-type': 'image/webp'}))
    res = await cache.cache_photo(url, 'Jane Doe', 'actor', 'female')

    assert res is not None
    f = tmp_path / 'actor.jane-doe_female.jpg'  # cropped -> JPEG ext
    assert f.exists() and f.read_bytes() == b'CROPPEDJPEGBYTES'
    log = face_crop_log.recent(str(tmp_path))
    assert log and log[0]['cropped'] is True and log[0]['orig_ext'] == '.webp'


@respx.mock
async def test_generic_not_cropped(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_FACE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_REPLACE_ENABLE', 'true')
    called = {'v': False}

    def _spy(_data: bytes) -> bytes:
        called['v'] = True
        return b'CROP'

    monkeypatch.setattr(face_crop, 'crop_to_headshot', _spy)
    url = generic_image_url('female')
    respx.get(url).mock(return_value=httpx.Response(200, content=b'ORIGINALBYTES', headers={'content-type': 'image/jpeg'}))
    await cache.cache_photo(url, 'Jane Doe', 'actor', 'female')

    assert called['v'] is False  # generic placeholder never cropped
    assert (tmp_path / 'actor.jane-doe_female.jpg').read_bytes() == b'ORIGINALBYTES'


@respx.mock
async def test_restore_original(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = str(tmp_path)
    (tmp_path / 'actor.jane-doe_female.jpg').write_bytes(b'CROPPED')
    face_crop_log.record(
        d,
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.webp',
        upstream_url='https://cdn.example/jane.webp',
        cropped=True,
    )
    respx.get('https://cdn.example/jane.webp').mock(return_value=httpx.Response(200, content=b'ORIGINALWEBP'))

    ok = await cache.restore_original('actor.jane-doe_female.jpg')
    assert ok is True
    assert (tmp_path / 'actor.jane-doe_female.webp').read_bytes() == b'ORIGINALWEBP'
    assert not (tmp_path / 'actor.jane-doe_female.jpg').exists()  # old cropped file removed
    log = face_crop_log.recent(d)
    assert log[0]['filename'] == 'actor.jane-doe_female.webp' and log[0]['cropped'] is False


def test_set_gender_renames_and_relogs(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    d = str(tmp_path)
    (tmp_path / 'actor.jane-doe_female.jpg').write_bytes(b'IMG')
    face_crop_log.record(
        d, name='Jane Doe', filename='actor.jane-doe_female.jpg', base='actor.jane-doe_female', orig_ext='.jpg', upstream_url='https://x/j.jpg', cropped=True
    )

    # female -> male: rename + log update; lookup reports the new gender.
    new = cache.set_gender('actor.jane-doe_female.jpg', 'male')
    assert new == 'actor.jane-doe_male.jpg'
    assert (tmp_path / 'actor.jane-doe_male.jpg').read_bytes() == b'IMG'
    assert not (tmp_path / 'actor.jane-doe_female.jpg').exists()
    assert face_crop_log.recent(d)[0]['filename'] == 'actor.jane-doe_male.jpg'
    assert cache.lookup_cached('Jane Doe', 'actor') == {'served_url': cache.lookup_cached('Jane Doe', 'actor')['served_url'], 'gender': 'male'}  # type: ignore[index]

    # male -> none: drops the suffix entirely.
    new2 = cache.set_gender('actor.jane-doe_male.jpg', '')
    assert new2 == 'actor.jane-doe.jpg'
    assert (tmp_path / 'actor.jane-doe.jpg').exists()
    assert cache.lookup_cached('Jane Doe', 'actor')['gender'] == ''  # type: ignore[index]


def test_purge_deletes_file_and_log(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    d = str(tmp_path)
    (tmp_path / 'actor.jane-doe_female.jpg').write_bytes(b'IMG')
    face_crop_log.record(
        d, name='Jane Doe', filename='actor.jane-doe_female.jpg', base='actor.jane-doe_female', orig_ext='.jpg', upstream_url='https://x/j.jpg', cropped=True
    )

    assert cache.purge('actor.jane-doe_female.jpg') is True
    assert not (tmp_path / 'actor.jane-doe_female.jpg').exists()
    assert face_crop_log.recent(d) == []
    assert cache.purge('actor.jane-doe_female.jpg') is False  # already gone
    assert cache.purge('../escape.jpg') is False  # path-traversal guard


def test_set_gender_rejects_bad_value(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    assert cache.set_gender('actor.jane-doe_female.jpg', 'other') is None  # invalid
    assert cache.set_gender('nonexistent.jpg', 'male') is None  # not in log
