from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.clients.aggregators.data18 import Data18Client
from app.clients.base import ActorResult, Client, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import iso_date, slugify
from app.utils.helpers.html_helpers import strip_tags
from app.utils.logging.logger import logger

_STATE_RE = re.compile(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', re.DOTALL)
_DATA18_PROVIDERS = ['TeamSkeet', 'MYLF', 'Family Strokes', 'Pervz', 'FreeUse', 'Swappz']


def _normalize(s: str) -> str:
    return re.sub(r'\W', '', s).lower()


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
        self._data18: Data18Client | None = None

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

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        slug = slugify(ctx.title.replace("'", ''))
        if not slug:
            return []
        url = ctx.site_info.base_url.rstrip('/') + ctx.site_info.search_path.replace('{query}', slug)
        state = await self._fetch_initial_state(url, ctx.capture)
        if not state:
            return []
        picked = self._pick_scene(state)
        if not picked:
            return []
        cur, scene_type, scene_json = picked
        composite = f'{cur}|{scene_type}|{url}'
        release_date = iso_date(scene_json['publishedDate']) if scene_json.get('publishedDate') else None
        return [
            SearchResult(
                title=scene_json.get('title') or '',
                scene_url=url,
                cur_id=self.encode(composite),
                thumb_url=scene_json.get('img'),
                release_date=release_date or ctx.search_date or None,
                display_date=release_date,
            )
        ]

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
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

        sub_site = ((scene_json.get('site') or {}).get('name') or '').strip() or site.name
        title = (scene_json.get('title') or '').strip()
        summary = _strip_tags(scene_json.get('description') or '')
        release_date = iso_date(scene_json['publishedDate']) if scene_json.get('publishedDate') else None

        actors: list[ActorResult] = []
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
            actors.append(ActorResult(name=name, photo_url=photo, gender=gender))

        genres = [t.strip() for t in (scene_json.get('tags') or []) if t.strip()]
        if len(actors) > 1 and sub_site != 'Mylfed':
            genres.append('Threesome')

        raw_images: list[str] = []
        if scene_json.get('img'):
            raw_images.append(scene_json['img'])

        if site.scraper_config.data18_enrichment and env.data18_enabled:
            try:
                self._data18 = self._data18 or Data18Client()
                date_obj = datetime.fromisoformat(release_date) if release_date else None
                sid = scene_json.get('id')
                mapping_id = (f'{sid}-{_normalize(sub_site)}' if sub_site else str(sid)) if sid is not None else None
                providers = [*_DATA18_PROVIDERS, sub_site]
                data18_url = await self._data18.find_scene_url(mapping_id, title, providers, date_obj)
                if data18_url:
                    logger.info(site.name, f'data18 enrichment match: {data18_url}')
                    for u in await self._data18.fetch_images(data18_url):
                        if u not in raw_images:
                            raw_images.append(u)
            except Exception as err:  # noqa: BLE001 - enrichment is best-effort
                logger.warn(site.name, f'data18 enrichment failed: {err}')

        has_sub = bool(sub_site) and sub_site != site.name
        return SceneDetail(
            title=title,
            summary=summary,
            studio=site.name,
            tagline=sub_site if has_sub else None,
            release_date=release_date,
            collections=[sub_site] if has_sub else [site.name],
            genres=genres,
            actors=actors,
            raw_image_urls=raw_images,
        )
