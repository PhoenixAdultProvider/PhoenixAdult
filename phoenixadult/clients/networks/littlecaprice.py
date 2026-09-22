from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import absolute_first_attr, first_attr
from phoenixadult.utils.helpers.urls import absolute_url, join_url

_CATEGORY_TAGLINES: dict[str, str] = load_data(__file__, 'littlecaprice_category_taglines')


class LittleCapriceClient(Client):
    summary_xpath = '(//div[contains(@class,"desc-text")])[1]'
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = f'{base}/?s={search_data.encoded}'
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[@id="left-area"]/article'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return (source.xpath('(.//h2[contains(@class,"entry-title")]/a)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_search_scene_url(self, source: Any, loaded: LoadedSearch) -> str:
        href = first_attr(source, '(.//h2[contains(@class,"entry-title")]/a)[1]/@href')
        return absolute_url(href, loaded.site.base_url) if href else ''

    async def fetch_search_date(self, source: Any, loaded: LoadedSearch) -> str | None:
        return iso_date((source.xpath('(.//span[contains(@class,"published")])[1]').xpath('string(.)').get() or '').strip())

    # ── Context Loader (two-hop: gallery page → video page) ─────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None

        gallery_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] gallery {url}'
        )
        if not gallery_page_elements:
            return None

        detail = gallery_page_elements
        video_href = first_attr(gallery_page_elements['sel'], '(//a[contains(@class,"et_pb_button")])[2]/@href')
        if video_href:
            video_page_elements = await self.fetch_and_load(
                absolute_url(video_href, site.base_url), FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'GET {video_href}'
            )
            if video_page_elements:
                detail = video_page_elements

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=detail['sel'],
            html=detail['html'],
            extra={'gallery': gallery_page_elements['sel']},
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        cls = details_page_elements.xpath('(//div[@id="main-project-content"])[1]/@class').get() or ''
        for token in cls.split():
            if token in _CATEGORY_TAGLINES:
                return _CATEGORY_TAGLINES[token]

        return scene.site.name

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = (details_page_elements.xpath('(//div[contains(@class,"project-details")]//h1)[1]').xpath('string(.)').get() or '').strip()
        tagline = self._tagline(scene)
        if title.lower().startswith(tagline.lower()):
            title = title[len(tagline) :].strip()

        metadata.title = title or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        text = details_page_elements.xpath('(//div[contains(@class,"relese-date")])[1]').xpath('string(.)').get() or ''
        date = text.split('Release:')[1].strip() if 'Release:' in text else ''

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []

        def add(sel: Any) -> None:
            for genre_link in sel.xpath('//div[contains(@class,"project-tags")]/div[contains(@class,"list")]/a'):
                genre_name = first_attr(genre_link, 'normalize-space(.)').lower()
                if genre_name and genre_name not in genres:
                    genres.append(genre_name)

        add(details_page_elements)
        gallery = (scene.extra or {}).get('gallery')
        if gallery is not None:
            add(gallery)

        cast = len(details_page_elements.xpath('//div[contains(@class,"project-models")]//a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return absolute_first_attr(sel, '(//img[contains(@class,"img-poster")])[1]/@src', base)

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"project-models")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            if actor_name == 'LittleCaprice':
                actor_name = 'Little Caprice'

            href = first_attr(actor_link, '@href')
            refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: join_url(image, base))

        images.push(first_attr(details_page_elements, '(//meta[@property="og:image"])[1]/@content'))
        gallery = (scene.extra or {}).get('gallery')
        if gallery is not None:
            images.push(first_attr(gallery, '(//meta[@property="og:image"])[1]/@content'))
            for src in gallery.xpath('//div[contains(@class,"gallery") and contains(@class,"spotlight-group")]//img/@src').getall():
                images.push(src)

        metadata.art = images.items
