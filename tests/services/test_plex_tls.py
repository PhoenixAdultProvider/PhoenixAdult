from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVICES = Path(__file__).resolve().parents[2] / 'phoenixadult' / 'services'
_CREDENTIALED = ('plex_account.py', 'plex_reconcile.py')


def _make_http_calls(path: Path) -> list[ast.Call]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'make_http']


@pytest.mark.parametrize('filename', _CREDENTIALED)
def test_every_plex_client_verifies_certificates(filename: str) -> None:
    calls = _make_http_calls(_SERVICES / filename)
    assert calls, f'{filename} should still build its own http client'
    for call in calls:
        verify = next((kw.value for kw in call.keywords if kw.arg == 'verify'), None)
        assert isinstance(verify, ast.Constant) and verify.value is True, (
            f'{filename}:{call.lineno} calls make_http without verify=True. These clients carry the Plex account token, and make_http defaults to verify=False.'
        )
