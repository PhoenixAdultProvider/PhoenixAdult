from __future__ import annotations

import re
from typing import Any

from app.clients.base import (
    ActorResult,
    Client,
    FetchCtx,
    LoadedScene,
    RawCaptureEntry,
    SceneContext,
    SearchContext,
    SearchResult,
)
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, date_distance_score, iso_date, load_site_json, title_distance_score

STUDIO = 'Dirty Flix'
_TOUR_HOST = 'https://dirtyflix.com'
_SCENE_ID_RE = re.compile(r'tour_thumbs/([^/]+)/')

_SITES: dict[str, dict[str, Any]] = load_site_json(__file__, 'dirtyflix_sites')
_SCENE_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'dirtyflix_scene_actors')


def _actors_for_scene_id(scene_id: str) -> list[str]:
    if not scene_id:
        return []
    return [name for name, ids in _SCENE_ACTORS.items() if scene_id in ids]


def _scenes_for_actor_name(query: str) -> list[str]:
    if not query:
        return []
    want = query.strip().lower()
    for name, ids in _SCENE_ACTORS.items():
        if name.lower() == want:
            return ids
    return []


__testing__ = {'actors_for_scene_id': _actors_for_scene_id, 'scenes_for_actor_name': _scenes_for_actor_name}


class DirtyFlixClient(Client):
    # ── Search (paginated listing + shared tour-date resolution) ────────────────

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        cfg = _SITES.get(ctx.site_info.name)
        if not cfg:
            return []
        actor_scene_ids = _scenes_for_actor_name(ctx.title)
        date_by_scene_id = await self._fetch_tour_dates(int(cfg['tour_key']), ctx.capture)

        search_base = ctx.site_info.base_url.rstrip('/') + ctx.site_info.search_path
        title_xp = cfg['search_title_xp']
        results: list[SearchResult] = []
        for page in range(1, int(cfg['search_pages']) + 1):
            page_url = search_base if page == 1 else f'{search_base}{page}'
            loaded = await self.fetch_and_load(page_url, FetchCtx(capture=ctx.capture), f'GET {page_url}')
            if not loaded:
                break
            for row in loaded['sel'].xpath('//div[contains(@class,"movie-block")]'):
                img_src = (row.xpath('(.//li//img)[1]/@src').get() or '').strip()
                m = _SCENE_ID_RE.search(img_src)
                if not m:
                    continue
                scene_id = m.group(1)
                title = (row.xpath(f'({title_xp})[1]').xpath('string(.)').get() or '').strip()
                if not title:
                    continue
                date_iso = date_by_scene_id.get(scene_id, '')
                if scene_id in actor_scene_ids:
                    score: float = 100
                elif ctx.search_date and date_iso:
                    score = date_distance_score(ctx.search_date, date_iso)
                else:
                    score = title_distance_score(ctx.title, title)
                results.append(
                    SearchResult(
                        title=title, scene_url=page_url, cur_id=self.encode(f'{scene_id}|{date_iso}|{page_url}'), release_date=date_iso or None, score=score
                    )
                )
            if any((r.score or 0) >= 80 for r in results):
                break
        return results

    # ── Detail (search-page-as-detail: re-find the row by sceneID) ──────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        cfg = _SITES.get(site.name)
        if not cfg:
            return None
        parts = payload.split('|')
        if len(parts) < 3:
            return None
        scene_id, iso = parts[0], parts[1]
        page_url = '|'.join(parts[2:])

        extract = await self._try_page(page_url, scene_id, cfg, ctx)
        if not extract:
            search_base = site.base_url.rstrip('/') + site.search_path
            for page in range(1, int(cfg['search_pages']) + 1):
                url = search_base if page == 1 else f'{search_base}{page}'
                if url == page_url:
                    continue
                extract = await self._try_page(url, scene_id, cfg, ctx)
                if extract:
                    break
        if not extract:
            return None

        extract['scene_id'] = scene_id
        return LoadedScene(url=page_url, site=site, scene_date=iso or None, capture=ctx.capture if ctx else None, extra=extract)

    async def _try_page(self, url: str, scene_id: str, cfg: dict[str, Any], ctx: SceneContext | None) -> dict[str, Any] | None:
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'GET {url}')
        if not loaded:
            return None
        for row in loaded['sel'].xpath('//div[contains(@class,"movie-block")]'):
            img_src = (row.xpath('(.//li//img)[1]/@src').get() or '').strip()
            if f'tour_thumbs/{scene_id}/' not in img_src:
                continue
            return {
                'title': (row.xpath(f'({cfg["search_title_xp"]})[1]').xpath('string(.)').get() or '').strip(),
                'summary': (row.xpath(f'({cfg["detail_summary_xp"]})[1]').xpath('string(.)').get() or '').strip(),
                'poster': (row.xpath('(.//img)[1]/@src').get() or '').strip(),
            }
        return None

    async def _fetch_tour_dates(self, tour_key: int, capture: list[RawCaptureEntry] | None) -> dict[str, str]:
        out: dict[str, str] = {}
        for url in (f'{_TOUR_HOST}/index.php/main/show_one_tour/{tour_key}', f'{_TOUR_HOST}/index.php/main/show_one_tour/{tour_key}/2'):
            loaded = await self.fetch_and_load(url, FetchCtx(capture=capture), f'GET {url}')
            if not loaded:
                continue
            for item in loaded['sel'].xpath('//div[contains(@class,"thumbs-item")]'):
                matches = (_SCENE_ID_RE.search(src) for src in item.xpath('.//img/@src').getall())
                m = next((x for x in matches if x), None)
                if not m:
                    continue
                scene_id = m.group(1)
                date_raw = (item.xpath('(.//span[contains(@class,"added")])[1]').xpath('string(.)').get() or '').strip()
                iso = iso_date(date_raw) or date_raw
                if iso:
                    out[scene_id] = iso
        return out

    # ── Field hooks (read the row extract stashed in scene.extra) ────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (scene.extra or {}).get('title') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (scene.extra or {}).get('summary') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        cfg = _SITES.get(scene.site.name)
        genres = list(cfg['genres']) if cfg else []
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        scene_id = (scene.extra or {}).get('scene_id', '')
        actors = [ActorResult(name=n) for n in _actors_for_scene_id(scene_id)]
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        poster = (scene.extra or {}).get('poster', '')
        return [absolute_url(poster, scene.site.base_url)] if poster else None
