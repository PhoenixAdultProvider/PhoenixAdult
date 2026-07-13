from __future__ import annotations

from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, append_unique, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class HoloGirlsVRClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id
        rest = ctx.title.strip()

        if scene_id and not rest:
            scene_url = f'{base}/Scenes/Videos/{scene_id}'
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if not loaded:
                return
            title = first_text(loaded['sel'], '//div[contains(@class,"video-title")]//h3')
            if not title:
                return
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )
            return

        search_url = base + ctx.site_info.search_path.replace('{query}', quote(rest or ctx.title))
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"memVid")]'):
            anchor = card.xpath('(.//div[contains(@class,"memVidTitle")]/a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=rest or ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, '//div[contains(@class,"video-title")]//h3') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        nodes = sel.xpath('(//div[contains(@class,"vidpage-info")])[1]/text()').getall()
        if len(nodes) <= 4:
            return
        metadata.summary = nodes[4].strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in sel.xpath('//div[contains(@class,"videopage-tags")]//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        entries: list[ActorResult] = []
        for card in sel.xpath('//div[contains(@class,"col-md-3")]'):
            name = first_text(card, './/div[contains(@class,"vidpage-mobilePad")]//a//strong')
            raw = first_attr(card, '(.//img[contains(@class,"imgHover")]/@src)[1]')
            photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw, scene.site.base_url)

        push(sel.xpath('(//div[contains(@class,"vidCover")]//img/@src)[1]').get() or '')
        for raw in sel.xpath('//div[contains(@class,"vid-flex-container")]//span//img/@src').getall():
            push((raw or '').replace('_thumb', ''))
        metadata.art = images
