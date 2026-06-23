from __future__ import annotations

import httpx2
from parsel import Selector

from app.utils.logging.logger import logger

_JAVBUS_BASE = 'https://www.javbus.com'
_JAVBUS_COOKIE = 'existmag=all; dv=1'


async def _get(http: httpx2.AsyncClient, url: str) -> str | None:
    try:
        r = await http.get(url, headers={'Cookie': _JAVBUS_COOKIE})
        return None if r.status_code >= 400 else r.text
    except httpx2.HTTPError as err:
        logger.debug(f'javbusImages GET {url}: {err}')
        return None


async def fetch_javbus_images(http: httpx2.AsyncClient, jav_id: str, date_iso: str | None = None) -> list[str]:
    html = await _get(http, f'{_JAVBUS_BASE}/en/{jav_id}')
    # A 404 page may be a date-suffixed JAVID — retry once.
    if (html is None or '404 Page' in html) and date_iso:
        retry = await _get(http, f'{_JAVBUS_BASE}/en/{jav_id}_{date_iso}')
        if retry is not None:
            html = retry
    if html is None or '404 Page' in html:
        return []

    sel = Selector(text=html)
    images: list[str] = []

    def push(raw: str) -> None:
        if not raw:
            return
        abs_url = raw if raw.startswith('http') else _JAVBUS_BASE + raw
        if 'nowprinting' in abs_url or abs_url in images:
            return
        images.append(abs_url)

    for href in sel.xpath('//a[contains(@href,"/cover/")]/@href').getall():
        push(href)
    for href in sel.xpath('//a[contains(@class,"sample-box")]/@href').getall():
        push(href)

    # Derive a /thumb/<code>.jpg cover from the first cover/sample image.
    cover_raw = sel.xpath('//a[contains(@href,"/cover/")]/@href').get() or sel.xpath('//img[contains(@src,"/sample/")]/@src').get() or ''
    if cover_raw:
        code = cover_raw.split('/')[-1].split('.')[0].split('_')[0]
        host = '/'.join(cover_raw.split('/')[:-2])
        if code and host:
            cover = f'{host}/thumb/{code}.jpg'
            if cover.count('/images.') == 1:
                cover = cover.replace('thumb', 'thumbs')
            push(cover)
    return images
