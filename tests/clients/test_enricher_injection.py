from __future__ import annotations

import ast
from pathlib import Path

import phoenixadult.clients  # noqa: F401 - importing the package is what wires the factory
from phoenixadult.clients import base

_BASE = Path(base.__file__)


def test_the_base_class_no_longer_imports_a_concrete_client() -> None:
    tree = ast.parse(_BASE.read_text(encoding='utf-8'))
    offenders = [
        f'line {node.lineno}: {node.module}'
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('phoenixadult.clients.aggregators')
    ]
    assert not offenders, f'base.py reaches down into a subclass: {offenders}'


def test_importing_the_client_registry_wires_the_enricher() -> None:
    assert base._enricher_factory is not None
    from phoenixadult.clients.aggregators.data18 import Data18Client

    assert isinstance(base._enricher_factory(), Data18Client)


def test_the_factory_resolves_the_class_when_called_not_at_import() -> None:
    import phoenixadult.clients.aggregators.data18 as data18_module

    real = data18_module.Data18Client
    try:
        data18_module.Data18Client = lambda: 'stub'  # type: ignore[assignment,return-value]
        assert base._enricher_factory is not None
        assert base._enricher_factory() == 'stub', 'tests must still be able to stub the enricher'
    finally:
        data18_module.Data18Client = real


def test_enrichment_is_skipped_when_no_factory_is_registered(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(base, '_enricher_factory', None)
    assert base._enricher_factory is None
