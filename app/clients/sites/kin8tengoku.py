from __future__ import annotations

from urllib.parse import quote

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

_TITLE_XP = '//p[contains(@class,"sub_title")]'


def _table_value(sel: Selector, label: str) -> str:
    return first_text(sel, f'(//tr[contains(.,"{label}")]//td[contains(@class,"movie_table_td2")])[1]')


def _title_of(sel: Selector) -> str:
    return first_text(sel, _TITLE_XP).split('/')[0].strip()


class Kin8tengokuClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        keyword = ctx.title.strip()
        if ctx.scene_id:
            direct_url = f'{base}/moviepages/{ctx.scene_id}/index.html'
            loaded = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {direct_url}')
            raw_title = _title_of(loaded['sel']) if loaded else ''
            if raw_title:
                date = _table_value(loaded['sel'], 'Date') if loaded else ''
                seen.add(direct_url)
                results.append(
                    build_search_result(
                        title=raw_title,
                        scene_url=direct_url,
                        query=ctx.title,
                        display_date=iso_date(date) if date else None,
                        search_date=ctx.search_date,
                        score=100,
                        cur_id=pack_cur_id([x for x in (direct_url, (iso_date(date) if date else ctx.search_date)) if x]),
                    )
                )

        search_url = base + ctx.site_info.search_path + quote(keyword or ctx.title).replace('%20', '+')
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//div[contains(@class,"movie_list")]'):
                href = (card.xpath('(.//div[contains(@class,"movielisttext03")]//a/@href)[1]').get() or '').strip()
                if not href:
                    continue
                scene_url = href if href.startswith('http') else base + href
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                raw_title = first_text(card, './/div[contains(@class,"movielisttext02")]')
                if not raw_title:
                    continue
                results.append(
                    build_search_result(
                        title=raw_title,
                        scene_url=scene_url,
                        query=keyword or ctx.title,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                    )
                )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _title_of(scene.sel) or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = _table_value(scene.sel, 'Date')
        return (iso_date(raw, '%Y-%m-%d') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath('//tr[contains(.,"Category")]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//tr[contains(.,"Model")]//a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            if name and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        return actors
