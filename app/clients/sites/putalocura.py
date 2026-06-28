from __future__ import annotations

import re
from urllib.parse import urlsplit

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text
from app.utils.logging.logger import logger
from app.utils.searchengines import SearchOptions, web_search

_POSTER_RE = re.compile(r'posterImage:\s*"([^"]*)"')
_WS_NL_RE = re.compile(r'\s*\n\s*')
_BAD_SUBSTRINGS = ('/tags/', '/actr', '?pag', '/xvideos', '/tag/')


def _remap_actor(actor_name: str, title: str) -> str:
    if 'africa' in actor_name.lower():
        return 'Africat'
    if title == 'MAMADA ARGENTINA':
        return 'Alejandra Argentina'
    if actor_name == 'Alika':
        return 'Alyka'
    return actor_name


def _parsed_title(sel: Selector) -> str:
    return first_text(sel, '//title').split('|')[0].split('-')[0].strip()


class PutalocuraClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        host = urlsplit(ctx.site_info.base_url).hostname or ''
        found: list[str] = []
        try:
            found = await web_search(SearchOptions(query=ctx.title, site=host, num=10, language='enes'))
        except Exception as err:  # noqa: BLE001 - search failure is non-fatal
            logger.warn(ctx.site_info.name, f'webSearch threw: {err}')

        candidates: list[str] = []
        for raw in found:
            url = raw.replace('index.php/', '').replace('es/', '')
            if any(s in url for s in _BAD_SUBSTRINGS) or url in candidates:
                continue
            candidates.append(url)
            if '/en/' in raw:
                twin = raw.replace('en/', '')
                if twin not in candidates:
                    candidates.append(twin)

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {scene_url}')
            if not loaded:
                continue
            title = _parsed_title(loaded['sel'])
            if not title:
                continue
            date = iso_date(first_text(loaded['sel'], '//div[contains(@class,"released-views")]//span'), '%d/%m/%Y')
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _parsed_title(scene.sel) or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"description") and contains(@class,"clearfix")]')
        if not raw:
            return None
        return _WS_NL_RE.sub(' ', raw.split(':')[-1].strip()) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//div[contains(@class,"released-views")]//span')
        return (iso_date(raw, '%d/%m/%Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//div[contains(@class,"categories")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        title = _parsed_title(scene.sel)
        if not title:
            return []
        base = scene.site.base_url.rstrip('/')
        is_english = '/en/' in scene.url

        if '&' in title:
            names = title.split('&')
        else:
            site_name = first_text(scene.sel, '//span[contains(@class,"site-name")]')
            names = site_name.split(' and ' if is_english else ' y ')

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for raw_name in names:
            actor_name = raw_name.strip()
            if not actor_name:
                continue
            title_index = await self._fetch_model_index(scene, base, title[0])
            if any(m['name'].lower() == title.lower() for m in title_index):
                actor_name = title
            actor_name = _remap_actor(actor_name, title)
            if actor_name in seen:
                continue
            seen.add(actor_name)
            index = await self._fetch_model_index(scene, base, actor_name[0] if actor_name else '')
            hit = next((m for m in index if m['name'].lower() == actor_name.lower()), None)
            actors.append(ActorResult(name=actor_name, photo_url=hit['photoURL'] if hit else ''))
        return actors

    async def _fetch_model_index(self, scene: LoadedScene, base: str, letter: str) -> list[dict[str, str]]:
        if not letter:
            return []
        url = f'{base}/actrices/{letter.lower()}'
        loaded = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'GET {url} (models)')
        if not loaded:
            return []
        models: list[dict[str, str]] = []
        for anchor in loaded['sel'].xpath('//div[contains(@class,"c-boxlist__box--image")]/parent::a'):
            name = first_attr(anchor, 'normalize-space(.)')
            if not name:
                continue
            raw = first_attr(anchor, '(.//img/@src)[1]')
            models.append({'name': name, 'photoURL': absolute_url(raw, base) if raw else ''})
        return models

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        script = scene.sel.xpath('string((//div[contains(@class,"top-area-content")]//script)[1])').get() or ''
        m = _POSTER_RE.search(script)
        return [m.group(1)] if m and m.group(1) else []
