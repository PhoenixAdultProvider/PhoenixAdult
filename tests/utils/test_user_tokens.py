from __future__ import annotations

import os

import pytest

from phoenixadult.utils.auth import user_store, user_tokens


@pytest.fixture(autouse=True)
def _fresh_cache() -> None:
    user_tokens.clear_fallback_cache()
    user_tokens.current_metadataapi_token.set(None)


def test_the_context_token_wins_over_the_fallback() -> None:
    uid = user_store.create_user('one', 'pw', is_admin=True)
    user_tokens.save_token_for_user(uid, 'fallback-tok')
    assert user_tokens.metadataapi_token() == 'fallback-tok'
    user_tokens.current_metadataapi_token.set('ctx-tok')
    assert user_tokens.metadataapi_token() == 'ctx-tok'


def test_the_fallback_is_the_first_configured_token() -> None:
    first = user_store.create_user('one', 'pw', is_admin=True)
    second = user_store.create_user('two', 'pw', is_admin=False)
    user_tokens.save_token_for_user(second, 'second-tok')
    assert user_tokens.metadataapi_token() == 'second-tok'
    user_tokens.save_token_for_user(first, 'first-tok')
    assert user_tokens.metadataapi_token() == 'first-tok'


def test_no_tokens_anywhere_means_none() -> None:
    user_store.create_user('one', 'pw', is_admin=True)
    assert user_tokens.metadataapi_token() is None


def test_env_token_migrates_into_the_first_admin_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from phoenixadult.config import env_overrides

    admin = user_store.create_user('one', 'pw', is_admin=True)
    monkeypatch.setattr(env_overrides, 'clear_override', lambda _key: None)
    monkeypatch.setitem(os.environ, 'METADATAAPI_TOKEN', 'env-tok')
    assert user_tokens.migrate_env_token() is True
    assert user_tokens.token_for_user(admin) == 'env-tok'
    assert user_tokens.migrate_env_token() is False
