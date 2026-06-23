from __future__ import annotations

import base64
import binascii
import json
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

from app.clients.aggregators.data18 import Data18Client
from app.clients.base import ActorResult, Client, FetchCtx, SceneContext, SceneDetail, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import date_distance_score, iso_date, pack_cur_id, slugify, title_distance_score
from app.utils.logging.logger import logger
from app.utils.processors.title_case import title_case

_DEFAULT_API_BASE = 'https://site-api.project1service.com'
_DEFAULT_IMAGE_BASE = 'https://image-service-ht.project1content.com/'
_SEARCH_TYPES = ('scene', 'movie', 'serie', 'trailer')
_TOKEN_CACHE: dict[str, tuple[str, int]] = {}
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


class Project1ServiceClient(Client):
    def __init__(self) -> None:
        super().__init__({'Accept': 'application/json'})
        self._data18: Data18Client | None = None

    async def _get_token(self, site: ResolvedSiteInfo) -> str | None:
        host = urlsplit(site.base_url).hostname or ''
        if not host:
            return None
        now = int(time.time())
        cached = _TOKEN_CACHE.get(host)
        if cached and cached[1] > now:
            return cached[0]

        token: str | None = None
        try:
            r = await self.http.head(site.base_url)
            token = r.cookies.get('instance_token')
            if not token:
                for ck in r.headers.get_list('set-cookie'):
                    m = _INSTANCE_RE.search(ck)
                    if m:
                        token = m.group(1)
                        break
        except Exception as err:  # noqa: BLE001 - token fetch is best-effort
            logger.warn(site.name, f'token HEAD failed: {err}')

        if not token:
            return cached[0] if cached else None
        exp = _parse_jwt_exp(token) or now + 3600
        _TOKEN_CACHE[host] = (token, exp)
        return token

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        token = await self._get_token(ctx.site_info)
        if not token:
            logger.warn(ctx.site_info.name, 'no Instance token; aborting search')
            return []
        headers = {'Instance': token}

        scene_id: str | None = None
        q = ctx.title.strip()
        first_word = q.split()[0] if q.split() else ''
        if first_word.isdigit():
            scene_id = first_word
            q = q.replace(first_word, '', 1).strip()

        match_target_key = _normalize(ctx.search_site or ctx.site_info.name)
        results: list[SearchResult] = []
        for type_ in _SEARCH_TYPES:
            params = f'type={type_}&id={quote(scene_id)}' if scene_id and not q else f'type={type_}&search={quote(q)}'
            url = f'{_DEFAULT_API_BASE}/v2/releases?{params}'
            body = await self.fetch_json(url, FetchCtx(capture=ctx.capture), headers=headers, label=f'GET {url}')
            releases = body.get('result') or [] if isinstance(body, dict) else []

            for r in releases:
                if not isinstance(r, dict):
                    continue
                title = (r.get('title') or '').replace('�', "'")
                cur = str(r.get('id'))
                colls = r.get('collections') or []
                sub_site = (colls[0].get('name') or '').strip() if colls and isinstance(colls[0], dict) else ''
                release_date = iso_date(r['dateReleased']) or '' if r.get('dateReleased') else ''

                if scene_id and scene_id == cur:
                    score: float = 100
                elif scene_id:
                    score = title_distance_score(scene_id, cur)
                elif ctx.search_date and release_date:
                    score = date_distance_score(ctx.search_date, release_date)
                else:
                    score = title_distance_score(q, title)
                if type_ == 'trailer':
                    score -= 10
                if sub_site and _normalize(sub_site) != match_target_key:
                    score -= 10

                composite = f'{cur}|{type_}|{release_date}' if release_date else f'{cur}|{type_}'
                results.append(
                    SearchResult(
                        title=f'[Trailer] {title}' if type_ == 'trailer' else title,
                        scene_url=url,
                        cur_id=pack_cur_id([composite]),
                        thumb_url=_best_image_url(r, _DEFAULT_IMAGE_BASE),
                        score=score,
                    )
                )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
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
        body = await self.fetch_json(url, FetchCtx(capture=capture), headers=headers, label=f'GET {url}')
        releases = body.get('result') or [] if isinstance(body, dict) else []
        if not releases or not isinstance(releases[0], dict):
            return None
        detail = releases[0]

        title = (detail.get('title') or '').strip().replace('�', "'")
        summary = detail.get('description') or (detail.get('parent') or {}).get('description') or ''
        studio = title_case(detail.get('brand') or '', site_name=site.name) or site.name

        colls = detail.get('collections') or []
        sub_site = (colls[0].get('name') or '').strip() if colls and isinstance(colls[0], dict) else ''
        has_sub = bool(sub_site) and _normalize(sub_site) != _normalize(studio)
        tagline = sub_site if has_sub else None
        collections = [sub_site] if has_sub else [studio]

        release_date = iso_date(detail['dateReleased']) if detail.get('dateReleased') else None
        genres = [g for g in ((t.get('name') or '').strip() for t in (detail.get('tags') or []) if isinstance(t, dict)) if g]

        actors: list[ActorResult] = []
        for a in detail.get('actors') or []:
            if not isinstance(a, dict) or a.get('id') is None:
                continue
            fetched = await self._fetch_actor(int(a['id']), headers, capture)
            if fetched:
                actors.append(fetched)

        raw_images: list[str] = []
        for kind in ('poster', 'cover'):
            bucket = (detail.get('images') or {}).get(kind)
            if not isinstance(bucket, dict):
                continue
            for k in sorted(bucket):
                if not k.isdigit():
                    continue
                u = _service_url(((bucket[k] or {}).get('xx') or {}).get('url'), _DEFAULT_IMAGE_BASE)
                if u:
                    raw_images.append(u)

        if site.scraper_config.data18_enrichment and env.data18_enabled:
            try:
                self._data18 = self._data18 or Data18Client()
                date_obj = datetime.fromisoformat(release_date) if release_date else None
                providers = [site.name, sub_site]
                data18_url = await self._data18.find_scene_url(slugify(title.replace("'", '')), title, providers, date_obj)
                if data18_url:
                    logger.info(site.name, f'data18 enrichment match: {data18_url}')
                    for u in await self._data18.fetch_images(data18_url):
                        if u not in raw_images:
                            raw_images.append(u)
            except Exception as err:  # noqa: BLE001 - enrichment is best-effort
                logger.warn(site.name, f'data18 enrichment failed: {err}')

        return SceneDetail(
            title=title,
            summary=summary,
            studio=studio,
            tagline=tagline,
            release_date=release_date,
            collections=collections,
            genres=genres,
            actors=actors,
            raw_image_urls=raw_images,
        )

    async def _fetch_actor(self, actor_id: int, headers: dict[str, str], capture: Any) -> ActorResult | None:
        url = f'{_DEFAULT_API_BASE}/v1/actors?id={actor_id}'
        body = await self.fetch_json(url, FetchCtx(capture=capture), headers=headers, label=f'GET {url}')
        results = body.get('result') or [] if isinstance(body, dict) else []
        if not results or not isinstance(results[0], dict):
            return None
        a = results[0]
        photo = _service_url((((a.get('images') or {}).get('profile') or {}).get('0') or {}).get('xs', {}).get('url'), _DEFAULT_IMAGE_BASE) or ''
        return ActorResult(name=a.get('name', ''), photo_url=photo, gender=a.get('gender', ''))
