from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, slugify
from app.utils.helpers.html_helpers import first_attr, meta_content, web_search_urls

_ID_SEPARATOR = ' Id '
_WORD_RE = re.compile(r'\w\S*')


def _py_title(s: str) -> str:
    return _WORD_RE.sub(lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), s)


class GirlsRimmingClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        direct = base + search_data.site_info.search_path.replace('{query}', slugify(search_data.title))
        candidates = [direct]
        for u in await web_search_urls(search_data.title, search_data.site_info, include=['/trailers/']):
            lc = u.lower()
            if lc not in candidates:
                candidates.append(lc)

        for scene_url in candidates:
            details_page_elements = await self.fetch_and_load(
                scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] candidate {scene_url}'
            )
            if not details_page_elements or details_page_elements['html'].strip() == 'Page not found':
                continue

            title = first_attr(details_page_elements['sel'], '(//h2[contains(@class,"title")]/text())[1]')
            if not title:
                continue

            date = search_data.search_date

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _keywords(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return details_page_elements.xpath('(//meta[@name="keywords"]/@content)[1]').get() or ''

    async def _resolve_actor_photo(self, actor_name: str, scene: LoadedScene) -> str:
        base = scene.site.base_url.rstrip('/')
        slug = re.sub(r'\s+', '-', actor_name.lower())
        direct_url = f'{base}/tour/models/{slug}.html'
        model_page_elements = await self.fetch_and_load(direct_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-direct {actor_name}')
        if not model_page_elements or model_page_elements['html'].strip() == 'Page not found':
            model_page_elements = None
            for u in (x.lower() for x in await web_search_urls(actor_name, scene.site, include=['/models/'])):
                candidate_page_elements = await self.fetch_and_load(u, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor-fallback {actor_name}')
                if candidate_page_elements and candidate_page_elements['html'].strip() != 'Page not found':
                    model_page_elements = candidate_page_elements
                    break

        if not model_page_elements:
            return ''

        raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model_picture")]//img/@src0_3x)[1]')
        return join_url(raw, base) if raw else ''

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_attr(details_page_elements, '(//h2[contains(@class,"title")]/text())[1]') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = meta_content(details_page_elements, 'description') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Girls Rimming'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres: list[str] = []
        for part in self._keywords(scene).split(','):
            entry = part.strip()
            if not entry or _ID_SEPARATOR in entry:
                continue

            titled = _py_title(entry)
            if titled not in genres:
                genres.append(titled)

        if 'Rim Job' not in genres:
            genres.append('Rim Job')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for part in self._keywords(scene).split(','):
            entry = part.strip()
            if _ID_SEPARATOR not in entry:
                continue

            actor_name = entry.split(_ID_SEPARATOR)[0].strip()
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name, photo_url=await self._resolve_actor_photo(actor_name, scene)))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: join_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[@id="fakeplayer"]//img/@src0_3x').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
