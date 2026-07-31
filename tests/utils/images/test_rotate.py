from __future__ import annotations

import io

from PIL import Image

from phoenixadult.utils.images.image_fetcher import rotate_image_bytes


def _two_tone(width: int = 2, height: int = 1) -> bytes:
    img = Image.new('RGB', (width, height))
    img.putpixel((0, 0), (255, 0, 0))
    if width > 1:
        img.putpixel((1, 0), (0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def test_clockwise_rotation_moves_the_left_pixel_to_the_top() -> None:
    rotated = rotate_image_bytes(_two_tone(), 90)
    with Image.open(io.BytesIO(rotated)) as img:
        assert img.size == (1, 2)
        assert img.getpixel((0, 0)) == (255, 0, 0)
        assert img.getpixel((0, 1)) == (0, 0, 255)


def test_counter_clockwise_rotation_moves_the_left_pixel_to_the_bottom() -> None:
    rotated = rotate_image_bytes(_two_tone(), 270)
    with Image.open(io.BytesIO(rotated)) as img:
        assert img.size == (1, 2)
        assert img.getpixel((0, 0)) == (0, 0, 255)
        assert img.getpixel((0, 1)) == (255, 0, 0)


def test_half_turn_and_noop_degrees() -> None:
    data = _two_tone()
    with Image.open(io.BytesIO(rotate_image_bytes(data, 180))) as img:
        assert img.size == (2, 1)
        assert img.getpixel((0, 0)) == (0, 0, 255)
    assert rotate_image_bytes(data, 0) == data
    assert rotate_image_bytes(data, 360) == data


def test_jpeg_survives_rotation_as_jpeg() -> None:
    img = Image.new('RGB', (4, 2), (200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    rotated = rotate_image_bytes(buf.getvalue(), 90)
    with Image.open(io.BytesIO(rotated)) as out:
        assert out.format == 'JPEG'
        assert out.size == (2, 4)
