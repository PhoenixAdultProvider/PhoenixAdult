from __future__ import annotations

import re
from urllib.parse import urlsplit

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, load_data, pack_cur_id, sceneid_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr, meta_content
from phoenixadult.utils.helpers.javbus_images import push_javbus_images
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.title_case import title_case
from phoenixadult.utils.searchengines import SearchOptions, web_search

_TABLES = load_data(__file__, 'javlibrary_tables')
_ACTORS: dict[str, list[str]] = _TABLES['actors']
_CROSS_SITE: dict[str, str] = _TABLES['crossSite']
_IGNORE_LIST: list[str] = _TABLES['ignoreList']


class JavLibraryClient(Client):
    async def _web_search_vjav(self, query: str, base_url: str) -> list[str]:
        host = urlsplit(base_url).hostname or ''
        found = await web_search(SearchOptions(query=query, site=host, num=10))
        out: list[str] = []
        for url in found:
            if '?v=jav' not in url or 'videoreviews' in url:
                continue

            normalized = url.replace('/ja/', '/en/').replace('/tw/', '/en/').replace('/cn/', '/en/')
            if not normalized.lower().startswith('http'):
                normalized = f'http://{normalized}'

            if normalized not in out:
                out.append(normalized)

        return out

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        tokens = search_data.title.strip().split()
        if tokens:
            tokens[0] = re.sub(r'^(13dsvr|3dsvr)', 'dsvr', tokens[0], flags=re.IGNORECASE)

        search_javid = f'{tokens[0]}-{tokens[1]}' if len(tokens) > 1 and re.fullmatch(r'\d+', tokens[1]) else None
        encoded = search_javid or search_data.encoded

        seen: set[str] = set()

        def add(scene_url: str, jav_id: str, title: str, score: float | None = None) -> None:
            if scene_url in seen:
                return

            seen.add(scene_url)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=f'[{jav_id}] {title}',
                    scene_url=scene_url,
                    query=search_javid or search_data.title,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (scene_url, search_data.search_date) if p]),
                )
            )

        search_url = search_data.search_url(encoded)
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            cards = search_results['sel'].xpath('//div[contains(@class,"video")]')
            if cards:
                for card in cards:
                    title = first_attr(card, '(.//a/@title)[1]')
                    href = first_attr(card, '(.//a/@href)[1]')
                    if not title or not href:
                        continue

                    jav_id = title.split(' ')[0]
                    scene_url = f'{base}/en{href.split(".")[-1]}'
                    add(scene_url, jav_id, title, sceneid_distance_score(search_javid.lower(), jav_id.lower()) if search_javid else None)
            else:
                og_url = meta_content(search_results['sel'], 'og:url')
                if '?v=jav' in og_url:
                    og = meta_content(search_results['sel'], 'og:title')
                    if og:
                        add(og_url.replace('//www', 'https://www'), og.split(' ')[0], og, 100)

        try:
            query = ' '.join(tokens[:2]) or search_data.title
            for candidate_url, details_page_elements in await self.fetch_candidate_pages(
                await self._web_search_vjav(query, search_data.site_info.base_url),
                FetchCtx(capture=search_data.capture),
                lambda candidate_url: f'[{search_data.site_info.name}] {candidate_url}',
            ):
                if not details_page_elements:
                    continue

                post_title = first_attr(details_page_elements['sel'], '(//h3[contains(@class,"post-title") and contains(@class,"text")]//a)[1]/text()')
                if not post_title:
                    continue

                title = ' '.join(post_title.split(' ')[1:])
                jav_id = (
                    details_page_elements['sel'].xpath('(//td[contains(.,"ID:")])[1]/following-sibling::td[1]').xpath('normalize-space(.)').get() or ''
                ).strip()
                og_url = meta_content(details_page_elements['sel'], 'og:url')
                scene_url = (og_url or candidate_url).replace('//www', 'https://www')
                add(scene_url, jav_id, title, sceneid_distance_score(search_javid.lower(), jav_id.lower()) if search_javid else None)
        except Exception as err:  # noqa: BLE001
            logger.debug(search_data.site_info.name, f'webSearch fallback: {err}')

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _table_link(self, scene: LoadedScene, label: str) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath(f'(//td[contains(.,"{label}")])[1]/following-sibling::td[1]//span//a[1]/text()').get() or '').strip()

    def _og_jav_id(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return meta_content(details_page_elements, 'og:title').split(' ')[0]

    def _og_title_parts(self, scene: LoadedScene) -> tuple[str, str]:
        details_page_elements = scene.require_sel()

        og = meta_content(details_page_elements, 'og:title')
        if not og:
            return '', ''

        jav_id = og.split(' ')[0]
        title = ' '.join(og.split(' ')[1:]).replace(' - JAVLibrary', '').replace(jav_id, '').strip()
        return jav_id, title

    def _release_date(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//td[contains(.,"Release Date:")])[1]/following-sibling::td[1]').xpath('normalize-space(.)').get() or '').strip()
        return (iso_date(date, '%Y-%m-%d') if date else None) or scene.scene_date or None

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        jav_id, title = self._og_title_parts(scene)
        if not jav_id:
            return

        metadata.title = f'[{jav_id.upper()}] {title}'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        _, title = self._og_title_parts(scene)

        metadata.summary = title_case(title) if len(title) > 80 else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._table_link(scene, 'Maker:') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._table_link(scene, 'Label:') or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        label = self._table_link(scene, 'Label:')
        maker = self._table_link(scene, 'Maker:')

        metadata.collections = [label or maker or 'Japan Adult Video']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._release_date(scene)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//a[@rel="category tag"]')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = name.strip()
            if n and n.lower() not in seen:
                seen.add(n.lower())
                actors.append(ActorResult(name=n))

        jav_id = self._og_jav_id(scene)
        for actor_name, ids in _ACTORS.items():
            if any(i.lower() == jav_id.lower() for i in ids):
                add(actor_name)

        for actor_link in details_page_elements.xpath('//span[contains(@class,"star")]//a'):
            add(actor_link.xpath('normalize-space(.)').get() or '')

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        director_name = self._table_link(scene, 'Director:')

        metadata.directors = [ActorResult(name=director_name)] if director_name else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: (image or '').strip())

        poster = first_attr(details_page_elements, '(//img[@id="video_jacket_img"]/@src)[1]')
        if poster and 'https' not in poster:
            poster = f'https:{poster}'

        images['push'](poster)

        for thumb in details_page_elements.xpath('//div[contains(@class,"previewthumbs")]//img/@src').getall():
            thumb = (thumb or '').strip()
            m = re.search(r'-([1-9]+)\.jpg', thumb)
            images['push'](f'{thumb[: m.start()]}jp{thumb[m.start() :]}' if m else thumb)

        jav_id = self._og_jav_id(scene)
        if jav_id:
            for lib_id, bus_id in _CROSS_SITE.items():
                if jav_id.lower() == lib_id.lower():
                    jav_id = bus_id
                    break

            await push_javbus_images(self.http, images, jav_id, _IGNORE_LIST, self._release_date(scene))

        metadata.art = images['list']
