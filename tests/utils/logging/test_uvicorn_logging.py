from __future__ import annotations

import logging

from app.utils.logging.uvicorn_logging import StartupAddressFilter


def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord('uvicorn.error', logging.INFO, __file__, 0, msg, None, None)


def test_drops_running_on_line_in_production(monkeypatch):
    monkeypatch.setenv('NODE_ENV', 'production')
    assert StartupAddressFilter().filter(_record('Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)')) is False


def test_keeps_running_on_line_outside_production(monkeypatch):
    monkeypatch.setenv('NODE_ENV', 'development')
    assert StartupAddressFilter().filter(_record('Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)')) is True


def test_keeps_other_lines_in_production(monkeypatch):
    monkeypatch.setenv('NODE_ENV', 'production')
    assert StartupAddressFilter().filter(_record('Application startup complete.')) is True
