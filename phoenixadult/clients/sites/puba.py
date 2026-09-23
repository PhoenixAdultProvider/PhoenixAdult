from __future__ import annotations

from typing import Any

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail, SearchContext
from phoenixadult.utils.helpers.html_helpers import first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.urls import absolute_url, css_bg_image

_TITLE_XP = '//div[@id="body-player-container"]//div//div[contains(@class,"tour-video-title")]'


class PubaClient(Client):
    candidate_include = ('show_video',)
    candidate_exclude = ('index',)
    genres_xpath = '//center//div//a[contains(@class,"btn-outline-secondary")]'
    actors_xpath = '//center//div//a[contains(@class,"btn-secondary")]'

    def __init__(self) -> None:
        super().__init__({'Referer': 'https://www.puba.com/pornstarnetwork/index.php', 'Cookie': 'PHPSESSID=rvo9ieo5bhoh81knnmu88c3lf3'})

    # ── Search Field Hooks ────────────────────────────────────────────────────

    async def candidate_urls(self, search_data: SearchContext) -> list[str]:
        if not search_data.scene_id:
            return []
        return [f'{search_data.site_info.base_url.rstrip("/")}{search_data.site_info.search_path}show_video.php?galid={search_data.scene_id}']

    async def fetch_search_title(self, source: Any, loaded: LoadedSearch) -> str:
        return first_text(source.sel, _TITLE_XP)

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([scene_url])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, _TITLE_XP)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        style = details_page_elements.xpath('(//div[@id="body-player-container"]/div/a/img/@style)[1]').get() or ''
        bg = css_bg_image(style)
        if not bg:
            return

        metadata.art = [absolute_url(bg, scene.site.base_url)]
