from __future__ import annotations

import pytest

import app.utils.logging.best_effort as be


def test_swallows_exception_and_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(be.logger, 'warn', lambda *a, **k: calls.append(a))
    with be.best_effort('scope', 'token HEAD'):
        raise ValueError('boom')
    assert calls == [('scope', 'token HEAD failed: boom')]  # uniform '<action> failed: <err>'


def test_level_override(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(be.logger, 'debug', lambda *a, **k: calls.append(a))
    with be.best_effort('s', 'web search', level='debug'):
        raise RuntimeError('x')
    assert calls == [('s', 'web search failed: x')]


def test_success_does_not_log(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(be.logger, 'warn', lambda *a, **k: calls.append(a))
    ran = False
    with be.best_effort('s', 'thing'):
        ran = True
    assert ran and calls == []


def test_base_exception_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(be.logger, 'warn', lambda *a, **k: None)

    class Boom(BaseException):
        pass

    with pytest.raises(Boom), be.best_effort('s', 'thing'):
        raise Boom
