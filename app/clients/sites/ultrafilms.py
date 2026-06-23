from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text


class UltrafilmsClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        seen: set[str] = set()
        results: list[SearchResult] = []

        await self._parse_page(f'{base}/?s=%22{ctx.encoded}%22', ctx, results, seen)
        if not results:
            await self._parse_page(f'{base}/?s={ctx.encoded}', ctx, results, seen)
        return results

    async def _parse_page(self, url: str, ctx: SearchContext, results: list[SearchResult], seen: set[str]) -> None:
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {url}')
        if not loaded:
            return
        for row in loaded['sel'].xpath('//main//article[@data-video-uid]'):
            title = (row.xpath('(.//a)[1]/@title').get() or '').strip()
            href = (row.xpath('(.//a)[1]/@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            if scene_url in seen:
                continue
            seen.add(scene_url)
            poster_url = (row.xpath('(.//img/@data-src)[1]').get() or '').strip()
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url, ctx.search_date or '', poster_url]),
                )
            )

    # ── Context loader: unpack the poster slot ────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0]
        date = (parts[1] if len(parts) > 1 else '').strip()
        poster_url = (parts[2] if len(parts) > 2 else '').strip()
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=date or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'poster_url': poster_url},
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '(//h1[contains(@class,"entry-title")])[last()]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"video-description")]//div[contains(@class,"desc")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//meta[@property="article:published_time"]/@content)[1]').get() or '').strip()
        if raw:
            parsed = iso_date(raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//div[contains(@class,"tags-list")]//a[i[contains(@class,"fa-folder-open")]]'):
            t = (a.xpath('normalize-space(.)').get() or '').replace('Movies', '').strip().lower()
            if t and t not in genres:
                genres.append(t)
        count = len(scene.sel.xpath('//div[@id="video-actors"]//a'))
        extra = {3: 'Threesome', 4: 'Foursome'}.get(count) or ('Orgy' if count > 4 else None)
        if extra and extra not in genres:
            genres.append(extra)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=(a.xpath('normalize-space(.)').get() or '')) for a in scene.sel.xpath('//div[@id="video-actors"]//a')]
        return self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        poster = scene.extra.get('poster_url') if isinstance(scene.extra, dict) else ''
        return [poster] if poster else []
