from __future__ import annotations

import json
import re
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr
from app.utils.processors.title_case import title_case

_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'jesseloads_actors')
_WS_RE = re.compile(r'\s+')
_NUM_RE = re.compile(r'(\d+)')


def _resolve_actors(raw: str) -> list[str]:
    return [clean for clean, variants in _ACTORS.items() if raw in variants]


def _last_tour_page(sel: Selector) -> int:
    values = sel.xpath('//span[contains(@class,"bppindex")]//option[@value]')
    if not values:
        return 1

    text = values[-1].xpath('normalize-space(.)').get() or ''
    m = _NUM_RE.search(text)
    return max(int(m.group(1)), 1) if m else 1


class JesseLoadsMonsterFacialsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        def tour_url(idx: int) -> str:
            return f'{base}/visitors/tour_{idx:02d}.html'

        first_page_elements = await self.fetch_and_load(tour_url(1), FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {tour_url(1)}')
        if not first_page_elements:
            return

        last_page = _last_tour_page(first_page_elements['sel'])

        for idx in range(1, last_page + 1):
            loaded = (
                first_page_elements
                if idx == 1
                else await self.fetch_and_load(tour_url(idx), FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] {tour_url(idx)}')
            )
            if not loaded:
                break

            saw_scene, exact_hit = self._collect_scenes(loaded['sel'], results, search_data)
            if not saw_scene or exact_hit:
                break

    def _collect_scenes(self, sel: Selector, results: list[SearchResult], search_data: SearchContext) -> tuple[bool, bool]:
        current_date = ''
        saw_scene = False
        exact_hit = False
        for node in sel.xpath('//b | //table[@width="880"]'):
            tag = getattr(node.root, 'tag', '')
            if tag == 'b':
                txt = node.xpath('normalize-space(.)').get() or ''
                if 'Update' in txt:
                    current_date = iso_date(txt.split(':')[-1].strip(), '%m/%d/%Y') or ''

                continue

            saw_scene = True

            summary = _WS_RE.sub(' ', node.xpath('normalize-space((.//td[@height="105" or @height="90"])[1])').get() or '').strip()
            if not summary:
                continue

            poster = first_attr(node, '(.//img[contains(@src,"tour")][@width="400"]/@src)[1]')
            if not poster:
                continue

            actor_first = summary.split(' ')[0].strip().lower()
            fft_src = node.xpath('(.//img[contains(@src,"fft")]/@src)[1]').get() or ''
            from_img = (fft_src.split('_')[-1].split('.')[0]).strip().lower()
            tail = from_img.split(actor_first)[-1] if actor_first else from_img
            raw_name = title_case(f'{actor_first} {tail}'.strip())

            resolved = _resolve_actors(raw_name)
            actors = resolved or [raw_name]
            detail = {'poster': poster, 'releaseDate': current_date, 'actors': actors, 'summary': summary}

            if search_data.search_date and current_date == search_data.search_date:
                exact_hit = True

            results.append(
                build_search_result(
                    title=' and '.join(actors),
                    scene_url=poster,
                    query=search_data.title,
                    display_date=current_date or None,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([json.dumps(detail)]),
                )
            )

        return saw_scene, exact_hit

    # ── Detail (decoded from the curID JSON — no HTTP) ────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        try:
            extra = json.loads(payload)
        except (ValueError, TypeError):
            return None

        return LoadedScene(url=extra.get('poster', ''), site=site, extra=extra)

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        assert isinstance(scene.extra, dict)
        return scene.extra

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = f'{" and ".join(self._data(scene)["actors"])} from JesseLoadsMonsterFacials.com'

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = self._data(scene).get('summary') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Jesse Loads Monster Facials'

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = ['Jesse Loads Monster Facials']

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._data(scene).get('releaseDate') or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Facial']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = [ActorResult(name=n) for n in self._data(scene).get('actors', []) if n != 'Compilation']

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = self._data(scene).get('poster')

        metadata.art = [absolute_url(poster, scene.site.base_url)] if poster else []
