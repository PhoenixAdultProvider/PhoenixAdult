from __future__ import annotations

import json
from pathlib import Path

import pytest

from phoenixadult.utils.images import logo_cache


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv('STATE_DB_PATH', str(tmp_path / 'phoenixadult.db'))
    monkeypatch.setattr(logo_cache, '_WELL_CACHE', {'vixen/logo.vixen.png|0|0': 'dark'}, raising=False)
    monkeypatch.setattr(logo_cache, '_WELL_LOADED', True, raising=False)
    monkeypatch.setattr(logo_cache, '_WELL_DIRTY', True, raising=False)


def test_a_failed_write_leaves_the_backdrops_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    real_write = Path.write_text

    def refuse(self: Path, *a: object, **kw: object) -> int:
        raise OSError('disk full')

    monkeypatch.setattr(Path, 'write_text', refuse)
    logo_cache._save_wells()
    assert logo_cache._WELL_DIRTY is True, 'a write that failed must stay pending, not be dropped'

    monkeypatch.setattr(Path, 'write_text', real_write)
    logo_cache._save_wells()
    stored = json.loads(logo_cache._well_store().read_text(encoding='utf-8'))
    assert stored == {'vixen/logo.vixen.png|0|0': 'dark'}, 'the retry must persist what the failed write held'


def test_a_clean_cache_does_not_rewrite_the_file() -> None:
    logo_cache._save_wells()
    assert logo_cache._WELL_DIRTY is False
    logo_cache._well_store().unlink()
    logo_cache._save_wells()
    assert not logo_cache._well_store().exists(), 'nothing dirty means nothing to write'
