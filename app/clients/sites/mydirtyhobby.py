from __future__ import annotations

import json
import re
from typing import Any

import httpx2

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.logging.logger import logger

_SUPPORTED_LANGS = {'en', 'de', 'fr', 'es', 'it'}
_SLUG_RE = re.compile(r'[^A-Za-z0-9-]+')
_TRIM_DASH_RE = re.compile(r'^-+|-+$')
_JSON_RE = re.compile(r'\{[\s\S]*\}')


def _primary_lang(language: str | None) -> str:
    return language.lower().split('-')[0] if language else ''


def _slug(s: str) -> str:
    return _TRIM_DASH_RE.sub('', _SLUG_RE.sub('-', s))


class MyDirtyHobbyClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = base + ctx.site_info.search_path
        lang = _primary_lang(ctx.language) or 'en'
        try:
            r = await self.http.post(
                search_url,
                json={'country': 'us', 'keyword': ctx.title, 'user_language': lang},
                headers={'Content-Type': 'application/json', 'Accept-Language': lang},
            )
            items = (r.json() or {}).get('items', [])
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn(ctx.site_info.name, f'search POST threw: {err}')
            return []

        results: list[SearchResult] = []
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
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )
        return results

    # ── Context loader (detail JSON embedded in the scene HTML) ───────────────

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

        loaded = await self.fetch_and_load(fetch_url, FetchCtx(capture=ctx.capture if ctx else None, headers=headers), f'[{site.name}] detail {fetch_url}')
        if not loaded:
            return None
        script_text = loaded['sel'].xpath('string((//div[./div[@id="profile_page"]]/script)[1])').get() or ''
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
            sel=loaded['sel'],
            html=loaded['html'],
            extra=extra,
        )

    def _content(self, scene: LoadedScene) -> dict[str, Any]:
        return (scene.extra or {}).get('content', {}) if isinstance(scene.extra, dict) else {}

    def _avatar(self, scene: LoadedScene) -> dict[str, Any]:
        if not isinstance(scene.extra, dict):
            return {}
        return (scene.extra.get('profileHeader') or {}).get('profileAvatar') or {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return ((self._content(scene).get('title') or {}).get('text') or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return ((self._content(scene).get('description') or {}).get('text') or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'My Dirty Hobby'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return (self._avatar(scene).get('title') or '').strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        name = (self._avatar(scene).get('title') or '').strip()
        return [name] if name else None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        raw = ((self._content(scene).get('subtitle') or {}).get('text') or '').strip()
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        items = (self._content(scene).get('categories') or {}).get('items') or []
        values: list[str | None] = [(it.get('text') or '').strip().lower() for it in items]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        avatar = self._avatar(scene)
        name = (avatar.get('title') or '').strip()
        if not name:
            return []
        photo = ((avatar.get('thumbImg') or {}).get('src') or '').strip()
        return [ActorResult(name=name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        src = ((self._content(scene).get('videoNotPurchased') or {}).get('thumbnail') or {}).get('src')
        src = (src or '').strip()
        return [src] if src else []
