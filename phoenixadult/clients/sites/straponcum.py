from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_WS_RE = re.compile(r'\s+')
_ACTOR_XP = '//div[contains(@class,"card")]//span[contains(text(),"Featuring:")]/following-sibling::a'

_FIXED_GENRES: list[str] = ['Lesbian', 'Strap-On']


def _parse_date(tok: str) -> str | None:
    return iso_date(tok, '%B %d, %Y') or iso_date(tok)


def _date_from_clock(node: Any) -> str | None:
    parents = node.xpath('.//i[contains(@class,"fa-clock")]/..')
    if not parents:
        return None

    trail = first_attr(parents[0], 'normalize-space(.)')
    parts = trail.split('•')
    if len(parts) < 2:
        return None

    tok = parts[1].strip()
    return tok or None


class StraponCumClient(Client):
    title_xpath = '//h1[contains(@class,"card-title")]'
    summary_xpath = '//p[contains(@class,"card-text") and contains(@class,"mb-2")]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = _WS_RE.sub('-', search_data.title.strip())
        scene_url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct-URL {slug}')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"card")]'):
            title = first_text(search_result, './/h1[contains(@class,"card-title")]')
            if not title:
                continue

            tok = _date_from_clock(search_result)
            release_date = _parse_date(tok) if tok else None

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=release_date,
                    search_date=search_data.search_date,
                    score=100,
                    cur_id=pack_cur_id([p for p in (scene_url, release_date) if p]),
                )
            )

    # ── Context Loader (default fetches the scene URL) ─────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url = payload.split('|', 1)[0]
        details_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] detail {url}'
        )
        if not details_page_elements:
            return None

        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=details_page_elements['sel'], html=details_page_elements['html'])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        cards = details_page_elements.xpath('//div[contains(@class,"card")]')
        tok = _date_from_clock(cards[0]) if cards else None

        metadata.release_date = _parse_date(tok) if tok else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = list(_FIXED_GENRES)
        for genre_link in details_page_elements.xpath('//div[contains(@class,"tag-cloud")]//a'):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        count = len(details_page_elements.xpath(_ACTOR_XP))
        if (group := self.group_genre_for(count)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//img[starts-with(@id,"set-target")]/@data-src0_1x)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(_ACTOR_XP):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            href = first_attr(actor_link, '@href')
            if actor_name and href:
                refs.append((actor_name, absolute_url(href, base)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        scene_id = first_attr(details_page_elements, '(//div[contains(@class,"trailer")]//img/@alt)[1]')
        if not scene_id:
            return

        metadata.art = [f'{base}/content/{scene_id}/{idx}.jpg' for idx in range(4)]
