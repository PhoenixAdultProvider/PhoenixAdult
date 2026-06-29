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
    # Undecodable input -> None ("keep original"); never raises.
    assert crop_to_headshot(b'not an image at all') is None


def test_crop_no_face_keeps_original() -> None:
    # A flat image has no face -> None, with or without opencv installed.
    assert crop_to_headshot(_solid_jpeg()) is None


def test_headshot_crop_recenters_face_near_top_edge() -> None:
    # Full-body shot: face near the top edge. The square is shrunk so the face sits at
    # ~_FACE_VPOS instead of being pinned to the top of an over-tall square.
    np = pytest.importorskip('numpy')
    from app.utils.images.face_crop import _headshot_crop

    img = np.zeros((600, 433, 3), dtype=np.uint8)
    crop = _headshot_crop(np, img, (214, 12, 111, 156))  # box = (x, y, w, h), small y
    assert crop is not None
    ch, cw = crop.shape[:2]
    assert ch == cw  # square
    assert 195 <= ch <= 235  # ~cy/0.42 ≈ 214, not the full 433 it would pin at the top


def test_headshot_crop_keeps_full_square_with_headroom() -> None:
    # Face with ample headroom -> no shrink; square ≈ 2.8·h capped to the image width.
    np = pytest.importorskip('numpy')
    from app.utils.images.face_crop import _headshot_crop

    img = np.zeros((600, 433, 3), dtype=np.uint8)
    crop = _headshot_crop(np, img, (160, 220, 111, 156))
    assert crop is not None
    assert crop.shape[0] >= 420  # ~433, unshrunk


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


def test_log_trims_and_orders(tmp_path: pytest.TempPathFactory) -> None:
    d = str(tmp_path)
    for i in range(30):
        face_crop_log.record(d, name=f'A{i}', filename=f'f{i}.jpg', base=f'f{i}', orig_ext='.jpg', upstream_url=f'u{i}', cropped=False)
    entries = face_crop_log.recent(d)
    assert len(entries) == 20  # ring buffer caps at 20
    assert entries[0]['filename'] == 'f29.jpg'  # newest first
