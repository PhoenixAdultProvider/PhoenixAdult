from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx2

from app.clients.base import ActorResult, Client, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.concurrency.single_flight import SingleFlight
from app.utils.helpers.helpers import iso_date, pack_cur_id
from app.utils.logging.logger import logger
from app.utils.processors.similarity import compare_string
from app.utils.processors.studio_name import normalize_studio
from app.utils.processors.title_case import title_case

_ALGOLIA_APP_ID = 'TSMKFA364Q'
_IMG_BASE = 'https://images-fame.gammacdn.com'

_ACTOR_DB: dict[str, list[str]] = {'218114': ['Lara Lee']}

_API_KEYS: SingleFlight[str, str] = SingleFlight()  # per-host Algolia key; stable, so cached without expiry

SceneType = Literal['scenes', 'movies']


def _actor_overrides(scene_id: str) -> list[ActorResult]:
    return [ActorResult(name=n, gender='female') for n in _ACTOR_DB.get(scene_id, [])]


class GammaEntOtherClient(Client):
    # ── Search (Algolia) ────────────────────────────────────────────────────────

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        title = ctx.title.strip()
        scene_id = ctx.scene_id
        api_key = await self._get_api_key(ctx.site_info)
        if not api_key:
            logger.warn(ctx.site_info.name, 'could not resolve Algolia apiKey')
            return

        site_norm = ctx.site_info.name.replace(' ', '').lower()
        for scene_type in ('scenes', 'movies'):
            id_field = 'clip_id' if scene_type == 'scenes' else 'movie_id'
            params = f'filters={id_field}={scene_id}' if scene_id and not title else f'query={quote(title)}'
            for hit in await self._algolia(ctx.site_info, api_key, f'all_{scene_type}', params):
                cur = hit.get(id_field)
                if cur is None:
                    continue
                date_raw = hit.get('release_date', '') if scene_type == 'scenes' else (hit.get('last_modified') or hit.get('date_created') or '')
                release = iso_date(date_raw) or ''
                title_nf = hit.get('title') or ''
                main_channel = hit.get('mainChannel') or {}
                sub_site = (main_channel.get('name') or '').strip() or (hit.get('serie_name') or '').strip()

                score: float = 100 if sub_site.replace(' ', '').lower() == site_norm else 99
                if 'BTS' in title_nf:
                    score -= 1
                for ch in hit.get('channels') or []:
                    if 'behindthescenes' in (ch.get('id') or '') and 'BTS' not in title_nf:
                        title_nf = f'{title_nf} BTS'
                        score -= 1
                if scene_id:
                    score -= compare_string(scene_id, str(cur)).levenshtein
                elif ctx.search_date and release:
                    score -= compare_string(ctx.search_date, release).levenshtein
                else:
                    score -= compare_string(title.lower(), title_nf.lower()).levenshtein

                results.append(
                    SearchResult(
                        title=title_nf,
                        scene_url=ctx.site_info.base_url,
                        cur_id=pack_cur_id([f'{cur}|{scene_type}|{release}']),
                        release_date=release or ctx.search_date or None,
                        display_date=release or None,
                        score=score,
                        subsite=sub_site or None,
                    )
                )

    # ── Detail (Algolia; end-to-end JSON override) ──────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_id = parts[0] if parts else ''
        scene_type: SceneType = 'movies' if len(parts) > 1 and parts[1] == 'movies' else 'scenes'
        scene_date = parts[2] if len(parts) > 2 else ''
        id_field = 'clip_id' if scene_type == 'scenes' else 'movie_id'

        api_key = await self._get_api_key(site)
        hits = await self._algolia(site, api_key, f'all_{scene_type}', f'filters={id_field}={scene_id}')
        if not hits:
            return None
        d = hits[0]

        url_title = d.get('url_title') or ''
        scene_list: list[dict[str, Any]] = []
        if url_title:
            scene_list = sorted(
                await self._algolia(site, api_key, 'all_scenes', f'query={quote(url_title)}'),
                key=lambda h: h.get('clip_id') or 0,
            )
        return LoadedScene(
            url=site.base_url,
            site=site,
            scene_date=(iso_date(scene_date) or scene_date) if scene_date else None,
            subsite=ctx.subsite if ctx else None,
            extra={'d': d, 'scene_list': scene_list, 'scene_id': scene_id, 'scene_type': scene_type, 'api_key': api_key},
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        base_lower = site.base_url.lower()
        d: dict[str, Any] = scene.extra['d']
        scene_list: list[dict[str, Any]] = scene.extra['scene_list']
        scene_id: str = scene.extra['scene_id']
        scene_type: SceneType = scene.extra['scene_type']
        api_key: str = scene.extra['api_key']
        url_title = d.get('url_title') or ''

        title = ''
        if 'dogfart' in base_lower:
            title = f'{d.get("title") or ""} from {d.get("serie_name") or ""}.com'
        elif scene_type == 'scenes' and len(scene_list) > 1 and 'filthykings' not in base_lower:
            for i, s in enumerate(scene_list):
                if s.get('clip_id') == int(scene_id):
                    title = f'{d.get("title") or ""}, Scene {i + 1}'
        if not title:
            title = d.get('title') or ''

        summary = (d.get('description') or '').replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n').strip()

        if not d.get('network_name'):
            if 'filthykings' in base_lower:
                studio = normalize_studio(d.get('sitename_pretty') or '', site.name)
            else:
                studio = normalize_studio(d.get('studio_name') or '', site.name).replace('DFXtra', 'DogFart Network')
        else:
            studio = normalize_studio(d['network_name'], site.name).replace('DFXtra', 'DogFart Network')

        collections: list[str] = []
        tagline: str | None = None

        def add_collection(c: str) -> None:
            if c and c not in collections:
                collections.append(c)

        if not d.get('network_name'):
            if 'filthykings' in base_lower or 'touchmywife' in base_lower:
                tagline = title_case(d.get('serie_name') or '', site_name=site.name) or None
                if tagline:
                    add_collection(tagline)
            elif d.get('studio_name'):
                add_collection(normalize_studio(d['studio_name'], site.name))
        elif d.get('serie_name'):
            tagline = normalize_studio(title_case(d['serie_name'].replace('Devils Film', "Devil's Film"), site_name=site.name), site.name)
            add_collection(tagline)
            add_collection(studio)
        elif d.get('studio_name'):
            add_collection(normalize_studio(title_case(d['studio_name'].replace('Devils Film', "Devil's Film"), site_name=site.name), site.name))

        if env.phoenix_extra_collections:
            for field in ('studio_name', 'serie_name'):
                v = d.get(field)
                if v:
                    add_collection(title_case(v.replace('Devils Film', "Devil's Film"), site_name=site.name))
            t = d.get('title') or ''
            if (':' in t or '#' in t) and len(scene_list) > 1 and d.get('movie_title'):
                add_collection(d['movie_title'])

        genres: list[str] = []

        def add_genre(g: str | None) -> None:
            if g and g not in genres:
                genres.append(g)

        for c in d.get('categories') or []:
            add_genre(c.get('name'))
        if scene_type == 'movies':
            for s in scene_list:
                for c in s.get('categories') or []:
                    add_genre(c.get('name'))

        female: list[ActorResult] = []
        male: list[ActorResult] = []
        for a in d.get('actors') or []:
            name = a.get('name')
            if not name:
                continue
            photo = ''
            if a.get('actor_id'):
                actor_hits = await self._algolia(site, api_key, 'all_actors', f'filters=actor_id={a["actor_id"]}')
                pics = actor_hits[0].get('pictures') if actor_hits else None
                if isinstance(pics, dict) and pics:
                    max_quality = sorted(pics.keys())[-1]
                    photo = f'{_IMG_BASE}/actors{pics[max_quality]}'
            entry = ActorResult(name=name, photo_url=photo, gender='female' if a.get('gender') == 'female' else 'male')
            (female if a.get('gender') == 'female' else male).append(entry)
        actors = [*female, *male, *_actor_overrides(scene_id)]

        raw_images: list[str] = []

        def push_img(u: str) -> None:
            if u and u not in raw_images:
                raw_images.append(u)

        skip_front = base_lower.rstrip('/').endswith('girlsway.com') or base_lower.rstrip('/').endswith('puretaboo.com')
        if not skip_front and d.get('movie_id') is not None:
            slug = url_title.lower().replace('-', '_')
            if slug:
                push_img(f'{_IMG_BASE}/movies/{d["movie_id"]}/{d["movie_id"]}_{slug}_front_400x625.jpg')
            if d.get('url_movie_title'):
                movie_slug = d['url_movie_title'].lower().replace('-', '_')
                push_img(f'{_IMG_BASE}/movies/{d["movie_id"]}/{d["movie_id"]}_{movie_slug}_front_400x625.jpg')

        picture_url = self._pick_picture(d.get('pictures'))
        if picture_url:
            if scene_type == 'movies':
                push_img(picture_url)
            else:
                raw_images.insert(0, picture_url)

        metadata.title = title
        metadata.summary = summary
        metadata.studio = studio
        metadata.tagline = tagline
        metadata.collections = collections or None
        metadata.genres = genres
        metadata.actors = actors
        metadata.raw_image_urls = raw_images

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _get_api_key(self, site: ResolvedSiteInfo) -> str:
        host = urlsplit(site.base_url).netloc

        async def _fetch() -> tuple[str, float] | None:
            base = site.base_url.rstrip('/')
            text = ''
            for path in ('/en/login', '/en'):
                try:
                    r = await self.http.get(base + path)
                    if r.status_code < 400:
                        text = r.text
                        break
                except httpx2.HTTPError:
                    continue
            m = re.search(r'"apiKey":"(.*?)"', text)
            key = m.group(1) if m else ''
            return (key, float('inf')) if key else None

        return await _API_KEYS.get(host, _fetch) or ''

    async def _algolia(self, site: ResolvedSiteInfo, api_key: str, index_name: str, params: str) -> list[dict[str, Any]]:
        url = f'{site.search_path}?x-algolia-application-id={_ALGOLIA_APP_ID}&x-algolia-api-key={api_key}'
        try:
            r = await self.http.post(
                url,
                json={'requests': [{'indexName': index_name, 'params': params}]},
                headers={'Content-Type': 'application/json', 'Referer': site.base_url},
            )
            if r.status_code >= 400:
                return []
            data = r.json()
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn(site.name, f'Algolia {index_name} query failed: {err}')
            return []
        hits = (data.get('results') or [{}])[0].get('hits')
        return hits or []

    def _pick_picture(self, pictures: Any) -> str:
        if not isinstance(pictures, dict):
            return ''
        nsfw = pictures.get('nsfw')
        top = nsfw.get('top') if isinstance(nsfw, dict) else None
        if not isinstance(top, dict) or not top:
            return ''
        key = next(iter(top.keys()), None)
        path = pictures.get(key) if key else None
        return f'{_IMG_BASE}/movies/{path}' if isinstance(path, str) else ''
