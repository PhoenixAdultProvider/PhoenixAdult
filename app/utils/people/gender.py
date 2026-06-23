from __future__ import annotations

from parsel import Selector

from app.config.env import env
from app.utils.http.bypass import bypass_get
from app.utils.logging.logger import logger
from app.utils.people.sources._http import encode_name, fix_iafd_encoding, levenshtein
from app.utils.people.types import Gender


def gender_detect_enabled() -> bool:
    return env.gender_detect_enabled


async def iafd_gender_check(actor_name: str) -> Gender:
    try:
        enc = fix_iafd_encoding(encode_name(actor_name))
        url = f'http://www.iafd.com/results.asp?searchtype=comprehensive&searchstring={enc}'
        resp = await bypass_get(url)
        if not resp or resp.status != 200:
            raise ValueError(f'bypassGet: unable to resolve "{resp}"')
        sel = Selector(text=resp.body)

        rows = sel.xpath('//table[@id="tblFem"]/tbody/tr | //table[@id="tblMal"]/tbody/tr')
        males = {h for h in sel.xpath('//table[@id="tblMal"]/tbody/tr/td[2]//a/@href').getall()}

        want = actor_name.lower()
        best_score = float('inf')
        best_href = ''
        for tr in rows:
            link = tr.xpath('./td[2]//a[1]')
            name = (link.xpath('normalize-space(.)').get() or '').lower()
            if not name:
                continue
            score = float(levenshtein(want, name))
            alias_text = (tr.xpath('normalize-space(.//td[contains(@class,"text-left")])').get() or '').lower()
            if score != 0 and want in alias_text:
                score -= 1
            if score < best_score:
                best_score = score
                best_href = link.xpath('./@href').get() or ''
        if not best_href:
            return ''
        return 'male' if best_href in males else 'female'
    except Exception as err:  # noqa: BLE001 - any failure → unknown gender
        logger.debug('gender', f'IAFD check failed for "{actor_name}": {err}')
        return ''
