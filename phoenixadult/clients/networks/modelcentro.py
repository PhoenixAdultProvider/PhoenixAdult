from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo, normalize_site_key
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import api_date
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_LIST_QUERY = (
    'content.load?_method=content.load&tz=1&limit=512&transitParameters[v1]=OhUOlmasXD&transitParameters[v2]=OhUOlmasXD&transitParameters[preset]=videos'
)
_MODEL_QUERY = 'model.getModelContent?_method=model.getModelContent&tz=1&limit=25&transitParameters[contentId]='

_AH_RE = re.compile(r'"ah".?:.?"([0-9a-zA-Z()@:,/!+\-.$_=\\\']*)"')
_AET_RE = re.compile(r'"aet".?:([0-9]+)')

_LEAD_ACTORS: dict[str, str] = load_data(__file__, 'modelcentro_actors')


def _detail_query(scene_id: int) -> str:
    return (
        'content.load?_method=content.load&tz=1'
        f'&filter[id][fields][0]=id&filter[id][values][0]={scene_id}'
        '&limit=1&transitParameters[v1]=ykYa8ALmUD&transitParameters[preset]=scene'
    )


def _collection_items(collection: Any) -> list[Any]:
    if isinstance(collection, list):
        return collection

    if isinstance(collection, dict):
        return list(collection.values())

    return []


class ModelCentroClient(Client):
    async def _get_api_token(self, page_url: str, capture: list[RawCaptureEntry] | None) -> str | None:
        loaded = await self.fetch_and_load(page_url, FetchCtx(capture=capture), f'GET {page_url} (token)')
        if not loaded:
            return None

        html = loaded['html']
        ah = _AH_RE.search(html)
        aet = _AET_RE.search(html)
        if not ah or not aet:
            return None

        return ''.join(reversed(ah.group(1))) + '/' + aet.group(1) + '/'

    def _quote_token(self, token: str) -> str:
        return quote(token, safe="-_.!~*'()").replace('%2F', '/')

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        api_base = base + search_data.site_info.search_path

        scene_id = int(search_data.scene_id) if search_data.scene_id else None
        query = search_data.title.strip() or search_data.title

        token = await self._get_api_token(f'{base}/videos/', search_data.capture)
        if not token:
            return

        list_url = f'{api_base}{self._quote_token(token)}{_LIST_QUERY}'
        search_results = await self.fetch_json(list_url, FetchCtx(capture=search_data.capture))
        scenes = _collection_items(search_results.get('response', {}).get('collection') if isinstance(search_results, dict) else None)

        for scene in scenes:
            if not isinstance(scene, dict) or scene.get('id') is None or not scene.get('title'):
                continue

            sid = scene['id']
            sites = (scene.get('sites') or {}).get('collection') or {}
            date = api_date((sites.get(str(sid)) or {}).get('publishDate')) or ''
            art = [r.get('url', '') for r in ((scene.get('_resources') or {}).get('base') or []) if r.get('url')]
            payload = {'id': sid, 'title': scene['title'], 'releaseDate': date, 'art': art}

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=scene['title'].strip(),
                    scene_url=f'{base}/scene/{sid}/',
                    query=query,
                    display_date=date or None,
                    search_date=search_data.search_date,
                    score=100 if scene_id == sid else None,
                    cur_id=pack_cur_id([json.dumps(payload)]),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            parsed = json.loads(payload)
        except (ValueError, TypeError):
            return None

        sid = parsed['id']
        search_title = parsed.get('title', '')
        search_date = parsed.get('releaseDate', '')
        art = parsed.get('art') or []
        base = site.base_url.rstrip('/')
        api_base = base + site.search_path
        capture = ctx.capture if ctx else None

        token = await self._get_api_token(f'{base}/scene/{sid}/{quote(search_title)}', capture)
        if not token:
            return None

        quoted = self._quote_token(token)

        details_page_elements = await self.fetch_json(f'{api_base}{quoted}{_detail_query(sid)}', FetchCtx(capture=capture, use_bypass=site.use_bypass))
        scenes = _collection_items(details_page_elements.get('response', {}).get('collection') if isinstance(details_page_elements, dict) else None)
        if not scenes:
            return None

        scene = scenes[0]

        model_page_elements = await self.fetch_json(f'{api_base}{quoted}{_MODEL_QUERY}{sid}', FetchCtx(capture=capture, use_bypass=site.use_bypass))
        return LoadedScene(
            url=f'{base}/scene/{sid}/',
            site=site,
            capture=capture,
            extra={'sid': sid, 'search_title': search_title, 'search_date': search_date, 'art': art, 'scene': scene, 'model_body': model_page_elements},
            subsite=ctx.subsite if ctx else None,
        )

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        e = scene.extra
        sid = e['sid']
        search_title = e['search_title']
        search_date = e['search_date']
        art = e['art']
        scene_json = e['scene']
        model_body = e['model_body']

        sites = (scene_json.get('sites') or {}).get('collection') or {}
        date = api_date((sites.get(str(sid)) or {}).get('publishDate')) or search_date

        tags_are_actors = normalize_site_key(site.name) == normalize_site_key('Jerk Off with Me')
        tag_aliases = [
            alias for alias in ((t.get('alias') or '').strip() for t in _collection_items((scene_json.get('tags') or {}).get('collection'))) if alias
        ]

        actor_names: list[str] = []
        for entry in _collection_items(model_body.get('response', {}).get('collection') if isinstance(model_body, dict) else None):
            for model in _collection_items((entry.get('modelId') or {}).get('collection')):
                name = (model.get('stageName') or '').strip()
                if name:
                    actor_names.append(name)

        if tags_are_actors:
            actor_names.extend(alias.replace('-', ' ') for alias in tag_aliases)

        lead = _LEAD_ACTORS.get(site.name)
        if lead:
            actor_names.append(lead)

        # Title
        metadata.title = (scene_json.get('title') or search_title or '').strip()

        # Summary
        metadata.summary = (scene_json.get('description') or '').strip()

        # Studio
        metadata.studio = site.name

        # Tagline and Collection(s)
        metadata.collections = [site.name]

        # Release Date
        metadata.release_date = date or None

        # Genres
        metadata.genres = [] if tags_are_actors else tag_aliases

        # Actor(s)
        metadata.actors = [ActorResult(name=n) for n in dict.fromkeys(actor_names)]

        # Posters
        metadata.art = art
