from __future__ import annotations

from urllib.parse import parse_qs, quote, urlsplit

import httpx2
from parsel import Selector

from app.utils.logging.logger import logger
from app.utils.searchengines.types import SearchOptions

_ENDPOINT = 'https://html.duckduckgo.com/html/'

# DDG's HTML interface returns 403 to a default UA; mimic a browser.
_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def _resolve_ddg_href(href: str) -> str | None:
    normalized = f'https:{href}' if href.startswith('//') else href
    parts = urlsplit(normalized)
    if not parts.scheme or not parts.netloc:
        return None
    if (parts.hostname or '').endswith('duckduckgo.com') and parts.path == '/l/':
        uddg = parse_qs(parts.query).get('uddg', [None])[0]
        if not uddg:
            return None
        target = urlsplit(uddg)
        return uddg if target.scheme and target.netloc else None
    return normalized


class DuckDuckGoClient:
    name = 'duckduckgo'

    def available(self) -> bool:
        return True

    async def search(self, opts: SearchOptions) -> list[str]:
        num = max(1, opts.num or 10)
        # DDG has no site-search param — fold the restriction into the query.
        query = f'site:{opts.site} {opts.query}'
        url = f'{_ENDPOINT}?q={quote(query)}'
        logger.debug('search:ddg', f'GET {url}')
        try:
            async with httpx2.AsyncClient(timeout=10.0, verify=False) as client:
                resp = await client.get(url, headers=_HEADERS)
                resp.raise_for_status()
        except httpx2.HTTPError as err:
            logger.warn('search:ddg', f'request failed: {err}')
            raise

        urls: list[str] = []
        for href in Selector(text=resp.text).xpath('//a[contains(@class,"result__a")]/@href').getall():
            resolved = _resolve_ddg_href(href)
            if resolved and resolved not in urls:
                urls.append(resolved)

        sliced = urls[:num]
        logger.info('search:ddg', f'site={opts.site} q="{opts.query}" → {len(sliced)} URL(s) (parsed {len(urls)} total)')
        return sliced
