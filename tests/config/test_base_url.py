from __future__ import annotations

import app.config as cfg


def test_default_derives_from_port():
    assert cfg._normalize_base_url(None, 8080) == 'http://localhost:8080'
    assert cfg._normalize_base_url('', 3000) == 'http://localhost:3000'
    assert cfg._normalize_base_url('   ', 9000) == 'http://localhost:9000'


def test_schemeless_gets_http():
    assert cfg._normalize_base_url('10.0.0.50', 3000) == 'http://10.0.0.50'
    # A port in the value is preserved; the listen PORT is never injected.
    assert cfg._normalize_base_url('10.0.0.50:3000', 3000) == 'http://10.0.0.50:3000'
    assert cfg._normalize_base_url('example.internal', 3000) == 'http://example.internal'


def test_explicit_scheme_is_untouched():
    assert cfg._normalize_base_url('http://host:3000', 3000) == 'http://host:3000'
    assert cfg._normalize_base_url('https://name.trycloudflare.com', 3000) == 'https://name.trycloudflare.com'
    assert cfg._normalize_base_url('  https://x.example/  ', 3000) == 'https://x.example/'


def test_warning_only_when_set_and_schemeless(monkeypatch):
    monkeypatch.setattr(cfg, '_RAW_BASE_URL', None)
    assert cfg.base_url_config_warning() is None
    monkeypatch.setattr(cfg, '_RAW_BASE_URL', 'https://name.example')
    assert cfg.base_url_config_warning() is None
    monkeypatch.setattr(cfg, '_RAW_BASE_URL', '10.0.0.50')
    warning = cfg.base_url_config_warning()
    assert warning is not None and '10.0.0.50' in warning
