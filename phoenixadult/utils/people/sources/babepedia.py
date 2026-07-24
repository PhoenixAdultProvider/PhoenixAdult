from __future__ import annotations

import re
from urllib.parse import quote

import httpx2

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import make_source_http
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


class _BabepediaSource:
    name = 'Babepedia'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        slug = quote(re.sub(r'\b\w', lambda m: m.group().upper(), actor_name))
        url = f'http://www.babepedia.com/pics/{slug}.jpg'
        logger.debug('babepediaSource', f'HEAD {url}')
        try:
            async with make_source_http() as client:
                r = await client.head(url)
            if 200 <= r.status_code < 300:
                logger.debug('babepediaSource', f'matched "{actor_name}" → {url}')
                return PhotoHit(url=url, gender='female')
            logger.debug('babepediaSource', f'HEAD {url} → {r.status_code}')
        except httpx2.HTTPError as err:
            logger.debug('babepediaSource', f'HEAD threw for "{actor_name}": {err}')
        return None


babepedia_source = _BabepediaSource()
