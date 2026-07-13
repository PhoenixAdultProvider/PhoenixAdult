from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, append_unique, build_search_result, iso_date, pack_cur_id, to_https
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content
from app.utils.logging.logger import logger

STUDIO = 'VRAllure'
_TITLE_XP = '//h1[contains(@class,"latest-scene-title")]'
_DATE_XP = '//p[contains(@class,"publish-date")]'
_ACTOR_LINK_XP = '//p[contains(@class,"model-name")]//a[contains(@href,"/models/")]'
_ACTOR_PHOTO_XP = '//img[@id="model-thumbnail"]/@src'


class VRAllureClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.replace(' ', '_')
        if not slug:
            return
        search_url = f'{base}{ctx.site_info.search_path}{slug}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {search_url}')
        if not loaded:
            return
        title = first_text(loaded['sel'], _TITLE_XP)
        if not title:
            return
        canonical = first_attr(loaded['sel'], '(//link[@rel="canonical"]/@href)[1]')
        scene_url = canonical or search_url
        date_raw = first_text(loaded['sel'], _DATE_XP)
        date = iso_date(date_raw) if date_raw else None
        logger.info(ctx.site_info.name, f'VRAllure direct hit "{title}" ({scene_url})')
        results.append(
            build_search_result(
                title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, date or ''])
            )
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = first_text(sel, '//p[contains(@class,"desc")]//span') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = first_text(sel, _DATE_XP)
        if raw:
            parsed = iso_date(raw)
            if parsed:
                metadata.release_date = parsed
                return
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in sel.xpath('//a[contains(@class,"label") and contains(@class,"label-tag")]')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in sel.xpath(_ACTOR_LINK_XP):
            name = first_attr(a, 'normalize-space(.)')
            href = first_attr(a, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    photo = to_https((page['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip())
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw)

        push(to_https(meta_content(sel, 'og:image')))
        for href in sel.xpath(f'{_ACTOR_LINK_XP}/@href').getall():
            href = (href or '').strip()
            if not href:
                continue
            url = absolute_url(href, base)
            page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-art {url}')
            if page:
                push(to_https((page['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip()))
        metadata.art = images
