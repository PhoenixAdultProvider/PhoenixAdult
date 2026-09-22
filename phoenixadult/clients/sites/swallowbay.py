from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text, meta_content
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result

_SLUG_RE = re.compile(r"[\s']")
_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)')
_DATE_PREFIX_RE = re.compile(r'^Date:\s*', re.IGNORECASE)
_MODELS_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " content-models ")]/a'


def _parse_date(raw: str) -> str | None:
    cleaned = _ORDINAL_RE.sub(r'\1', raw)
    return iso_date(cleaned, '%d %b %Y') or iso_date(cleaned)


class SwallowBayClient(Client):
    summary_xpath = '//div[contains(@class,"content-desc") and contains(@class,"more-desc")]'
    genres_xpath = '//div[contains(@class,"box")]//a'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = _SLUG_RE.sub('-', search_data.title.strip().lower())
        scene_url = search_data.search_url(slug)
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct-URL {slug}')
        if not search_results:
            return

        title = meta_content(search_results['sel'], 'twitter:image:alt')
        if not title:
            return

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([scene_url]),
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

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = meta_content(details_page_elements, 'twitter:image:alt') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = _DATE_PREFIX_RE.sub('', first_text(details_page_elements, '//div[contains(@class,"content-date")]'))

        metadata.release_date = _parse_date(date) if date else None

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath(_MODELS_XP):
            actor_name = first_attr(actor_link, '@title')
            photo = ''
            if actor_name and '"' not in actor_name:
                photo = (
                    details_page_elements.xpath(f'(//div[contains(@class,"content-models-photos")]//a[@title="{actor_name}"]//span//img/@src)[1]').get() or ''
                ).strip()

            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        poster = meta_content(details_page_elements, 'og:image')

        metadata.art = [poster] if poster else []
