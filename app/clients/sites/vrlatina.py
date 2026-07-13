from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, to_https
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content, web_search_urls


def _title_or_text(node: Any) -> str:
    return (node.xpath('@title').get() or node.xpath('normalize-space(.)').get() or '').strip()


class VRLatinaClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.replace(' ', '-').lower()
        if not slug:
            return
        direct_url = f'{base}{ctx.site_info.search_path}{slug}.html'

        seen = {direct_url}
        candidates = [direct_url]
        for raw in await web_search_urls(ctx.title, ctx.site_info):
            if '/video/' in raw and raw not in seen:
                seen.add(raw)
                candidates.append(raw)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = meta_content(loaded['sel'], 'og:title')
            if not title:
                continue
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, ctx.search_date or ''])
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h2') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//div[contains(@class,"content-desc")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"content-base-info")]//div[contains(@class,"info-elem") and contains(@class,"-length")]//span')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [_title_or_text(a) for a in scene.sel.xpath('//div[contains(@class,"content-links") and contains(@class,"-tags")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//div[contains(@class,"content-links") and contains(@class,"-models")]//a'):
            name = _title_or_text(a)
            href = first_attr(a, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    photo = first_attr(page['sel'], '(//div[contains(@class,"model-avatar")]//img/@src)[1]')
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: to_https((raw or '').strip()))
        for href in scene.sel.xpath('//a[contains(@class,"video-gallery-item")]/@href').getall():
            coll['push'](href)
        coll['push'](scene.sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')
        metadata.art = coll['list']
