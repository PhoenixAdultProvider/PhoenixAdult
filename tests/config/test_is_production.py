from __future__ import annotations

import pytest

from app.config.env import env


def test_unset_defaults_to_production(monkeypatch):
    monkeypatch.delenv('NODE_ENV', raising=False)
    assert env.is_production is True


def test_blank_defaults_to_production(monkeypatch):
    monkeypatch.setenv('NODE_ENV', '')
    assert env.is_production is True


@pytest.mark.parametrize('value', ['development', 'dev', 'test', 'local', 'Development', ' DEV '])
def test_explicit_dev_values_are_not_production(monkeypatch, value):
    monkeypatch.setenv('NODE_ENV', value)
    assert env.is_production is False


@pytest.mark.parametrize('value', ['production', 'prod', 'staging', 'anything'])
def test_non_dev_values_are_production(monkeypatch, value):
    monkeypatch.setenv('NODE_ENV', value)
    assert env.is_production is True


def test_log_redact_hosts_follows_production_default(monkeypatch):
    monkeypatch.delenv('NODE_ENV', raising=False)
    monkeypatch.delenv('LOG_REDACT_HOSTS', raising=False)
    assert env.log_redact_hosts is True
