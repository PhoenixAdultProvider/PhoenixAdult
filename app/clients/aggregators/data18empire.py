from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
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


def _release_date(sel: Any) -> str | None:
    nodes = sel.xpath('//div[contains(@class,"release-date")][.//span[contains(.,"Released:")]]')
    if not nodes:
        return None
    txt = re.sub(r'.*Released:\s*', '', nodes[0].xpath('string(.)').get() or '', flags=re.S).strip()
    if not txt or txt.lower() == 'unknown':
        return None
    return iso_date(txt, '%b %d, %Y') or iso_date(txt)


class Data18EmpireClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        scene_id = ctx.scene_id if ctx.scene_id and ctx.scene_id.isdigit() and int(ctx.scene_id) > 100 else ''

        movie_urls: list[str] = []

        def add_movie(url: str) -> None:
            if url not in movie_urls:
                movie_urls.append(url)

        if scene_id:
            add_movie(f'{base}/{scene_id}')
        else:
            encoded = re.sub(r'\s+', '+', ctx.title.strip())
            search_page = await self.fetch_and_load(
                f'{base}{ctx.site_info.search_path}{encoded}',
                FetchCtx(capture=ctx.capture, headers=_AGE_HEADERS),
                f'[{ctx.site_info.name}] search "{ctx.title}"',
            )
            if search_page:
                for href in search_page['sel'].xpath('//a[contains(@class,"boxcover")]/@href').getall():
                    if 'movies' in href:
                        add_movie(href if href.startswith('http') else base + href)
            with best_effort(ctx.site_info.name, 'webSearch', level='debug'):
                host = urlsplit(ctx.site_info.base_url).hostname or ''
                for u in await web_search(SearchOptions(query=ctx.title, site=host, num=10)):
                    if _is_movie_url(u):
                        add_movie(u)

        results: list[SearchResult] = []
        for movie_url in movie_urls:
            loaded = await self.fetch_and_load(movie_url, FetchCtx(capture=ctx.capture, headers=_AGE_HEADERS), f'[{ctx.site_info.name}] movie {movie_url}')
            if not loaded:
                continue
            sel = loaded['sel']
            title = first_attr(sel, '(//h1[contains(@class,"description")])[1]/text()')
            if not title:
                continue
            date = _release_date(sel)
            score = sceneid_distance_score(scene_id, _movie_id(movie_url)) if scene_id else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=movie_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'searchDate': ctx.search_date})]),
                )
            )
            scene_count = len(sel.xpath(_GRID_ITEM_XP))
            for scene_num in range(1, scene_count + 1):
                results.append(
                    build_search_result(
                        title=f'{title} [Scene {scene_num}]',
                        scene_url=movie_url,
                        query=ctx.title,
                        display_date=date,
                        search_date=ctx.search_date,
                        score=score,
                        cur_id=pack_cur_id([json.dumps({'movieURL': movie_url, 'sceneNum': scene_num, 'searchDate': ctx.search_date})]),
                    )
                )
        return results

    # ── Context loader ────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            packed = json.loads(payload)
            if not isinstance(packed, dict):
                packed = {'movieURL': payload}
        except (ValueError, TypeError):
            packed = {'movieURL': payload}
        movie_url = packed.get('movieURL', '')
        loaded = await self.fetch_and_load(movie_url, FetchCtx(capture=ctx.capture if ctx else None, headers=_AGE_HEADERS), f'[{site.name}] detail {movie_url}')
        if not loaded:
            return None
        return LoadedScene(
            url=movie_url,
            site=site,
            scene_date=packed.get('searchDate') or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra=packed,
        )

    def _packed(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    def _studio(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return first_attr(scene.sel, '(//div[contains(@class,"studio")]//a)[1]/text()')

    def _tagline_raw(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        studio = self._studio(scene)
        tagline = first_attr(scene.sel, '(//p[contains(.,"A scene from")]//a)[1]/text()')
        if not tagline:
            raw = first_attr(scene.sel, '(//a[@data-label="Series List"]//h2)[1]/text()')
            tagline = re.sub(rf'\({re.escape(studio)}\)', '', raw.replace('Series:', '')).strip()
        return tagline or studio

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        title = first_attr(scene.sel, '(//h1[contains(@class,"description")])[1]/text()')
        if not title:
            return None
        scene_num = self._packed(scene).get('sceneNum')
        return f'{title} [Scene {scene_num}]' if scene_num is not None else title

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"synopsis")])[1]').xpath('normalize-space(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return self._studio(scene) or None

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        tagline = self._tagline_raw(scene)
        studio = self._studio(scene)
        return tagline if tagline and tagline != studio else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline_raw(scene) or self._studio(scene) or scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _release_date(scene.sel)

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"categories")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        sel = scene.sel
        packed = self._packed(scene)
        actors: list[ActorResult] = []
        seen: set[str] = set()

        def performer_photo(name: str) -> str:
            return (sel.xpath(f'(//div[contains(@class,"video-performer")]//a//img[@title="{name}"]/@data-bgsrc)[1]').get() or '').strip()

        def add(name: str, photo: str = '') -> None:
            n = name.strip()
            if n and n not in seen:
                seen.add(n)
                actors.append(ActorResult(name=n, photo_url=photo))

        if packed.get('sceneNum') is not None:
            rows = sel.xpath(_GRID_ITEM_XP)
            idx = (packed['sceneNum'] or 1) - 1
            if idx < len(rows):
                cast = rows[idx].xpath('.//p[contains(@class,"scene-performer-names")]//a') or rows[idx].xpath('.//div[contains(@class,"scene-cast-list")]//a')
                for a in cast:
                    name = first_attr(a, 'normalize-space(.)')
                    add(name, performer_photo(name))
            return actors
        for name in sel.xpath('//div[contains(@class,"video-performer")]//img/@title').getall():
            add(name.strip(), performer_photo(name.strip()))
        if not actors:
            for el in sel.xpath('//div[contains(@class,"performer-name")]') or sel.xpath('//div[contains(@class,"performers")]//a'):
                name = first_attr(el, 'normalize-space(.)')
                add(name, performer_photo(name))
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        directors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//div[contains(@class,"director")]//a'):
            raw = first_attr(a, 'normalize-space(.)')
            name = raw.split(':')[-1].strip() if ':' in raw else raw
            if name and name != 'Unknown' and name not in seen:
                seen.add(name)
                directors.append(ActorResult(name=name))
        return directors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        sel = scene.sel
        base = scene.site.base_url.rstrip('/')
        packed = self._packed(scene)
        images: list[str] = []

        def add(u: str) -> None:
            u = (u or '').strip()
            if not u:
                return
            abs_url = join_url(u, base)
            if abs_url not in images:
                images.append(abs_url)

        srcset = sel.xpath('(//div[@id="video-container-details"]//div//section//a//picture//source/@data-srcset)[1]').get()
        if srcset:
            add(srcset)
        for noscript in sel.xpath('//div[@id="viewLargeBoxcoverCarousel"]//noscript/text()').getall():
            for img_src in Selector(text=noscript).xpath('//img/@src').getall():
                add(img_src)

        gallery_href = first_attr(sel, '(//div[@id="video-container-details"]//a[@data-label="Gallery"]/@href)[1]')
        if gallery_href:
            gallery_url = gallery_href if gallery_href.startswith('http') else base + gallery_href
            gallery = await self.fetch_and_load(gallery_url, FetchCtx(capture=scene.capture, headers=_AGE_HEADERS), f'[{scene.site.name}] gallery')
            if gallery:
                for src in (
                    gallery['sel']
                    .xpath('//div[contains(@class,"item-grid") and contains(@class,"item-grid-gallery")]//div[contains(@class,"grid-item")]//a//img/@data-src')
                    .getall()
                ):
                    add(src)

        if packed.get('sceneNum') is not None:
            rows = sel.xpath(_GRID_ITEM_XP)
            idx = (packed['sceneNum'] or 1) - 1
            if idx < len(rows):
                add(rows[idx].xpath('.//a[contains(@class,"scene-img")]//img/@src').get() or '')
        return images
