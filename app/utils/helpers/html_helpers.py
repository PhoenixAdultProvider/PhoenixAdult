from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

if TYPE_CHECKING:
    from parsel import Selector

    from app.registry import ResolvedSiteInfo


async def web_search_urls(query: str, site: ResolvedSiteInfo, include: list[str] | None = None, exclude: list[str] | None = None) -> list[str]:
    host = (urlsplit(site.base_url).hostname or '').removeprefix('www.')
    if not host:
        return []
    try:
        urls = await web_search(SearchOptions(query=query, site=host, num=10))
    except Exception as err:  # noqa: BLE001 - search failure is non-fatal
        logger.debug(site.name, f'webSearch threw: {err}')
        return []

    if not include and not exclude:
        return urls
    return [u for u in urls if (not include or any(s in u for s in include)) and not (exclude and any(s in u for s in exclude))]


def append_year_param(url: str, param_name: str, year: int | None = None, search_date: str | None = None) -> str:
    y = ''
    if year is not None:
        y = str(year)
    elif search_date:
        y = search_date[:4]
    if not re.match(r'^\d{4}$', y):
        return url
    sep = '&' if '?' in url else '?'
    return f'{url}{sep}{param_name}={y}'


_TAG_RE = re.compile(r'<[^>]+>')


def strip_tags(html: str | None) -> str:
    """Remove HTML tags and trim. Does not collapse internal whitespace."""
    return _TAG_RE.sub('', html or '').strip()


def script_match(script_text: str, pattern: re.Pattern[str] | str) -> str:
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    m = compiled.search(script_text)
    return m.group(1) if m and m.lastindex else ''


def first_text(node: Selector, xpath: str) -> str:
    """Normalized text of the first element matching the XPath ('' if none)."""
    nodes = node.xpath(xpath)
    return (nodes[0].xpath('normalize-space(.)').get() or '').strip() if nodes else ''


def meta_content(node: Selector, key: str) -> str:
    """Content of the first <meta property=KEY> or <meta name=KEY> ('' if none).
    Covers OpenGraph (og:*) and Twitter-card (twitter:*) tags interchangeably."""
    return (node.xpath(f'(//meta[@property="{key}" or @name="{key}"]/@content)[1]').get() or '').strip()
