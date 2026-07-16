from __future__ import annotations

import httpx2

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger


def _srcset_entry(srcset: str, index: int, drop_chars: int) -> str:
    parts = srcset.split(',')
    if index >= len(parts) or index < -len(parts):
        return ''

    entry = parts[index]
    return entry[:-drop_chars].strip().replace('https', 'http') if entry else ''


class RealityLoversClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        search_url = base + search_data.site_info.search_path
        try:
            r = await self.http.post(
                search_url,
                json={'sortBy': 'MOST_RELEVANT', 'searchQuery': search_data.title, 'videoView': 'MEDIUM'},
                headers={'Content-Type': 'application/json'},
            )
            contents = (r.json() or {}).get('contents', [])
        except (httpx2.HTTPError, ValueError) as err:
            logger.warn(search_data.site_info.name, f'search POST threw: {err}')
            return

        for c in contents:
            title = (c.get('title') or '').strip()
            uri = (c.get('videoUri') or '').strip()
            if not title or not uri:
                continue

            scene_url = uri if uri.startswith('http') else f'{base}/{uri.lstrip("/")}'
            date = iso_date(c['released']) if c.get('released') else None

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

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1[contains(@class,"video-detail-name")]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//p[@itemprop="description"]').replace('…', '').replace('Read more', '')

        metadata.summary = ' '.join(raw.split())

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"videoClip__Details-infoValue")]')

        metadata.release_date = (iso_date(date) if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            first_attr(genre_link, 'normalize-space(.)').lower() for genre_link in details_page_elements.xpath('//span[@itemprop="keywords"]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath('//span[@itemprop="actors"]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            photo = ''
            href = first_attr(actor_link, '@href')
            if href:
                model_page_elements = await self.fetch_and_load(href, FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                srcset = (
                    (model_page_elements['sel'].xpath('(//img[contains(@class,"girlDetails-posterImage")]/@srcset)[1]').get() or '')
                    if model_page_elements
                    else ''
                )
                if srcset:
                    photo = _srcset_entry(srcset, 1, 3)

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: _srcset_entry(image, len(image.split(',')) - 1, 6))
        for data_big in details_page_elements.xpath('//img[contains(@class,"videoClip__Details--galleryItem")]/@data-big').getall():
            images['push']((data_big or '').strip())

        metadata.art = images['list']
