from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, meta_content

_FULLSTORY_ONLY = {'Freeze', 'Plants vs Cunts'}
_LOOSE_ACTOR = {'Defeated Sex Fight'}


def _clean_poster(url: str) -> str:
    out = url
    q = parse_qs(urlparse(url).query)
    if q.get('src'):
        out = q['src'][0]

    return out.replace('-scaled', '')


def _clean_detail_title(raw: str) -> str:
    return raw.split('|')[0].split('- Free Video')[0].strip()


class RomeroClient(Client):
    search_url_xpath = '(.//a)[1]/@href'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"half")] | //article[contains(@class,"post")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h2)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        h2s = source.xpath('.//h2')
        raw = first_attr(h2s[1]).split('&nbsp')[-1].strip() if len(h2s) > 1 else ''
        if not raw:
            raw = (source.xpath('(.//div[@class="entry-date"])[1]').xpath('string(.)').get() or '').strip()

        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_attr(details_page_elements, '(//meta[@itemprop="name"]/@content | //h1/text())[1]')

        metadata.title = _clean_detail_title(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if scene.site.name in _FULLSTORY_ONLY:
            paras = details_page_elements.xpath('//div[@id="fullstory"]/p')
        else:
            paras = details_page_elements.xpath(
                '//div[@class="cont"]/p | //div[@class="cont"]//div[@id="fullstory"]/p | //div[@class="zapdesc"]//div[not(contains(.,"Including"))][.//br]'
            )

        parts: list[str] = []
        for row in paras:
            text = first_attr(row)
            if text and text != '\xa0':
                parts.append(text)

        metadata.summary = '\n'.join(parts).strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = meta_content(details_page_elements, 'article:published_time', 'property').split('T')[0].strip()
        if date:
            metadata.release_date = iso_date(date, '%Y-%m-%d') or iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            t
            for t in details_page_elements.xpath(
                '//div[@class="Cats"]//a/text() | //div[@class="zapdesc"]/div/div/div[contains(.,"Including:")]/text()'
            ).getall()
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if scene.site.name in _LOOSE_ACTOR:
            links = details_page_elements.xpath('//div[contains(@class,"tagsmodels")]//a')
        else:
            links = details_page_elements.xpath('//div[contains(@class,"tagsmodels")][./img[@alt="model icon"]]//a')

        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in links]

        metadata.actors = self.dedup_people(entries)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=first_attr(director_link, 'normalize-space(.)'))
            for director_link in details_page_elements.xpath('//div[contains(@class,"director")]//a')
        ]

        metadata.directors = self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(_clean_poster)
        for row in details_page_elements.xpath('//img'):
            cls = row.xpath('@class').get() or ''
            if 'wp-image-4512' in cls or 'wp-image-492' in cls:
                continue

            if ('alignnone' in cls and 'size-full' in cls) or 'size-medium' in cls:
                images.push(row.xpath('@src').get() or '')

        xpaths = (
            '//div[@class="iehand"]/a/@href',
            '//a[contains(@class,"colorbox-cats")]/@href',
            '//div[@class="gallery"]//a/@href',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
