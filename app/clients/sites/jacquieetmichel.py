from __future__ import annotations

import json
from pathlib import Path

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

_ACTORS_DATA = Path(__file__).parent / '_data' / 'json' / 'jacquieetmichel_actors.json'
_ACTORS: dict[str, list[str]] = json.loads(_ACTORS_DATA.read_text(encoding='utf-8'))

_RELEASE_XP = '(//div[contains(@class,"content-detail__infos__row")]//p[contains(@class,"content-detail__description--link")])[2]'


class JacquieEtMichelClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//a[contains(@class,"content-card--video")]'):
                title = first_text(card, './/h2[contains(@class,"content-card__title")]')
                href = (card.xpath('@href').get() or '').strip()
                if not title or not href:
                    continue
                scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date_raw = first_text(card, './/div[contains(@class,"content-card__date")]').replace('Added on', '').strip()
                date = iso_date(date_raw)
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

        if ctx.scene_id:
            scene_url = f'{base}/en/content/{ctx.scene_id}'
            if scene_url not in seen:
                direct = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
                title = first_text(direct['sel'], '//h1[contains(@class,"content-detail__title")]') if direct else ''
                if title:
                    results.append(
                        build_search_result(
                            title=title,
                            scene_url=scene_url,
                            query=ctx.title,
                            search_date=ctx.search_date,
                            score=100,
                            cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                        )
                    )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1[contains(@class,"content-detail__title")]') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"content-detail__description")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Jacquie Et Michel TV'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, _RELEASE_XP)
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//div[contains(@class,"content-detail__row")]//li[contains(@class,"content-detail__tag")]'):
            g = (el.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            if g == 'Sodomy':
                g = 'Anal'
            if g and g not in genres:
                genres.append(g)
        if 'French porn' not in genres:
            genres.append('French porn')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        for fragment, names in _ACTORS.items():
            if fragment in scene.url:
                return [ActorResult(name=name) for name in names]
        return []

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//video/@poster)[1]').get() or '').strip()
        if not raw:
            return []
        return [raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)]
