from __future__ import annotations

import re

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, script_match, web_search_urls
from phoenixadult.utils.logging.best_effort import best_effort

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
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        found: list[str] = []
        with best_effort(search_data.site_info.name, 'webSearch'):
            found = await web_search_urls(search_data.title, search_data.site_info, language='enes')

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

        for scene_url, search_results in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] {scene_url}'
        ):
            if not search_results:
                continue

            title = _parsed_title(search_results['sel'])
            if not title:
                continue

            date = iso_date(first_text(search_results['sel'], '//div[contains(@class,"released-views")]//span'), '%d/%m/%Y')

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

    async def _fetch_model_index(self, scene: LoadedScene, base: str, letter: str) -> list[dict[str, str]]:
        if not letter:
            return []

        url = f'{base}/actrices/{letter.lower()}'
        model_page_elements = await self.fetch_and_load(url, FetchCtx(capture=scene.capture), f'GET {url} (models)')
        if not model_page_elements:
            return []

        models: list[dict[str, str]] = []
        for anchor in model_page_elements['sel'].xpath('//div[contains(@class,"c-boxlist__box--image")]/parent::a'):
            name = first_attr(anchor, 'normalize-space(.)')
            if not name:
                continue

            raw = first_attr(anchor, '(.//img/@src)[1]')
            models.append({'name': name, 'photoURL': absolute_url(raw, base) if raw else ''})

        return models

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _parsed_title(details_page_elements)

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//div[contains(@class,"description") and contains(@class,"clearfix")]')
        if not raw:
            return

        metadata.summary = _WS_NL_RE.sub(' ', raw.split(':')[-1].strip())

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//div[contains(@class,"released-views")]//span')

        metadata.release_date = (iso_date(date, '%d/%m/%Y') if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"categories")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        title = _parsed_title(details_page_elements)
        if not title:
            return

        base = scene.site.base_url.rstrip('/')
        is_english = '/en/' in scene.url

        if '&' in title:
            names = title.split('&')
        else:
            site_name = first_text(details_page_elements, '//span[contains(@class,"site-name")]')
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

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        script = details_page_elements.xpath('string((//div[contains(@class,"top-area-content")]//script)[1])').get() or ''
        poster = script_match(script, _POSTER_RE)

        metadata.art = [poster] if poster else []
