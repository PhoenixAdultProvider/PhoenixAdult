from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, append_unique, build_search_result, iso_date, pack_cur_id, to_https
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content
from app.utils.logging.logger import logger

STUDIO = 'VRAllure'
_TITLE_XP = '//h1[contains(@class,"latest-scene-title")]'
_DATE_XP = '//p[contains(@class,"publish-date")]'
_ACTOR_LINK_XP = '//p[contains(@class,"model-name")]//a[contains(@href,"/models/")]'
_ACTOR_PHOTO_XP = '//img[@id="model-thumbnail"]/@src'


class VRAllureClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = search_data.title.replace(' ', '_')
        if not slug:
            return

        search_url = f'{base}{search_data.site_info.search_path}{slug}'
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct {search_url}')
        if not search_results:
            return

        title = first_text(search_results['sel'], _TITLE_XP)
        if not title:
            return

        canonical = first_attr(search_results['sel'], '(//link[@rel="canonical"]/@href)[1]')
        scene_url = canonical or search_url
        date_raw = first_text(search_results['sel'], _DATE_XP)
        date = iso_date(date_raw) if date_raw else None
        logger.info(search_data.site_info.name, f'VRAllure direct hit "{title}" ({scene_url})')

        results.append(
            build_search_result(
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, date or '']),
            )
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP) or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//p[contains(@class,"desc")]//span') or ''

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
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get()
            for genre_link in details_page_elements.xpath('//a[contains(@class,"label") and contains(@class,"label-tag")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_ACTOR_LINK_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            photo = ''
            if href:
                url = absolute_url(href, base)
                model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    photo = to_https((model_page_elements['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip())

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images: list[str] = []

        def push(raw: str) -> None:
            append_unique(images, raw)

        push(to_https(meta_content(details_page_elements, 'og:image')))
        for href in details_page_elements.xpath(f'{_ACTOR_LINK_XP}/@href').getall():
            href = (href or '').strip()
            if not href:
                continue

            url = absolute_url(href, base)
            model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-art {url}')
            if model_page_elements:
                push(to_https((model_page_elements['sel'].xpath(f'({_ACTOR_PHOTO_XP})[1]').get() or '').strip()))

        metadata.art = images
