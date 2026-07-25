from __future__ import annotations

import re

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, load_data
from phoenixadult.utils.helpers.html_helpers import first_attr

STUDIO = 'FuelVirtual'
_IMG_SCRIPT_RE = re.compile(r'image:\s*"(.+)"')
_SCENE_ID_RE = re.compile(r'id=(\d+)')

_ACTOR_DB: dict[str, dict[str, list[str]]] = load_data(__file__, 'fuelvirtual_actors')


def _server_path(site_name: str) -> str:
    return '/tour/newgirlpov/' if site_name == 'NewGirlPOV' else '/membersarea/'


def _actors_for_scene(site_name: str, scene_id: str) -> list[str] | None:
    return _ACTOR_DB.get(site_name, {}).get(scene_id)


class FuelVirtualClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        sp = _server_path(search_data.site_info.name)
        search_results = await self.fetch_and_load(
            base + search_data.site_info.search_path + search_data.encoded, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search'
        )
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[@align="left"]'):
            a = search_result.xpath('(.//td[@valign="top"])[2]//a[1]')
            title = first_attr(a)
            href = first_attr(a, '@href')
            if not title or not href:
                continue

            date_raw = (search_result.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').replace('Added', '').strip()
            date_iso = iso_date(date_raw) if date_raw else None
            scene_url = f'{base}{sp}{href}'

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date_iso,
                    search_date=search_data.search_date,
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or ''
        if scene.site.name == 'NewGirlPOV':
            parts = raw.split(' ')
            metadata.title = (parts[1].strip() if len(parts) > 1 else '') or ''
            return

        metadata.title = raw.split('-')[0].strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = [
            genre_name
            for genre_name in (
                first_attr(genre_link, 'normalize-space(.)')
                for genre_link in details_page_elements.xpath('//td[contains(@class,"plaintext")]//a[contains(@class,"model_category_link")]')
            )
            if genre_name
        ]
        if scene.site.name != 'NewGirlPOV':
            genres.append('18-Year-Old')

        cast = len(details_page_elements.xpath('//div[@id="description"]//td[@align="left"]//a'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actor_els = details_page_elements.xpath('//div[@id="description"]//td[@align="left"]//a')
        if not actor_els:
            return

        m = _SCENE_ID_RE.search(scene.url)
        db_names = _actors_for_scene(scene.site.name, m.group(1)) if m else None
        if db_names is not None:
            metadata.actors = [ActorResult(name=n) for n in db_names]
            return

        actors = [ActorResult(name=actor_name) for actor_name in (first_attr(a, 'normalize-space(.)') for a in actor_els) if actor_name]

        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: (image or '').strip())

        for src in details_page_elements.xpath('//a[contains(@class,"jqModal")]//img/@src | //div[@id="overallthumb"]//a//img/@src').getall():
            if not src:
                continue

            images['push'](base + src if src.startswith('/') else f'{base}/tour/newgirlpov/{src}')

        photo_url = scene.url.replace('vids', 'highres')
        if photo_url != scene.url:
            photo_page_elements = await self.fetch_and_load(photo_url, None, f'GET {photo_url} (highres)')
            if photo_page_elements:
                for src in photo_page_elements['sel'].xpath('//a[contains(@class,"jqModal")]//img/@src').getall():
                    if src:
                        images['push'](base + src)

        for script in details_page_elements.xpath('//div[@id="mediabox"]//script'):
            m = _IMG_SCRIPT_RE.search(script.xpath('string(.)').get() or '')
            if m:
                images['push'](base + m.group(1))

        metadata.art = images['list'] or []
