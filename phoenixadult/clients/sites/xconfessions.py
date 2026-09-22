from __future__ import annotations

import re
from typing import Any

import httpx2

from phoenixadult.clients.base import Client, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import strip_query
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.response_trace import trace_response

_TOKEN_RE = re.compile(r'\.access_token="([^"]+)"')
_TOKEN_ORIGIN_MARKERS = ('//api.', '//next-prod-api.')


def _token_origin(base_url: str) -> str:
    for marker in _TOKEN_ORIGIN_MARKERS:
        if marker in base_url:
            return base_url.replace(marker, '//', 1)

    return base_url


def _slugify_title(s: str) -> str:
    return s.lower().replace(' ', '-')


def _full_name(person: dict[str, Any] | None) -> str:
    if not person:
        return ''

    return ' '.join(p for p in (person.get('name'), person.get('last_name')) if p).strip()


class XConfessionsClient(Client):
    async def _fetch_token(self, base_url: str) -> str | None:
        origin = _token_origin(base_url)
        try:
            r = await self.http.get(origin)
            m = _TOKEN_RE.search(r.text)
            return m.group(1) if m else None
        except httpx2.HTTPError as err:
            logger.warn('XConfessions', f'token fetch failed for {origin}: {err}')
            return None

    async def _api_search(self, base_url: str, search_path: str, query: str, token: str) -> list[dict[str, Any]]:
        try:
            r = await self.http.post(
                f'{base_url}{search_path}', json={'query': query}, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            )
            trace_response(r)
            if r.status_code >= 400:
                return []

            data = r.json().get('data')
            return data if isinstance(data, list) else []
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn('XConfessions', f'search POST failed: {err}')
            return []

    async def _api_movie_by_slug(self, base_url: str, slug: str, token: str) -> dict[str, Any] | None:
        try:
            r = await self.http.get(f'{base_url}/api/movies/slug/{slug}', headers={'Authorization': f'Bearer {token}'})
            if r.status_code >= 400:
                return None

            data = r.json().get('data')
            return data if isinstance(data, dict) else None
        except (httpx2.HTTPError, ValueError):
            return None

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base_url = search_data.site_info.base_url.rstrip('/')
        token = await self._fetch_token(base_url)
        if not token:
            return

        seen: set[str] = set()

        for hit in await self._api_search(base_url, search_data.site_info.search_path, search_data.title, token):
            if hit.get('resourceType') != 'movies':
                continue

            slug = (hit.get('slug') or '').strip()
            title = (hit.get('title') or '').strip()
            if not slug or not title or slug in seen:
                continue

            seen.add(slug)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=f'{base_url}/api/movies/slug/{slug}',
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([slug, search_data.search_date or '']),
                )
            )

        direct_slug = _slugify_title(search_data.title)
        if direct_slug and direct_slug not in seen:
            direct = await self._api_movie_by_slug(base_url, direct_slug, token)
            if direct and (direct.get('title') or '').strip():
                seen.add(direct_slug)

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=direct['title'].strip(),
                        scene_url=f'{base_url}/api/movies/slug/{direct_slug}',
                        query=search_data.title,
                        search_date=search_data.search_date,
                        score=100,
                        cur_id=pack_cur_id([direct_slug, search_data.search_date or '']),
                    )
                )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        base_url = site.base_url.rstrip('/')
        slug, _, tail = payload.partition('|')
        slug = slug.strip()
        cur_id_date = tail.strip()
        if not slug:
            return None

        token = await self._fetch_token(base_url)
        if not token:
            logger.warn(site.name, 'XConfessions detail: no token')
            return None

        scene = await self._api_movie_by_slug(base_url, slug, token)
        if not scene:
            logger.warn(site.name, f'XConfessions detail: no scene for slug "{slug}"')
            return None

        return LoadedScene(
            url=f'{base_url}/api/movies/slug/{slug}', site=site, scene_date=cur_id_date or None, capture=ctx.capture if ctx else None, extra=scene
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    # ── Update Field Hooks (all read scene.extra) ─────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (scene.extra_or(dict, {}).get('title') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = (scene.extra_or(dict, {}).get('synopsis_clean') or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _full_name(scene.extra_or(dict, {}).get('producer')) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        date = scene.extra_or(dict, {}).get('release_date')
        if date:
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = scene.extra_or(dict, {})
        genres = self.dedup_strings([(t.get('title') or '').strip() for t in d.get('tags') or []])
        hay = f'{(d.get("title") or "").lower()} {(d.get("synopsis_clean") or "").lower()}'
        if (d.get('is_compilation') or 'compilation' in hay) and 'Compilation' not in genres:
            genres.append('Compilation')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for p in scene.extra_or(dict, {}).get('performers') or []:
            actor_name = _full_name(p)
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name, photo_url=strip_query(p.get('poster_image'))))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        director_name = _full_name(scene.extra_or(dict, {}).get('director'))

        metadata.directors = [ActorResult(name=director_name)] if director_name else None

    async def fetch_producers(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        producer = scene.extra_or(dict, {}).get('producer')
        producer_name = _full_name(producer)
        if not producer_name or not isinstance(producer, dict):
            return

        metadata.producers = [ActorResult(name=producer_name, photo_url=strip_query(producer.get('poster_image')))]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        d = scene.extra_or(dict, {})
        images = self.image_collector(lambda image: (image or '').strip())
        if d.get('poster_picture'):
            images.push(strip_query(d['poster_picture']))
        elif d.get('banner_image_mobile'):
            images.push(strip_query(d['banner_image_mobile']))

        for a in d.get('album') or []:
            if a.get('path'):
                images.push(strip_query(a['path']))

        metadata.art = images.items
