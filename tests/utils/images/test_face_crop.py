from __future__ import annotations

import io

import pytest
from PIL import Image

from app.utils.images import face_crop_log
from app.utils.images.face_crop import crop_to_headshot


def _solid_jpeg(color: tuple[int, int, int] = (128, 128, 128), size: int = 400) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (size, size), color).save(buf, 'JPEG')
    return buf.getvalue()


def test_crop_bad_bytes_keeps_original() -> None:
    assert crop_to_headshot(b'not an image at all') is None


def test_crop_no_face_keeps_original() -> None:
    assert crop_to_headshot(_solid_jpeg()) is None


def test_headshot_crop_is_head_and_shoulders() -> None:
    np = pytest.importorskip('numpy')
    from app.utils.images.face_crop import _headshot_crop

    x, y, w, h = 300, 100, 111, 156
    img = np.zeros((900, 700, 3), dtype=np.uint8)
    img[y : y + h, x : x + w] = 255
    crop = _headshot_crop(np, img, (x, y, w, h))
    assert crop is not None
    ch, cw = crop.shape[:2]
    assert ch == cw
    assert ch == pytest.approx(3 * h, abs=2)

    rows = np.where(crop.any(axis=(1, 2)))[0]
    face_top, face_bottom = int(rows.min()), int(rows.max())
    assert face_top < ch * 0.25
    assert face_bottom < ch * 0.6
    assert ch - face_bottom > ch * 0.3


def test_headshot_crop_keeps_original_when_already_closeup() -> None:
    np = pytest.importorskip('numpy')
    from app.utils.images.face_crop import _headshot_crop

    img = np.zeros((150, 150, 3), dtype=np.uint8)
    assert _headshot_crop(np, img, (15, 15, 120, 120)) is None


def test_log_roundtrip(tmp_path: pytest.TempPathFactory) -> None:
    d = str(tmp_path)
    face_crop_log.record(
        d, name='Jane Doe', filename='actor.jane-doe_female.jpg', base='actor.jane-doe_female', orig_ext='.webp', upstream_url='https://x/j.webp', cropped=True
    )
    entries = face_crop_log.recent(d)
    assert len(entries) == 1
    assert entries[0]['name'] == 'Jane Doe' and entries[0]['cropped'] is True and entries[0]['orig_ext'] == '.webp'

    face_crop_log.update(d, 'actor.jane-doe_female.jpg', filename='actor.jane-doe_female.webp', cropped=False)
    updated = face_crop_log.recent(d)
    assert updated[0]['filename'] == 'actor.jane-doe_female.webp' and updated[0]['cropped'] is False


def test_log_keeps_all_and_orders(tmp_path: pytest.TempPathFactory) -> None:
    d = str(tmp_path)
    for i in range(30):
        face_crop_log.record(d, name=f'A{i}', filename=f'f{i}.jpg', base=f'f{i}', orig_ext='.jpg', upstream_url=f'u{i}', cropped=False)
    entries = face_crop_log.recent(d)
    assert len(entries) == 30
    assert entries[0]['filename'] == 'f29.jpg'
