from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, b64url_decode, b64url_encode, build_search_result, iso_date, pack_cur_id

_PAYWALL_HOST = 'join.hollyrandall.com'


class HollyRandallClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"item-video")]'):
            anchor = card.xpath('(.//div[contains(@class,"item-thumb")]/a)[1]')
            title = (anchor.xpath('@title').get() or '').strip()
            href = (anchor.xpath('@href').get() or '').strip()
            if not title or not href or _PAYWALL_HOST in href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
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
        return results

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

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (scene.fallback_title or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Holly Randall Productions'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//ul[contains(@class,"tags")]//li//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        p = scene.sel.xpath('(//div[contains(@class,"info")]//p)[1]')
        text = p.xpath('string(.)').get() or ''
        lines = text.split('\n')
        if len(lines) <= 3:
            return []
        line = lines[3].replace('Featuring:', '').strip()
        if not line:
            return []
        return self.dedup_people([ActorResult(name=part) for part in line.split(',')])

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//img[contains(@class,"update_thumb")]/@src0_3x').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
