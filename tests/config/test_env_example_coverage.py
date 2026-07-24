"""Every catalog env var must appear in .env.example (set or commented), so the
sample can't silently fall behind new config."""

from __future__ import annotations

import re
from pathlib import Path

from phoenixadult.config.env_catalog import ENV_CATALOG

_EXAMPLE = Path(__file__).resolve().parents[2] / '.env.example'


def test_env_example_covers_catalog() -> None:
    keys = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=', _EXAMPLE.read_text(encoding='utf-8'), re.M))
    missing = sorted(s.key for s in ENV_CATALOG if s.key not in keys)
    assert not missing, f'.env.example is missing catalog vars: {missing}'
