from __future__ import annotations

import httpx
import pytest
import respx

from phoenixadult.registry import find_site
from phoenixadult.utils.helpers.html_helpers import web_search_urls
from phoenixadult.utils.searchengines import web_search
from phoenixadult.utils.searchengines.duckduckgo import DuckDuckGoClient
from phoenixadult.utils.searchengines.types import SearchOptions

DDG_HTML = """<html><body>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fscene-1&rut=x">one</a>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fextra.html&rut=y">two</a>
</body></html>"""


@pytest.fixture(autouse=True)
def no_google(monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_web_search_urls_filters_what_the_engine_returned() -> None:
    site = find_site('Brazzers')
    assert site is not None
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=DDG_HTML))

    assert await web_search_urls('jane', site, include=['.html']) == ['https://example.com/extra.html']
    assert await web_search_urls('jane', site, exclude=['extra']) == ['https://example.com/scene-1']
    assert await web_search_urls('', site) == []


@respx.mock
async def test_web_search_urls_strips_www_from_the_site_operator() -> None:
    site = find_site('Brazzers')
    assert site is not None
    seen: list[str] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=DDG_HTML)

    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(side_effect=_capture)
    await web_search_urls('jane', site, host='www.example.com')
    await web_search_urls('jane', site)

    assert 'site%3Awww.example.com' in seen[0]
    assert 'www.' not in seen[1].split('site%3A')[1].split('%20')[0]


@respx.mock
async def test_google_cse_used_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GOOGLE_SEARCH_API_KEY', 'k')
    monkeypatch.setenv('GOOGLE_SEARCH_CX', 'cx')
    payload = {'items': [{'link': 'https://example.com/g1'}], 'searchInformation': {'totalResults': '1'}}
    respx.route(method='GET', url__regex=r'googleapis\.com/customsearch').mock(return_value=httpx.Response(200, json=payload))
    urls = await web_search(SearchOptions(query='jane', site='example.com'))
    assert urls == ['https://example.com/g1']
