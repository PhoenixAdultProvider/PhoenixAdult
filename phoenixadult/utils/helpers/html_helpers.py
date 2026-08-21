from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from w3lib.html import remove_tags, replace_entities
from w3lib.url import add_or_replace_parameter

from phoenixadult.utils.helpers.helpers import absolute_url
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.searchengines import SearchOptions, web_search

if TYPE_CHECKING:
    from parsel import Selector, SelectorList

    from phoenixadult.registry import ResolvedSiteInfo

    Node = Selector | SelectorList[Selector]


async def web_search_urls(
    query: str,
    site: ResolvedSiteInfo,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    *,
    host: str | None = None,
    num: int = 10,
    language: str | None = None,
) -> list[str]:
    target = host if host is not None else (urlsplit(site.base_url).hostname or '').removeprefix('www.')
    if not query or not target:
        return []
    try:
        urls = await web_search(SearchOptions(query=query, site=target, num=num, language=language))
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
    return add_or_replace_parameter(url, param_name, y)


def strip_tags(html: str | None) -> str:
    return replace_entities(remove_tags(html or '')).strip()


def script_match(script_text: str, pattern: re.Pattern[str] | str) -> str:
    compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
    m = compiled.search(script_text)
    return m.group(1) if m and m.lastindex else ''


def first_text(node: Selector, xpath: str) -> str:
    nodes = node.xpath(xpath)
    return (nodes[0].xpath('normalize-space(.)').get() or '').strip() if nodes else ''


def first_attr(node: Node, xpath: str = 'string(.)') -> str:
    return (node.xpath(xpath).get() or '').strip()


def absolute_first_attr(node: Node, xpath: str, base_url: str) -> str:
    raw = first_attr(node, xpath)
    return absolute_url(raw, base_url) if raw else ''


def meta_content(node: Selector, key: str, attr: str | None = None) -> str:
    match = f'@{attr}="{key}"' if attr else f'@property="{key}" or @name="{key}"'
    return (node.xpath(f'(//meta[{match}]/@content)[1]').get() or '').strip()
