from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from parsel import Selector

from app.clients.aggregators.data18 import data18_scene_id
from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, pack_cur_id, sceneid_distance_score
from app.utils.helpers.html_helpers import first_attr
from app.utils.logging.best_effort import best_effort
from app.utils.searchengines import SearchOptions, web_search

_SCENE_GRID_XP = '//div[contains(@class,"item-grid") and contains(@class,"item-grid-scene")]'
_GRID_ITEM_XP = f'{_SCENE_GRID_XP}//div[contains(@class,"grid-item")]'
_AGE_HEADERS = {'Cookie': 'ageConfirmed=true'}


def _movie_id(url: str) -> str:
    return (urlsplit(url).path.strip('/').split('/') or [''])[0]


def _is_movie_url(url: str) -> bool:
    path = urlsplit(url).path
    return '/movies/' in path or path.endswith('-porn-movies.html')


def _rotate_article(raw: str) -> str:
    """Rotate a ", The"/", A" anywhere in the string to the front (Empire's catalog
    format), splitting on the first marker only."""
    lower = raw.lower()
    if ', the' in lower:
        idx = lower.index(', the')
    elif ', a' in lower:
        idx = lower.index(', a')
    else:
        return raw

    end = idx + 5 if lower[idx + 2] == 't' else idx + 3
    article = lower[idx + 2 : end]
    head = raw[:idx]
    tail = raw[idx + 2 + len(article) :]
    return f'{article[:1].upper()}{article[1:]} {head}{tail}'


def _release_date(sel: Any) -> str | None:
    nodes = sel.xpath('//div[contains(@class,"release-date")][.//span[contains(.,"Released:")]]')
    if not nodes:
        return None

    txt = re.sub(r'.*Released:\s*', '', nodes[0].xpath('string(.)').get() or '', flags=re.S).strip()
    if not txt or txt.lower() == 'unknown':
        return None

    return iso_date(txt, '%b %d, %Y') or iso_date(txt)


