from __future__ import annotations

import io
import time

import pytest
from PIL import Image

from phoenixadult.mappers.metadata_mapper import _dedupe_artwork
from phoenixadult.utils.images import image_fetcher as fetcher
from phoenixadult.utils.images.image_fetcher import ImageEntry


@pytest.fixture(autouse=True)
def _clean() -> None:
    fetcher._cache.clear()
    fetcher._byte_digests.clear()
    fetcher._pixel_digests.clear()


def _jpeg(width: int, height: int, *, quality: int = 95, shade: int = 200) -> bytes:
    buf = io.BytesIO()
    img = Image.new('RGB', (width, height), (shade, 30, 30))
    img.save(buf, format='JPEG', quality=quality, optimize=quality < 95)
    return buf.getvalue()


def _seed(url: str, data: bytes) -> dict[str, object]:
    with Image.open(io.BytesIO(data)) as img:
        width, height = img.size
    fetcher._cache[url] = ImageEntry(data=data, content_type='image/jpeg', cached_at=time.time(), width=width, height=height)
    return {'url': url, 'dims': {'width': width, 'height': height}, 'image_class': 'background'}


async def test_byte_identical_copies_keep_only_the_first() -> None:
    body = _jpeg(800, 600)
    probed = [_seed('https://a/1.jpg', body), _seed('https://b/2.jpg', body), _seed('https://c/3.jpg', _jpeg(800, 600, shade=10))]

    kept = await _dedupe_artwork(probed)
    assert [p['url'] for p in kept] == ['https://a/1.jpg', 'https://c/3.jpg']


async def test_a_reencode_is_caught_by_the_pixel_pass() -> None:
    source = Image.new('RGB', (640, 480), (12, 200, 90))
    a, b = io.BytesIO(), io.BytesIO()
    source.save(a, format='PNG')
    source.save(b, format='BMP')
    probed = [_seed('https://a/x.png', a.getvalue()), _seed('https://b/x.bmp', b.getvalue())]
    assert probed[0]['url'] != probed[1]['url']
    assert fetcher._cache['https://a/x.png'].data != fetcher._cache['https://b/x.bmp'].data

    kept = await _dedupe_artwork(probed)
    assert [p['url'] for p in kept] == ['https://a/x.png']


async def test_different_pictures_of_the_same_size_are_both_kept() -> None:
    probed = [_seed('https://a/1.jpg', _jpeg(500, 500, shade=10)), _seed('https://b/2.jpg', _jpeg(500, 500, shade=240))]

    kept = await _dedupe_artwork(probed)
    assert len(kept) == 2


async def test_differing_dimensions_never_collide() -> None:
    probed = [_seed('https://a/1.jpg', _jpeg(800, 600)), _seed('https://b/2.jpg', _jpeg(400, 300))]

    kept = await _dedupe_artwork(probed)
    assert len(kept) == 2


async def test_without_cached_bytes_nothing_is_deduped() -> None:
    body = _jpeg(800, 600)
    probed = [_seed('https://a/1.jpg', body), _seed('https://b/2.jpg', body)]
    fetcher._cache.clear()

    kept = await _dedupe_artwork(probed)
    assert len(kept) == 2


def _entry(url: str, width: int, height: int) -> dict[str, object]:
    return {'url': url, 'dims': {'width': width, 'height': height}, 'image_class': 'poster'}


def test_only_images_sharing_a_shape_are_worth_a_pixel_comparison() -> None:
    from phoenixadult.mappers.metadata_mapper import needs_pixel_check

    entries = [_entry('a', 1920, 1080), _entry('b', 1920, 1080), _entry('c', 800, 1200)]
    assert needs_pixel_check(entries) == [True, True, False], 'a unique shape cannot be a pixel duplicate'


def test_a_single_image_never_triggers_a_pixel_fetch() -> None:
    from phoenixadult.mappers.metadata_mapper import needs_pixel_check

    assert needs_pixel_check([_entry('a', 100, 100)]) == [False]
    assert needs_pixel_check([]) == []


def test_pixel_keys_are_scoped_to_the_shape() -> None:
    from phoenixadult.mappers.metadata_mapper import pixel_keys

    entries = [_entry('a', 1920, 1080), _entry('b', 800, 1200)]
    assert pixel_keys(entries, ['deadbeef', 'deadbeef']) == ['1920x1080:deadbeef', '800x1200:deadbeef'], (
        'the same pixels at different sizes are different images'
    )


def test_a_missing_digest_never_dedupes() -> None:
    from phoenixadult.mappers.metadata_mapper import pixel_keys

    assert pixel_keys([_entry('a', 10, 10)], [None]) == [None], 'an unreadable image must be kept, not silently dropped'


def test_first_wins_when_keys_collide() -> None:
    from phoenixadult.mappers.metadata_mapper import _keep_first_by

    entries = [_entry('first', 10, 10), _entry('second', 10, 10), _entry('third', 20, 20)]
    kept = _keep_first_by(entries, ['same', 'same', 'other'])
    assert [e['url'] for e in kept] == ['first', 'third']
