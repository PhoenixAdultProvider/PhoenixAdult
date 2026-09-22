from __future__ import annotations

from urllib.parse import quote

import httpx2

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.auth.user_tokens import metadataapi_token
from phoenixadult.utils.helpers.dates import api_date
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.http.client import make_http

_API_BASE = 'https://api.theporndb.net'


def _auth_headers() -> dict[str, str]:
    token = metadataapi_token()
    return {'Accept': 'application/json', 'Authorization': f'Bearer {token}'} if token else {}


class MetadataAPIClient(Client):
    @property
    def http(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = make_http(self._extra_headers, verify=True)

        return self._http

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        url = f'{_API_BASE}/scenes?parse={search_data.encoded}'
        if search_data.ohash:
            url += f'&hash={quote(search_data.ohash)}'

        search_results = await self.fetch_json(url, FetchCtx(capture=search_data.capture), headers=_auth_headers(), label=f'GET {url}')
        if not isinstance(search_results, dict) or not search_results.get('data'):
            return

        for s in search_results['data']:
            scene_id = s.get('_id') or s.get('id')
            if not scene_id:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=s.get('title') or '',
                    scene_url=f'{_API_BASE}/scenes/{scene_id}',
                    query=search_data.title,
                    display_date=api_date(s.get('date')),
                    search_date=search_data.search_date,
                    subsite=((s.get('site') or {}).get('name') or '').strip() or None,
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        fallback_date = tail.strip()
        details_page_elements = await self.fetch_json(
            url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), headers=_auth_headers(), label=f'GET {url}'
        )
        d = details_page_elements.get('data') if isinstance(details_page_elements, dict) else None
        if not isinstance(d, dict):
            return None

        return LoadedScene(url=url, site=site, scene_date=fallback_date or None, capture=ctx.capture if ctx else None, extra=d)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        d = scene.extra
        site = scene.site
        headers = _auth_headers()

        # Title
        metadata.title = d.get('title') or ''

        # Summary
        metadata.summary = d.get('description') or ''

        site_obj = d.get('site') or {}
        studio = site_obj.get('name') or site.name
        collections: list[str] = [site_obj['name']] if site_obj.get('name') else []
        if site_obj.get('network_id') and site_obj.get('id') != site_obj.get('network_id'):
            parent = await self.fetch_json(f'{_API_BASE}/sites/{site_obj["network_id"]}', FetchCtx(capture=scene.capture), headers=headers)
            parent_name = (parent.get('data') or {}).get('name') if isinstance(parent, dict) else None
            if parent_name:
                studio = parent_name
                collections.append(parent_name)

        metadata.studio = studio
        metadata.collections = collections or None

        # Release Date
        metadata.release_date = api_date(d.get('date')) or scene.scene_date or None

        # Genres
        metadata.genres = [t['name'].strip() for t in (d.get('tags') or []) if (t.get('name') or '').strip()]

        # Actor(s)
        for p in d.get('performers') or []:
            name = p.get('name') or ''
            face = p.get('face') or ''
            photo = face if face and 'default' not in face else ''
            parent_p = p.get('parent') or {}
            if parent_p.get('name'):
                name = parent_p['name']
                photo = parent_p.get('face') or ''

            if name:
                metadata.actors.append(ActorResult(name=name, photo_url=photo))

        # Posters
        if (d.get('posters') or {}).get('large'):
            metadata.art.append(d['posters']['large'])

        if (d.get('background') or {}).get('large'):
            metadata.art.append(d['background']['large'])
