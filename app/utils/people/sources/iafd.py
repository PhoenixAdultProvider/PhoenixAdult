from __future__ import annotations

import re

from parsel import Selector

from app.utils.http.bypass import bypass_get
from app.utils.logging.logger import logger
from app.utils.people.sources._http import encode_name, fix_iafd_encoding, levenshtein
from app.utils.people.types import Gender, PersonLookupContext, PhotoHit

_BASE = 'http://www.iafd.com'


async def iafd_best_match(actor_name: str, studio: str = '') -> tuple[str, Gender] | None:
    """Run the IAFD comprehensive search; return (href, gender) for the closest
    performer match, or None.

    Uses the anti-bot bypass chain — IAFD sits behind Cloudflare, so a plain client
    gets a 403 "Just a moment" challenge and never sees the results table. Shared by
    gender detection (gender.py) and headshot lookup (_IafdSource). When `studio` is
    given, a row whose aliases mention that studio is forced to the best score.
    """
    try:
        enc = fix_iafd_encoding(encode_name(actor_name))
        search_url = f'{_BASE}/results.asp?searchtype=comprehensive&searchstring={enc}'
        logger.debug('iafd', f'GET {search_url}')
        resp = await bypass_get(search_url)
        if not resp or resp.status != 200:
            logger.debug('iafd', f'search failed for "{actor_name}": {resp.status if resp else "no response"}')
            return None
        sel = Selector(text=resp.body)

        rows = sel.xpath('//table[@id="tblFem"]/tbody/tr | //table[@id="tblMal"]/tbody/tr')
        males = set(sel.xpath('//table[@id="tblMal"]/tbody/tr/td[2]//a/@href').getall())

        want = actor_name.lower()
        studio_key = re.sub(r'\s+', '', studio or '').lower()
        best_score = float('inf')
        best_href = ''
        for tr in rows:
            link = tr.xpath('./td[2]//a[1]')
            name = (link.xpath('normalize-space(.)').get() or '').lower()
            if not name:
                continue
            alias_text = (tr.xpath('normalize-space(.//td[contains(@class,"text-left")])').get() or '').lower()
            score = float(levenshtein(want, name))
            if score != 0 and want in alias_text:
                score -= 1
            if studio_key and studio_key in re.sub(r'\s+', '', alias_text):
                score = 0
            if score < best_score:
                best_score = score
                best_href = link.xpath('./@href').get() or ''

        if not best_href:
            logger.debug('iafd', f'no row matched "{actor_name}" (bestScore={best_score})')
            return None
        gender: Gender = 'male' if best_href in males else 'female'
        return best_href, gender
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
            # No usable headshot, but the person was found — keep the gender so the
            # resolver can still fall back to the gendered silhouette.
            logger.debug('iafd', f'rejected placeholder image for "{actor_name}" (keeping gender={gender})')
            return PhotoHit(url='', gender=gender)
        logger.debug('iafd', f'matched "{actor_name}" → {img} (gender={gender})')
        return PhotoHit(url=img, gender=gender)


iafd_source = _IafdSource()
