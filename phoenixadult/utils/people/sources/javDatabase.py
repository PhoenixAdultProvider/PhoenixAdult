from __future__ import annotations

import httpx2
from parsel import Selector

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import levenshtein, make_source_http
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


class _JavDatabaseSource:
    name = 'JAVDatabase'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        query = '+'.join(actor_name.split())
        url = f'https://www.javdatabase.com/?wpessid=391488&s={query}'
        logger.debug('javDatabaseSource', f'GET {url}')
        try:
            async with make_source_http() as client:
                html = (await client.get(url)).text
                best = ''
                best_score = float('inf')
                for thumb_img in Selector(text=html).xpath('//div[contains(@class,"idol-thumb")]//img[@class]'):
                    name = (thumb_img.xpath('./@alt').get() or '').strip()
                    src = thumb_img.xpath('./@data-src').get() or ''
                    score = float(levenshtein(actor_name, name))
                    if score < best_score or not best:
                        best_score = score
                        best = src
                if not best:
                    logger.debug('javDatabaseSource', f'no thumb match for "{actor_name}"')
                    return None
                try:
                    head = await client.head(best)
                    if 'unknown.' in str(head.url):
                        logger.debug('javDatabaseSource', f'rejected placeholder for "{actor_name}"')
                        return None
                except httpx2.HTTPError:
                    pass
        except httpx2.HTTPError as err:
            logger.debug('javDatabaseSource', f'GET {url} threw: {err}')
            return None

        logger.debug('javDatabaseSource', f'matched "{actor_name}" → {best}')
        return PhotoHit(url=best, gender='female')


jav_database_source = _JavDatabaseSource()
