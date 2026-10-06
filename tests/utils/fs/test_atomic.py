from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from phoenixadult.utils.fs import atomic


def test_a_write_replaces_the_file_and_leaves_nothing_behind(tmp_path: Path) -> None:
    folder = tmp_path / 'actors'
    folder.mkdir()
    target = folder / 'jane.jpg'
    target.write_bytes(b'old')
    atomic.write_bytes_atomic(target, b'new')
    assert target.read_bytes() == b'new'
    assert sorted(p.name for p in folder.iterdir()) == ['jane.jpg']


def test_an_interrupted_write_keeps_the_previous_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    folder = tmp_path / 'actors'
    folder.mkdir()
    target = folder / 'jane.jpg'
    target.write_bytes(b'old')

    def killed(src: object, dst: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(atomic.os, 'replace', killed)
    with pytest.raises(KeyboardInterrupt):
        atomic.write_bytes_atomic(target, b'half')
    assert target.read_bytes() == b'old'
    assert sorted(p.name for p in folder.iterdir()) == ['jane.jpg']


def test_the_sweep_removes_only_stale_partials(tmp_path: Path) -> None:
    nested = tmp_path / 'actors' / 'female'
    nested.mkdir(parents=True)
    stale = nested / '.jane.jpg.0a1b2c3d.part'
    fresh = nested / '.joan.jpg.4e5f6a7b.part'
    image = nested / 'jane.jpg'
    for path in (stale, fresh, image):
        path.write_bytes(b'x')
    hours_ago = time.time() - 2 * 3600
    os.utime(stale, (hours_ago, hours_ago))
    os.utime(image, (hours_ago, hours_ago))
    assert atomic.sweep_partials(tmp_path, tmp_path / 'missing') == 1
    assert not stale.exists() and fresh.exists() and image.exists(), 'an in-flight write and real images stay'
