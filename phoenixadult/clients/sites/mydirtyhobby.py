from __future__ import annotations

import json
import re
from typing import Any

import httpx2

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.response_trace import trace_response

_SUPPORTED_LANGS = {'en', 'de', 'fr', 'es', 'it'}
_SLUG_RE = re.compile(r'[^A-Za-z0-9-]+')
_TRIM_DASH_RE = re.compile(r'^-+|-+$')
_JSON_RE = re.compile(r'\{[\s\S]*\}')


def _primary_lang(language: str | None) -> str:
    return language.lower().split('-')[0] if language else ''


def _slug(s: str) -> str:
    return _TRIM_DASH_RE.sub('', _SLUG_RE.sub('-', s))


class MyDirtyHobbyClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        search_url = base + search_data.site_info.search_path
        lang = _primary_lang(search_data.language) or 'en'
        try:
            r = await self.http.post(
                search_url,
                json={'country': 'us', 'keyword': search_data.title, 'user_language': lang},
                headers={'Content-Type': 'application/json', 'Accept-Language': lang},
            )
            trace_response(r)
            items = (r.json() or {}).get('items', [])
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn(search_data.site_info.name, f'search POST threw: {err}')
            return

        for item in items:
            if item.get('contentType') != 'video':
                continue

            title = str(item.get('title') or '')
            if not title:
                continue

            scene_url = f'{base}/profil/{item.get("u_id")}-{item.get("nick")}/videos/{item.get("uv_id")}-{_slug(title)}'
            date = None
            if item.get('onlineAt'):
                date = iso_date(str(item['onlineAt']), '%d/%m/%y') or iso_date(str(item.get('latestPictureChange') or '').split('T')[0])

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Context Loader (detail JSON embedded in the scene HTML) ───────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        lang = _primary_lang(ctx.language if ctx else None)
        headers = {'Referer': site.base_url, 'Cookie': 'AGEGATEPASSED=1'}
        fetch_url = url
        if lang in _SUPPORTED_LANGS:
            fetch_url = url.replace('://www.', f'://{lang}.')
            headers['Accept-Language'] = lang

        details_page_elements = await self.fetch_and_load(
            fetch_url, FetchCtx(capture=ctx.capture if ctx else None, headers=headers, use_bypass=site.use_bypass), f'[{site.name}] detail {fetch_url}'
        )
        if not details_page_elements:
            return None

        script_text = details_page_elements['sel'].xpath('string((//div[./div[@id="profile_page"]]/script)[1])').get() or ''
        m = _JSON_RE.search(script_text)
        if not m:
            return None

        try:
            extra = json.loads(m.group(0))
        except (ValueError, TypeError):
            return None

        return LoadedScene(
            url=fetch_url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra=extra,
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _content(self, scene: LoadedScene) -> dict[str, Any]:
        return (scene.extra or {}).get('content', {}) if isinstance(scene.extra, dict) else {}

    def _avatar(self, scene: LoadedScene) -> dict[str, Any]:
        if not isinstance(scene.extra, dict):
            return {}

        return (scene.extra.get('profileHeader') or {}).get('profileAvatar') or {}

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = ((self._content(scene).get('title') or {}).get('text') or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = ((self._content(scene).get('description') or {}).get('text') or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'My Dirty Hobby'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = (self._avatar(scene).get('title') or '').strip()

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        name = (self._avatar(scene).get('title') or '').strip()

        metadata.collections = [name] if name else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        date = ((self._content(scene).get('subtitle') or {}).get('text') or '').strip()

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        items = (self._content(scene).get('categories') or {}).get('items') or []
        values: list[str | None] = [(it.get('text') or '').strip().lower() for it in items]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        avatar = self._avatar(scene)
        actor_name = (avatar.get('title') or '').strip()
        if not actor_name:
            return

        photo = ((avatar.get('thumbImg') or {}).get('src') or '').strip()

        metadata.actors = [ActorResult(name=actor_name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        src = ((self._content(scene).get('videoNotPurchased') or {}).get('thumbnail') or {}).get('src')
        src = (src or '').strip()

        metadata.art = [src] if src else []
