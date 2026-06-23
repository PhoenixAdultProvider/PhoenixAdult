from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.processors.title_case import title_case

_ACTORS_DATA = Path(__file__).parent / '_data' / 'json' / 'jesseloads_actors.json'
_ACTORS: dict[str, list[str]] = json.loads(_ACTORS_DATA.read_text(encoding='utf-8'))
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
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        def tour_url(idx: int) -> str:
            return f'{base}/visitors/tour_{idx:02d}.html'

        first = await self.fetch_and_load(tour_url(1), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {tour_url(1)}')
        if not first:
            return []
        last_page = _last_tour_page(first['sel'])

        results: list[SearchResult] = []
        for idx in range(1, last_page + 1):
            loaded = first if idx == 1 else await self.fetch_and_load(tour_url(idx), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] {tour_url(idx)}')
            if not loaded:
                break
            saw_scene, exact_hit = self._collect_scenes(loaded['sel'], results, ctx)
            if not saw_scene or exact_hit:
                break
        return results

    def _collect_scenes(self, sel: Selector, results: list[SearchResult], ctx: SearchContext) -> tuple[bool, bool]:
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
            poster = (node.xpath('(.//img[contains(@src,"tour")][@width="400"]/@src)[1]').get() or '').strip()
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

            if ctx.search_date and current_date == ctx.search_date:
                exact_hit = True
            results.append(
                build_search_result(
                    title=' and '.join(actors),
                    scene_url=poster,
                    query=ctx.title,
                    display_date=current_date or None,
                    search_date=ctx.search_date,
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

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        return f'{" and ".join(self._data(scene)["actors"])} from JesseLoadsMonsterFacials.com'

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        return self._data(scene).get('summary') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Jesse Loads Monster Facials'

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return ['Jesse Loads Monster Facials']

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return self._data(scene).get('releaseDate') or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return ['Facial']

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        return [ActorResult(name=n) for n in self._data(scene).get('actors', []) if n != 'Compilation']

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        poster = self._data(scene).get('poster')
        return [absolute_url(poster, scene.site.base_url)] if poster else []
