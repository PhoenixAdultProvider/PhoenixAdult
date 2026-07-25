from __future__ import annotations

import re
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_LEADING_ID_RE = re.compile(r'^(\d+)\s*(.*)$')
_GENRES_LIST_FIRST_A = '//div[contains(@class,"genres-list")]//a'


class AnalVidsClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        m = _LEADING_ID_RE.match(search_data.title.strip())
        source_id = m.group(1) if m else None
        text = (m.group(2).strip() if m else search_data.title.strip()) or search_data.title.strip()

        search_results = await self.fetch_json(
            f'{base}/api/autocomplete/search?q={quote(text)}',
            FetchCtx(capture=search_data.capture),
            label=f'[{search_data.site_info.name}] AnalVids search "{text}"',
        )

        for term in (search_results or {}).get('terms', []):
            if term.get('type') != 'scene' or not term.get('url') or not term.get('name'):
                continue

            url = term['url']
            scene_url = absolute_url(url, search_data.site_info.base_url)
            direct_hit = source_id is not None and str(term.get('source_id', '')) == source_id

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=term['name'].strip(),
                    scene_url=scene_url,
                    query=text,
                    search_date=search_data.search_date,
                    score=100 if direct_hit else None,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//h1[contains(@class,"watch__title")]')

        metadata.title = raw.split('featuring')[0].strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//div[contains(@class,"text-mob-more")]')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'AnalVids'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.tagline = first_text(details_page_elements, _GENRES_LIST_FIRST_A)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        tagline = first_text(details_page_elements, _GENRES_LIST_FIRST_A)

        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_text(details_page_elements, '//i[contains(@class,"bi-calendar3")]')

        metadata.release_date = iso_date(date) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        values: list[str | None] = [
            genre_link.xpath('normalize-space(.)').get()
            for genre_link in details_page_elements.xpath('//div[contains(@class,"genres-list")]//a[contains(@href,"/genre/")]')
        ]

        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"model")]//img/@src)[1]')

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//a[contains(@href,"/model/")]'):
            href = first_attr(actor_link, '@href')
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if not actor_name or not href or 'forum' in href:
                continue

            refs.append((actor_name, absolute_url(href, scene.site.base_url)))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture)

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        directors: list[ActorResult] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            n = name.strip()
            if n and n not in seen:
                seen.add(n)
                directors.append(ActorResult(name=n))

        tagline = first_text(details_page_elements, _GENRES_LIST_FIRST_A)
        if tagline in ('Giorgio Grandi', "Giorgio's Lab"):
            add('Giorgio Grandi')

        for director_link in details_page_elements.xpath('//p[contains(@class,"director")]//a'):
            add(director_link.xpath('normalize-space(.)').get() or '')

        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        poster = first_attr(details_page_elements, '(//div[contains(@class,"watch__video")]//video/@data-poster)[1]')

        metadata.art = [poster] if poster else []
