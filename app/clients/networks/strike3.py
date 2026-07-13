from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any

from app.clients.aggregators.data18 import Data18Client, mapping_slug
from app.clients.base import ActorResult, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.config.env import env
from app.registry import ResolvedSiteInfo
from app.utils.helpers.graphql_client import GraphQLClient
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id

# Strike3 (Vixen Media Group) is behind Cloudflare; space GraphQL calls a little.
_PACE_SECONDS = 1.0

_SEARCH_QUERY = (
    'query getSearchResults($query:String!,$site:Site!,$first:Int,$skip:Int)'
    '{searchVideos(input:{query:$query,site:$site,first:$first,skip:$skip})'
    '{edges{node{videoId title releaseDate slug images{listing{src}}}}}}'
)
_SEARCH_ID_QUERY = 'query getSearchResults($videoId:ID!,$site:Site!){findOneVideo(input:{videoId:$videoId,site:$site}){videoId title releaseDate slug}}'
_UPDATE_QUERY = (
    'query getSearchResults($slug:String!,$site:Site!)'
    '{findOneVideo(input:{slug:$slug,site:$site}){videoId title description releaseDate '
    'models{name slug images{listing{highdpi{double}}}}directors{name}categories{name}'
    'carousel{listing{highdpi{triple}}}}}'
)


class Strike3Client(GraphQLClient):
    def __init__(self, extra_headers: dict[str, str] | None = None) -> None:
        super().__init__(extra_headers)
        self._pace_lock = asyncio.Lock()
        self._last_fetch = 0.0
        self._data18: Data18Client | None = None

    async def _gql(self, endpoint: str, query: str, variables: dict[str, Any], base_url: str, label: str, sink: list[RawCaptureEntry] | None) -> Any:
        async with self._pace_lock:
            delta = time.monotonic() - self._last_fetch
            if delta < _PACE_SECONDS:
                await asyncio.sleep(_PACE_SECONDS - delta)
            self._last_fetch = time.monotonic()
            return await self.graphql(endpoint, query, variables, headers={'Referer': base_url}, capture_label=label, capture_sink=sink, use_bypass=True)

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        endpoint = f'{ctx.site_info.base_url.rstrip("/")}/graphql'
        site_var = ctx.site_info.name.replace(' ', '').upper()
        text = ctx.title.strip()
        scene_id = ctx.scene_id if ctx.scene_id and len(ctx.scene_id) > 4 else ''

        if scene_id:
            data = await self._gql(
                endpoint,
                _SEARCH_ID_QUERY,
                {'videoId': scene_id, 'site': site_var},
                ctx.site_info.base_url,
                f'[{ctx.site_info.name}] search id={scene_id}',
                ctx.capture,
            )
            v = data.get('findOneVideo') if isinstance(data, dict) else None
            if isinstance(v, dict) and v.get('slug') and v.get('title'):
                results.append(
                    build_search_result(
                        title=v['title'],
                        scene_url=v['slug'],
                        query=text,
                        display_date=iso_date(v.get('releaseDate') or ''),
                        search_date=ctx.search_date,
                        score=100 if str(v.get('videoId')) == scene_id else None,
                        cur_id=pack_cur_id([v['slug']]),
                    )
                )
            return

        data = await self._gql(
            endpoint,
            _SEARCH_QUERY,
            {'query': text, 'site': site_var, 'first': 10, 'skip': 0},
            ctx.site_info.base_url,
            f'[{ctx.site_info.name}] search "{text}"',
            ctx.capture,
        )
        edges = ((data.get('searchVideos') or {}).get('edges') or []) if isinstance(data, dict) else []
        for edge in edges:
            v = edge.get('node') if isinstance(edge, dict) else None
            if not isinstance(v, dict) or not v.get('slug') or not v.get('title'):
                continue
            results.append(
                build_search_result(
                    title=v['title'],
                    scene_url=v['slug'],
                    query=text,
                    display_date=iso_date(v.get('releaseDate') or ''),
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([v['slug']]),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        endpoint = f'{site.base_url.rstrip("/")}/graphql'
        sink = ctx.capture if ctx else None
        data = await self._gql(
            endpoint, _UPDATE_QUERY, {'slug': payload, 'site': site.name.replace(' ', '').upper()}, site.base_url, f'[{site.name}] detail {payload}', sink
        )
        v = data.get('findOneVideo') if isinstance(data, dict) else None
        if not isinstance(v, dict) or not v.get('title'):
            return None
        return LoadedScene(url=payload, site=site, capture=sink, extra=v)

    async def update(self, metadata: SceneDetail, scene: LoadedScene) -> None:
        site = scene.site
        v = scene.extra

        # Title
        metadata.title = v['title'].strip()

        # Summary
        metadata.summary = (v.get('description') or '').strip()

        # Studio
        metadata.studio = site.name

        # Collection(s)
        metadata.collections = [site.name]

        # Release Date
        metadata.release_date = iso_date(v.get('releaseDate') or '') or None

        # Genres
        genres: list[str] = []
        if site.name in ('Tushy', 'TushyRaw'):
            genres.append('Anal')
        for c in v.get('categories') or []:
            name = (c.get('name') or '').strip()
            if name and name not in genres:
                genres.append(name)
        metadata.genres = genres

        # Actor(s)
        for mdl in v.get('models') or []:
            name = (mdl.get('name') or '').strip()
            if not name:
                continue
            listing = (mdl.get('images') or {}).get('listing') or []
            photo = (listing[0].get('highdpi') or {}).get('double', '') if listing else ''
            metadata.actors.append(ActorResult(name=name, photo_url=photo))

        # Director(s)
        directors = [ActorResult(name=(d.get('name') or '').strip()) for d in (v.get('directors') or []) if (d.get('name') or '').strip()]
        metadata.directors = directors or None

        # Posters
        coll = self.image_collector()
        for img in v.get('carousel') or []:
            listing = img.get('listing') or []
            uri = (listing[0].get('highdpi') or {}).get('triple') if listing else None
            coll['push'](uri)
        metadata.raw_image_urls = coll['list']

        # Posters from Data18
        if site.scraper_config.data18_enrichment and env.data18_enabled:
            self._data18 = self._data18 or Data18Client()
            date_obj = datetime.fromisoformat(metadata.release_date) if metadata.release_date else None
            metadata.data18_url = await self._data18.enrich_images(
                scope=site.name,
                images=metadata.raw_image_urls,
                scene_id=mapping_slug(metadata.title, site.name),
                title=metadata.title,
                providers=[site.name],
                scene_date=date_obj,
            )
