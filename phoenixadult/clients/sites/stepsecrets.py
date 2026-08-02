from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, LoadedSearch, SceneDetail, SearchContext
from phoenixadult.utils.helpers.helpers import absolute_url, strip_query
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Joymii'
TAGLINE = 'Step Secrets'

_FIXED_GENRES: list[str] = ['European', 'Glamcore', 'Taboo']


class StepSecretsClient(Client):
    search_url_xpath = '(.//a/@href)[1]'
    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def load_search_context(self, search_data: SearchContext) -> LoadedSearch | None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return None

        sources = list(search_results['sel'].xpath('//div[contains(@class,"card-simple")]'))
        return LoadedSearch(ctx=search_data, site=search_data.site_info, sources=sources, capture=search_data.capture)

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source, './/a[contains(@class,"color-title")]')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1[contains(@class,"font-cond")]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"descripton")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = TAGLINE

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [TAGLINE]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = list(_FIXED_GENRES)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for href in details_page_elements.xpath('//p[contains(@class,"mb-2")]//a/@href').getall():
            href = (href or '').strip()
            if not href:
                continue

            actor_url = absolute_url(href, base)
            model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_url}')
            if not model_page_elements:
                continue

            actor_name = first_text(model_page_elements['sel'], '//h1[contains(@class,"font-cond")]')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model-about")]//img/@src)[1]')
            photo = strip_query(raw) if raw else ''
            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.dedup_strings([(src or '').strip() for src in details_page_elements.xpath('//video/@poster').getall()])
        for src in details_page_elements.xpath('//div[@id="photoCarousel"]//img/@src').getall():
            s = (src or '').strip()
            if s and s not in images:
                images.append(s)

        metadata.art = images
