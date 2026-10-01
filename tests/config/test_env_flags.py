from __future__ import annotations

import pytest

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import find_env_var, normalize_env_value
from phoenixadult.utils.processors.filename_parser import clean_search_title


@pytest.mark.parametrize('value', ['1', 'true', 'YES', 'on'])
def test_an_off_by_default_flag_accepts_every_truthy_spelling(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv('DEV_UI_ENABLE', value)
    assert env.dev_ui_enabled is True


@pytest.mark.parametrize('value', ['0', 'false', 'no', 'OFF'])
def test_an_on_by_default_flag_turns_off_for_every_falsy_spelling(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv('IMAGE_GUARD_ENABLE', value)
    assert env.image_guard_enabled is False


def test_disable_auto_match_zero_keeps_auto_match_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('DISABLE_AUTO_MATCH', '0')
    assert env.disable_auto_match is False
    monkeypatch.setenv('DISABLE_AUTO_MATCH', 'true')
    assert env.disable_auto_match is True


def test_search_title_trash_rejects_an_invalid_pattern() -> None:
    spec = find_env_var('SEARCH_TITLE_TRASH')
    assert spec is not None
    ok, message = normalize_env_value(spec, 'XXX, Bad(')
    assert not ok and 'Bad(' in message
    assert normalize_env_value(spec, 'XXX, Promo\\d+') == (True, 'XXX,Promo\\d+')


def test_a_bad_trash_pattern_already_in_the_environment_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_TITLE_TRASH', 'Bad(,Promo')
    assert clean_search_title('Great Scene Promo 1080p') == 'Great Scene'
