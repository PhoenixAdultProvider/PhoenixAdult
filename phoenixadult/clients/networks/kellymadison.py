from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr

STUDIO = 'Kelly Madison Productions'
_NATS_COOKIE = 'nats=MC4wLjMuNTguMC4wLjAuMC4w'

_POSTER_TEMPLATES: list[str] = [
    'https://tour-content-cdn.kellymadisonmedia.com/episode/poster_image/{slug}/poster.jpg',
    'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/{slug}/1.jpg',
    'https://tour-content-cdn.kellymadisonmedia.com/episode/episode_thumb_image_1/{slug}/01.jpg',
]


def _tagline_from_title(title: str, site_name: str) -> str:
    lc = title.lower()
    if 'teenfidelity' in lc:
        return 'TeenFidelity'

    if 'kelly madison' in lc:
        return 'Kelly Madison'

    return site_name


class KellyMadisonClient(Client):
    title_xpath = '(//h1[contains(@class,"title")])[1]'
    summary_xpath = '(//div[contains(.,"Episode Summary")]/p)[1]'

    def __init__(self) -> None:
        super().__init__({'Cookie': _NATS_COOKIE})

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        scene_id = search_data.scene_id or ''
        if not scene_id and search_data.full_title:
            first_tok = search_data.full_title.strip().split()[0] if search_data.full_title.strip() else ''
            stripped = re.sub(r'^e', '', first_tok, flags=re.IGNORECASE)
            if stripped and stripped.isdigit():
                scene_id = stripped

        url = search_data.search_url(quote(search_data.title.strip()))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//a[contains(@class,"video-card")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture, extra={'scene_id': scene_id})

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h3)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = (source.xpath('(.//time)[1]').xpath('string(.)').get() or '').strip()
        return iso_date(raw, '%m/%d/%y') if raw else loaded.ctx.search_date

    async def fetch_search_score(self, source: Any, loaded: LoadedSearch) -> float | None:
        scene_id = (loaded.extra or {}).get('scene_id') or ''
        if not scene_id:
            return None

        episode_id = (source.xpath('(.//span[contains(@class,"video-title")])[1]').xpath('string(.)').get() or '').split('#')[-1].strip()
        href = first_attr(source, '@href')
        scene_url = absolute_url(href, loaded.site.base_url) if href else ''
        search_id = scene_url.rstrip('/').split('/')[-1]
        return 100 if scene_id in (episode_id, search_id) else None

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        raw = (details_page_elements.xpath('(//h1[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
        return _tagline_from_title(raw, scene.site.name)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_of(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_of(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//p[contains(.,"Published")]//strong)[1]').xpath('string(.)').get() or '').strip()
        if date:
            metadata.release_date = iso_date(date, '%Y-%m-%d') or iso_date(date)
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = ['Hardcore', 'Heterosexual']
        cast = len(details_page_elements.xpath('//p[contains(.,"Starring")]//a[contains(@href,"/models/")]'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//div[contains(@class,"one")]//img)[1]/@src', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//p[contains(.,"Starring")]//a[contains(@href,"/models/")]'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        slug = scene.url.rstrip('/').split('/')[-1]
        if not slug:
            return

        metadata.art = [t.replace('{slug}', slug) for t in _POSTER_TEMPLATES]
