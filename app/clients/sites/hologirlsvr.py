from __future__ import annotations

from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_text


class HoloGirlsVRClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id
        rest = ctx.title.strip()

        if scene_id and not rest:
            scene_url = f'{base}/Scenes/Videos/{scene_id}'
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if not loaded:
                return []
            title = first_text(loaded['sel'], '//div[contains(@class,"video-title")]//h3')
            if not title:
                return []
            return [
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            ]

        search_url = base + ctx.site_info.search_path.replace('{query}', quote(rest or ctx.title))
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"memVid")]'):
            anchor = card.xpath('(.//div[contains(@class,"memVidTitle")]/a)[1]')
            title = (anchor.xpath('@title').get() or '').strip()
            href = (anchor.xpath('@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=rest or ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"video-title")]//h3') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        nodes = scene.sel.xpath('(//div[contains(@class,"vidpage-info")])[1]/text()').getall()
        if len(nodes) <= 4:
            return None
        return nodes[4].strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"videopage-tags")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries: list[ActorResult] = []
        for card in scene.sel.xpath('//div[contains(@class,"col-md-3")]'):
            name = first_text(card, './/div[contains(@class,"vidpage-mobilePad")]//a//strong')
            raw = (card.xpath('(.//img[contains(@class,"imgHover")]/@src)[1]').get() or '').strip()
            photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        push(scene.sel.xpath('(//div[contains(@class,"vidCover")]//img/@src)[1]').get() or '')
        for raw in scene.sel.xpath('//div[contains(@class,"vid-flex-container")]//span//img/@src').getall():
            push((raw or '').replace('_thumb', ''))
        return images
