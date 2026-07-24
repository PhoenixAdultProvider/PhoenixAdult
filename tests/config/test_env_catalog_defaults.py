from __future__ import annotations

from collections.abc import Callable

import pytest

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import ENV_CATALOG, EnvVarSpec

_DERIVED = {'LOG_REDACT_HOSTS', 'LOG_REDACT_TOKEN'}

_BOOL_GETTERS: dict[str, Callable[[], bool]] = {
    'METADATA_CACHE_ENABLE': lambda: env.metadata_cache_enabled,
    'PEOPLE_CACHE_ENABLE': lambda: env.people_cache_enabled,
    'PEOPLE_CACHE_REPLACE_ENABLE': lambda: env.people_cache_replace_enabled,
    'PEOPLE_CACHE_FACE_ENABLE': lambda: env.people_cache_face_enabled,
    'GENDER_DETECT_ENABLE': lambda: env.gender_detect_enabled,
    'GENDER_SKIP_MALE_ENABLE': lambda: env.gender_skip_male_enabled,
    'GENERIC_IMAGE_ENABLE': lambda: env.generic_image_enabled,
    'REQBIN_ENABLE': lambda: env.reqbin_enabled,
    'BYPASS_AUTO_RETRY': lambda: env.bypass_auto_retry,
    'DATA18_ENABLE': lambda: env.data18_enabled,
    'DATA18_EXTRA': lambda: env.data18_extra_enabled,
    'PHOENIX_EXTRA_COLLECTIONS': lambda: env.phoenix_extra_collections,
    'STRIP_ENABLE': lambda: env.strip_symbols_enabled,
    'DISABLE_AUTO_MATCH': lambda: env.disable_auto_match,
    'IMAGE_PROXY_PIN': lambda: env.image_proxy_pin,
}


def _bool_specs() -> list[EnvVarSpec]:
    return [s for s in ENV_CATALOG if s.kind == 'boolean' and s.key not in _DERIVED]


def test_every_boolean_var_has_a_getter_mapping() -> None:
    keys = {s.key for s in _bool_specs()}
    assert keys == set(_BOOL_GETTERS), 'boolean env var added/removed — update _BOOL_GETTERS so its default stays drift-checked'


@pytest.mark.parametrize('spec', _bool_specs(), ids=lambda s: s.key)
def test_unset_boolean_default_matches_catalog(spec: EnvVarSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(spec.key, raising=False)
    effective = _BOOL_GETTERS[spec.key]()
    assert effective is (spec.default_value == 'true'), f'{spec.key}: catalog says default {spec.default_value!r}, env.py getter returns {effective}'


def test_redaction_defaults_follow_node_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _DERIVED:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('NODE_ENV', 'production')
    assert env.log_redact_hosts is True
    assert env.log_redact_token is True
    monkeypatch.setenv('NODE_ENV', 'development')
    assert env.log_redact_hosts is False
    assert env.log_redact_token is False
