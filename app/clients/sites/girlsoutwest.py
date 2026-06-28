from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content, web_search_urls

_TRAILER_P_XP = '//div[contains(@class,"trailer") and contains(@class,"topSpace")]//div//p'
_CAST_XP = _TRAILER_P_XP + '//a'


class GirlsOutWestClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        direct = base + ctx.site_info.search_path.replace('{query}', slugify(ctx.title))
        candidates = [direct]
        for u in await web_search_urls(ctx.title, ctx.site_info, include=['/trailers/']):
            if u not in candidates:
                candidates.append(u)

        results: list[SearchResult] = []
        for scene_url in candidates:
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not page or page['html'].strip() == 'Page not found':
                continue
            title = meta_content(page['sel'], 'twitter:title')
            if not title:
                continue
            date = self._date_from(page['sel'])
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )
        return results

    def _date_from(self, sel: Any) -> str | None:
        text = first_text(sel, _TRAILER_P_XP)
        parts = text.split('\\')
        if len(parts) < 2:
            return None
        return iso_date(parts[1].strip(), '%m/%d/%Y')

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return meta_content(scene.sel, 'twitter:title') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'GirlsOutWest'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return self._date_from(scene.sel)

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = ['Amateur', 'Australian']
        count = len(scene.sel.xpath(_CAST_XP))
        if count == 3:
            genres.append('Threesome')
        elif count == 4:
            genres.append('Foursome')
        elif count > 4:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_CAST_XP):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = join_url(href, scene.site.base_url)
            actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = ''
            if actor_page:
                raw = first_attr(actor_page['sel'], '(//div[contains(@class,"profilePic")]//img/@src0_3x)[1]')
                photo = join_url(raw, scene.site.base_url) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []
        for raw in scene.sel.xpath('//div[contains(@class,"videoplayer")]//img/@src0_3x').getall():
            raw = (raw or '').strip()
            if not raw:
                continue
            abs_url = join_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)
        return images
