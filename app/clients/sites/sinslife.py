from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from app.utils.helpers.helpers import absolute_url, iso_date
from app.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'SinsLife'

_SUMMARY_XP = '//div[4]/div/div[2]/div/div/div[2]/div[2]/p'
_DATE_XP = '//div[4]/div/div[2]/div/div/div[2]/div[1]/div/div[1]'
_ACTORS_XP = '//div[4]/div/div[2]/div/div/div[2]/div[3]/ul/li'
_POSTER_XP = '//div[4]/div/div[2]/div/div/div[1]/div[2]/div/div[1]/img'
_SEARCH_CARD_XP = '//div[4]/div/div[3]/div/div'


class SinsLifeClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_SEARCH_CARD_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a/@title)[1]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"section")]//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, _SUMMARY_XP) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, _DATE_XP)
        if date.lower().startswith('release date'):
            date = date[len('release date') :].lstrip(': ').strip()

        metadata.release_date = iso_date(date, '%B %d, %Y') if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        count = len(details_page_elements.xpath(_ACTORS_XP))
        group = self.group_genre_for(count)

        metadata.genres = [group] if group else []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_ACTORS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if actor_name and actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        src = (details_page_elements.xpath(_POSTER_XP + '/@src').get() or '').strip()
        if not src:
            return

        metadata.art = [src if src.startswith('http') else f'https:{src}']
