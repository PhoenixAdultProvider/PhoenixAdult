from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, slugify
from app.utils.helpers.html_helpers import web_search_urls

STUDIO = 'Thick Cash'


class ThickCashOtherClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        async def add_scene(scene_url: str) -> None:
            if scene_url in seen:
                return
            seen.add(scene_url)
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not page:
                return
            title = (page['sel'].xpath('(//h3[contains(@class,"top-title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])))

        await add_scene(f'{base}/videos/{slugify(ctx.title)}.html')

        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/videos/']):
            await add_scene(u)

        words = ctx.title.strip().split()
        model_id = '-'.join(words[:2])
        if model_id:
            model_page = await self.fetch_and_load(f'{base}/models/{model_id}.html', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model {model_id}')
            if model_page:
                for href in model_page['sel'].xpath('//div[contains(@class,"model-grid")]//a/@href').getall():
                    href = href.strip()
                    if href:
                        await add_scene(href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url))
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h3[contains(@class,"top-title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"player-box")]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [
            ActorResult(name=(a.xpath('normalize-space(.)').get() or '').strip())
            for a in scene.sel.xpath('//a[contains(@class,"tag") and contains(@href,"models")]')
        ]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector()
        for raw in scene.sel.xpath('//video/@poster').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
