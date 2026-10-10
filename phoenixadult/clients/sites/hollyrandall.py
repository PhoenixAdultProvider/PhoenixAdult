from __future__ import annotations

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import b64url_decode, b64url_encode, pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_PAYWALL_HOST = 'join.hollyrandall.com'


class HollyRandallClient(Client):
    genres_xpath = '//ul[contains(@class,"tags")]//li//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        url = search_data.search_url()
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"item-video")]'):
            anchor = search_result.xpath('(.//div[contains(@class,"item-thumb")]/a)[1]')
            title = first_attr(anchor, '@title')
            href = first_attr(anchor, '@href')
            if not title or not href or _PAYWALL_HOST in href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            raw_date = search_result.xpath('normalize-space((.//div[contains(@class,"timeDate")])[1])').get() or ''
            date_tok = raw_date.split('|')[-1].strip()
            date = iso_date(date_tok) if date_tok else None
            title_b64 = b64url_encode(title)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, f'{date or ""}|{title_b64}']),
                )
            )

    # ── Context Loader (curID-packed title/date) ──────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        parts = payload.split('|')
        url = parts[0] if parts else ''
        if not url:
            return None

        date_tok = parts[1] if len(parts) > 1 else ''
        title_b64 = parts[2] if len(parts) > 2 else ''
        fallback_title = None
        if title_b64:
            try:
                decoded = b64url_decode(title_b64)
                fallback_title = decoded or None
            except (ValueError, UnicodeDecodeError):
                fallback_title = None

        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        return LoadedScene(
            url=url,
            site=site,
            scene_date=date_tok or None,
            fallback_title=fallback_title,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
        )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (scene.fallback_title or '').strip() or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = details_page_elements.xpath('(//div[contains(@class,"info")]//p)[1]')
        text = p.xpath('string(.)').get() or ''
        lines = text.split('\n')
        if len(lines) <= 3:
            return

        line = lines[3].replace('Featuring:', '').strip()
        if not line:
            return

        metadata.actors = self.dedup_people([ActorResult(name=part) for part in line.split(',')])

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//img[contains(@class,"update_thumb")]/@src0_3x').getall():
            images.push((image_url or '').strip())

        metadata.art = images.items
