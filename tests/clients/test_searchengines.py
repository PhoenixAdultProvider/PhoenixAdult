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


class _StubDDGS:
    calls: list[dict[str, object]] = []
    rows: list[dict[str, str]] = []
    raises: Exception | None = None

    def __init__(self, **kwargs: object) -> None:
        pass

    def text(self, query: str, **kwargs: object) -> list[dict[str, str]]:
        _StubDDGS.calls.append({'query': query, **kwargs})
        if _StubDDGS.raises is not None:
            raise _StubDDGS.raises
        return list(_StubDDGS.rows)


@pytest.fixture
def stub_ddgs(monkeypatch: pytest.MonkeyPatch) -> type[_StubDDGS]:
    from phoenixadult.utils.searchengines import metasearch

    _StubDDGS.calls, _StubDDGS.rows, _StubDDGS.raises = [], [], None
    monkeypatch.setattr(metasearch, 'DDGS', _StubDDGS)
    return _StubDDGS


async def test_metasearch_dedupes_and_slices(stub_ddgs: type[_StubDDGS]) -> None:
    from phoenixadult.utils.searchengines.metasearch import MetasearchClient

    stub_ddgs.rows = [{'href': 'https://example.com/a'}, {'href': 'https://example.com/a'}, {'href': 'https://example.com/b'}, {'href': ''}]
    urls = await MetasearchClient().search(SearchOptions(query='jane', site='example.com', num=2))
    assert urls == ['https://example.com/a', 'https://example.com/b']
    assert stub_ddgs.calls[0]['query'] == 'site:example.com jane'
    assert stub_ddgs.calls[0]['safesearch'] == 'off'


async def test_metasearch_honors_safe_search_and_no_results(stub_ddgs: type[_StubDDGS]) -> None:
    from ddgs.exceptions import DDGSException

    from phoenixadult.utils.searchengines.metasearch import MetasearchClient

    stub_ddgs.raises = DDGSException('No results found.')
    urls = await MetasearchClient().search(SearchOptions(query='jane', site='example.com', safe_search=True))
    assert urls == []
    assert stub_ddgs.calls[0]['safesearch'] == 'moderate'


@respx.mock
async def test_the_chain_falls_through_to_metasearch(stub_ddgs: type[_StubDDGS]) -> None:
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text='<html><body></body></html>'))
    stub_ddgs.rows = [{'href': 'https://example.com/meta-hit'}]
    urls = await web_search(SearchOptions(query='jane', site='example.com'))
    assert urls == ['https://example.com/meta-hit']


@respx.mock
async def test_google_cse_used_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('GOOGLE_SEARCH_API_KEY', 'k')
    monkeypatch.setenv('GOOGLE_SEARCH_CX', 'cx')
    payload = {'items': [{'link': 'https://example.com/g1'}], 'searchInformation': {'totalResults': '1'}}
    respx.route(method='GET', url__regex=r'googleapis\.com/customsearch').mock(return_value=httpx.Response(200, json=payload))
    urls = await web_search(SearchOptions(query='jane', site='example.com'))
    assert urls == ['https://example.com/g1']
