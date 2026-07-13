from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'WowNetwork'
_SEARCH_PAGES = 5


class WowNetworkClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.encoded

        async def fetch_rows(page: int) -> list[Any] | None:
            page_url = f'{base}/?s={slug}' if page == 1 else f'{base}/page/{page}/?s={slug}'
            loaded = await self.fetch_and_load(page_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search p{page} {page_url}')
            return list(loaded['sel'].xpath('//article[contains(@class,"thumb-block")]')) if loaded else None

        def build_row(el: Any) -> SearchResult | None:
            anchor = el.xpath('(.//a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href:
                return None
            scene_url = absolute_url(href, ctx.site_info.base_url)
            image = first_attr(el, '(.//img)[1]/@src')
            image_packed = self.encode(image) if image else ''
            return build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                cur_id=pack_cur_id([scene_url, f'{ctx.search_date or ""}|{image_packed}']),
            )

        results.extend(await self.paginate_search(fetch_rows=fetch_rows, build_row=build_row, max_pages=_SEARCH_PAGES, stop_on_empty_page=True))

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1[contains(@class,"entry-title")])[last()]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[@id="video-date"])[1]').xpath('string(.)').get() or '').replace('Date:', '').strip()
        if raw:
            metadata.release_date = iso_date(raw)
            return
        meta = first_attr(scene.sel, '(//meta[@property="article:published_time"])[1]/@content')
        if meta:
            metadata.release_date = iso_date(meta.split('T')[0])
            return
        packed_date = scene.scene_date.split('|')[0].strip() if scene.scene_date else ''
        metadata.release_date = iso_date(packed_date) if packed_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = self.dedup_strings(
            [
                (el.xpath('string(.)').get() or '').replace('Movies', '').strip()
                for el in scene.sel.xpath('//div[contains(@class,"tags-list")]//a[.//i[contains(@class,"fa-folder-open")]]')
            ]
        )
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in scene.sel.xpath('//div[@id="video-actors"]//a')]
        metadata.actors = self.dedup_people(entries) or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()
        if scene.scene_date and '|' in scene.scene_date:
            b64 = scene.scene_date.split('|', 1)[1]
            if b64:
                try:
                    coll['push'](self.decode(b64))
                except (ValueError, TypeError):
                    pass
        coll['push'](first_attr(scene.sel, '(//meta[@property="og:image"])[1]/@content'))
        images: list[str] = coll['list']
        metadata.art = images or []
