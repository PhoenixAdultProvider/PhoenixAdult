from __future__ import annotations

import os
import tempfile

os.environ['LOG_DIR'] = os.path.join(tempfile.gettempdir(), 'phoenixadult-pytest-logs')

import pytest  # noqa: E402
import pytest_httpx2  # noqa: E402, F401  — registers the "httpcore2" respx mocker
import respx.mocks  # noqa: E402

respx.mocks.DEFAULT_MOCKER = 'httpcore2'


@pytest.fixture(autouse=True)
def _offline_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the anti-bot bypass chain offline by default.

    bypass_get() escapes respx (Impersonate/curl_cffi, Playwright aren't httpx), so
    a source/scraper that falls through to it would make a real network call. Pin the
    order to the HTTP backends and leave them unconfigured → every backend is
    unavailable → http_bypass() returns None. Tests that exercise bypass set their own
    BYPASS_ORDER + backend config, which overrides this.
    """
    monkeypatch.setenv('BYPASS_ORDER', 'FlareSolverr,ReqBin')
    monkeypatch.delenv('FLARESOLVERR_URL', raising=False)
    monkeypatch.delenv('REQBIN_ENABLE', raising=False)
    from app.utils.http.impersonate import impersonate_backend

    monkeypatch.setattr(impersonate_backend, 'is_available', lambda: False)


@pytest.fixture
def no_web_search() -> object:
    """A stand-in for a client module's imported web_search that finds nothing."""

    async def _none(*_args: object, **_kwargs: object) -> list[str]:
        return []

    return _none
