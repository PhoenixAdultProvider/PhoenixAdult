from __future__ import annotations

import socket

import app.config as cfg

# Documentation/reserved ranges only — never the host's real address (RFC 5737 / RFC 3849).
_DOC_IPV4 = '192.0.2.10'
_DOC_IPV6 = '2001:db8::10'


def _patch_detect(monkeypatch):
    monkeypatch.setattr(cfg, '_local_ip', lambda family, probe: _DOC_IPV4 if family == socket.AF_INET else _DOC_IPV6)


def test_baseurl_is_default(monkeypatch):
    monkeypatch.delenv('PEOPLE_IMAGE_URL', raising=False)
    assert cfg.people_image_base() == cfg.config.base_url


def test_localhost_uses_loopback(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', 'localhost')
    assert cfg.people_image_base() == f'http://localhost:{cfg.config.port}'


def test_localipv4_uses_detected_lan_address(monkeypatch):
    _patch_detect(monkeypatch)
    monkeypatch.setenv('PEOPLE_IMAGE_URL', 'localipv4')
    assert cfg.people_image_base() == f'http://{_DOC_IPV4}:{cfg.config.port}'


def test_localipv6_is_bracketed(monkeypatch):
    _patch_detect(monkeypatch)
    monkeypatch.setenv('PEOPLE_IMAGE_URL', 'localipv6')
    assert cfg.people_image_base() == f'http://[{_DOC_IPV6}]:{cfg.config.port}'


def test_baseurl_token_and_empty_use_baseurl(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', 'baseurl')
    assert cfg.people_image_base() == cfg.config.base_url
    monkeypatch.setenv('PEOPLE_IMAGE_URL', '')
    assert cfg.people_image_base() == cfg.config.base_url


def test_explicit_url_with_port_is_used_verbatim(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', f'http://{_DOC_IPV4}:8080/')
    assert cfg.people_image_base() == f'http://{_DOC_IPV4}:8080'


def test_explicit_url_without_port_gets_the_configured_port(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', f'http://{_DOC_IPV4}')
    assert cfg.people_image_base() == f'http://{_DOC_IPV4}:{cfg.config.port}'


def test_bare_host_gets_scheme_and_configured_port(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', _DOC_IPV4)
    assert cfg.people_image_base() == f'http://{_DOC_IPV4}:{cfg.config.port}'


def test_bare_host_with_port_gets_scheme_only(monkeypatch):
    monkeypatch.setenv('PEOPLE_IMAGE_URL', f'{_DOC_IPV4}:8080')
    assert cfg.people_image_base() == f'http://{_DOC_IPV4}:8080'
