from __future__ import annotations

import re

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_text, web_search_urls

_WS_RE = re.compile(r'\s+')
_ACTOR_SPLIT_RE = re.compile(r',|\sand\s')


def _slugify(query: str) -> str:
    return _WS_RE.sub('-', query.strip()).lower()


def _normalize_web_url(raw: str) -> str:
    no_join = raw.split('/join.php')[0]
    idx = no_join.rfind('/')
    return no_join[:idx] if idx > 0 else no_join


class TeenyTabooClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = _slugify(search_data.title)
        direct_url = search_data.search_url(slug)

        seen = {direct_url}
        candidates = [direct_url]
        for raw in await web_search_urls(search_data.title, search_data.site_info):
            normalized = _normalize_web_url(raw)
            if '/video/' in normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

        for scene_url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] candidate {scene_url}'
        ):
            if not details_page_elements:
                continue

            raw = first_text(details_page_elements['sel'], '//h1[contains(@class,"customhcolor")]')
            if not raw:
                continue

            title = raw.replace('-', ' ')
            date_raw = first_text(details_page_elements['sel'], '//span[contains(@class,"date")]')
            release_date = iso_date(date_raw) if date_raw else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=release_date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([p for p in (scene_url, release_date or search_data.search_date) if p]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//h1[contains(@class,"customhcolor")]')

        metadata.title = raw.replace('-', ' ') if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//h2[contains(@class,"customhcolor2")]') or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//span[contains(@class,"date")]')

        metadata.release_date = iso_date(date) if date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('string((//h3)[1])').get() or ''
        if not raw:
            return

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for piece in _ACTOR_SPLIT_RE.split(raw):
            actor_name = re.sub(r'\d', '', piece).replace('&nbsp', '').replace('\xa0', ' ').strip()
            if actor_name and actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: absolute_url((image or '').strip(), base))
        for src in details_page_elements.xpath('//center//img/@src').getall():
            images['push'](src)

        metadata.art = images['list']
