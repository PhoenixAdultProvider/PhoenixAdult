from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.images import logo_cache
from app.utils.images.image_fetcher import ImageEntry


@pytest.fixture(autouse=True)
def _fresh_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('LOGO_CACHE_ENABLE', 'true')
    monkeypatch.setenv('LOGO_CACHE_DIR', str(tmp_path))
    logo_cache.invalidate()
    return tmp_path


def _put(root: Path, folder: str, name: str, data: bytes = b'png') -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_bytes(data)
    return f


def test_logo_slug_transforms() -> None:
    assert logo_cache.logo_slug('Baby Got Boobs') == 'baby-got-boobs'
    assert logo_cache.logo_slug('Nubiles.net') == 'nubilesnet'
    assert logo_cache.logo_slug("Daddy's Lil Angel") == 'daddys-lil-angel'
    assert logo_cache.logo_slug('Casting Couch-X') == 'casting-couchx'


def test_find_logo_tagline_beats_studio(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    sub = _put(tmp_path, 'brazzers', 'logo.baby-got-boobs.png')
    assert logo_cache.find_logo('Baby Got Boobs', 'Brazzers') == sub
    assert logo_cache.find_logo(None, 'Brazzers') == tmp_path / 'brazzers' / 'logo.brazzers.png'
    assert logo_cache.find_logo('No Such Site', 'No Such Studio') is None


def test_find_logo_disabled_returns_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    monkeypatch.setenv('LOGO_CACHE_ENABLE', 'false')
    logo_cache.invalidate()
    assert logo_cache.find_logo(None, 'Brazzers') is None


def test_first_file_wins_on_duplicate_slug(tmp_path: Path) -> None:
    first = _put(tmp_path, 'alpha', 'logo.brazzers.png')
    _put(tmp_path, 'zeta', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == first


def test_replaced_file_visible_after_invalidate(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') is not None
    (tmp_path / 'brazzers' / 'logo.brazzers.png').unlink()
    logo_cache.invalidate()
    assert logo_cache.find_logo(None, 'Brazzers') is None


def test_local_url_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(logo_cache, 'config', SimpleNamespace(base_url='http://prov:3000'))
    f = _put(tmp_path, 'brazzers', 'logo.baby-got-boobs.png')
    assert logo_cache.local_url(f) == 'http://prov:3000/images/local/logos/brazzers/logo.baby-got-boobs.png'


async def test_resolve_logo_prefers_local_over_upstream(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')

    async def _no_fetch(*_a: object, **_k: object) -> ImageEntry:
        raise AssertionError('local hit must not download')

    logo_cache.fetch_image, orig = _no_fetch, logo_cache.fetch_image  # type: ignore[assignment]
    try:
        url = await logo_cache.resolve_logo(None, 'Brazzers', 'http://up/logo.png')
    finally:
        logo_cache.fetch_image = orig  # type: ignore[assignment]
    assert url is not None and url.endswith('/images/local/logos/brazzers/logo.brazzers.png')


async def test_resolve_logo_downloads_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    async def fake_fetch(url: str, *a: object, **k: object) -> ImageEntry:
        calls.append(url)
        return ImageEntry(data=b'PNGDATA', content_type='image/png', cached_at=0.0, width=10, height=10)

    monkeypatch.setattr(logo_cache, 'fetch_image', fake_fetch)
    url1 = await logo_cache.resolve_logo('Baby Got Boobs', 'Brazzers', 'http://up/logo.png')
    url2 = await logo_cache.resolve_logo('Baby Got Boobs', 'Brazzers', 'http://up/logo.png')
    assert url1 == url2
    assert url1 is not None and url1.endswith('/images/local/logos/brazzers/logo.baby-got-boobs.png')
    assert calls == ['http://up/logo.png']
    assert (tmp_path / 'brazzers' / 'logo.baby-got-boobs.png').read_bytes() == b'PNGDATA'


async def test_resolve_logo_svg_download_converts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_fetch(url: str, *a: object, **k: object) -> ImageEntry:
        return ImageEntry(data=b'<svg/>', content_type='image/svg+xml', cached_at=0.0, width=0, height=0)

    def fake_convert(svg: Path) -> Path:
        png = svg.with_suffix('.png')
        png.write_bytes(b'converted')
        svg.unlink()
        return png

    monkeypatch.setattr(logo_cache, 'fetch_image', fake_fetch)
    monkeypatch.setattr(logo_cache, 'convert_svg', fake_convert)
    url = await logo_cache.resolve_logo('Smashed', 'Nubiles Porn', 'http://up/logo.svg')
    assert url is not None and url.endswith('/logo.smashed.png')
    assert (tmp_path / 'nubiles-porn' / 'logo.smashed.png').read_bytes() == b'converted'
    assert not (tmp_path / 'nubiles-porn' / 'logo.smashed.svg').exists()


async def test_resolve_logo_disabled_passes_upstream(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    monkeypatch.setenv('LOGO_CACHE_ENABLE', 'false')
    logo_cache.invalidate()
    assert await logo_cache.resolve_logo(None, 'Brazzers', 'http://up/logo.png') == 'http://up/logo.png'
    assert await logo_cache.resolve_logo(None, 'Brazzers', None) is None


def test_index_converts_dropped_svgs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svg = _put(tmp_path, 'nubiles', 'logo.smashed.svg', b'<svg/>')

    def fake_convert(path: Path) -> Path:
        png = path.with_suffix('.png')
        png.write_bytes(b'converted')
        path.unlink()
        return png

    monkeypatch.setattr(logo_cache, 'convert_svg', fake_convert)
    hit = logo_cache.find_logo('Smashed', None)
    assert hit == tmp_path / 'nubiles' / 'logo.smashed.png'
    assert not svg.exists()


def test_entries_and_purge(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    _put(tmp_path, 'nubiles', 'logo.nubilesnet.png')
    rows = logo_cache.entries()
    assert {r['slug'] for r in rows} == {'brazzers', 'nubilesnet'}
    assert logo_cache.purge('brazzers/logo.brazzers.png') is True
    assert logo_cache.purge('brazzers/logo.brazzers.png') is False
    assert logo_cache.purge('../outside.png') is False
    assert logo_cache.purge_all() == 1
    assert logo_cache.entries() == []
