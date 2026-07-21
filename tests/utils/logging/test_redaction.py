from __future__ import annotations

import logging

import pytest

from app.utils.logging.redaction import RedactionFilter, redact


def test_redact_own_host_keeps_scheme_and_path(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://my-tunnel.example.com')
    assert redact('Config UI: https://my-tunnel.example.com/config?lang=en') == 'Config UI: https://***REDACTED***/config?lang=en'


def test_redact_leaves_scraped_hosts_untouched(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://my-tunnel.example.com')
    assert redact('Requesting GET "https://czechcasting.com/video/lucie-1484/"') == 'Requesting GET "https://czechcasting.com/video/lucie-1484/"'


def test_redact_own_host_not_confused_with_lookalike(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://example.com')
    assert redact('https://notexample.com/x and https://example.community/y') == 'https://notexample.com/x and https://example.community/y'


def test_own_host_not_redacted_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://my-tunnel.example.com')
    assert redact('Config UI: https://my-tunnel.example.com/config') == 'Config UI: https://my-tunnel.example.com/config'


def test_no_own_host_when_base_url_localhost(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    monkeypatch.setenv('PHOENIX_BASE_URL', 'http://localhost:3000')
    assert redact('http://plex.example.com:32400/config') == 'http://plex.example.com:32400/config'


def test_private_ipv4_masked_when_flag_on(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    assert redact('client 192.168.1.50 connected') == 'client ***REDACTED*** connected'


def test_private_ipv4_shown_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    assert redact('serving http://10.0.0.5:3000/x') == 'serving http://10.0.0.5:3000/x'


def test_public_ipv4_masked_even_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    assert redact('upstream 8.8.8.8 reached') == 'upstream ***REDACTED*** reached'


def test_private_ipv6_masked_when_flag_on(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    assert redact('from fe80::1ff:fe23:4567:890a here') == 'from ***REDACTED*** here'


def test_link_local_ipv6_shown_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    assert redact('from fe80::1ff:fe23:4567:890a here') == 'from fe80::1ff:fe23:4567:890a here'


def test_public_ipv6_masked_even_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    assert redact('peer 2606:4700:4700::1111 ok') == 'peer ***REDACTED*** ok'


def test_redact_leaves_plain_text_untouched():
    assert redact('Plex Metadata Provider running on port 3000') == 'Plex Metadata Provider running on port 3000'


def test_redact_query_token(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    assert redact('http://h.example/config?token=s3cret&x=1') == 'http://h.example/config?token=***REDACTED***&x=1'


def test_redact_query_token_in_bare_path(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    assert redact('/config?token=abc123') == '/config?token=***REDACTED***'


def test_token_not_redacted_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'false')
    assert redact('/config?token=abc123') == '/config?token=abc123'


def test_token_default_follows_production_posture(monkeypatch):
    monkeypatch.delenv('LOG_REDACT_TOKEN', raising=False)
    monkeypatch.setenv('NODE_ENV', 'development')
    assert redact('/config?token=abc123') == '/config?token=abc123'
    monkeypatch.setenv('NODE_ENV', 'production')
    assert redact('/config?token=abc123') == '/config?token=***REDACTED***'


@pytest.mark.parametrize('name', ['apikey', 'api_key', 'access_token', 'auth_token', 'secret', 'password', 'pwd'])
def test_redact_secret_param_names(monkeypatch, name):
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    assert redact(f'/x?{name}=zzz') == f'/x?{name}=***REDACTED***'


def test_redact_does_not_mask_author_param(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    assert redact('/x?author=jane') == '/x?author=jane'


def _record(name: str, msg: str, args=None) -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 0, msg, args, None)


def test_filter_shows_private_ip_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    rec = _record('phoenixadult', 'host http://10.0.0.1/x')
    RedactionFilter().filter(rec)
    assert rec.getMessage() == 'host http://10.0.0.1/x'


def test_filter_redacts_public_uvicorn_access_ip_and_token_when_flag_off(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    args = ('8.8.8.8:0', 'GET', '/people?token=deadbeefcafe', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:0'
    assert rec.args[2] == '/people?token=***REDACTED***'


def test_filter_redacts_uvicorn_access_client_addr(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    args = ('127.0.0.1:54321', 'GET', '/health', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:54321'
    assert rec.args[1:] == ('GET', '/health', '1.1', 200)


def test_filter_redacts_ipv6_uvicorn_access_client_addr(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    args = ('2001:db8:7a3c:f19e:4b62:8d05:1ce7:9f4a:0', 'GET', '/x', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:0'


def test_filter_redacts_token_in_uvicorn_access_path(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'true')
    args = ('127.0.0.1:54321', 'GET', '/config?token=abc123', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:54321'
    assert rec.args[2] == '/config?token=***REDACTED***'


@pytest.mark.parametrize('flag', ['1', 'yes', 'on', 'TRUE'])
def test_flag_truthy_values(monkeypatch, flag):
    from app.config.env import env

    monkeypatch.setenv('LOG_REDACT_HOSTS', flag)
    assert env.log_redact_hosts is True


def test_log_redact_token_follows_production_default(monkeypatch):
    from app.config.env import env

    monkeypatch.delenv('LOG_REDACT_TOKEN', raising=False)
    monkeypatch.delenv('NODE_ENV', raising=False)
    assert env.log_redact_token is True
    monkeypatch.setenv('NODE_ENV', 'development')
    assert env.log_redact_token is False
    monkeypatch.setenv('LOG_REDACT_TOKEN', 'false')
    assert env.log_redact_token is False
    for flag in ('1', 'yes', 'on', 'TRUE'):
        monkeypatch.setenv('LOG_REDACT_TOKEN', flag)
        assert env.log_redact_token is True
