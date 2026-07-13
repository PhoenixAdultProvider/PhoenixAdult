from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, web_search_urls

_STUDIO_CLASS = '_euacs6n160'
_SUMMARY_CLASS = '_s1jg1wcd75'
_DATE_CLASS = '_38471wcd31'
_GENRE_CLASS = '_1xdu1wcd88'
_ACTOR_CLASS = '_n7wm1ua719'
_ACTOR_AVATAR_CLASS = '_z763mqyu24 avatar avatar-size-32 outlined'
_COVER_CLASS = '_30hk1wta22'
_STUDIO_XP = f'//a[contains(@class,"{_STUDIO_CLASS}")]'


class SexLikeRealClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = '-'.join(ctx.title.strip().lower().split())
        direct_url = base + ctx.site_info.search_path.replace('{query}', slug)

        seen = {direct_url}
        candidates = [direct_url]
        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/scenes/']):
            if u not in seen:
                seen.add(u)
                candidates.append(u)

        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title = first_text(loaded['sel'], '//h1')
            if not title:
                continue
            raw = first_attr(loaded['sel'], '(//time/@datetime)[1]')
            date = iso_date(raw) if raw else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=100 if scene_url == direct_url else None,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = first_text(sel, '//h1')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        parts: list[str] = []
        for p in sel.xpath(f'//p[contains(@class,"{_SUMMARY_CLASS}")]'):
            t = first_attr(p, 'normalize-space(.)')
            if t and 'Video specifications' not in t:
                parts.append(t)
        metadata.summary = '\n'.join(parts)

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.studio = first_text(sel, _STUDIO_XP)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        studio = first_text(sel, _STUDIO_XP)
        metadata.collections = [studio] if studio else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = (sel.xpath(f'(//p[contains(@class,"{_DATE_CLASS}")]//time/@datetime)[1]').get() or '').strip()
        metadata.release_date = iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [s.xpath('normalize-space(.)').get() for s in sel.xpath(f'//a[contains(@class,"{_GENRE_CLASS}")]//span')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in sel.xpath(f'//a[contains(@class,"{_ACTOR_CLASS}")]'):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            src = (actor_page['sel'].xpath(f'(//div[contains(@class,"{_ACTOR_AVATAR_CLASS}")]//img/@src)[1]').get() or '').strip() if actor_page else ''
            photo = (absolute_url(src, scene.site.base_url)) if src else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: (raw or '').strip().replace('.webp', '.jpg'))
        coll['push'](sel.xpath('(//meta[@property="og:image"]/@content)[1]').get() or '')
        for raw in sel.xpath(f'//img[contains(@class,"{_COVER_CLASS}")]/@src').getall():
            coll['push'](raw)
        metadata.art = coll['list']
