from __future__ import annotations

import re

from parsel import Selector

from app.utils.logging.logger import logger
from app.utils.people.sources._http import encode_name, fix_iafd_encoding, levenshtein, make_source_http
from app.utils.people.types import Gender, PersonLookupContext, PhotoHit

_BASE = 'http://www.iafd.com'


class _IafdSource:
    name = 'IAFD'

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None:
        enc = fix_iafd_encoding(encode_name(actor_name))
        search_url = f'{_BASE}/results.asp?searchtype=comprehensive&searchstring={enc}'
        logger.debug('iafdSource', f'GET {search_url}')
        async with make_source_http() as client:
            sel = Selector(text=(await client.get(search_url)).text)

            rows = sel.xpath('//table[@id="tblFem"]/tbody/tr | //table[@id="tblMal"]/tbody/tr')
            males = set(sel.xpath('//table[@id="tblMal"]/tbody/tr/td[2]//a/@href').getall())

            want = actor_name.lower()
            studio = re.sub(r'\s+', '', ctx.studio or '').lower()

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
                if studio and studio in re.sub(r'\s+', '', alias_text):
                    score = 0
                if score < best_score:
                    best_score = score
                    best_href = link.xpath('./@href').get() or ''

            if not best_href:
                logger.debug('iafdSource', f'no row matched "{actor_name}" (bestScore={best_score})')
                return None

            actor_page = best_href if best_href.startswith('http') else f'{_BASE}{best_href}'
            logger.debug('iafdSource', f'candidate {best_href} (bestScore={best_score}); GET {actor_page}')
            page_sel = Selector(text=(await client.get(actor_page)).text)

        img = page_sel.xpath('(//div[@id="headshot"]//img/@src)[1]').get() or ''
        if not img or 'nophoto' in img or 'th_iafd_ad' in img:
            logger.debug('iafdSource', f'rejected placeholder image for "{actor_name}"')
            return None
        gender: Gender = 'male' if best_href in males else 'female'
        logger.debug('iafdSource', f'matched "{actor_name}" → {img} (gender={gender})')
        return PhotoHit(url=img, gender=gender)


iafd_source = _IafdSource()
