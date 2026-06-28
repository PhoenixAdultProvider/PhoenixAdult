from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_TITLE_SUFFIX = ' - Sex Movies Featuring Melena Maria Rya'


def _clean_title(raw: str, strip_four_k: bool) -> str:
    t = re.sub(r'[^A-Za-z0-9\s-]', ' ', raw.split(_TITLE_SUFFIX)[0]).strip()
    if strip_four_k:
        t = re.sub(r'\s+4\s*K(?:\s+Video)?$', '', t, flags=re.IGNORECASE).strip()
    return t


class MelenaMariaRyaClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.title.strip().split()[0] if ctx.title.strip() else ''
        if not scene_id:
            return []
        scene_url = f'{base}{ctx.site_info.search_path}{scene_id}'

        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] sceneID {scene_id}')
        if not loaded:
            return []
        title = _clean_title(first_text(loaded['sel'], '//title'), False)
        if not title:
            return []
        return [
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=ctx.title,
                search_date=ctx.search_date,
                score=100,
                cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
            )
        ]

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _clean_title(first_text(scene.sel, '//title'), True) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_attr(scene.sel, '//meta[@name="description"]/@content') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Melena Maria Rya'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return ['European']

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors = [ActorResult(name='Melena Maria Rya', photo_url='', gender='')]
        co_star = re.search(r' with ([A-Za-z]+ [A-Za-z]+)$', _clean_title(first_text(scene.sel, '//title'), True), re.IGNORECASE)
        if co_star:
            actors.append(ActorResult(name=co_star.group(1), photo_url='', gender=''))
        return actors
