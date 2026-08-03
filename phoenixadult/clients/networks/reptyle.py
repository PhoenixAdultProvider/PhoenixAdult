from __future__ import annotations

import json
import re
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, slugify
from phoenixadult.utils.helpers.html_helpers import strip_tags
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.episode_tag import strip_episode_tag

_STATE_RE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.DOTALL)
_DATA18_PROVIDERS = ['TeamSkeet', 'MYLF', 'Family Strokes', 'Pervz', 'FreeUse', 'Swappz']
_MODEL_SLUG_TRIES = 8


def _normalize(s: str) -> str:
    return re.sub(r'\W', '', s).lower()


def _model_name_candidates(title: str) -> list[str]:
    segments: list[list[str]] = [[]]
    for word in title.split():
        if word.lower() == 'and':
            segments.append([])
        else:
            segments[-1].append(word)
    out: list[str] = []
    for seg in segments:
        if len(seg) <= 4:
            out.append(' '.join(seg))
        for n in (2, 3, 4):
            if len(seg) > n:
                out.append(' '.join(seg[:n]))
                out.append(' '.join(seg[n:]))
    return list(dict.fromkeys(c for c in out if c))


def _strip_tags(html: str) -> str:
    s = strip_tags(html)
    if s and s[-1] not in '.!?':
        s += '.'

    return s


