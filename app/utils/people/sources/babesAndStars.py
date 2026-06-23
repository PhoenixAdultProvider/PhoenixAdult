from __future__ import annotations

import re

import httpx2
from parsel import Selector

from app.utils.logging.logger import logger
from app.utils.people.sources._http import make_source_http
from app.utils.people.types import PersonLookupContext, PhotoHit


class _BabesAndStarsSource:
    name = 'Babes and Stars'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        first = actor_name[0].lower() if actor_name else ''
        slug = re.sub(r"'", '-', re.sub(r'\s+', '-', actor_name.lower()))
        url = f'http://www.babesandstars.com/{first}/{slug}/'
        logger.debug('babesAndStarsSource', f'GET {url}')
        try:
            async with make_source_http() as client:
                data = (await client.get(url)).text
            img = Selector(text=data).xpath('(//div[contains(@class,"profile")]//div[contains(@class,"thumb")]//img/@src)[1]').get()
            if img:
                logger.debug('babesAndStarsSource', f'matched "{actor_name}" → {img}')
                return PhotoHit(url=img, gender='female')
            logger.debug('babesAndStarsSource', f'no img.src in {url}')
            return None
        except httpx2.HTTPError as err:
            logger.debug('babesAndStarsSource', f'GET {url} threw: {err}')
            return None


babes_and_stars_source = _BabesAndStarsSource()
