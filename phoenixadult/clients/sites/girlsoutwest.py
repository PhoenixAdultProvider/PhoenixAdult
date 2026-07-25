from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content, web_search_urls

_TRAILER_P_XP = '//div[contains(@class,"trailer") and contains(@class,"topSpace")]//div//p'
_CAST_XP = _TRAILER_P_XP + '//a'


class GirlsOutWestClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        direct = base + search_data.site_info.search_path.replace('{query}', slugify(search_data.title))
        candidates = [direct]
        for u in await web_search_urls(search_data.title, search_data.site_info, include=['/trailers/']):
            if u not in candidates:
                candidates.append(u)

        for scene_url in candidates:
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {scene_url}'
            )
            if not details_page_elements or details_page_elements['html'].strip() == 'Page not found':
                continue

            title = meta_content(details_page_elements['sel'], 'twitter:title')
            if not title:
                continue

            date = self._date_from(details_page_elements['sel'])

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _date_from(self, sel: Any) -> str | None:
        text = first_text(sel, _TRAILER_P_XP)
        parts = text.split('\\')
        if len(parts) < 2:
            return None

        return iso_date(parts[1].strip(), '%m/%d/%Y')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = meta_content(details_page_elements, 'twitter:title') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'GirlsOutWest'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = self._date_from(details_page_elements)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = ['Amateur', 'Australian']
        count = len(details_page_elements.xpath(_CAST_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath(_CAST_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if not actor_name or not href or actor_name in seen:
                continue

            seen.add(actor_name)
            actor_url = join_url(href, scene.site.base_url)
            model_page_elements = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {actor_name}')
            photo = ''
            if model_page_elements:
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"profilePic")]//img/@src0_3x)[1]')
                photo = join_url(raw, scene.site.base_url) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: join_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[contains(@class,"videoplayer")]//img/@src0_3x').getall():
            image_url = (image_url or '').strip()
            if not image_url:
                continue

            images['push'](image_url)

        metadata.art = images['list']
