from __future__ import annotations

import io

import httpx
import pytest
import respx
from PIL import Image

from phoenixadult.utils.images import image_fetcher as fetcher
from phoenixadult.utils.images.image_fetcher import fetch_dimensions

URL = 'https://cdn.example.com/scene/poster.jpg'


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'false')
    fetcher._cache.clear()
    fetcher._dims_cache.clear()
    fetcher._shared_probe_clients.clear()
    fetcher._shared_image_clients.clear()


def _jpeg(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new('RGB', (width, height), (200, 30, 30)).save(buf, format='JPEG', quality=95)
    return buf.getvalue()


@respx.mock
async def test_a_ranged_head_is_enough_to_size_an_image() -> None:
    body = _jpeg(1500, 1000)
    route = respx.get(URL).mock(return_value=httpx.Response(206, content=body[:4096], headers={'Content-Type': 'image/jpeg'}))

    assert await fetch_dimensions(URL) == {'width': 1500, 'height': 1000}
    assert route.call_count == 1
    assert route.calls[0].request.headers['Range'] == f'bytes=0-{fetcher._PROBE_HEAD_BYTES - 1}'
    assert not fetcher._cache


@respx.mock
async def test_a_sized_url_is_answered_from_cache_next_time() -> None:
    body = _jpeg(800, 1200)
    route = respx.get(URL).mock(return_value=httpx.Response(206, content=body[:4096], headers={'Content-Type': 'image/jpeg'}))

    assert await fetch_dimensions(URL) == {'width': 800, 'height': 1200}
    assert await fetch_dimensions(URL) == {'width': 800, 'height': 1200}
    assert route.call_count == 1


@respx.mock
async def test_an_unreachable_host_never_falls_back_to_a_full_fetch() -> None:
    route = respx.get(URL).mock(side_effect=httpx.ConnectTimeout('no route'))

    assert await fetch_dimensions(URL) is None
    assert route.call_count == 1


@respx.mock
async def test_a_404_is_taken_as_final() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))

    assert await fetch_dimensions(URL) is None
    assert route.call_count == 1


@respx.mock
async def test_a_failed_probe_is_remembered_briefly() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))

    assert await fetch_dimensions(URL) is None
    assert await fetch_dimensions(URL) is None
    assert route.call_count == 1


@respx.mock
async def test_an_unparseable_head_falls_back_to_the_full_image() -> None:
    body = _jpeg(640, 480)
    route = respx.get(URL).mock(
        side_effect=[
            httpx.Response(200, content=b'\xff\xd8\xff', headers={'Content-Type': 'image/jpeg'}),
            httpx.Response(200, content=body, headers={'Content-Type': 'image/jpeg'}),
        ]
    )

    assert await fetch_dimensions(URL) == {'width': 640, 'height': 480}
    assert route.call_count == 2


@respx.mock
async def test_an_already_downloaded_image_is_not_probed_again() -> None:
    body = _jpeg(300, 300)
    respx.get(URL).mock(return_value=httpx.Response(200, content=body, headers={'Content-Type': 'image/jpeg'}))
    entry = await fetcher.fetch_image(URL)
    assert entry.width == 300

    respx.reset()
    blocked = respx.get(URL).mock(return_value=httpx.Response(500))
    assert await fetch_dimensions(URL) == {'width': 300, 'height': 300}
    assert blocked.call_count == 0


@respx.mock
async def test_the_probe_is_skipped_when_snapshots_will_download_anyway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('METADATA_CACHE_ENABLE', 'true')
    body = _jpeg(1200, 800)
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=body, headers={'Content-Type': 'image/jpeg'}))

    assert await fetch_dimensions(URL) == {'width': 1200, 'height': 800}
    assert route.call_count == 1
    assert 'Range' not in route.calls[0].request.headers
    assert fetcher._cache.get(URL) is not None


def test_a_solid_colour_image_is_flagged_and_real_detail_is_not() -> None:
    import io

    from PIL import Image, ImageDraw

    from phoenixadult.utils.images.image_fetcher import _decode_dims

    def encode(img: Image.Image, quality: int = 88) -> bytes:
        buf = io.BytesIO()
        img.convert('RGB').save(buf, format='JPEG', quality=quality)
        return buf.getvalue()

    solid = encode(Image.new('RGB', (600, 900), (0, 0, 0)), quality=30)
    assert _decode_dims(solid) == (600, 900, True)

    navy = encode(Image.new('RGB', (600, 900), (12, 20, 60)), quality=20)
    assert _decode_dims(navy)[2] is True

    marked = Image.new('RGB', (600, 900), (0, 0, 0))
    ImageDraw.Draw(marked).rectangle([280, 430, 320, 470], fill=(255, 255, 255))
    assert _decode_dims(encode(marked))[2] is False

    faint = Image.effect_noise((600, 900), 4).convert('RGB').point(lambda v: max(0, v - 122))
    assert _decode_dims(encode(faint))[2] is False


def test_a_fully_transparent_png_counts_as_solid() -> None:
    import io

    from PIL import Image

    from phoenixadult.utils.images.image_fetcher import _decode_dims

    buf = io.BytesIO()
    Image.new('RGBA', (400, 600), (0, 0, 0, 0)).save(buf, format='PNG')
    assert _decode_dims(buf.getvalue())[2] is True
