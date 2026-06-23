from __future__ import annotations

import re

import httpx
import pytest
import respx

from app.models.scraper_config import ScraperConfig
from app.registry import ResolvedSiteInfo
from app.utils.helpers.html_helpers import append_year_param, script_match, web_search_urls

_DDG = """<html><body>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fscene-1&rut=x">one</a>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fabout&rut=y">two</a>
</body></html>"""


def test_append_year_param() -> None:
    assert append_year_param('https://x.com/s', 'year', year=2024) == 'https://x.com/s?year=2024'
    assert append_year_param('https://x.com/s?q=1', 'year', search_date='2023-05-01') == 'https://x.com/s?q=1&year=2023'
    assert append_year_param('https://x.com/s', 'year') == 'https://x.com/s'


def test_script_match() -> None:
    assert script_match('var id = "abc123";', re.compile(r'var id = "(\w+)"')) == 'abc123'
    assert script_match('nothing here', r'id=(\d+)') == ''


@respx.mock
async def test_web_search_urls_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('GOOGLE_SEARCH_API_KEY', raising=False)
    respx.route(method='GET', url__regex=r'duckduckgo\.com/html').mock(return_value=httpx.Response(200, text=_DDG))
    site = ResolvedSiteInfo(
        name='Example',
        base_url='https://www.example.com',
        search_path='/',
        content_type='sceneName',
        scraper_config=ScraperConfig(type='example'),
        provider_id='phoenixadult',
    )
    urls = await web_search_urls('jane', site, include=['scene'])
    assert urls == ['https://example.com/scene-1']
