from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text


class PlayboyPlusClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        scene_url = f'{base}{search_data.site_info.search_path}/{search_data.encoded}'
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {scene_url}')
        if not search_results:
            return

        page_poster = (search_results['sel'].xpath('(//img[contains(@class,"image")]/@data-src)[1]').get() or '').split('?')[0]

        for search_result in search_results['sel'].xpath('//div[@id="search-results-gallery"]//li[contains(@class,"item")]'):
            title = first_text(search_result, './/h3[contains(@class,"title")]')
            href = first_attr(search_result, '(.//a[contains(@class,"cardLink")]/@href)[1]')
            if not title or not href:
                continue

            url = href if href.startswith('http') else base + href
            date = iso_date(first_text(search_result, './/p[contains(@class,"date")]'))

            results.append(
                build_search_result(
                    title=title,
                    scene_url=url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([url, page_poster]),
                )
            )

    # ── Context loader (curID packs the search-card poster) ───────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        poster = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra={'poster': poster},
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1[contains(@class,"title")]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//p[contains(@class,"description-truncated")]').replace('...', '')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Playboy Plus'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//p[contains(@class,"date")]')

        metadata.release_date = (iso_date(date, '%B %d, %Y') if date else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.genres = ['Glamour']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=actor_link.xpath('normalize-space(.)').get() or '')
            for actor_link in details_page_elements.xpath('//p[contains(@class,"contributorName")]//a')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image.split('?')[0].strip(), scene.site.base_url))
        images['push'](scene.extra.get('poster', '') if isinstance(scene.extra, dict) else '')
        images['push'](details_page_elements.xpath('(//img[contains(@class,"image")]/@data-src)[1]').get() or '')
        for image_url in details_page_elements.xpath('//section[contains(@class,"gallery")]//img[contains(@class,"image")]/@data-src').getall():
            images['push'](image_url)

        metadata.art = images['list']
