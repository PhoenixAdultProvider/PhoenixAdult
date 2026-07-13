from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content

UMBRELLA_STUDIO = 'Dorcel Vision'
_YEAR_RE = re.compile(r'\d{4}')
_STUDIO_OVERRIDE_XP = '//div[contains(@class,"entries")]//strong[contains(.,"Studio")]/following-sibling::a[1]'


def _page_studio_override(scene: LoadedScene) -> str:
    assert scene.sel is not None
    return first_text(scene.sel, _STUDIO_OVERRIDE_XP)


class DorcelVisionClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return
        for el in loaded['sel'].xpath('//a[contains(@class,"movies")]'):
            title = first_attr(el, '(.//img/@alt)[1]')
            href = first_attr(el, '@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        meta = meta_content(scene.sel, 'twitter:description')
        metadata.summary = meta or first_text(scene.sel, '//div[@id="summaryList"]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _page_studio_override(scene) or UMBRELLA_STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = _page_studio_override(scene) or UMBRELLA_STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        override = _page_studio_override(scene)
        metadata.collections = [UMBRELLA_STUDIO, override] if override else [UMBRELLA_STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        year_entries = scene.sel.xpath('//div[contains(@class,"entries")]//strong[contains(.,"Production year")]')
        if not year_entries:
            return
        text = ''.join(year_entries[0].xpath('following-sibling::text()').getall())
        m = _YEAR_RE.search(text)
        metadata.release_date = f'{m.group(0)}-01-01' if m else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for card in scene.sel.xpath('//div[contains(@class,"casting")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]'):
            name = first_text(card, './/a/strong')
            if not name or name in seen:
                continue
            seen.add(name)
            photo_raw = first_attr(card, '(.//img/@data-src)[1]')
            photo = absolute_url(photo_raw, scene.site.base_url) if photo_raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def add(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            stripped = raw.replace('blur9/', '')
            abs_url = absolute_url(stripped, base)
            if abs_url not in images:
                images.append(abs_url)

        for href in scene.sel.xpath('//div[contains(@class,"covers")]//a[contains(@class,"cover")]/@href').getall():
            add(href)
        for href in scene.sel.xpath(
            '//div[contains(@class,"screenshots")]//div[contains(@class,"slider-xl")]//div[contains(@class,"col-xs-2")]//a/@href'
        ).getall():
            add(href)
        metadata.raw_image_urls = images
