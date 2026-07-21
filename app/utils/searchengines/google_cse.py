from __future__ import annotations

import httpx2

from app.config.env import env
from app.utils.logging.logger import logger
from app.utils.searchengines.types import SearchOptions

_ENDPOINT = 'https://www.googleapis.com/customsearch/v1'


def _clamp_num(n: int) -> int:
    if n < 1:
        return 1
    return min(n, 10)


class GoogleCseClient:
    name = 'google-cse'

    def available(self) -> bool:
        return bool(env.google_search_api_key) and bool(env.google_search_cx)

    async def search(self, opts: SearchOptions) -> list[str]:
        api_key = env.google_search_api_key
        cx = env.google_search_cx
        if not api_key or not cx:
            raise ValueError('GoogleCseClient: GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX env vars are required')

        num = _clamp_num(opts.num or 10)
        language = opts.language or 'en'
        params = {
            'key': api_key,
            'cx': cx,
            'q': opts.query,
            'siteSearch': opts.site,
            'siteSearchFilter': 'i',
            'num': str(num),
            'lr': f'lang_{language}',
            'safe': 'active' if opts.safe_search else 'off',
        }
        if opts.region:
            params['gl'] = opts.region

        logger.debug('search:google', f'GET customsearch siteSearch={opts.site} q="{opts.query}"')
        try:
            async with httpx2.AsyncClient(timeout=10.0, verify=True) as client:
                resp = await client.get(_ENDPOINT, params=params)
            data = resp.json()
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn('search:google', f'request failed: {err}')
            raise

        if data.get('error'):
            code, message = data['error'].get('code'), data['error'].get('message')
            logger.warn('search:google', f'API error {code}: {message}')
            raise ValueError(f'GoogleCseClient API error {code}: {message}')

        total = (data.get('searchInformation') or {}).get('totalResults', '0')
        urls = [item['link'] for item in (data.get('items') or []) if item.get('link')]
        logger.info('search:google', f'site={opts.site} q="{opts.query}" → {len(urls)} URL(s) (totalResults={total})')
        return urls
