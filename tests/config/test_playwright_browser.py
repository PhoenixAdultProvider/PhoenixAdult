from __future__ import annotations

import pytest

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import ENV_CATALOG


def test_default_is_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PLAYWRIGHT_BROWSER', raising=False)
    assert env.playwright_browser == 'chromium'


@pytest.mark.parametrize('value', ['firefox', 'webkit', 'chromium', 'FireFox', '  webkit '])
def test_valid_values_normalized(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv('PLAYWRIGHT_BROWSER', value)
    assert env.playwright_browser == value.strip().lower()


def test_unknown_falls_back_to_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLAYWRIGHT_BROWSER', 'safari')
    assert env.playwright_browser == 'chromium'


def test_catalog_entry() -> None:
    spec = next(s for s in ENV_CATALOG if s.key == 'PLAYWRIGHT_BROWSER')
    assert spec.kind == 'enum'
    assert spec.options == ['chromium', 'firefox', 'webkit']
    assert spec.default_value == 'chromium'
