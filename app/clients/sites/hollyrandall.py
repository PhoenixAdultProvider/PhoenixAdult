from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, b64url_decode, b64url_encode, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

_PAYWALL_HOST = 'join.hollyrandall.com'


class HollyRandallClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"item-video")]'):
            anchor = card.xpath('(.//div[contains(@class,"item-thumb")]/a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href or _PAYWALL_HOST in href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            raw_date = card.xpath('normalize-space((.//div[contains(@class,"timeDate")])[1])').get() or ''
            date_tok = raw_date.split('|')[-1].strip()
            date = iso_date(date_tok) if date_tok else None
            title_b64 = b64url_encode(title)
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url, f'{date or ""}|{title_b64}']),
                )
            )

    # ── Context loader (curID-packed title/date) ─────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0] if parts else ''
        if not url:
            return None
        date_tok = parts[1] if len(parts) > 1 else ''
        title_b64 = parts[2] if len(parts) > 2 else ''
        fallback_title = None
        if title_b64:
            try:
                decoded = b64url_decode(title_b64)
                fallback_title = decoded or None
            except (ValueError, UnicodeDecodeError):
                fallback_title = None
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=date_tok or None,
            fallback_title=fallback_title,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (scene.fallback_title or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Holly Randall Productions'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//ul[contains(@class,"tags")]//li//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        p = scene.sel.xpath('(//div[contains(@class,"info")]//p)[1]')
        text = p.xpath('string(.)').get() or ''
        lines = text.split('\n')
        if len(lines) <= 3:
            return
        line = lines[3].replace('Featuring:', '').strip()
        if not line:
            return
        metadata.actors = self.dedup_people([ActorResult(name=part) for part in line.split(',')])

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//img[contains(@class,"update_thumb")]/@src0_3x').getall():
            coll['push']((raw or '').strip())
        metadata.raw_image_urls = coll['list']
