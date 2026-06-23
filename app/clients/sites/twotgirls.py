from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text
from app.utils.logging.logger import logger

STUDIO = 'TwoTGirls'


class TwoTGirlsClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.replace(' ', '-')
        if not slug:
            return []
        direct_url = f'{base}/video/{slug}'

        direct = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct {direct_url}')
        if direct:
            cards = direct['sel'].xpath('//div[contains(@class,"video-details")]')
            title = first_text(cards[0], './/h1') if cards else ''
            if title:
                logger.info(ctx.site_info.name, f'TwoTGirls direct hit "{title}" ({direct_url})')
                return [
                    build_search_result(
                        title=title, scene_url=direct_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([direct_url, ctx.search_date or ''])
                    )
                ]

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []
        results: list[SearchResult] = []
        seen: set[str] = set()
        for row in loaded['sel'].xpath('//article'):
            title = first_text(row, './/h2')
            href = (row.xpath('(.//a/@href)[1]').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            if scene_url in seen:
                continue
            seen.add(scene_url)
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url, ctx.search_date or ''])
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"shadow") and contains(@class,"video-details")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        if not scene.scene_date:
            return None
        return iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//p[contains(@class,"video-tags")]//a'):
            t = (el.xpath('normalize-space(.)').get() or '').strip()
            if t and t not in genres:
                genres.append(t)
        count = len(scene.sel.xpath('//p[contains(@class,"video-date")]//a'))
        extra = {3: 'Threesome', 4: 'Foursome'}.get(count) or ('Orgy' if count > 4 else None)
        if extra and extra not in genres:
            genres.append(extra)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//p[contains(@class,"video-date")]//a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            href = (a.xpath('@href').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                url = href if href.startswith('http') else absolute_url(href, base)
                page = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if page:
                    raw = (page['sel'].xpath('(//div[contains(@class,"col-md-4")]//img/@src)[1]').get() or '').strip()
                    if raw:
                        photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            upgraded = raw.replace('720p', '1080p')
            abs_url = upgraded if upgraded.startswith('http') else absolute_url(upgraded, base)
            if abs_url not in images:
                images.append(abs_url)

        for poster in scene.sel.xpath('//video/@poster').getall():
            push(poster)
        for src in scene.sel.xpath('//article//div[contains(@class,"row")]//img/@src').getall():
            push(src)
        return images
