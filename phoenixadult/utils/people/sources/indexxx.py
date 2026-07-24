from __future__ import annotations

from parsel import Selector

from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import encode_name, make_source_http
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


class _IndexxxSource:
    name = 'Indexxx'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        search_url = f'https://www.indexxx.com/search/?query={encode_name(actor_name)}'
        logger.debug('indexxxSource', f'GET {search_url}')
        async with make_source_http() as client:
            search_html = (await client.get(search_url)).text
            page_url = Selector(text=search_html).xpath('(//div[contains(@class,"modelPanel")]//a[contains(@class,"modelLink3")]/@href)[1]').get()
            if not page_url:
                logger.debug('indexxxSource', f'no modelPanel match for "{actor_name}"')
                return None
            logger.debug('indexxxSource', f'candidate page {page_url}')
            page = (await client.get(page_url)).text

        img = Selector(text=page).xpath('(//img[contains(@class,"model-img")]/@src)[1]').get()
        if img:
            logger.debug('indexxxSource', f'matched "{actor_name}" → {img}')
        return PhotoHit(url=img, gender='female') if img else None


indexxx_source = _IndexxxSource()
