from __future__ import annotations

import re
from typing import Any

import httpx2

from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, strip_query
from app.utils.logging.logger import logger

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

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base_url = ctx.site_info.base_url.rstrip('/')
        token = await self._fetch_token(base_url)
        if not token:
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()

        for hit in await self._api_search(base_url, ctx.site_info.search_path, ctx.title, token):
            if hit.get('resourceType') != 'movies':
                continue
            slug = (hit.get('slug') or '').strip()
            title = (hit.get('title') or '').strip()
            if not slug or not title or slug in seen:
                continue
            seen.add(slug)
            results.append(
                build_search_result(
                    title=title,
                    scene_url=f'{base_url}/api/movies/slug/{slug}',
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([slug, ctx.search_date or '']),
                )
            )

        direct_slug = _slugify_title(ctx.title)
        if direct_slug and direct_slug not in seen:
            direct = await self._api_movie_by_slug(base_url, direct_slug, token)
            if direct and (direct.get('title') or '').strip():
                seen.add(direct_slug)
                results.append(
                    build_search_result(
                        title=direct['title'].strip(),
                        scene_url=f'{base_url}/api/movies/slug/{direct_slug}',
                        query=ctx.title,
                        search_date=ctx.search_date,
                        score=100,
                        cur_id=pack_cur_id([direct_slug, ctx.search_date or '']),
                    )
                )
        return results

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

    # ── Detail field hooks (all read scene.extra) ─────────────────────────────

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return (self._data(scene).get('title') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return (self._data(scene).get('synopsis_clean') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _full_name(self._data(scene).get('producer')) or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        raw = self._data(scene).get('release_date')
        if raw:
            parsed = iso_date(raw)
            if parsed:
                return parsed
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        return None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        d = self._data(scene)
        genres = self.dedup_strings([(t.get('title') or '').strip() for t in d.get('tags') or []])
        hay = f'{(d.get("title") or "").lower()} {(d.get("synopsis_clean") or "").lower()}'
        if (d.get('is_compilation') or 'compilation' in hay) and 'Compilation' not in genres:
            genres.append('Compilation')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for p in self._data(scene).get('performers') or []:
            name = _full_name(p)
            if not name or name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name, photo_url=strip_query(p.get('poster_image'))))
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        name = _full_name(self._data(scene).get('director'))
        return [ActorResult(name=name)] if name else None

    async def fetch_producers(self, scene: LoadedScene) -> list[ActorResult] | None:
        producer = self._data(scene).get('producer')
        name = _full_name(producer)
        if not name or not isinstance(producer, dict):
            return None
        return [ActorResult(name=name, photo_url=strip_query(producer.get('poster_image')))]

    # Legacy set `rating = data.rating * 2`; SceneDetail has no rating slot, so
    # the rating is dropped (parity with the TS port).

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        d = self._data(scene)
        images: list[str] = []

        def push(raw: str) -> None:
            if raw and raw not in images:
                images.append(raw)

        if d.get('poster_picture'):
            push(strip_query(d['poster_picture']))
        elif d.get('banner_image_mobile'):
            push(strip_query(d['banner_image_mobile']))
        for a in d.get('album') or []:
            if a.get('path'):
                push(strip_query(a['path']))
        return images
