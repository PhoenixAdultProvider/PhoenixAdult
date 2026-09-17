from __future__ import annotations

import pathlib

from scripts.generate_sitelist import build

_SITELIST = pathlib.Path(__file__).resolve().parents[2] / 'docs' / 'sitelist.md'


def test_the_committed_sitelist_matches_the_registry() -> None:
    committed = _SITELIST.read_text(encoding='utf-8').replace('\r\n', '\n')
    assert committed == build(), 'docs/sitelist.md is stale — run `python -m scripts.generate_sitelist`'
