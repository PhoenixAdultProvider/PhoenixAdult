from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'VIPissy'
_SEARCH_ROW_XP = '//div[contains(@style,"position:relative") and contains(@style,"background:black")]'
_TITLE_XP = '//section[contains(@class,"downloads")]//strong'
_SUMMARY_BLOCK_XP = '//section[4]/div'
_TAGS_BLOCK_XP = '//section[4]/div/p'
_TAGS_LINK_XP = '//section[4]/div/p//a'
_DATE_XP = '//section[2]//dl//dd[2]'
_ACTORS_XP = '//section[2]//dl//dd[1]//a'
_ACTOR_PHOTO_XP = '//section[1]/div/div[1]/img/@src'
_POSTERS_XP = '//div[contains(@id,"pics2")]//div//ul//li//div//div//img/@src'


class VIPissyClient(Client):
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath(_SEARCH_ROW_XP))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_attr(source, '(.//a/@title)[1]')

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//a/@href)[1]')
        if not href:
            return ''

        return absolute_url(href, loaded.site.base_url)

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        raw = first_text(source, './/span[contains(@class,"date")]')
        return iso_date(raw) if raw else None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        all_text = first_text(details_page_elements, _SUMMARY_BLOCK_XP)
        if not all_text:
            return

        tags = first_text(details_page_elements, _TAGS_BLOCK_XP)
        summary = all_text.replace(tags, '').strip() if tags else all_text

        metadata.summary = summary.split('Show more...')[0].strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, _DATE_XP)
        if date:
            parsed = iso_date(date, '%b %d, %Y') or iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath(_TAGS_LINK_XP):
            t = first_attr(genre_link, 'normalize-space(.)').lower()
            if t and t not in genres:
                genres.append(t)

        count = len(details_page_elements.xpath(_ACTORS_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = (sel.xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip()
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_ACTORS_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))

        idx = scene.url.find('/updates')
        if idx >= 0:
            images['push'](f'https://media.vipissy.com/videos{scene.url[idx + len("/updates") :]}cover/l.jpg')

        for image_url in details_page_elements.xpath(_POSTERS_XP).getall():
            images['push'](image_url)

        metadata.art = images['list']
