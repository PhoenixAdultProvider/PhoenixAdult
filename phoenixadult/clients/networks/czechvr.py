from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date, sceneid_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Czech VR'
_DATE_FMT = '%b %d, %Y'
_BRAND_SUFFIXES = ['Czech VR Network', ' - Czech VR Fetish Porn Videos', 'Czech VR Fetish', 'Czech VR Casting', 'Czech VR']
_CDN_RE = re.compile(r'/cdn-cgi/image/[^/]*/')


def _strip_brand(title: str) -> str:
    out = title
    for suffix in _BRAND_SUFFIXES:
        out = out.replace(suffix, '')

    return out.strip()


__testing__ = {'strip_brand': _strip_brand}


class CzechVRClient(Client):
    search_url_xpath = '(.//a)[1]/@href'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url(quote(search_data.title.strip(), safe=''))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"postTag")]'))
        return LoadedSearch(
            ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture, extra={'scene_id': search_data.scene_id or ''}
        )

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"nazev")]//h2//a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//div[contains(@class,"datum")])[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw, _DATE_FMT) if raw else loaded.ctx.search_date

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        scene_id = (loaded.extra or {}).get('scene_id') or ''
        if not scene_id:
            return None

        cur = (source.xpath('(.//div[contains(@class,"nazev")]//h2//a)[1]').xpath('string(.)').get() or '').strip().split(' -')[0].strip()
        return sceneid_distance_score(scene_id, cur)

    async def fetch_search_thumb_url(self, source: Any, loaded: LoadedSearch) -> str | None:
        thumb = first_attr(source, '(.//img)[1]/@data-src')
        if not thumb:
            return None

        datasrc = _CDN_RE.sub('/cdn-cgi/image//', thumb)
        return absolute_url(datasrc, loaded.site.base_url)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//div[contains(@class,"nazev")]//h1)[1]').xpath('string(.)').get() or '').split('-')[-1].strip()
        if not raw:
            return

        metadata.title = _strip_brand(raw) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        text = (details_page_elements.xpath('(//div[@class="text"])[1]').xpath('string(.)').get() or '').strip()
        if text:
            metadata.summary = text
            return

        metadata.summary = (details_page_elements.xpath('(//div[@class="textDetail"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"nazev")]//div[contains(@class,"datum")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date, _DATE_FMT)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            (genre_link.xpath('string(.)').get() or '').lower()
            for genre_link in details_page_elements.xpath('//div[contains(@class,"tag") and contains(@class,"new")]//a | //div[@class="tag"]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"modelky")]//a'):
            entries.append(ActorResult(name=first_attr(actor_link)))

        for actor_link in details_page_elements.xpath('(//div[contains(@class,"nazev")])[1]//div[contains(@class,"featuring")]//a'):
            entries.append(ActorResult(name=first_attr(actor_link)))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        xpaths = (
            '//div[@class="foto"]//dl8-video/@poster',
            '//div[contains(@class,"galerka")]//a/@href',
            '//meta[@property="og:image"]/@content',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
