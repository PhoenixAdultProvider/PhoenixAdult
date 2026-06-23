from __future__ import annotations

import httpx
import pytest
import respx

from app.utils.searchengines import web_search, web_search_filtered
from app.utils.searchengines.duckduckgo import DuckDuckGoClient
from app.utils.searchengines.types import SearchOptions

DDG_HTML = """<html><body>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fscene-1&rut=x">one</a>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fextra.html&rut=y">two</a>
</body></html>"""


@pytest.fixture(autouse=True)
def no_google(monkeypatch: pytest.MonkeyPatch) -> None:
    # Google CSE unavailable so the chain falls through to DuckDuckGo.
    monkeypatch.delenv('GOOGLE_SEARCH_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_SEARCH_CX', raising=False)


@respx.mock
async def test_ddg_resolves_redirect_links() -> None:
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=DDG_HTML))
    urls = await DuckDuckGoClient().search(SearchOptions(query='jane', site='example.com'))
    assert urls == ['https://example.com/scene-1', 'https://example.com/extra.html']


@respx.mock
async def test_web_search_falls_through_to_ddg() -> None:
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=DDG_HTML))
    urls = await web_search(SearchOptions(query='jane', site='example.com'))
    assert 'https://example.com/scene-1' in urls


@respx.mock
async def test_web_search_filtered() -> None:
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=DDG_HTML))
    urls = await web_search_filtered(SearchOptions(query='jane', site='example.com'), url_ends_with='.html')
    assert urls == ['https://example.com/extra.html']


@respx.mock
async def test_google_cse_used_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GOOGLE_SEARCH_API_KEY', 'k')
    monkeypatch.setenv('GOOGLE_SEARCH_CX', 'cx')
    payload = {'items': [{'link': 'https://example.com/g1'}], 'searchInformation': {'totalResults': '1'}}
    respx.route(method='GET', url__regex=r'googleapis\.com/customsearch').mock(return_value=httpx.Response(200, json=payload))
    urls = await web_search(SearchOptions(query='jane', site='example.com'))
    assert urls == ['https://example.com/g1']
