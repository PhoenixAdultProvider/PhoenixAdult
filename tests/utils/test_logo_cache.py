from __future__ import annotations

from pathlib import Path

import pytest

from phoenixadult.utils.images import logo_cache


@pytest.fixture(autouse=True)
def logo_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = tmp_path / 'logos'
    root.mkdir()
    logo_cache.invalidate()
    return root


def _put(root: Path, folder: str, name: str, data: bytes = b'png') -> Path:
    d = root / folder
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_bytes(data)
    return f


def test_logo_slug_transforms() -> None:
    assert logo_cache.logo_slug('Baby Got Boobs') == 'babygotboobs'
    assert logo_cache.logo_slug('Nubiles.net') == 'nubilesnet'
    assert logo_cache.logo_slug("Daddy's Lil Angel") == 'daddyslilangel'
    assert logo_cache.logo_slug('Casting Couch-X') == 'castingcouchx'


def test_logo_slug_ignores_spacing_and_casing() -> None:
    for spelling in ('VR PMV Bay', 'vr-pmv-bay', 'vrpmvbay', 'VRPMVBay', 'Vr  Pmv  Bay'):
        assert logo_cache.logo_slug(spelling) == 'vrpmvbay'
    for spelling in ('Blurred Media', 'blurred-media', 'blurredmedia', 'BlurredMedia'):
        assert logo_cache.logo_slug(spelling) == 'blurredmedia'


def test_find_logo_tagline_beats_studio(logo_dir: Path) -> None:
    _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    sub = _put(logo_dir, 'brazzers', 'logo.baby-got-boobs.png')
    assert logo_cache.find_logo('Baby Got Boobs', 'Brazzers') == sub
    assert logo_cache.find_logo(None, 'Brazzers') == logo_dir / 'brazzers' / 'logo.brazzers.png'
    assert logo_cache.find_logo('No Such Site', 'No Such Studio') is None


def test_first_file_wins_on_duplicate_slug(logo_dir: Path) -> None:
    first = _put(logo_dir, 'alpha', 'logo.brazzers.png')
    _put(logo_dir, 'zeta', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == first


def test_replaced_file_visible_after_invalidate(logo_dir: Path) -> None:
    _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') is not None
    (logo_dir / 'brazzers' / 'logo.brazzers.png').unlink()
    logo_cache.invalidate()
    assert logo_cache.find_logo(None, 'Brazzers') is None


def test_local_url_shape(logo_dir: Path) -> None:
    f = _put(logo_dir, 'brazzers', 'logo.baby-got-boobs.png')
    assert logo_cache.local_url(f) == '/images/local/logos/brazzers/logo.baby-got-boobs.png'
    assert logo_cache.local_url(f, 1785269272.5) == '/images/local/logos/brazzers/logo.baby-got-boobs.png?v=1785269272'


def test_index_converts_dropped_svgs(monkeypatch: pytest.MonkeyPatch, logo_dir: Path) -> None:
    svg = _put(logo_dir, 'nubiles', 'logo.smashed.svg', b'<svg/>')

    def fake_convert(path: Path) -> Path:
        png = path.with_suffix('.png')
        png.write_bytes(b'converted')
        path.unlink()
        return png

    monkeypatch.setattr(logo_cache, 'convert_svg', fake_convert)
    hit = logo_cache.find_logo('Smashed', None)
    assert hit == logo_dir / 'nubiles' / 'logo.smashed.png'
    assert not svg.exists()


def test_find_bin_falls_back_to_install_prefix(monkeypatch: pytest.MonkeyPatch, logo_dir: Path) -> None:
    monkeypatch.setattr(logo_cache.shutil, 'which', lambda _name: None)
    monkeypatch.setattr(logo_cache.Path, 'is_file', lambda self: self.as_posix() == '/usr/local/bin/rsvg-convert')
    found = logo_cache._find_bin('rsvg-convert')
    assert found is not None and Path(found).as_posix() == '/usr/local/bin/rsvg-convert'
    assert logo_cache._find_bin('magick') is None


def test_convert_svg_prefers_rsvg_over_magick(monkeypatch: pytest.MonkeyPatch, logo_dir: Path) -> None:
    svg = logo_dir / 'logo.x.svg'
    svg.write_text('<svg/>', encoding='utf-8')
    called = []

    def fake_rsvg(s: Path, p: Path) -> bool:
        called.append('rsvg')
        p.write_bytes(b'png')
        return True

    monkeypatch.setattr(logo_cache, '_rsvg', fake_rsvg)
    monkeypatch.setattr(logo_cache, '_magick', lambda s, p: called.append('magick') or True)
    out = logo_cache.convert_svg(svg)
    assert out == logo_dir / 'logo.x.png' and not svg.exists()
    assert called == ['rsvg']


def test_rescan_adopts_and_converts_manual_drops(monkeypatch: pytest.MonkeyPatch, logo_dir: Path) -> None:
    _put(logo_dir, 'badoinkvr', 'BadoinkVR Logo.svg', b'<svg/>')
    _put(logo_dir, 'brazzers', 'brazzers.png', b'png')

    def fake_convert(path: Path) -> Path:
        png = path.with_suffix('.png')
        png.write_bytes(b'converted')
        path.unlink()
        return png

    monkeypatch.setattr(logo_cache, 'convert_svg', fake_convert)
    assert logo_cache.rescan() == 2
    assert (logo_dir / 'badoinkvr' / 'logo.badoinkvrlogo.png').exists()
    assert logo_cache.find_logo(None, 'Brazzers') == logo_dir / 'brazzers' / 'logo.brazzers.png'


def test_index_rebuilds_after_db_loss(monkeypatch: pytest.MonkeyPatch, logo_dir: Path) -> None:
    from phoenixadult.utils import db

    f = _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == f

    db.close()
    monkeypatch.setenv('STATE_DB_PATH', str(logo_dir / 'state2.db'))
    assert logo_cache.find_logo(None, 'Brazzers') == f


def test_stale_row_healed_without_invalidate(logo_dir: Path) -> None:
    f = _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') == f
    f.unlink()
    assert logo_cache.find_logo(None, 'Brazzers') is None


def test_find_logo_scans_candidate_folders_on_miss(logo_dir: Path) -> None:
    _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    assert logo_cache.find_logo(None, 'Brazzers') is not None
    dropped = _put(logo_dir, 'brazzers', 'logo.baby-got-boobs.png')
    _put(logo_dir, 'elsewhere', 'logo.unrelated.png')
    assert logo_cache.find_logo('Baby Got Boobs', 'Brazzers') == dropped
    assert logo_cache.find_logo('Unrelated', None) is None


def test_entries_reads_the_table_without_a_rescan(logo_dir: Path) -> None:
    _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers'}
    _put(logo_dir, 'nubiles', 'logo.nubilesnet.png')
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers'}
    logo_cache.invalidate()
    assert {r['slug'] for r in logo_cache.entries()} == {'brazzers', 'nubilesnet'}


def test_entries_and_purge(logo_dir: Path) -> None:
    _put(logo_dir, 'brazzers', 'logo.brazzers.png')
    _put(logo_dir, 'nubiles', 'logo.nubilesnet.png')
    rows = logo_cache.entries()
    assert {r['slug'] for r in rows} == {'brazzers', 'nubilesnet'}
    assert logo_cache.purge('brazzers/logo.brazzers.png') is True
    assert logo_cache.purge('brazzers/logo.brazzers.png') is False
    assert logo_cache.purge('../outside.png') is False
    assert logo_cache.purge_all() == 1
    assert logo_cache.entries() == []
