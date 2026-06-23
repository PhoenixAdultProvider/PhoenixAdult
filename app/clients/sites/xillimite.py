from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_text

_BR_RE = re.compile(r'</?br\s*/?>', re.IGNORECASE)


def _join(base: str, path: str) -> str:
    if path.startswith('http'):
        return path
    return f'{base}{path}' if path.startswith('/') else f'{base}/{path}'


class XillimiteClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return None
        sources = list(loaded['sel'].xpath('//a[contains(@class,"movies")]'))
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=sources, capture=ctx.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//img/@alt)[1]').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = (source.xpath('@href').get() or '').strip()
        if not href:
            return ''
        return href if href.startswith('http') else absolute_url(href, loaded.site.base_url)

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        nodes = scene.sel.xpath('//div[@id="synopsis"]/node()').getall()
        raw_html = ''.join(nodes) if nodes else (scene.sel.xpath('(//meta[@name="twitter:description"]/@content)[1]').get() or '')
        if not raw_html:
            return None
        with_newlines = _BR_RE.sub('\n', raw_html)
        stripped = (Selector(text=f'<div>{with_newlines}</div>').xpath('string(.)').get() or '').strip()
        return stripped or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        if not scene.scene_date:
            return None
        return iso_date(scene.scene_date) or scene.scene_date

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        entries: list[ActorResult] = []
        for img in scene.sel.xpath('//div[contains(@class,"casting")]//div[contains(@class,"slider-xl")]//a[contains(@class,"movies")]//img'):
            name = (img.xpath('@alt').get() or '').strip()
            data_src = (img.xpath('@data-src').get() or '').strip()
            photo = _join(base, data_src) if data_src else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = _join(base, raw.replace('blur9/', '/'))
            if abs_url not in images:
                images.append(abs_url)

        for href in scene.sel.xpath('//div[contains(@class,"covers")]//a[contains(@class,"cover")]/@href').getall():
            push(href)
        for href in scene.sel.xpath('//div[contains(@class,"screenshots")]//div[contains(@class,"slides")]//a/@href').getall():
            push(href)
        return images
