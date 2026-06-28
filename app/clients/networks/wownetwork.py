from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'WowNetwork'
_SEARCH_PAGES = 5


class WowNetworkClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.encoded
        results: list[SearchResult] = []
        seen: set[str] = set()

        for page_num in range(1, _SEARCH_PAGES + 1):
            page_url = f'{base}/?s={slug}' if page_num == 1 else f'{base}/page/{page_num}/?s={slug}'
            loaded = await self.fetch_and_load(page_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search p{page_num} {page_url}')
            if not loaded:
                break

            found = 0
            for el in loaded['sel'].xpath('//article[contains(@class,"thumb-block")]'):
                anchor = el.xpath('(.//a)[1]')
                title = first_attr(anchor, '@title')
                href = first_attr(anchor, '@href')
                if not title or not href:
                    continue
                found += 1
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                image = first_attr(el, '(.//img)[1]/@src')
                image_packed = self.encode(image) if image else ''
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([scene_url, f'{ctx.search_date or ""}|{image_packed}']),
                    )
                )
            if found == 0:
                break
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[contains(@class,"entry-title")])[last()]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[@id="video-date"])[1]').xpath('string(.)').get() or '').replace('Date:', '').strip()
        if raw:
            return iso_date(raw)
        meta = first_attr(scene.sel, '(//meta[@property="article:published_time"])[1]/@content')
        if meta:
            return iso_date(meta.split('T')[0])
        packed_date = scene.scene_date.split('|')[0].strip() if scene.scene_date else ''
        return iso_date(packed_date) if packed_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"tags-list")]//a[.//i[contains(@class,"fa-folder-open")]]'):
            g = (el.xpath('string(.)').get() or '').replace('Movies', '').strip()
            if g and g not in genres:
                genres.append(g)
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [ActorResult(name=first_attr(a, 'normalize-space(.)')) for a in scene.sel.xpath('//div[@id="video-actors"]//a')]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
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
        return images or None
