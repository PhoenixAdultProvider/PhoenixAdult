from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils.images import logo_cache


@pytest.fixture(autouse=True)
def _fresh_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
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


def test_find_bin_falls_back_to_install_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logo_cache.shutil, 'which', lambda _name: None)
    monkeypatch.setattr(logo_cache.Path, 'is_file', lambda self: self.as_posix() == '/usr/local/bin/rsvg-convert')
    found = logo_cache._find_bin('rsvg-convert')
    assert found is not None and Path(found).as_posix() == '/usr/local/bin/rsvg-convert'
    assert logo_cache._find_bin('magick') is None


def test_convert_svg_prefers_rsvg_over_magick(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    svg = tmp_path / 'logo.x.svg'
    svg.write_text('<svg/>', encoding='utf-8')
    called = []

    def fake_rsvg(s: Path, p: Path) -> bool:
        called.append('rsvg')
        p.write_bytes(b'png')
        return True

    monkeypatch.setattr(logo_cache, '_rsvg', fake_rsvg)
    monkeypatch.setattr(logo_cache, '_magick', lambda s, p: called.append('magick') or True)
    out = logo_cache.convert_svg(svg)
    assert out == tmp_path / 'logo.x.png' and not svg.exists()
    assert called == ['rsvg']


def test_rescan_adopts_and_converts_manual_drops(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _put(tmp_path, 'badoinkvr', 'BadoinkVR Logo.svg', b'<svg/>')
    _put(tmp_path, 'brazzers', 'brazzers.png', b'png')

    def fake_convert(path: Path) -> Path:
        png = path.with_suffix('.png')
        png.write_bytes(b'converted')
        path.unlink()
        return png

    monkeypatch.setattr(logo_cache, 'convert_svg', fake_convert)
    assert logo_cache.rescan() == 2
    assert (tmp_path / 'badoinkvr' / 'logo.badoinkvr-logo.png').exists()
    assert logo_cache.find_logo(None, 'Brazzers') == tmp_path / 'brazzers' / 'logo.brazzers.png'


def test_index_rebuilds_after_db_loss(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from phoenixadult.utils import db

    f = _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == f

    db.close()
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'state2.db'))
    assert logo_cache.find_logo(None, 'Brazzers') == f


def test_stale_row_healed_without_invalidate(tmp_path: Path) -> None:
    f = _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == f
    f.unlink()
    assert logo_cache.find_logo(None, 'Brazzers') is None


def test_find_logo_scans_candidate_folders_on_miss(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') is not None
    dropped = _put(tmp_path, 'brazzers', 'logo.baby-got-boobs.png')
    _put(tmp_path, 'elsewhere', 'logo.unrelated.png')
    assert logo_cache.find_logo('Baby Got Boobs', 'Brazzers') == dropped
    assert logo_cache.find_logo('Unrelated', None) is None


def test_entries_reads_the_table_without_a_rescan(tmp_path: Path) -> None:
    _put(tmp_path, 'brazzers', 'logo.brazzers.png')
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers'}
    _put(tmp_path, 'nubiles', 'logo.nubilesnet.png')
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers'}
    logo_cache.invalidate()
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers', 'nubilesnet'}


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
