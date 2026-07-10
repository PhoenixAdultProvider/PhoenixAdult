from __future__ import annotations

import json
import os
from pathlib import Path

from app.utils.fs.reloadable import MtimeCachedJson


def _write(f: Path, obj: object) -> None:
    f.write_text(json.dumps(obj), encoding='utf-8')


def test_reparses_on_mtime_change(tmp_path: Path) -> None:
    f = tmp_path / 'd.json'
    _write(f, {'v': 1})
    res: MtimeCachedJson[int] = MtimeCachedJson(f, lambda raw: raw['v'])
    assert res.get() == 1

    _write(f, {'v': 2})
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    res._stat_checked_at = 0.0
    assert res.get() == 2


def test_stat_throttle_serves_cached_within_interval(tmp_path: Path) -> None:
    f = tmp_path / 'd.json'
    _write(f, {'v': 1})
    res: MtimeCachedJson[int] = MtimeCachedJson(f, lambda raw: raw['v'], stat_interval=1000.0)
    assert res.get() == 1

    _write(f, {'v': 2})
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    assert res.get() == 1
