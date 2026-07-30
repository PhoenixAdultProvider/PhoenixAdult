from __future__ import annotations

import re
from dataclasses import dataclass, field

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_FULLTITLE_RE = re.compile(r'content/(.*)/')


@dataclass
class _SmtExtra:
    actors: list[ActorResult] = field(default_factory=list)
    release_date: str | None = None


class ScrewMeTooClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        encoded = search_data.title.strip().lower().replace(' ', '+').replace('--', '+')
        url = base + search_data.site_info.search_path.replace('{query}', encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"fsp")]//article'):
            title = first_text(search_result, './/h4')
            href = first_attr(search_result, '(.//*[@href]/@href)[1]')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            date = iso_date(first_text(search_result, './/div[contains(@class,"fsdate")]//span'))

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Context Loader (model headshots + cross-page release date) ────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback_date = payload[pipe + 1 :].strip() if pipe >= 0 else ''

        details_page_elements = await self.fetch_and_load(
            url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'[{site.name}] scene {url}'
        )
        if not details_page_elements:
            return None

        actors: list[ActorResult] = []
        last_model_sel: Selector | None = None
        for row in details_page_elements['sel'].xpath('//a[contains(@title,"Model Bio")]'):
            name = first_attr(row, 'normalize-space(.)')
            href = first_attr(row, '@href')
            if not name or not href:
                continue

            model_url = absolute_url(href, site.base_url)
            model_page_elements = await self.fetch_and_load(
                model_url, FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass), f'GET {model_url} (actor)'
            )
            photo = ''
            if model_page_elements:
                last_model_sel = model_page_elements['sel']
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"model-contr-colone")]//*[@src]/@src)[1]')
                photo = (absolute_url(raw, site.base_url)) if raw else ''

            actors.append(ActorResult(name=name, photo_url=photo))

        release_date = fallback_date or None
        m = _FULLTITLE_RE.search(url)
        if last_model_sel is not None and m:
            full_title = m.group(1)
            raw = first_text(last_model_sel, f'//a[contains(@href,"{full_title}")]//div[contains(@class,"fsdate")]')
            release_date = iso_date(raw) or (fallback_date or None)

        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback_date or None,
            capture=ctx.capture if ctx else None,
            sel=details_page_elements['sel'],
            html=details_page_elements['html'],
            extra=_SmtExtra(actors=actors, release_date=release_date),
        )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _extra(self, scene: LoadedScene) -> _SmtExtra:
        return scene.extra if isinstance(scene.extra, _SmtExtra) else _SmtExtra()

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[h2]').replace('Read More ...Read Less', '').strip()

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._extra(scene).release_date or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        category_text = details_page_elements.xpath('string((//div[contains(@class,"amp-category")])[1])').get() or ''
        for line in category_text.split('\n'):
            genre_name = line.strip()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        cast = len(self._extra(scene).actors)
        if group := self.group_genre_for(cast + 1):
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._extra(scene).actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//div[contains(@class,"amp-vis-mobile")]//*[@src]/@src').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
