from __future__ import annotations

import logging

import pytest

from app.utils.logging.redaction import RedactionFilter, redact


def test_redact_own_host_keeps_scheme_and_path(monkeypatch):
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://my-tunnel.example.com')
    assert redact('Config UI: https://my-tunnel.example.com/config?lang=en') == 'Config UI: https://***REDACTED***/config?lang=en'


def test_redact_leaves_scraped_hosts_untouched(monkeypatch):
    # Scraped target sites must stay visible — only the server's own host is redacted.
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://my-tunnel.example.com')
    assert redact('Requesting GET "https://czechcasting.com/video/lucie-1484/"') == 'Requesting GET "https://czechcasting.com/video/lucie-1484/"'


def test_redact_own_host_not_confused_with_lookalike(monkeypatch):
    monkeypatch.setenv('PHOENIX_BASE_URL', 'https://example.com')
    assert redact('https://notexample.com/x and https://example.community/y') == 'https://notexample.com/x and https://example.community/y'


def test_no_own_host_when_base_url_localhost(monkeypatch):
    monkeypatch.setenv('PHOENIX_BASE_URL', 'http://localhost:3000')
    assert redact('http://plex.example.com:32400/config') == 'http://plex.example.com:32400/config'


def test_redact_ipv4():
    assert redact('client 192.168.1.50 connected') == 'client ***REDACTED*** connected'


def test_redact_ipv6():
    assert redact('from fe80::1ff:fe23:4567:890a here') == 'from ***REDACTED*** here'


def test_redact_leaves_plain_text_untouched():
    assert redact('Plex Metadata Provider running on port 3000') == 'Plex Metadata Provider running on port 3000'


def test_redact_query_token():
    # Host left intact (not the server's own host); only the token value is masked.
    assert redact('http://h.example/config?token=s3cret&x=1') == 'http://h.example/config?token=***REDACTED***&x=1'


def test_redact_query_token_in_bare_path():
    assert redact('/config?token=abc123') == '/config?token=***REDACTED***'


@pytest.mark.parametrize('name', ['apikey', 'api_key', 'access_token', 'auth_token', 'secret', 'password', 'pwd'])
def test_redact_secret_param_names(name):
    assert redact(f'/x?{name}=zzz') == f'/x?{name}=***REDACTED***'


def test_redact_does_not_mask_author_param():
    assert redact('/x?author=jane') == '/x?author=jane'


def _record(name: str, msg: str, args=None) -> logging.LogRecord:
    return logging.LogRecord(name, logging.INFO, __file__, 0, msg, args, None)


def test_filter_off_when_flag_disabled(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'false')
    rec = _record('phoenixadult', 'host http://10.0.0.1/x')
    RedactionFilter().filter(rec)
    assert rec.getMessage() == 'host http://10.0.0.1/x'


def test_filter_redacts_when_enabled(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    rec = _record('phoenixadult', 'host http://10.0.0.1/x')
    RedactionFilter().filter(rec)
    assert rec.getMessage() == 'host http://***REDACTED***/x'


def test_filter_redacts_uvicorn_access_client_addr(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    args = ('127.0.0.1:54321', 'GET', '/health', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:54321'
    assert rec.args[1:] == ('GET', '/health', '1.1', 200)


def test_filter_redacts_ipv6_uvicorn_access_client_addr(monkeypatch):
    # IPv6 client_addr is "<addr>:<port>"; the glued port must not defeat redaction.
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
    args = ('2001:db8:7a3c:f19e:4b62:8d05:1ce7:9f4a:0', 'GET', '/x', '1.1', 200)
    rec = _record('uvicorn.access', '%s - "%s %s HTTP/%s" %d', args)
    RedactionFilter().filter(rec)
    assert rec.args[0] == '***REDACTED***:0'


def test_filter_redacts_token_in_uvicorn_access_path(monkeypatch):
    monkeypatch.setenv('LOG_REDACT_HOSTS', 'true')
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
