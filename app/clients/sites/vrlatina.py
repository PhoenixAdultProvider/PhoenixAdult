from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text, web_search_urls


def _with_http(raw: str) -> str:
    if not raw:
        return ''
    if raw.startswith('http'):
        return raw
    if raw.startswith('//'):
        return f'http:{raw}'
    return raw


def _title_or_text(node: Any) -> str:
    return (node.xpath('@title').get() or node.xpath('normalize-space(.)').get() or '').strip()


class VRLatinaClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.replace(' ', '-').lower()
        if not slug:
            return []
        direct_url = f'{base}{ctx.site_info.search_path}{slug}.html'

        seen = {direct_url}
        candidates = [direct_url]
        for raw in await web_search_urls(ctx.title, ctx.site_info):
            if '/video/' in raw and raw not in seen:
                seen.add(raw)
                candidates.append(raw)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = (loaded['sel'].xpath('(//meta[@property="og:title"]/@content)[1]').get() or '').strip()
            if not title:
                continue
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, ctx.search_date or ''])
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h2') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"content-desc")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"content-base-info")]//div[contains(@class,"info-elem") and contains(@class,"-length")]//span')
        if raw:
            parsed = iso_date(raw, '%b %d, %Y') or iso_date(raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [_title_or_text(a) for a in scene.sel.xpath('//div[contains(@class,"content-links") and contains(@class,"-tags")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//div[contains(@class,"content-links") and contains(@class,"-models")]//a'):
            name = _title_or_text(a)
            href = (a.xpath('@href').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = href if href.startswith('http') else absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    photo = (page['sel'].xpath('(//div[contains(@class,"model-avatar")]//img/@src)[1]').get() or '').strip()
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            url = _with_http((raw or '').strip())
            if url and url not in images:
                images.append(url)

        for href in scene.sel.xpath('//a[contains(@class,"video-gallery-item")]/@href').getall():
            push(href)
        push(scene.sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')
        return images
