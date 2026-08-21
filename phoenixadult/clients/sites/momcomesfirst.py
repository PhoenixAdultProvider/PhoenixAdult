from __future__ import annotations

import re
from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import iso_date, load_data
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.processors.actor_strip import enabled_for, strip_actor_prefix
from phoenixadult.utils.processors.title_case import title_case

_ACTORS: set[str] = set(load_data(__file__, 'momcomesfirst_actors'))


class MomComesFirstClient(Client):
    search_url_xpath = '(.//h2//a/@href)[1]'
    title_xpath = '//h1'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        cleaned = ' '.join(search_data.title.replace('sons', '').replace('mothers', '').replace('moms', '').split())
        title_no_actors = (strip_actor_prefix(cleaned) if enabled_for(search_data.site_info) else cleaned).lower()
        encoded = title_no_actors.replace(' ', '+').replace("'", '')
        search_results = await self.fetch_and_load(f'{base}/?s={encoded}', FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//article'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/h2')

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date(first_text(source, './/p//span'), '%b %d, %Y')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts: list[str] = []
        for p in details_page_elements.xpath('//div[contains(@class,"entry-content")]//p'):
            t = first_attr(p, 'normalize-space(.)')
            if t and 'starring' not in t.lower():
                parts.append(t)

        metadata.summary = '\n'.join(parts) or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Mom Comes First'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Mom Comes First']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"published")]')

        metadata.release_date = (iso_date(date, '%b %d, %Y') if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//a[contains(@rel,"tag")]'):
            genre_name = title_case(first_attr(genre_link, 'normalize-space(.)'))
            if genre_name and genre_name.lower() not in _ACTORS and genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        names: list[str] = []
        for actor_link in details_page_elements.xpath('//a[contains(@rel,"tag")]'):
            g = title_case(first_attr(actor_link, 'normalize-space(.)'))
            if g and g.lower() in _ACTORS:
                names.append(g)

        paras = details_page_elements.xpath('//div[contains(@class,"entry-content")]//p')
        if paras:
            last_p = paras[-1].xpath('normalize-space(.)').get() or ''
            if 'starring' in last_p.lower():
                tail = re.split(r'starring', last_p, maxsplit=1, flags=re.IGNORECASE)[-1].split('*')[0]
                names.extend(n.strip() for n in tail.split('&'))

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_name in names:
            actor_name = actor_name.strip()
            if actor_name and actor_name.lower() not in seen:
                seen.add(actor_name.lower())
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors
