from __future__ import annotations

import pytest

from phoenixadult.config.env_catalog import find_env_var, normalize_env_value
from phoenixadult.utils.processors.filename_parser import clean_search_title


def test_search_title_trash_rejects_an_invalid_pattern() -> None:
    spec = find_env_var('SEARCH_TITLE_TRASH')
    assert spec is not None
    ok, message = normalize_env_value(spec, 'XXX, Bad(')
    assert not ok and 'Bad(' in message
    assert normalize_env_value(spec, 'XXX, Promo\\d+') == (True, 'XXX,Promo\\d+')


def test_a_bad_trash_pattern_already_in_the_environment_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SEARCH_TITLE_TRASH', 'Bad(,Promo')
    assert clean_search_title('Great Scene Promo 1080p') == 'Great Scene'
