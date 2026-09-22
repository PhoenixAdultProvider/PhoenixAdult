from __future__ import annotations

from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_TITLE_XP = '//p[contains(@class,"sub_title")]'


def _table_value(sel: Selector, label: str) -> str:
    return first_text(sel, f'(//tr[contains(.,"{label}")]//td[contains(@class,"movie_table_td2")])[1]')


def _title_of(sel: Selector) -> str:
    return first_text(sel, _TITLE_XP).split('/')[0].strip()


class Kin8tengokuClient(Client):
    genres_xpath = '//tr[contains(.,"Category")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        keyword = search_data.title.strip()
        if search_data.scene_id:
            direct_url = f'{base}/moviepages/{search_data.scene_id}/index.html'
            search_results = await self.fetch_and_load(
                direct_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {direct_url}'
            )
            raw_title = _title_of(search_results['sel']) if search_results else ''
            if raw_title:
                date = _table_value(search_results['sel'], 'Date') if search_results else ''
                seen.add(direct_url)

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=raw_title,
                        scene_url=direct_url,
                        query=search_data.title,
                        display_date=iso_date(date) if date else None,
                        search_date=search_data.search_date,
                        score=100,
                        cur_id=pack_cur_id([x for x in (direct_url, (iso_date(date) if date else search_data.search_date)) if x]),
                    )
                )

        search_url = base + search_data.site_info.search_path + quote(keyword or search_data.title).replace('%20', '+')
        search_results = await self.fetch_and_load(search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {search_url}')
        if search_results:
            for search_result in search_results['sel'].xpath('//div[contains(@class,"movie_list")]'):
                href = first_attr(search_result, '(.//div[contains(@class,"movielisttext03")]//a/@href)[1]')
                if not href:
                    continue

                scene_url = href if href.startswith('http') else base + href
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                raw_title = first_text(search_result, './/div[contains(@class,"movielisttext02")]')
                if not raw_title:
                    continue

                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=raw_title,
                        scene_url=scene_url,
                        query=keyword or search_data.title,
                        search_date=search_data.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, search_data.search_date) if x]),
                    )
                )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _title_of(details_page_elements) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = _table_value(details_page_elements, 'Date')

        metadata.release_date = (iso_date(date, '%Y-%m-%d') if date else None) or scene.scene_date or None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for actor_link in details_page_elements.xpath('//tr[contains(.,"Model")]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if actor_name and actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors
