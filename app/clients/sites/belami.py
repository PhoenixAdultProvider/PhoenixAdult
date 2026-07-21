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
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        scene_id = search_data.title.strip().split()[0] if search_data.title.strip() else ''
        if not scene_id:
            return None

        base = search_data.site_info.base_url.rstrip('/')
        scene_url = base + search_data.site_info.search_path.replace('{query}', quote(scene_id, safe=''))
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return None

        if not first_text(direct_page_elements['sel'], _TITLE_XP):
            return None

        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=[direct_page_elements['sel']], capture=search_data.capture, extra=scene_url)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, _TITLE_XP)

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        return str(loaded.extra)

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        return 100

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP)

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '(//div[contains(@class,"video_detail")]//div[contains(@class,"bottom")]//p)[2]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Bel Ami Online'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, _RELEASED_XP)

        metadata.release_date = iso_date(date, '%m/%d/%Y') if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        tags_xp = '//div[contains(@class,"video_detail")]//span[contains(@id,"ContentPlaceHolder1_LabelTags")]//a'
        for genre_link in details_page_elements.xpath(tags_xp):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        actor_count = len(details_page_elements.xpath(_ACTORS_XP))
        if (group := self.group_genre_for(actor_count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_ACTORS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = first_attr(actor_link, '(.//img/@src)[1]')
            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        m = _VIDEO_ID_RE.search(scene.url)
        if not m:
            return

        metadata.art = [f'https://freecdn.belamionline.com/Data/Contents/Content_{m.group(1)}/Thumbnail8.jpg']
