from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date, sceneid_distance_score
from app.utils.helpers.html_helpers import first_attr, first_string

STUDIO = 'CzechVR'
_DATE_FMT = '%b %d, %Y'
# Order matters — strip the most specific suffixes first.
_BRAND_SUFFIXES = ['Czech VR Network', ' - Czech VR Fetish Porn Videos', 'Czech VR Fetish', 'Czech VR Casting', 'Czech VR']
_CDN_RE = re.compile(r'/cdn-cgi/image/[^/]*/')


def _strip_brand(title: str) -> str:
    out = title
    for suffix in _BRAND_SUFFIXES:
        out = out.replace(suffix, '')
    return out.strip()


__testing__ = {'strip_brand': _strip_brand}


class CzechVRClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title.strip(), safe=''))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//div[contains(@class,"postTag")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture, extra={'scene_id': ctx.scene_id or ''})

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//div[contains(@class,"nazev")]//h2//a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

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

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"nazev")]//h1)[1]').xpath('string(.)').get() or '').split('-')[-1].strip()
        if not raw:
            return None
        return _strip_brand(raw) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        text = (scene.sel.xpath('(//div[@class="text"])[1]').xpath('string(.)').get() or '').strip()
        if text:
            return text
        return (scene.sel.xpath('(//div[@class="textDetail"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"nazev")]//div[contains(@class,"datum")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw, _DATE_FMT)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            (el.xpath('string(.)').get() or '').lower()
            for el in scene.sel.xpath('//div[contains(@class,"tag") and contains(@class,"new")]//a | //div[@class="tag"]//a')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries: list[ActorResult] = []
        for el in scene.sel.xpath('//div[contains(@class,"modelky")]//a'):
            entries.append(ActorResult(name=first_string(el)))
        for el in scene.sel.xpath('(//div[contains(@class,"nazev")])[1]//div[contains(@class,"featuring")]//a'):
            entries.append(ActorResult(name=first_string(el)))
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw, base))
        xpaths = (
            '//div[@class="foto"]//dl8-video/@poster',
            '//div[contains(@class,"galerka")]//a/@href',
            '//meta[@property="og:image"]/@content',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
