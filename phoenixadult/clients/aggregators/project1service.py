from __future__ import annotations

import base64
import binascii
import json
import re
import time
from typing import Any, TypedDict
from urllib.parse import quote, urlsplit

from phoenixadult.clients.aggregators.data18 import mapping_slug
from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.concurrency.single_flight import SingleFlight
from phoenixadult.utils.helpers.helpers import build_search_result, date_distance_score, iso_date, pack_cur_id, sceneid_distance_score, title_distance_score
from phoenixadult.utils.logging.best_effort import best_effort
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.title_case import title_case

_DEFAULT_API_BASE = 'https://site-api.project1service.com'
_DEFAULT_IMAGE_BASE = 'https://image-service-ht.project1content.com/'
_SEARCH_TYPES = ('scene', 'movie', 'serie', 'trailer')
_FORCED_SUBSITES = {'brazzerslive': 'Brazzers Live'}
_TOKENS: SingleFlight[str, str] = SingleFlight()
_INSTANCE_RE = re.compile(r'instance_token=([^;]+)')


def _parse_jwt_exp(token: str) -> int | None:
    parts = token.split('.')
    if len(parts) < 2:
        return None

    payload = parts[1]
    payload += '=' * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, binascii.Error):
        return None

    exp = data.get('exp')
    return exp if isinstance(exp, int) else None


def _normalize(s: str) -> str:
    return re.sub(r'\W', '', s).lower()


def _service_url(upstream: str | None, base: str) -> str | None:
    if not upstream:
        return None

    after_eq = upstream.split('=')[-1]
    after_slash = after_eq[after_eq.index('/') + 1 :] if '/' in after_eq else after_eq
    if not after_slash:
        return None

    return f'{base.rstrip("/")}/{after_slash}'


def _best_image_url(release: dict[str, Any], base: str) -> str | None:
    images = release.get('images') or {}
    for kind in ('poster', 'cover'):
        bucket = images.get(kind)
        if not isinstance(bucket, dict):
            continue

        for k in sorted(bucket):
            if not k.isdigit():
                continue

            u = _service_url(((bucket[k] or {}).get('xx') or {}).get('url'), base)
            if u:
                return u

    return None


class _SceneExtra(TypedDict):
    detail: dict[str, Any]
    headers: dict[str, str]


