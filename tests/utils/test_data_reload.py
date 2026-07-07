from __future__ import annotations

import json
import os

import pytest

from app.utils.genres import data as gdata
from app.utils.people import data as pdata


def test_genre_rules_reloads_on_mtime_change(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / 'genres.json'
    f.write_text(json.dumps({'replace': {'Blow Job': ['bj']}, 'skip': ['foo'], 'partial_skip': []}), encoding='utf-8')
    monkeypatch.setattr(gdata, '_RULES', gdata.MtimeCachedJson(f, gdata._build))

    rules = gdata.genre_rules()
    assert 'foo' in rules.skip_set
    assert rules.replace_lookup['bj'] == 'Blow Job'

    f.write_text(json.dumps({'replace': {}, 'skip': ['bar'], 'partial_skip': []}), encoding='utf-8')
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))  # force a newer mtime
    monkeypatch.setattr(gdata._RULES, '_stat_checked_at', 0.0)  # skip the stat rate-limit window

    reloaded = gdata.genre_rules()
    assert 'bar' in reloaded.skip_set
    assert 'foo' not in reloaded.skip_set


def test_actor_rules_reloads_on_mtime_change(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / 'actors.json'
    f.write_text(json.dumps({'replace': {'Jane Doe': ['jd']}, 'replace_studios': {}, 'studio_indexes': {}}), encoding='utf-8')
    monkeypatch.setattr(pdata, '_RULES', pdata.MtimeCachedJson(f, pdata._build))

    assert pdata.actor_rules().replace == {'Jane Doe': ['jd']}

    f.write_text(json.dumps({'replace': {'John Roe': ['jr']}, 'replace_studios': {}, 'studio_indexes': {}}), encoding='utf-8')
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))
    monkeypatch.setattr(pdata._RULES, '_stat_checked_at', 0.0)  # skip the stat rate-limit window

    assert pdata.actor_rules().replace == {'John Roe': ['jr']}
