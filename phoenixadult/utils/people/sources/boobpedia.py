from __future__ import annotations

import re

import httpx2
from parsel import Selector

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import make_source_http
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


class _BoobpediaSource:
    name = 'Boobpedia'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        slug = re.sub(r'\s+', '_', re.sub(r'\b\w', lambda m: m.group().upper(), actor_name))
        url = f'http://www.boobpedia.com/boobs/{slug}'
        logger.debug('boobpediaSource', f'GET {url}')
        try:
            async with make_source_http() as client:
                data = (await client.get(url)).text
            img = Selector(text=data).xpath('(//table[contains(@class,"infobox")]//a[contains(@class,"image")]//img/@src)[1]').get()
            if img:
                full = f'http://www.boobpedia.com{img}'
                logger.debug('boobpediaSource', f'matched "{actor_name}" → {full}')
                return PhotoHit(url=full, gender='female')
            logger.debug('boobpediaSource', f'no infobox image for "{actor_name}"')
            return None
        except httpx2.HTTPError as err:
            logger.debug('boobpediaSource', f'GET {url} threw: {err}')
            return None


boobpedia_source = _BoobpediaSource()
