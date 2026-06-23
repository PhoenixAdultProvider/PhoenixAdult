from __future__ import annotations

import httpx2
from parsel import Selector

from app.utils.logging.logger import logger
from app.utils.people.data import lookup_javbus_id
from app.utils.people.sources._http import encode_name, levenshtein, make_source_http
from app.utils.people.types import PersonLookupContext, PhotoHit

_BASE = 'https://www.javbus.com'


class _JavBusSource:
    name = 'JAVBus'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        jav_id = lookup_javbus_id(actor_name)
        url = f'{_BASE}/en/star/{jav_id}' if jav_id else f'{_BASE}/en/searchstar/{encode_name(actor_name)}'
        logger.debug('javBusSource', f'GET {url} (id={jav_id or "(none)"})')
        try:
            async with make_source_http() as client:
                html = (await client.get(url)).text
        except httpx2.HTTPError as err:
            logger.debug('javBusSource', f'GET {url} threw: {err}')
            return None

        best = ''
        best_score = float('inf')
        for el in Selector(text=html).xpath('//div[contains(@class,"photo-frame")]//img'):
            img = el.xpath('./@src').get() or ''
            name = (el.xpath('./@title').get() or '').strip()
            full = img if img.startswith('http') else f'{_BASE}{img}'
            if jav_id:
                best = full
                break
            score = levenshtein(actor_name, name)
            if score < best_score and 'nowprinting' not in img and 'dmm' not in img:
                best_score = score
                best = full
                if score == 0:
                    break

        if best:
            logger.debug('javBusSource', f'matched "{actor_name}" → {best}')
            return PhotoHit(url=best, gender='female')
        logger.debug('javBusSource', f'no usable image for "{actor_name}"')
        return None


jav_bus_source = _JavBusSource()
