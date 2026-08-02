from __future__ import annotations

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_text, web_search_urls
from phoenixadult.utils.logging.best_effort import best_effort

_TITLE_XP = '//div[@id="body-player-container"]//div//div[contains(@class,"tour-video-title")]'


class PubaClient(Client):
    def __init__(self) -> None:
        super().__init__({'Referer': 'https://www.puba.com/pornstarnetwork/index.php', 'Cookie': 'PHPSESSID=rvo9ieo5bhoh81knnmu88c3lf3'})

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        stem = f'{base}{search_data.site_info.search_path}'

        candidates: list[str] = []
        if search_data.scene_id:
            candidates.append(f'{stem}show_video.php?galid={search_data.scene_id}')

        with best_effort(search_data.site_info.name, 'webSearch'):
            for url in await web_search_urls(search_data.title, search_data.site_info):
                if 'show_video' in url and 'index' not in url and url not in candidates:
                    candidates.append(url)

        for scene_url, search_results in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda scene_url: f'[{search_data.site_info.name}] {scene_url}'
        ):
            if not search_results:
                continue

            card_title = first_text(search_results['sel'], _TITLE_XP)
            if not card_title:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=card_title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get()
            for genre_link in details_page_elements.xpath('//center//div//a[contains(@class,"btn-outline-secondary")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries = [
            ActorResult(name=actor_link.xpath('normalize-space(.)').get() or '')
            for actor_link in details_page_elements.xpath('//center//div//a[contains(@class,"btn-secondary")]')
        ]

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        style = details_page_elements.xpath('(//div[@id="body-player-container"]/div/a/img/@style)[1]').get() or ''
        bg = css_bg_image(style)
        if not bg:
            return

        metadata.art = [absolute_url(bg, scene.site.base_url)]
