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
    fetcher._cache_total_bytes = 0
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
    fetcher._cache_put(url, ImageEntry(data=data, content_type='image/jpeg', cached_at=time.time(), width=width, height=height))
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
    fetcher._cache_total_bytes = 0

    kept = await _dedupe_artwork(probed)
    assert len(kept) == 2
