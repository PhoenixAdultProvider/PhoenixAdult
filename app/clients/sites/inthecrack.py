from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_DIGITS_RE = re.compile(r'\d')


class InTheCrackClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        parts = ctx.title.strip().split()
        scene_id = parts[0] if parts and parts[0].isdigit() else ''
        model = (parts[1] if scene_id and len(parts) > 1 else ctx.title.strip()).lower()
        if not model:
            return

        index = await self.fetch_and_load(
            f'{base}/Collections/Name/{model[0]}', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model index {model[0]}'
        )
        if not index:
            return
        model_link = ''
        for li in index['sel'].xpath('//ul[contains(@class,"collectionGridLayout")]/li'):
            name = first_text(li, './/span').lower()
            if model in name:
                model_link = first_attr(li, '(.//a/@href)[1]')
                break
        if not model_link:
            return

        model_page = await self.fetch_and_load(
            absolute_url(model_link, ctx.site_info.base_url), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model page'
        )
        if not model_page:
            return

        for li in model_page['sel'].xpath('//ul[contains(@class,"Models")]/li'):
            title = first_text(li, './/figure/p[1]').replace('Collection:', '').strip()
            href = first_attr(li, '(.//a/@href)[1]')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            date = iso_date(first_text(li, './/figure/p[2]').replace('Release Date:', '').strip())
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=scene_id or model,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, '//h2//span') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '//p[@id="CollectionDescription"]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'InTheCrack'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Solo']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        page_title = first_text(scene.sel, '//title')
        if '#' not in page_title:
            return
        after_hash = page_title.split('#')[1]
        cleaned = _DIGITS_RE.sub('', after_hash).replace(',', '&')
        names = [n.strip() for n in cleaned.split('&') if n.strip()]
        metadata.actors = self.dedup_people([ActorResult(name=name) for name in names])

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        style_text = first_text(scene.sel, '//style')
        parts = style_text.split("'")
        if len(parts) < 2:
            return
        rel = parts[1].strip()
        if not rel:
            return
        metadata.raw_image_urls = [absolute_url(rel, scene.site.base_url)]
