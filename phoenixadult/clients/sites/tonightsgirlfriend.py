from __future__ import annotations

from typing import Any

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id, strip_query
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

STUDIO = 'Naughty America'
TAGLINE = "Tonight's Girlfriend"
MAX_PAGES = 4
FULL_PAGE_THRESHOLD = 9

_FIXED_GENRES: list[str] = ['Girlfriend Experience', 'Hotel', 'Pornstar', 'Pornstar Experience']
_GREY_XP = '//p[contains(@class,"grey-performers")]'


def _https(src: str) -> str:
    return src if src.startswith('http') else f'https:{src}'


class TonightsGirlfriendClient(Client):
    summary_xpath = '//p[contains(@class,"scene-description")]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        slug = search_data.title.lower().split('and ')[0].strip().replace(' ', '-')
        if not slug:
            return

        base = search_data.site_info.base_url.rstrip('/')
        path = search_data.site_info.search_path

        async def fetch_rows(page: int) -> list[Any] | None:
            url = f'{base}{path}{slug}/?p={page}'
            search_results = await self.fetch_and_load(
                url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search page {page} "{search_data.title}"'
            )
            return list(search_results['sel'].xpath('//div[contains(@class,"panel-body")]')) if search_results else None

        def build_row(row: Any) -> SearchResult | None:
            actor_names = [n for n in (a.xpath('normalize-space(.)').get() or '' for a in row.xpath('.//span[contains(@class,"scene-actors")]//a')) if n]
            if not actor_names:
                return None

            href = first_attr(row, '(.//a/@href)[1]')
            if not href:
                return None

            scene_url = (absolute_url(href, base)).split('?')[0]
            raw_date = first_text(row, './/span[contains(@class,"scene-date")]')
            date = iso_date(raw_date) if raw_date else None
            return build_search_result(
                site=search_data.site_info,
                title=', '.join(actor_names),
                scene_url=scene_url,
                query=actor_names[0],
                display_date=date,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url, date or '']),
            )

        results.extend(await self.paginate_search(fetch_rows=fetch_rows, build_row=build_row, max_pages=MAX_PAGES, full_page=FULL_PAGE_THRESHOLD))

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _linked_actor_names(self, scene: LoadedScene) -> list[str]:
        details_page_elements = scene.require_sel()

        names = self.dedup_strings([first_attr(actor_link, 'normalize-space(.)') for actor_link in details_page_elements.xpath(f'{_GREY_XP}//a')])
        return names

    def _male_actor_names(self, scene: LoadedScene, linked: list[str]) -> list[str]:
        details_page_elements = scene.require_sel()

        nodes = details_page_elements.xpath(_GREY_XP)
        info = first_attr(nodes[0], 'normalize-space(.)') if nodes else ''
        if not info:
            return []

        for actor_name in linked:
            info = info.replace(f'{actor_name},', '').strip()

        out = self.dedup_strings([part.strip() for part in info.split(',')])
        return out

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        names = self._linked_actor_names(scene)

        metadata.title = ', '.join(names) if names else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = TAGLINE

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [TAGLINE]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        if not scene.scene_date:
            return

        metadata.release_date = iso_date(scene.scene_date) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        genres = list(_FIXED_GENRES)
        linked = self._linked_actor_names(scene)
        male = self._male_actor_names(scene, linked)
        if len(linked) + len(male) == 3:
            genres.append('Threesome')
            genres.append('BGG' if len(linked) == 2 else 'BBG')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            src = first_attr(sel, '(//div[contains(@class,"performer-details")]//img/@src)[1]')
            return _https(src) if src else ''

        refs: list[tuple[str, str]] = []
        for a in details_page_elements.xpath(f'{_GREY_XP}//a'):
            actor_name = first_attr(a, 'normalize-space(.)')
            actor_url = strip_query(first_attr(a, '@href'))
            if actor_name:
                refs.append((actor_name, absolute_url(actor_url, base) if actor_url else ''))

        actors = list(await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name))
        seen = {a.name for a in actors}

        for actor_name in self._male_actor_names(scene, [a.name for a in actors]):
            if actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        src = first_attr(details_page_elements, '(//img[contains(@class,"playcard")]/@src)[1]')
        if not src:
            return

        poster = _https(src)
        out = [poster]
        head = poster.split('scene/image')[0].split('scene/horizontal')[0]
        vertical = f'{head}scene/vertical/390x590cdynamic.jpg'
        if vertical != poster:
            out.append(vertical)

        metadata.art = out
