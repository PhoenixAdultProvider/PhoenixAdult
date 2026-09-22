from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, meta_content
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url


class UltrafilmsClient(Client):
    title_xpath = '(//h1[contains(@class,"entry-title")])[last()]'
    summary_xpath = '//div[contains(@class,"video-description")]//div[contains(@class,"desc")]//p'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        await self._parse_page(f'{base}/?s=%22{search_data.encoded}%22', search_data, results, seen)
        if not results:
            await self._parse_page(f'{base}/?s={search_data.encoded}', search_data, results, seen)

    # ── Search Helpers ────────────────────────────────────────────────────────

    async def _parse_page(self, url: str, search_data: SearchContext, results: list[SearchResult], seen: set[str]) -> None:
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//main//article[@data-video-uid]'):
            title = first_attr(search_result, '(.//a)[1]/@title')
            href = first_attr(search_result, '(.//a)[1]/@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            if scene_url in seen:
                continue

            seen.add(scene_url)
            poster_url = first_attr(search_result, '(.//img/@data-src)[1]')

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, search_data.search_date or '', poster_url]),
                )
            )

    # ── Context Loader: unpack the poster slot ────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0]
        date = (parts[1] if len(parts) > 1 else '').strip()
        poster_url = (parts[2] if len(parts) > 2 else '').strip()
        details_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] detail {url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=date or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={'poster_url': poster_url},
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = meta_content(details_page_elements, 'article:published_time')
        if date:
            parsed = iso_date(date)
            if parsed:
                metadata.release_date = parsed
                return

        if scene.scene_date:
            metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//div[contains(@class,"tags-list")]//a[i[contains(@class,"fa-folder-open")]]'):
            t = (genre_link.xpath('normalize-space(.)').get() or '').replace('Movies', '').strip().lower()
            if t and t not in genres:
                genres.append(t)

        count = len(details_page_elements.xpath('//div[@id="video-actors"]//a'))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=(actor_link.xpath('normalize-space(.)').get() or '')) for actor_link in details_page_elements.xpath('//div[@id="video-actors"]//a')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra.get('poster_url') if isinstance(scene.extra, dict) else ''

        metadata.art = [poster] if poster else []
