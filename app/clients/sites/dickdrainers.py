from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, web_search_urls
from app.utils.processors.title_case import title_case

_SLUG_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'dickdrainers_slug_actors')

_CARD_XP = '//div[contains(@class,"item-video") and contains(@class,"hover")]'
_SRC0_3X_RE = re.compile(r'src0_3x="([^"]+)"')
_SLUG_RE = re.compile(r'/s/([^/]+)\.html$')


class DickDrainersClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        onsite_query = re.sub(r'\s+', '+', search_data.title.strip().lower())
        onsite_url = base + search_data.site_info.search_path.replace('{query}', onsite_query)

        onsite_hrefs: set[str] = set()

        search_results = await self.fetch_and_load(
            onsite_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if search_results:
            for search_result in search_results['sel'].xpath(_CARD_XP):
                raw_title = first_text(search_result, './/h4')
                href = first_attr(search_result, '(.//h4//a/@href)[1]')
                if not raw_title or not href:
                    continue

                scene_url = absolute_url(href, base)
                onsite_hrefs.add(scene_url)
                raw_date = first_text(search_result, './/div[contains(@class,"date")]')
                date = iso_date(raw_date) if raw_date else None

                results.append(self._result(raw_title, scene_url, search_data, date))

        for scene_url in await web_search_urls(search_data.title, search_data.site_info, include=['/trailers/']):
            if scene_url in onsite_hrefs:
                continue

            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] fallback {scene_url}'
            )
            if not details_page_elements:
                continue

            raw_title = first_text(details_page_elements['sel'], '//h3')
            if not raw_title:
                continue

            raw_date = first_attr(details_page_elements['sel'], '(//div[contains(@class,"videoInfo") and contains(@class,"clear")]/p/text())[1]')
            date = iso_date(raw_date) if raw_date else None

            results.append(self._result(raw_title, scene_url, search_data, date))

    def _result(self, title: str, scene_url: str, search_data: SearchContext, date: str | None) -> SearchResult:
        return build_search_result(
            title=title,
            scene_url=scene_url,
            query=search_data.title,
            display_date=date,
            search_date=search_data.search_date,
            cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h3') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        parts = [
            s.xpath('normalize-space(.)').get() or ''
            for s in details_page_elements.xpath('//div[contains(@class,"videoDetails") and contains(@class,"clear")]//p/span')
        ]
        parts = [p for p in parts if p]
        if not parts:
            return

        joined = ' '.join(parts).replace('FULL VIDEO', '').strip()

        metadata.summary = joined or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date
            return

        details_page_elements = scene.require_sel()

        date = first_attr(details_page_elements, '(//div[contains(@class,"videoInfo") and contains(@class,"clear")]/p/text())[1]')

        metadata.release_date = iso_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//li[contains(.,"Tags")]/following-sibling::ul[1]//a'):
            raw = first_attr(genre_link, 'normalize-space(.)')
            if not raw:
                continue

            genre_name = title_case(raw, site_name=scene.site.name)
            if genre_name not in genres:
                genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        items = details_page_elements.xpath('//li[contains(@class,"update_models")]')
        if not items:
            m = _SLUG_RE.search(scene.url)
            if m:
                metadata.actors = [ActorResult(name=actor_name) for actor_name in _SLUG_ACTORS.get(m.group(1).lower(), [])]

            return

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for li in items:
            actor_name = first_attr(li, 'normalize-space(.)')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            href = first_attr(li, '(.//a/@href)[1]')
            photo = ''
            if href:
                actor_url = absolute_url(href, scene.site.base_url)
                model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
                if model_page_elements:
                    raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]')
                    photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url((image or '').strip(), scene.site.base_url))

        for el in details_page_elements.xpath('//div[contains(@class,"player_thumbs")]'):
            images['push'](el.xpath('@src0_3x').get() or '')
            for child in el.xpath('.//*[@src0_3x]'):
                images['push'](child.xpath('@src0_3x').get() or '')

        for script in details_page_elements.xpath('//div[contains(@class,"player") and contains(@class,"full_width")]//script'):
            text = script.xpath('string(.)').get() or ''
            for m in _SRC0_3X_RE.finditer(text):
                images['push'](m.group(1))

        metadata.art = images['list']