class ReptyleClient(Client):
    def __init__(self) -> None:
        super().__init__(
            {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Cookie': 'age_verified=yes',
            }
        )

    async def _fetch_initial_state(self, url: str, capture: list[RawCaptureEntry] | None) -> dict[str, Any] | None:
        try:
            r = await self.http.get(url)
        except Exception as err:  # noqa: BLE001 - network failure yields no state
            logger.warn('Reptyle', f'fetchInitialState failed for {url}: {err}')
            return None

        m = _STATE_RE.search(r.text)
        if not m:
            return None

        try:
            parsed = json.loads(m.group(1))
        except ValueError:
            return None

        if capture is not None:
            capture.append(RawCaptureEntry(f'__INITIAL_STATE__ from {url}', 'json', parsed))

        content = parsed.get('content') if isinstance(parsed, dict) else None
        return content if isinstance(content, dict) else None

    def _pick_scene(self, state: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
        for t in ('moviesContent', 'videosContent'):
            bucket = state.get(t)
            if isinstance(bucket, dict) and bucket:
                cur = next(iter(bucket))
                return cur, t, bucket[cur]

        return None

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = slugify(search_data.title.replace("'", ''))
        if not slug:
            return

        site = search_data.site_info
        search_page_url = site.base_url.rstrip('/') + site.search_path.replace('{query}', slug)
        state = await self._fetch_initial_state(search_page_url, search_data.capture)
        picked = self._pick_scene(state) if state else None
        await self._search_model_page(results, search_data)
        if not picked:
            return

        cur, scene_type, scene_json = picked
        canonical = str(scene_json.get('id') or cur)
        result_url = site.base_url.rstrip('/') + site.search_path.replace('{query}', canonical) if canonical != cur else search_page_url
        self._add_result(results, search_data, scene_json, scene_type, canonical, result_url)

    async def _search_model_page(self, results: list[SearchResult], search_data: SearchContext) -> None:
        site = search_data.site_info
        base = site.base_url.rstrip('/')
        tried: set[str] = set()
        for candidate in _model_name_candidates(search_data.title):
            model_slug = slugify(candidate.replace("'", ''))
            if not model_slug or model_slug in tried or len(tried) >= _MODEL_SLUG_TRIES:
                continue

            tried.add(model_slug)
            state = await self._fetch_initial_state(f'{base}/models/{model_slug}', search_data.capture)
            models = (state or {}).get('modelsContent')
            entry = next((v for v in models.values() if isinstance(v, dict) and v.get('movies')), None) if isinstance(models, dict) else None
            if entry is None:
                continue

            for movie in entry['movies']:
                if not isinstance(movie, dict) or not movie.get('id'):
                    continue

                movie_id = str(movie['id'])
                scene_type = 'videosContent' if movie.get('type') == 'video' else 'moviesContent'
                self._add_result(results, search_data, movie, scene_type, movie_id, base + site.search_path.replace('{query}', movie_id))

            return

    def _add_result(
        self, results: list[SearchResult], search_data: SearchContext, scene_json: dict[str, Any], scene_type: str, canonical: str, result_url: str
    ) -> None:
        cur_id = self.encode(f'{canonical}|{scene_type}|{result_url}')
        if any(r.cur_id == cur_id for r in results):
            return

        release_date = iso_date(scene_json['publishedDate']) if scene_json.get('publishedDate') else None
        sub_site = ((scene_json.get('site') or {}).get('name') or '').strip()
        result_sub = sub_site if sub_site and _normalize(sub_site) != _normalize(search_data.site_info.name) else None

        results.append(
            build_search_result(
                title=strip_episode_tag(scene_json.get('title') or ''),
                scene_url=result_url,
                query=search_data.title,
                site=search_data.site_info,
                cur_id=cur_id,
                thumb_url=scene_json.get('img'),
                search_date=search_data.search_date,
                display_date=release_date,
                subsite=result_sub,
            )
        )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        scene_id = parts[0]
        scene_type = parts[1] if len(parts) > 1 else 'moviesContent'
        url = parts[2] if len(parts) > 2 else ''
        if not url:
            return None

        capture = ctx.capture if ctx else None

        state = await self._fetch_initial_state(url, capture)
        if not state:
            return None

        bucket = state.get(scene_type) or state.get('moviesContent') or state.get('videosContent') or {}
        scene_json = bucket.get(scene_id)
        if not isinstance(scene_json, dict):
            return None

        return LoadedScene(url=url, site=site, capture=capture, extra=scene_json, subsite=ctx.subsite if ctx else None)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        scene_json = scene.extra
        capture = scene.capture
        sub_site = ((scene_json.get('site') or {}).get('name') or '').strip() or site.name
        has_sub = bool(sub_site) and sub_site != site.name

        # Title
        metadata.title = strip_episode_tag(scene_json.get('title') or '')

        # Summary
        metadata.summary = _strip_tags(scene_json.get('description') or '')

        # Studio
        metadata.studio = site.name

        # Tagline and Collection(s)
        metadata.tagline = sub_site if has_sub else ''
        metadata.collections = [sub_site] if has_sub else [site.name]

        # Release Date
        metadata.release_date = iso_date(scene_json['publishedDate']) if scene_json.get('publishedDate') else None

        # Actor(s)
        for m in scene_json.get('models') or []:
            mid = m.get('modelId') or m.get('id') or ''
            name = m.get('modelName') or m.get('name') or ''
            if not name:
                continue

            photo, gender = '', ''
            if mid:
                mstate = await self._fetch_initial_state(f'{site.base_url.rstrip("/")}/models/{mid}', capture)
                entry = ((mstate or {}).get('modelsContent') or {}).get(mid) if mstate else None
                if isinstance(entry, dict):
                    photo = entry.get('img') or ''
                    gender = entry.get('gender') or ''

            metadata.actors.append(ActorResult(name=name, photo_url=photo, gender=gender))

        # Genres
        genres = [t.strip() for t in (scene_json.get('tags') or []) if t.strip()]
        if len(metadata.actors) > 1 and sub_site != 'Mylfed':
            genres.append('Threesome')

        metadata.genres = genres

        # Posters
        if scene_json.get('img'):
            metadata.art.append(scene_json['img'])

        # Posters from Data18
        sid = scene_json.get('id')
        search_sub = (sub_site if sub_site != site.name else None) or scene.subsite
        mapping_sub = sub_site or scene.subsite or site.name
        mapping_id = (f'{sid}-{_normalize(mapping_sub)}' if mapping_sub else str(sid)) if sid is not None else None
        providers = [*_DATA18_PROVIDERS, *([search_sub] if search_sub else [])]
        await self.enrich_from_data18(metadata, site, scene_id=mapping_id, providers=providers)
