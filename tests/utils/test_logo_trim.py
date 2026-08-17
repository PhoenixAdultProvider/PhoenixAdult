from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from phoenixadult.utils.images import logo_cache, logo_trim


@pytest.fixture(autouse=True)
def logo_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv('IMAGE_DIR', str(tmp_path))
    root = tmp_path / 'logos'
    root.mkdir()
    logo_cache.invalidate()
    return root


def _padded(path: Path, size: tuple[int, int], box: tuple[int, int, int, int], bg: tuple[int, int, int, int], fmt: str = 'PNG') -> Path:
    im = Image.new('RGBA', size, bg)
    for x in range(box[0], box[2]):
        for y in range(box[1], box[3]):
            im.putpixel((x, y), (255, 255, 255, 255))
    im.save(path, format=fmt)
    return path


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def test_trim_removes_transparent_padding(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'a.png', (100, 80), (30, 20, 70, 60), (0, 0, 0, 0))
    assert logo_trim.trim(f) == ((100, 80), (40, 40))
    assert _size(f) == (40, 40)


def test_trim_handles_content_flush_against_one_edge(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'b.png', (360, 240), (0, 186, 360, 240), (0, 0, 0, 0))
    assert logo_trim.trim(f) == ((360, 240), (360, 54))
    assert _size(f) == (360, 54)


def test_trim_removes_uniform_opaque_border(tmp_path: Path) -> None:
    im = Image.new('RGB', (60, 60), (12, 12, 12))
    for x in range(20, 40):
        for y in range(25, 35):
            im.putpixel((x, y), (255, 255, 255))
    f = tmp_path / 'c.png'
    im.save(f)
    assert logo_trim.trim(f) == ((60, 60), (20, 10))


def test_trim_leaves_a_tight_logo_alone(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'd.png', (40, 40), (0, 0, 40, 40), (0, 0, 0, 0))
    assert logo_trim.trim(f) is None
    assert _size(f) == (40, 40)


def test_trim_refuses_when_the_corners_disagree(tmp_path: Path) -> None:
    im = Image.new('RGB', (40, 40), (10, 10, 10))
    im.putpixel((39, 39), (200, 30, 30))
    f = tmp_path / 'e.png'
    im.save(f)
    assert logo_trim.trim(f) is None
    assert _size(f) == (40, 40)


def test_trim_refuses_a_fully_transparent_image(tmp_path: Path) -> None:
    f = tmp_path / 'f.png'
    Image.new('RGBA', (40, 40), (0, 0, 0, 0)).save(f)
    assert logo_trim.trim(f) is None
    assert _size(f) == (40, 40)


def test_trim_refuses_to_shave_a_logo_to_nothing(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'g.png', (80, 80), (40, 40, 42, 42), (0, 0, 0, 0))
    assert logo_trim.trim(f) is None
    assert _size(f) == (80, 80)


def test_trim_keeps_the_original_format(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'h.webp', (100, 80), (30, 20, 70, 60), (0, 0, 0, 0), fmt='WEBP')
    assert logo_trim.trim(f) == ((100, 80), (40, 40))
    with Image.open(f) as im:
        assert im.format == 'WEBP'
        assert im.size == (40, 40)


def test_trim_keeps_transparency_after_the_crop(tmp_path: Path) -> None:
    f = _padded(tmp_path / 'i.png', (100, 80), (30, 20, 70, 60), (0, 0, 0, 0))
    logo_trim.trim(f)
    with Image.open(f) as im:
        assert im.convert('RGBA').getchannel('A').getextrema() == (255, 255)


def test_saving_a_logo_trims_it_on_the_way_in(logo_dir: Path, tmp_path: Path) -> None:
    src = _padded(tmp_path / 'src.png', (300, 200), (100, 80, 200, 120), (0, 0, 0, 0))
    rel = logo_cache.save_logo('brazzers', 'babygotboobs', src.read_bytes(), '.png')
    assert _size(logo_dir / rel) == (100, 40)


def test_adopting_a_manual_drop_trims_it(logo_dir: Path, tmp_path: Path) -> None:
    folder = logo_dir / 'vixen'
    folder.mkdir()
    _padded(folder / 'Blacked Raw.png', (240, 160), (60, 40, 180, 120), (0, 0, 0, 0))
    logo_cache.rescan()
    assert _size(folder / 'logo.blackedraw.png') == (120, 80)
