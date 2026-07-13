from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//div[contains(@class,"video_detail")]//span[contains(@id,"ContentPlaceHolder1_LabelTitle")]'
_RELEASED_XP = '//div[contains(@class,"video_detail")]//span[contains(@id,"ContentPlaceHolder1_LabelReleased")]'
_ACTORS_XP = '//div[contains(@class,"video_detail")]//div[contains(@class,"right")]//div[contains(@class,"actors_list")]//div[contains(@class,"actor")]//a'
_VIDEO_ID_RE = re.compile(r'VideoID=([^&]+)')


class BelAmiClient(Client):
    async def load_search_context(self, ctx: SearchContext) -> LoadedSearch | None:
        scene_id = ctx.title.strip().split()[0] if ctx.title.strip() else ''
        if not scene_id:
            return None
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', quote(scene_id, safe=''))
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
        if not loaded:
            return None
        if not first_text(loaded['sel'], _TITLE_XP):
            return None
        return LoadedSearch(ctx=ctx, site=ctx.site_info, sources=[loaded['sel']], capture=ctx.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = first_text(scene.sel, _TITLE_XP)

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_text(scene.sel, '(//div[contains(@class,"video_detail")]//div[contains(@class,"bottom")]//p)[2]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Bel Ami Online'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _RELEASED_XP)
        metadata.release_date = iso_date(raw, '%m/%d/%Y') if raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        tags_xp = '//div[contains(@class,"video_detail")]//span[contains(@id,"ContentPlaceHolder1_LabelTags")]//a'
        for a in scene.sel.xpath(tags_xp):
            g = first_attr(a, 'normalize-space(.)')
            if g and g not in genres:
                genres.append(g)
        actor_count = len(scene.sel.xpath(_ACTORS_XP))
        if actor_count == 3 and 'Threesome' not in genres:
            genres.append('Threesome')
        elif actor_count == 4 and 'Foursome' not in genres:
            genres.append('Foursome')
        elif actor_count > 4 and 'Orgy' not in genres:
            genres.append('Orgy')
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath(_ACTORS_XP):
            name = first_attr(a, 'normalize-space(.)')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = first_attr(a, '(.//img/@src)[1]')
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        m = _VIDEO_ID_RE.search(scene.url)
        if not m:
            return
        metadata.raw_image_urls = [f'https://freecdn.belamionline.com/Data/Contents/Content_{m.group(1)}/Thumbnail8.jpg']
