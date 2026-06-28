from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_text

STUDIO = 'Strapon Cum'
_WS_RE = re.compile(r'\s+')
_ACTOR_XP = '//div[contains(@class,"card")]//span[contains(text(),"Featuring:")]/following-sibling::a'

_FIXED_GENRES: list[str] = load_site_json(__file__, 'straponcum_fixed_genres')


def _parse_date(tok: str) -> str | None:
    return iso_date(tok, '%B %d, %Y') or iso_date(tok)


def _date_from_clock(node: Any) -> str | None:
    parents = node.xpath('.//i[contains(@class,"fa-clock")]/..')
    if not parents:
        return None
    trail = (parents[0].xpath('normalize-space(.)').get() or '').strip()
    parts = trail.split('•')
    if len(parts) < 2:
        return None
    tok = parts[1].strip()
    return tok or None


class StraponCumClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = _WS_RE.sub('-', ctx.title.strip())
        scene_url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct-URL {slug}')
        if not loaded:
            return []
        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"card")]'):
            title = first_text(card, './/h1[contains(@class,"card-title")]')
            if not title:
                continue
            tok = _date_from_clock(card)
            release_date = _parse_date(tok) if tok else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=release_date,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([p for p in (scene_url, release_date) if p]),
                )
            )
        return results

    # ── Context loader (default fetches the scene URL) ─────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url = payload.split('|', 1)[0]
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'])

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1[contains(@class,"card-title")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//p[contains(@class,"card-text") and contains(@class,"mb-2")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        cards = scene.sel.xpath('//div[contains(@class,"card")]')
        tok = _date_from_clock(cards[0]) if cards else None
        return _parse_date(tok) if tok else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = list(_FIXED_GENRES)
        for el in scene.sel.xpath('//div[contains(@class,"tag-cloud")]//a'):
            g = (el.xpath('normalize-space(.)').get() or '').strip()
            if g and g not in genres:
                genres.append(g)
        count = len(scene.sel.xpath(_ACTOR_XP))
        if count == 3:
            genres.append('Threesome')
        elif count == 4:
            genres.append('Foursome')
        elif count > 4:
            genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(_ACTOR_XP):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            href = (el.xpath('@href').get() or '').strip()
            if not name or not href or name in seen:
                continue
            seen.add(name)
            actor_url = absolute_url(href, base)
            page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
            photo = (page['sel'].xpath('(//img[starts-with(@id,"set-target")]/@data-src0_1x)[1]').get() or '').strip() if page else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        scene_id = (scene.sel.xpath('(//div[contains(@class,"trailer")]//img/@alt)[1]').get() or '').strip()
        if not scene_id:
            return []
        return [f'{base}/content/{scene_id}/{idx}.jpg' for idx in range(4)]
