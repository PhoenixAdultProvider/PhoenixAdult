from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_LI_XP = '//div[contains(@class,"videoContent")]//ul/li'


class MeanaWolfClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        for search_result in search_results['sel'].xpath('//div[contains(@class,"videoBlock")]'):
            anchor = search_result.xpath('(.//p/a)[1]')
            title = first_attr(anchor, 'normalize-space(.)')
            href = first_attr(anchor, '@href')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            poster = first_attr(search_result, '(.//img[contains(@class,"video_placeholder")]/@src)[1]')

            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, poster]),
                )
            )

    # ── Context Loader (curID packs the search-card poster) ───────────────────

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

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//div[contains(@class,"trailerArea")]//h3') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"trailerContent")]//p') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Meana Wolf'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, f'({_LI_XP})[2]').replace('ADDED:', '').strip()

        metadata.release_date = iso_date(date, '%B %d, %Y') if date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [genre_link.xpath('normalize-space(.)').get() for genre_link in details_page_elements.xpath(f'({_LI_XP})[last()]//a')]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        for actor_link in details_page_elements.xpath(f'({_LI_XP})[3]//a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name:
                continue

            photo = ''
            href = first_attr(actor_link, '@href')
            if href:
                model_page_elements = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = first_attr(model_page_elements['sel'], '(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]') if model_page_elements else ''
                photo = (absolute_url(raw, scene.site.base_url)) if raw else ''

            actors.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        poster = scene.extra.get('poster', '') if isinstance(scene.extra, dict) else ''
        if not poster:
            return

        metadata.art = [absolute_url(poster, scene.site.base_url)]
