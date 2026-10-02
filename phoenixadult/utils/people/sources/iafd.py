from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.utils.http.bypass import bypass_get
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.people.sources._http import encode_name, fix_iafd_encoding, levenshtein
from phoenixadult.utils.people.types import Gender, PersonLookupContext, PhotoHit

_BASE = 'https://www.iafd.com'


def _row_score(tr: Selector, name: str, want: str, studio_key: str) -> float:
    alias_text = (tr.xpath('normalize-space(.//td[contains(@class,"text-left")])').get() or '').lower()
    if studio_key and studio_key in re.sub(r'\s+', '', alias_text):
        return 0
    score = float(levenshtein(want, name))
    return score - 1 if score != 0 and want in alias_text else score


def _best_href(sel: Selector, actor_name: str, studio: str) -> tuple[str, float]:
    want = actor_name.lower()
    studio_key = re.sub(r'\s+', '', studio or '').lower()
    best_score = float('inf')
    best_href = ''
    for tr in sel.xpath('//table[@id="tblFem"]/tbody/tr | //table[@id="tblMal"]/tbody/tr'):
        link = tr.xpath('./td[2]//a[1]')
        name = (link.xpath('normalize-space(.)').get() or '').lower()
        score = _row_score(tr, name, want, studio_key) if name else best_score
        if score < best_score:
            best_score, best_href = score, link.xpath('./@href').get() or ''
    return best_href, best_score


async def iafd_best_match(actor_name: str, studio: str = '') -> tuple[str, Gender] | None:
    try:
        enc = fix_iafd_encoding(encode_name(actor_name))
        search_url = f'{_BASE}/results.asp?searchtype=comprehensive&searchstring={enc}'
        logger.debug('iafd', f'GET {search_url}')
        resp = await bypass_get(search_url)
        if not resp or resp.status != 200:
            logger.debug('iafd', f'search failed for "{actor_name}": {resp.status if resp else "no response"}')
            return None
        sel = Selector(text=resp.body)
        best_href, best_score = _best_href(sel, actor_name, studio)
        if not best_href:
            logger.debug('iafd', f'no row matched "{actor_name}" (bestScore={best_score})')
            return None
        males = set(sel.xpath('//table[@id="tblMal"]/tbody/tr/td[2]//a/@href').getall())
        return best_href, 'male' if best_href in males else 'female'
    except Exception as err:  # noqa: BLE001 - any failure → no match
        logger.debug('iafd', f'IAFD search failed for "{actor_name}": {err}')
        return None


class _IafdSource:
    name = 'IAFD'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        match = await iafd_best_match(actor_name, ctx.studio or '')
        if not match:
            return None
        best_href, gender = match

        actor_page = best_href if best_href.startswith('http') else f'{_BASE}{best_href}'
        logger.debug('iafd', f'candidate {best_href} (gender={gender}); GET {actor_page}')
        resp = await bypass_get(actor_page)
        if not resp or resp.status != 200:
            logger.debug('iafd', f'actor-page fetch failed for "{actor_name}": {resp.status if resp else "no response"}')
            return None

        img = Selector(text=resp.body).xpath('(//div[@id="headshot"]//img/@src)[1]').get() or ''
        if not img or 'nophoto' in img or 'th_iafd_ad' in img:
            logger.debug('iafd', f'rejected placeholder image for "{actor_name}" (keeping gender={gender})')
            return PhotoHit(url='', gender=gender)
        logger.debug('iafd', f'matched "{actor_name}" → {img} (gender={gender})')
        return PhotoHit(url=img, gender=gender)


iafd_source = _IafdSource()
