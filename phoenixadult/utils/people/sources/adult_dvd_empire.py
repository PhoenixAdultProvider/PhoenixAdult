from __future__ import annotations

from typing import Literal

import httpx2
from parsel import Selector

from phoenixadult.config.env import env
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import encode_name, levenshtein, make_source_http
from phoenixadult.utils.people.types import PersonLookupContext, PhotoHit


def _cookie_header() -> str:
    tok = env.adult_empire_login_token
    return f'ageConfirmed=true; etoken={tok}' if tok else 'ageConfirmed=true'


async def _fetch_performer_page(client: httpx2.AsyncClient, gender_flag: Literal['F', 'M', 'T'], enc: str) -> Selector:
    base = 'https://www.adultdvdempire.com/hottest-pornstars.html' if gender_flag == 'M' else 'https://www.adultdvdempire.com/performer/search'
    url = f'{base}?fq=ag_cast_gender%3A{gender_flag}&fq={enc}'
    resp = await client.get(url, headers={'Cookie': _cookie_header()})
    return Selector(text=resp.text)


class _AdultDvdEmpireSource:
    name = 'AdultDVDEmpire'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        logger.debug('adultDvdEmpireSource', f'find name="{actor_name}"')
        enc = encode_name(actor_name)
        async with make_source_http() as client:
            sel_f = await _fetch_performer_page(client, 'F', enc)
            sel_t = await _fetch_performer_page(client, 'T', enc)
            sel_m = await _fetch_performer_page(client, 'M', enc)

        candidates: list[tuple[Selector, Literal['female', 'male']]] = []
        for row in sel_f.xpath('//div[@id="performerlist"]/div'):
            candidates.append((row, 'female'))
        for row in sel_t.xpath('//div[@id="performerlist"]/div'):
            candidates.append((row, 'female'))
        for row in sel_m.xpath('//div[@id="performerlist"]/div'):
            candidates.append((row, 'male'))

        best_score = float('inf')
        best: tuple[Selector, Literal['female', 'male']] | None = None
        for row, gender in candidates:
            name = (row.xpath('normalize-space(.)').get() or '').strip()
            first_img = row.xpath('(.//a//img/@src)[1]').get() or ''
            score = float(levenshtein(actor_name, name))
            if 'nophoto' in first_img:
                score += 1
            if score < best_score:
                best_score = score
                best = (row, gender)

        if not best:
            logger.debug('adultDvdEmpireSource', f'no candidates matched "{actor_name}"')
            return None

        img_link = best[0].xpath('(.//a//img/@src)[1]').get() or ''
        img_id = img_link.split('actor/')[-1].split('_')[0].split('/')[-1]
        if not img_id or img_id in ('nophoto', 'boxcover'):
            logger.debug('adultDvdEmpireSource', f'rejected placeholder image for "{actor_name}"')
            return None
        logger.debug('adultDvdEmpireSource', f'matched "{actor_name}" → {img_id} (gender={best[1]})')
        return PhotoHit(url=f'https://imgs1cdn.adultempire.com/actors/{img_id}h.jpg', gender=best[1])


adult_dvd_empire_source = _AdultDvdEmpireSource()
