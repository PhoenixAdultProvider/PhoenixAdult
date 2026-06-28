from __future__ import annotations

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, script_match, web_search_urls


class ExpliciteArtClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.strip().lower().replace(' ', '-')
        search_url = f'{base}/visitor/search/videos/{slug}/page1.html'

        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        results: list[SearchResult] = []
        if loaded:
            sel: Selector = loaded['sel']
            for card in sel.xpath('//div[contains(@class,"content")]'):
                if not card.xpath('.//*[contains(@src,"video")]'):
                    continue
                title = first_text(card, './/div[contains(@class,"vtitle")]')
                href = card.xpath('(.//a/@href)[1]').get() or ''
                if not title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                results.append(
                    build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))
                )

        # Web-search fallback when the on-site search produced nothing.
        if not results:
            for scene_url in await web_search_urls(ctx.title, ctx.site_info):
                page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] web-search {scene_url}')
                if not page:
                    continue
                title = first_text(page['sel'], '//title')
                if not title:
                    continue
                results.append(
                    build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))
                )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"player-info-desc")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//span[contains(@class,"tags")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        links: list[tuple[str, str]] = []
        for a in scene.sel.xpath('//div[contains(@class,"player-info-row")]//a'):
            name = first_attr(a, 'normalize-space(.)')
            href = a.xpath('@href').get() or ''
            if name and href:
                links.append((name, href))

        actors: list[ActorResult] = []
        for name, href in links:
            actor_url = absolute_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo_url = ''
            if actor_page:
                raw = actor_page['sel'].xpath('(//div[contains(@class,"pornstar-bio-left")]//*[@src])[1]/@src').get() or ''
                photo_url = absolute_url(raw, scene.site.base_url) if raw else ''
            if not any(a.name == name for a in actors):
                actors.append(ActorResult(name=name, photo_url=photo_url, gender=''))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        script_text = scene.sel.xpath('(//div[@id="player"]//script)[1]/text()').get() or ''
        poster = script_match(script_text, r'image:\s*"([^"]+)"')
        return [poster] if poster else []
