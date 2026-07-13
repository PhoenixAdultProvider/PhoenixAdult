from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Romero Multimedia'
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
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"half")] | //article[contains(@class,"post")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h2)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        h2s = source.xpath('.//h2')
        raw = first_attr(h2s[1]).split('&nbsp')[-1].strip() if len(h2s) > 1 else ''
        if not raw:
            raw = (source.xpath('(.//div[@class="entry-date"])[1]').xpath('string(.)').get() or '').strip()
        return (iso_date(raw) if raw else None) or loaded.ctx.search_date

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//meta[@itemprop="name"]/@content | //h1/text())[1]')
        metadata.title = _clean_detail_title(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        if scene.site.name in _FULLSTORY_ONLY:
            paras = scene.sel.xpath('//div[@id="fullstory"]/p')
        else:
            paras = scene.sel.xpath(
                '//div[@class="cont"]/p | //div[@class="cont"]//div[@id="fullstory"]/p | //div[@class="zapdesc"]//div[not(contains(.,"Including"))][.//br]'
            )
        parts: list[str] = []
        for el in paras:
            text = first_attr(el)
            if text and text != '\xa0':
                parts.append(text)
        metadata.summary = '\n'.join(parts).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//meta[@property="article:published_time"]/@content)[1]').get() or '').split('T')[0].strip()
        if raw:
            metadata.release_date = iso_date(raw, '%Y-%m-%d') or iso_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [
            t for t in scene.sel.xpath('//div[@class="Cats"]//a/text() | //div[@class="zapdesc"]/div/div/div[contains(.,"Including:")]/text()').getall()
        ]
        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        if scene.site.name in _LOOSE_ACTOR:
            links = scene.sel.xpath('//div[contains(@class,"tagsmodels")]//a')
        else:
            links = scene.sel.xpath('//div[contains(@class,"tagsmodels")][./img[@alt="model icon"]]//a')
        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in links]
        metadata.actors = self.dedup_people(entries) or []

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in scene.sel.xpath('//div[contains(@class,"director")]//a')]
        metadata.directors = self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(_clean_poster)
        for el in scene.sel.xpath('//img'):
            cls = el.xpath('@class').get() or ''
            if 'wp-image-4512' in cls or 'wp-image-492' in cls:
                continue
            if ('alignnone' in cls and 'size-full' in cls) or 'size-medium' in cls:
                coll['push'](el.xpath('@src').get() or '')
        xpaths = (
            '//div[@class="iehand"]/a/@href',
            '//a[contains(@class,"colorbox-cats")]/@href',
            '//div[@class="gallery"]//a/@href',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.raw_image_urls = images or []
