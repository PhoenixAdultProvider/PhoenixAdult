from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text, meta_content

STUDIO = 'Swallow Bay'
_SLUG_RE = re.compile(r"[\s']")
_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)')
_DATE_PREFIX_RE = re.compile(r'^Date:\s*', re.IGNORECASE)
_MODELS_XP = '//div[contains(concat(" ", normalize-space(@class), " "), " content-models ")]/a'


def _parse_date(raw: str) -> str | None:
    cleaned = _ORDINAL_RE.sub(r'\1', raw)
    return iso_date(cleaned, '%d %b %Y') or iso_date(cleaned)


class SwallowBayClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        slug = _SLUG_RE.sub('-', search_data.title.strip().lower())
        scene_url = base + search_data.site_info.search_path.replace('{query}', slug)
        search_results = await self.fetch_and_load(scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] direct-URL {slug}')
        if not search_results:
            return

        title = meta_content(search_results['sel'], 'twitter:image:alt')
        if not title:
            return

        results.append(
            build_search_result(
                title=title, scene_url=scene_url, query=search_data.title, search_date=search_data.search_date, score=100, cur_id=pack_cur_id([scene_url])
            )
        )

    # ── Context Loader (default fetches the scene URL) ─────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url = payload.split('|', 1)[0]
        details_page_elements = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not details_page_elements:
            return None

        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=details_page_elements['sel'], html=details_page_elements['html'])

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = meta_content(details_page_elements, 'twitter:image:alt') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"content-desc") and contains(@class,"more-desc")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = _DATE_PREFIX_RE.sub('', first_text(details_page_elements, '//div[contains(@class,"content-date")]'))

        metadata.release_date = _parse_date(date) if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath('//div[contains(@class,"box")]//a')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        entries: list[ActorResult] = []
        for actor_link in details_page_elements.xpath(_MODELS_XP):
            actor_name = first_attr(actor_link, '@title')
            photo = ''
            if actor_name:
                photo = (
                    details_page_elements.xpath(f'(//div[contains(@class,"content-models-photos")]//a[@title="{actor_name}"]//span//img/@src)[1]').get() or ''
                ).strip()

            entries.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        poster = meta_content(details_page_elements, 'og:image')

        metadata.art = [poster] if poster else []
