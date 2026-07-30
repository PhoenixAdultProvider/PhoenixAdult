from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import (
    ActorResult,
    Client,
    FetchCtx,
    LoadedScene,
    RawCaptureEntry,
    SceneContext,
    SceneDetail,
    SearchContext,
    SearchResult,
)
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_data
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'Dirty Flix'
_TOUR_HOST = 'https://dirtyflix.com'
_SCENE_ID_RE = re.compile(r'tour_thumbs/([^/]+)/')

_SITES: dict[str, dict[str, Any]] = load_data(__file__, 'dirtyflix_sites')
_SCENE_ACTORS: dict[str, list[str]] = load_data(__file__, 'dirtyflix_scene_actors')


def _actors_for_scene_id(scene_id: str) -> list[str]:
    if not scene_id:
        return []

    return [actor_name for actor_name, ids in _SCENE_ACTORS.items() if scene_id in ids]


def _scenes_for_actor_name(query: str) -> list[str]:
    if not query:
        return []

    want = query.strip().lower()
    for actor_name, ids in _SCENE_ACTORS.items():
        if actor_name.lower() == want:
            return ids

    return []


__testing__ = {'actors_for_scene_id': _actors_for_scene_id, 'scenes_for_actor_name': _scenes_for_actor_name}


class DirtyFlixClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        cfg = _SITES.get(search_data.site_info.name)
        if not cfg:
            return

        actor_scene_ids = _scenes_for_actor_name(search_data.title)
        date_by_scene_id = await self._fetch_tour_dates(int(cfg['tour_key']), search_data.capture)

        search_base = search_data.site_info.base_url.rstrip('/') + search_data.site_info.search_path
        title_xp = cfg['search_title_xp']
        page_url = ''

        async def fetch_rows(page: int) -> list[Any] | None:
            nonlocal page_url
            page_url = search_base if page == 1 else f'{search_base}{page}'
            search_results = await self.fetch_and_load(page_url, FetchCtx(capture=search_data.capture), f'GET {page_url}')
            return list(search_results['sel'].xpath('//div[contains(@class,"movie-block")]')) if search_results else None

        def build_row(row: Any) -> SearchResult | None:
            img_src = first_attr(row, '(.//li//img)[1]/@src')
            m = _SCENE_ID_RE.search(img_src)
            if not m:
                return None

            scene_id = m.group(1)
            title = (row.xpath(f'({title_xp})[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return None

            date_iso = date_by_scene_id.get(scene_id, '')
            return build_search_result(
                title=title,
                scene_url=page_url,
                query=search_data.title,
                site=search_data.site_info,
                cur_id=self.encode(f'{scene_id}|{date_iso}|{page_url}'),
                search_date=search_data.search_date,
                display_date=date_iso or None,
                score=100 if scene_id in actor_scene_ids else None,
            )

        results.extend(
            await self.paginate_search(
                fetch_rows=fetch_rows,
                build_row=build_row,
                max_pages=int(cfg['search_pages']),
                dedup=False,
                should_continue=lambda built: not any((r.score or 0) >= 100 for r in built),
            )
        )

    # ── Search Helpers ──────────────────────────────────────────────────────────

    async def _fetch_tour_dates(self, tour_key: int, capture: list[RawCaptureEntry] | None) -> dict[str, str]:
        out: dict[str, str] = {}
        for url in (f'{_TOUR_HOST}/index.php/main/show_one_tour/{tour_key}', f'{_TOUR_HOST}/index.php/main/show_one_tour/{tour_key}/2'):
            tour_page_elements = await self.fetch_and_load(url, FetchCtx(capture=capture), f'GET {url}')
            if not tour_page_elements:
                continue

            for item in tour_page_elements['sel'].xpath('//div[contains(@class,"thumbs-item")]'):
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

    # ── Context Loader (search-page-as-detail: re-find the row by sceneID) ──────

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
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'GET {url}')
        if not details_page_elements:
            return None

        for row in details_page_elements['sel'].xpath('//div[contains(@class,"movie-block")]'):
            img_src = first_attr(row, '(.//li//img)[1]/@src')
            if f'tour_thumbs/{scene_id}/' not in img_src:
                continue

            return {
                'title': (row.xpath(f'({cfg["search_title_xp"]})[1]').xpath('string(.)').get() or '').strip(),
                'summary': (row.xpath(f'({cfg["detail_summary_xp"]})[1]').xpath('string(.)').get() or '').strip(),
                'poster': first_attr(row, '(.//img)[1]/@src'),
            }

        return None

    # ── Update Field Hooks (read the row extract stashed in scene.extra) ─────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (scene.extra or {}).get('title') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = (scene.extra or {}).get('summary') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        cfg = _SITES.get(scene.site.name)

        metadata.genres = list(cfg['genres']) if cfg else []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        scene_id = (scene.extra or {}).get('scene_id', '')

        metadata.actors = [ActorResult(name=n) for n in _actors_for_scene_id(scene_id)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = (scene.extra or {}).get('poster', '')

        metadata.art = [absolute_url(poster, scene.site.base_url)] if poster else []
