from __future__ import annotations

import httpx
import pytest
import respx

from app.utils.images import face_crop, face_crop_log
from app.utils.people import cache
from app.utils.people.generic import generic_image_url


@respx.mock
async def test_crop_applied_logged_and_original_preserved(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_FACE_ENABLE', 'true')
    monkeypatch.setenv('PEOPLE_CACHE_REPLACE_ENABLE', 'true')
    monkeypatch.setattr(face_crop, 'crop_to_headshot', lambda _data: b'CROPPEDJPEGBYTES')

    url = 'https://cdn.example/jane.webp'
    respx.get(url).mock(return_value=httpx.Response(200, content=b'origwebp', headers={'content-type': 'image/webp'}))
    res = await cache.cache_photo(url, 'Jane Doe', 'actor', 'female')

    assert res is not None
    sub = tmp_path / 'actors' / 'female'  # type: ignore[operator]
    f = sub / 'actor.jane-doe_female.jpg'  # cropped -> JPEG ext, in the gender subfolder
    assert f.exists() and f.read_bytes() == b'CROPPEDJPEGBYTES'
    # pre-crop original preserved under originals/ (kept so the user can go back)
    assert (tmp_path / 'originals' / 'actor.jane-doe_female.webp').read_bytes() == b'origwebp'  # type: ignore[operator]
    log = face_crop_log.recent(str(sub))
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
    assert (tmp_path / 'actors' / 'female' / 'actor.jane-doe_female.jpg').read_bytes() == b'ORIGINALBYTES'  # type: ignore[operator]
    assert not (tmp_path / 'originals').exists()  # no separate original when not cropped  # type: ignore[operator]


@respx.mock
async def test_restore_uses_preserved_original(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # No respx route registered -> if restore hit the network it would error; it must use
    # the local original instead.
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    sub = tmp_path / 'actors' / 'female'  # type: ignore[operator]
    sub.mkdir(parents=True)
    (sub / 'actor.jane-doe_female.jpg').write_bytes(b'CROPPED')
    (tmp_path / 'originals').mkdir()  # type: ignore[operator]
    (tmp_path / 'originals' / 'actor.jane-doe_female.webp').write_bytes(b'ORIGINALWEBP')  # type: ignore[operator]
    face_crop_log.record(
        str(sub),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.webp',
        upstream_url='https://cdn.example/jane.webp',
        cropped=True,
    )

    ok = await cache.restore_original('actor.jane-doe_female.jpg')
    assert ok is True
    assert (sub / 'actor.jane-doe_female.webp').read_bytes() == b'ORIGINALWEBP'  # restored from local original
    assert not (sub / 'actor.jane-doe_female.jpg').exists()  # old cropped file removed
    log = face_crop_log.recent(str(sub))
    assert log[0]['filename'] == 'actor.jane-doe_female.webp' and log[0]['cropped'] is False


def test_set_gender_moves_folders_and_relogs(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    monkeypatch.setenv('PEOPLE_CACHE_ENABLE', 'true')
    fsub = tmp_path / 'actors' / 'female'  # type: ignore[operator]
    fsub.mkdir(parents=True)
    (fsub / 'actor.jane-doe_female.jpg').write_bytes(b'IMG')
    face_crop_log.record(
        str(fsub),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.jpg',
        upstream_url='https://x/j.jpg',
        cropped=True,
    )

    # female -> male: file + log move from actors/female to actors/male.
    new = cache.set_gender('actor.jane-doe_female.jpg', 'male')
    assert new == 'actor.jane-doe_male.jpg'
    msub = tmp_path / 'actors' / 'male'  # type: ignore[operator]
    assert (msub / 'actor.jane-doe_male.jpg').read_bytes() == b'IMG'
    assert not (fsub / 'actor.jane-doe_female.jpg').exists()
    assert face_crop_log.recent(str(msub))[0]['filename'] == 'actor.jane-doe_male.jpg'
    assert face_crop_log.recent(str(fsub)) == []  # moved out of the female log
    assert cache.lookup_cached('Jane Doe', 'actor')['gender'] == 'male'  # type: ignore[index]

    # male -> none: drops the suffix and moves to actors/unknown.
    new2 = cache.set_gender('actor.jane-doe_male.jpg', '')
    assert new2 == 'actor.jane-doe.jpg'
    assert (tmp_path / 'actors' / 'unknown' / 'actor.jane-doe.jpg').exists()  # type: ignore[operator]
    assert cache.lookup_cached('Jane Doe', 'actor')['gender'] == ''  # type: ignore[index]


def test_purge_deletes_file_original_and_log(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    fsub = tmp_path / 'actors' / 'female'  # type: ignore[operator]
    fsub.mkdir(parents=True)
    (fsub / 'actor.jane-doe_female.jpg').write_bytes(b'IMG')
    (tmp_path / 'originals').mkdir()  # type: ignore[operator]
    (tmp_path / 'originals' / 'actor.jane-doe_female.jpg').write_bytes(b'ORIG')  # type: ignore[operator]
    face_crop_log.record(
        str(fsub),
        name='Jane Doe',
        filename='actor.jane-doe_female.jpg',
        base='actor.jane-doe_female',
        orig_ext='.jpg',
        upstream_url='https://x/j.jpg',
        cropped=True,
    )

    assert cache.purge('actor.jane-doe_female.jpg') is True
    assert not (fsub / 'actor.jane-doe_female.jpg').exists()
    assert not (tmp_path / 'originals' / 'actor.jane-doe_female.jpg').exists()  # preserved original purged too  # type: ignore[operator]
    assert face_crop_log.recent(str(fsub)) == []
    assert cache.purge('actor.jane-doe_female.jpg') is False  # already gone


def test_set_gender_rejects_bad_value(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PEOPLE_CACHE_DIR', str(tmp_path))
    assert cache.set_gender('actor.jane-doe_female.jpg', 'other') is None  # invalid
    assert cache.set_gender('nonexistent.jpg', 'male') is None  # file not present