class Data18EmpireClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_id = data18_scene_id(search_data.scene_id)

        movie_urls: list[str] = []

        def add_movie(url: str) -> None:
            if url not in movie_urls:
                movie_urls.append(url)

        if scene_id:
            add_movie(f'{base}/{scene_id}')
        else:
            encoded = re.sub(r'\s+', '+', search_data.title.strip())
            search_results = await self.fetch_and_load(
                f'{base}{search_data.site_info.search_path}{encoded}',
                FetchCtx(capture=search_data.capture, headers=_AGE_HEADERS),
                f'[{search_data.site_info.name}] search "{search_data.title}"',
            )
            if search_results:
                for href in search_results['sel'].xpath('//a[contains(@class,"boxcover")]/@href').getall():
                    if 'movies' in href:
                        add_movie(href if href.startswith('http') else base + href)

            with best_effort(search_data.site_info.name, 'webSearch', level='debug'):
                host = urlsplit(search_data.site_info.base_url).hostname or ''
                for u in await web_search(SearchOptions(query=search_data.title, site=host, num=10)):
                    if _is_movie_url(u):
                        add_movie(u)

        for movie_url in movie_urls:
            movie_page_elements = await self.fetch_and_load(
                movie_url, FetchCtx(capture=search_data.capture, headers=_AGE_HEADERS), f'[{search_data.site_info.name}] movie {movie_url}'
            )
            if not movie_page_elements:
                continue

            sel = movie_page_elements['sel']
            title = _rotate_article(first_attr(sel, '(//h1[contains(@class,"description")])[1]/text()'))
            if not title:
                continue

            date = _release_date(sel)
            score = sceneid_distance_score(scene_id, _movie_id(movie_url)) if scene_id else None

            results.append(
                build_search_result(
                    title=title,
                    scene_url=movie_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'searchDate': search_data.search_date})]),
                )
            )
            scene_count = len(sel.xpath(_GRID_ITEM_XP))
            for scene_num in range(1, scene_count + 1):
                results.append(
                    build_search_result(
                        title=f'{title} [Scene {scene_num}]',
                        scene_url=movie_url,
                        query=search_data.title,
                        display_date=date,
                        search_date=search_data.search_date,
                        score=score,
                        cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'sceneNum': scene_num, 'searchDate': search_data.search_date})]),
                    )
                )

    # ── Context Loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
            if not isinstance(packed, dict):
                packed = {'movieURL': payload}
        except (ValueError, TypeError):
            packed = {'movieURL': payload}

        movie_url = packed.get('movieURL', '')
        movie_page_elements = await self.fetch_and_load(
            movie_url, FetchCtx(capture=ctx.capture if ctx else None, headers=_AGE_HEADERS), f'[{site.name}] detail {movie_url}'
        )
        if not movie_page_elements:
            return None

        return LoadedScene(
            url=movie_url,
            site=site,
            scene_date=packed.get('searchDate') or None,
            capture=ctx.capture if ctx else None,
            sel=movie_page_elements['sel'],
            html=movie_page_elements['html'],
            extra=packed,
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    def _studio(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return first_attr(details_page_elements, '(//div[contains(@class,"studio")]//a)[1]/text()')

    def _tagline_raw(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        studio = self._studio(scene)
        tagline = first_attr(details_page_elements, '(//p[contains(.,"A scene from")]//a)[1]/text()')
        if not tagline:
            raw = first_attr(details_page_elements, '(//a[@data-label="Series List"]//h2)[1]/text()')
            tagline = re.sub(rf'\({re.escape(studio)}\)', '', raw.replace('Series:', '')).strip()

        return _rotate_article(tagline) if tagline else studio

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = _rotate_article(first_attr(details_page_elements, '(//h1[contains(@class,"description")])[1]/text()'))
        if not title:
            return

        scene_num = self._packed(scene).get('sceneNum')

        metadata.title = f'{title} [Scene {scene_num}]' if scene_num is not None else title

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = (details_page_elements.xpath('(//div[contains(@class,"synopsis")])[1]').xpath('normalize-space(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = self._studio(scene) or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline_raw(scene)
        studio = self._studio(scene)

        metadata.tagline = tagline if tagline and tagline != studio else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_raw(scene) or self._studio(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.release_date = _release_date(details_page_elements)

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"categories")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        packed = self._packed(scene)
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def performer_photo(name: str) -> str:
            return (details_page_elements.xpath(f'(//div[contains(@class,"video-performer")]//a//img[@title="{name}"]/@data-bgsrc)[1]').get() or '').strip()

        def add(name: str, photo: str = '') -> None:
            n = name.strip()
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n, photo_url=photo))

        if packed.get('sceneNum') is not None:
            rows = details_page_elements.xpath(_GRID_ITEM_XP)
            idx = (packed['sceneNum'] or 1) - 1
            if idx < len(rows):
                cast = rows[idx].xpath('.//p[contains(@class,"scene-performer-names")]//a') or rows[idx].xpath('.//div[contains(@class,"scene-cast-list")]//a')
                for a in cast:
                    actor_name = first_attr(a, 'normalize-space(.)')
                    add(actor_name, performer_photo(actor_name))

            metadata.actors = actors
            return

        for actor_name in details_page_elements.xpath('//div[contains(@class,"video-performer")]//img/@title').getall():
            add(actor_name.strip(), performer_photo(actor_name.strip()))

        if not actors:
            for actor_link in details_page_elements.xpath('//div[contains(@class,"performer-name")]') or details_page_elements.xpath(
                '//div[contains(@class,"performers")]//a'
            ):
                actor_name = first_attr(actor_link, 'normalize-space(.)')
                add(actor_name, performer_photo(actor_name))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        directors: list[ActorResult] = []
        seen: set[str] = set()
        for director_link in details_page_elements.xpath('//div[contains(@class,"director")]//a'):
            raw = first_attr(director_link, 'normalize-space(.)')
            director_name = raw.split(':')[-1].strip() if ':' in raw else raw
            if director_name and director_name != 'Unknown' and director_name not in seen:
                seen.add(director_name)
                directors.append(ActorResult(name=director_name))

        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        packed = self._packed(scene)
        images = self.image_collector(lambda image: join_url(image.strip(), base) if image.strip() else '')

        srcset = details_page_elements.xpath('(//div[@id="video-container-details"]//div//section//a//picture//source/@data-srcset)[1]').get()
        if srcset:
            images['push'](srcset)

        for noscript in details_page_elements.xpath('//div[@id="viewLargeBoxcoverCarousel"]//noscript/text()').getall():
            for img_src in Selector(text=noscript).xpath('//img/@src').getall():
                images['push'](img_src)

        gallery_href = first_attr(details_page_elements, '(//div[@id="video-container-details"]//a[@data-label="Gallery"]/@href)[1]')
        if gallery_href:
            gallery_url = gallery_href if gallery_href.startswith('http') else base + gallery_href
            gallery_page_elements = await self.fetch_and_load(
                gallery_url, FetchCtx(capture=scene.capture, headers=_AGE_HEADERS), f'[{scene.site.name}] gallery'
            )
            if gallery_page_elements:
                for src in (
                    gallery_page_elements['sel']
                    .xpath('//div[contains(@class,"item-grid") and contains(@class,"item-grid-gallery")]//div[contains(@class,"grid-item")]//a//img/@data-src')
                    .getall()
                ):
                    images['push'](src)

        if packed.get('sceneNum') is not None:
            rows = details_page_elements.xpath(_GRID_ITEM_XP)
            idx = (packed['sceneNum'] or 1) - 1
            if idx < len(rows):
                images['push'](rows[idx].xpath('.//a[contains(@class,"scene-img")]//img/@src').get() or '')

        metadata.art = images['list']