class Project1ServiceClient(Client):
    def __init__(self) -> None:
        super().__init__({'Accept': 'application/json'})

    async def _get_token(self, site: ResolvedSiteInfo) -> str | None:
        host = urlsplit(site.base_url).hostname or ''
        if not host:
            return None

        async def _fetch() -> tuple[str, float] | None:
            token: str | None = None
            with best_effort(site.name, 'token HEAD'):
                r = await self.http.head(site.base_url)
                token = r.cookies.get('instance_token')
                if not token:
                    for ck in r.headers.get_list('set-cookie'):
                        m = _INSTANCE_RE.search(ck)
                        if m:
                            token = m.group(1)
                            break

            if not token:
                return None

            return token, float(_parse_jwt_exp(token) or int(time.time()) + 3600)

        return await _TOKENS.get(host, _fetch)

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        token = await self._get_token(search_data.site_info)
        if not token:
            logger.warn(search_data.site_info.name, 'no Instance token; aborting search')
            return

        headers = {'Instance': token}

        scene_id: str | None = None
        q = search_data.title.strip()
        first_word = q.split()[0] if q.split() else ''
        if first_word.isdigit() and int(first_word) >= 1000000:
            scene_id = first_word
            q = q.replace(first_word, '', 1).strip()

        match_target_key = _normalize(search_data.search_site or search_data.site_info.name)
        forced_sub = _FORCED_SUBSITES.get(match_target_key)
        seen: set[str] = set()

        if scene_id:
            await self._search_phase(search_data, headers, f'id={quote(scene_id)}', scene_id, q, match_target_key, forced_sub, results, seen)
            if any(r.score == 100 for r in results):
                return

        if q or not scene_id:
            await self._search_phase(search_data, headers, f'search={quote(q)}', scene_id, q, match_target_key, forced_sub, results, seen)

    async def _search_phase(
        self,
        search_data: SearchContext,
        headers: dict[str, str],
        query_param: str,
        scene_id: str | None,
        q: str,
        match_target_key: str,
        forced_sub: str | None,
        results: list[SearchResult],
        seen: set[str],
    ) -> None:
        for type_ in _SEARCH_TYPES:
            params = f'type={type_}&{query_param}'
            url = f'{_DEFAULT_API_BASE}/v2/releases?{params}'
            search_results = await self.fetch_json(url, FetchCtx(capture=search_data.capture), headers=headers, label=f'GET {url}')
            releases = search_results.get('result') or [] if isinstance(search_results, dict) else []

            for r in releases:
                if not isinstance(r, dict):
                    continue

                title = (r.get('title') or '').replace('�', "'")
                cur = str(r.get('id'))
                colls = r.get('collections') or []
                sub_site = (colls[0].get('name') or '').strip() if colls and isinstance(colls[0], dict) else ''
                release_date = iso_date(r['dateReleased']) if r.get('dateReleased') else None

                if scene_id and scene_id == cur:
                    score: float = 100
                elif scene_id:
                    score = sceneid_distance_score(scene_id, cur)
                elif search_data.search_date and release_date:
                    score = date_distance_score(search_data.search_date, release_date)
                else:
                    score = title_distance_score(q, title)

                if type_ == 'trailer':
                    score -= 10

                if sub_site and _normalize(sub_site) != match_target_key:
                    score -= 10

                composite = f'{cur}|{type_}|{release_date}' if release_date else f'{cur}|{type_}'
                if composite in seen:
                    continue

                seen.add(composite)
                result_sub = forced_sub or (sub_site if sub_site and _normalize(sub_site) != _normalize(search_data.site_info.name) else None)

                results.append(
                    build_search_result(
                        title=f'[Trailer] {title}' if type_ == 'trailer' else title,
                        scene_url=url,
                        query=q,
                        search_date=search_data.search_date,
                        display_date=release_date,
                        score=score,
                        cur_id=pack_cur_id([composite]),
                        thumb_url=_best_image_url(r, _DEFAULT_IMAGE_BASE),
                        subsite=result_sub,
                    )
                )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_id = parts[0]
        scene_type = parts[1] if len(parts) > 1 else 'scene'
        if not scene_id:
            return None

        token = await self._get_token(site)
        if not token:
            return None

        headers = {'Instance': token}
        capture = ctx.capture if ctx else None

        url = f'{_DEFAULT_API_BASE}/v2/releases?type={quote(scene_type)}&id={quote(scene_id)}'
        details_page_elements = await self.fetch_json(url, FetchCtx(capture=capture), headers=headers, label=f'GET {url}')
        releases = details_page_elements.get('result') or [] if isinstance(details_page_elements, dict) else []
        if not releases or not isinstance(releases[0], dict):
            return None

        extra: _SceneExtra = {'detail': releases[0], 'headers': headers}
        return LoadedScene(url=url, site=site, capture=capture, extra=extra, subsite=ctx.subsite if ctx else None)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        extra: _SceneExtra = scene.extra
        detail = extra['detail']
        headers = extra['headers']
        capture = scene.capture

        # Title
        metadata.title = (detail.get('title') or '').strip().replace('�', "'")

        # Summary
        metadata.summary = detail.get('description') or (detail.get('parent') or {}).get('description') or ''

        # Studio
        metadata.studio = title_case(detail.get('brand') or '', site_name=site.name) or site.name

        # Tagline and Collection(s)
        colls = detail.get('collections') or []
        sub_site = (colls[0].get('name') or '').strip() if colls and isinstance(colls[0], dict) else ''
        has_sub = bool(sub_site) and _normalize(sub_site) != _normalize(metadata.studio)
        metadata.tagline = sub_site if has_sub else ''
        metadata.collections = [sub_site] if has_sub else [metadata.studio]

        # Release Date
        metadata.release_date = iso_date(detail['dateReleased']) if detail.get('dateReleased') else None

        # Genres
        metadata.genres = [g for g in ((t.get('name') or '').strip() for t in (detail.get('tags') or []) if isinstance(t, dict)) if g]

        # Actor(s)
        for a in detail.get('actors') or []:
            if not isinstance(a, dict) or a.get('id') is None:
                continue

            fetched = await self._fetch_actor(int(a['id']), headers, capture)
            if fetched:
                metadata.actors.append(fetched)

        # Posters
        for kind in ('poster', 'cover'):
            bucket = (detail.get('images') or {}).get(kind)
            if not isinstance(bucket, dict):
                continue

            for k in sorted(bucket):
                if not k.isdigit():
                    continue

                u = _service_url(((bucket[k] or {}).get('xx') or {}).get('url'), _DEFAULT_IMAGE_BASE)
                if u:
                    metadata.art.append(u)

        # Posters from Data18
        search_sub = sub_site or scene.subsite
        providers = [p for p in (site.name, search_sub) if p]
        await self.enrich_from_data18(metadata, site, scene_id=mapping_slug(metadata.title, search_sub), providers=providers)

    async def _fetch_actor(self, actor_id: int, headers: dict[str, str], capture: Any) -> ActorResult | None:
        url = f'{_DEFAULT_API_BASE}/v1/actors?id={actor_id}'
        model_page_elements = await self.fetch_json(url, FetchCtx(capture=capture), headers=headers, label=f'GET {url}')

        results = model_page_elements.get('result') or [] if isinstance(model_page_elements, dict) else []
        if not results or not isinstance(results[0], dict):
            return None

        a = results[0]
        photo = _service_url(((((a.get('images') or {}).get('profile') or {}).get('0') or {}).get('xs') or {}).get('url'), _DEFAULT_IMAGE_BASE) or ''

        return ActorResult(name=a.get('name') or '', photo_url=photo, gender=a.get('gender') or '')
