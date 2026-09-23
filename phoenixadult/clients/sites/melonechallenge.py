from __future__ import annotations

from phoenixadult.clients.base import Client, LoadedScene, LoadedSearch
from phoenixadult.models.scrape import SceneDetail
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.urls import absolute_url


class MeloneChallengeClient(Client):
    candidate_include = ('/video/',)
    title_xpath = '//a[contains(@class,"dark")]'

    # ── Search Field Hooks ────────────────────────────────────────────────────

    def search_cur_id(self, scene_url: str, date: str | None, loaded: LoadedSearch) -> str:
        return pack_cur_id([p for p in (scene_url, date or loaded.ctx.search_date) if p])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for row in details_page_elements.xpath('//figure//img'):
            images.push(first_attr(row, '@src'))

        metadata.art = images.items
