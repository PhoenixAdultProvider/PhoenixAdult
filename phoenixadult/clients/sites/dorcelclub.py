from __future__ import annotations

import re
from urllib.parse import quote

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

_FIXED_GENRES: list[str] = ['Blockbuster Movie', 'French porn']

STUDIO = 'Marc Dorcel'
_DENSITY_RE = re.compile(r'\s*\d+x\s*$')

_SCENE_CARD_XP = (
    '//div[contains(@class,"scenes") and contains(@class,"list")]/div[contains(@class,"items")]/div[contains(@class,"scene") and contains(@class,"thumbnail")]'
)
_MOVIE_CARD_XP = (
    '//div[contains(@class,"movies") and contains(@class,"list")]/div[contains(@class,"items")]/a[contains(@class,"movie") and contains(@class,"thumbnail")]'
)
_MOVIE_SUBSCENE_XP = '//div[contains(@class,"scenes")]/div[contains(@class,"list")]/div[contains(@class,"scene") and contains(@class,"thumbnail")]'


def _is_movie_url(url: str) -> bool:
    return 'porn-movie' in url


def _clean_srcset_image(raw: str) -> str:
    if not raw:
        return ''

    value = raw.split(',')[-1].strip() if ',' in raw else raw
    value = _DENSITY_RE.sub('', value).strip()
    first3 = value.split('_')[:3]
    key = first3[-1].split('.')[0] if first3 else ''
    return value.replace(f'_{key}', '', 1)


class DorcelClubClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        url = search_data.search_url(quote(search_data.title))
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"')
        if not search_results:
            return

        sel = search_results['sel']

        def card_result(title: str, scene_url: str) -> SearchResult:
            return build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                search_date=search_data.search_date,
                cur_id=pack_cur_id([scene_url]),
            )

        for card in sel.xpath(_SCENE_CARD_XP):
            title = first_text(card, './/div[contains(@class,"textual")]/a')
            href = first_attr(card, '(.//a[contains(@class,"title")]/@href)[1]')
            if not title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)

            results.append(card_result(title, scene_url))

        for card in sel.xpath(_MOVIE_CARD_XP):
            movie_title = first_text(card, './h2')
            movie_href = first_attr(card, '@href')
            if not movie_title or not movie_href:
                continue

            movie_url = absolute_url(movie_href, search_data.site_info.base_url)

            results.append(card_result(f'{movie_title} - Full Movie', movie_url))

            movie_page_elements = await self.fetch_and_load(
                movie_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] movie {movie_title}'
            )
            if not movie_page_elements:
                continue

            for scene in movie_page_elements['sel'].xpath(_MOVIE_SUBSCENE_XP):
                scene_title = first_text(scene, './/div[contains(@class,"textual")]/a')
                scene_href = first_attr(scene, '(.//a[contains(@class,"title")]/@href)[1]')
                if not scene_title or not scene_href:
                    continue

                scene_url = absolute_url(scene_href, search_data.site_info.base_url)

                results.append(card_result(scene_title, scene_url))

    # ── Update Field Hooks (branch on movie vs scene URL) ─────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_text(details_page_elements, '//h1') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_text(details_page_elements, '//span[contains(@class,"full")]') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        out = [scene.site.name]
        movie_name = first_text(details_page_elements, '//span[contains(@class,"movie")]/a')
        if movie_name:
            out.append(movie_name)

        metadata.collections = out

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if _is_movie_url(scene.url):
            date = first_text(details_page_elements, '//span[contains(@class,"out_date")]').replace('Year :', '').strip()
        else:
            date = first_text(details_page_elements, '//span[contains(@class,"publish_date")]')

        metadata.release_date = iso_date(date) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres = list(_FIXED_GENRES)
        if not _is_movie_url(scene.url):
            count = len(details_page_elements.xpath('//div[contains(@class,"actress")]/a'))
            if group := self.group_genre_for(count):
                genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        if _is_movie_url(scene.url):
            els = details_page_elements.xpath('//div[contains(@class,"actor") and contains(@class,"thumbnail")]/a/div[contains(@class,"name")]')
        else:
            els = details_page_elements.xpath('//div[contains(@class,"actress")]/a')

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for row in els:
            actor_name = first_attr(row, 'normalize-space(.)')
            if not actor_name or actor_name in seen:
                continue

            seen.add(actor_name)
            actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = first_text(details_page_elements, '//span[contains(@class,"director")]').replace('Director :', '').strip()

        metadata.directors = [ActorResult(name=raw)] if raw else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(_clean_srcset_image)

        if _is_movie_url(scene.url):
            cover = first_attr(details_page_elements, '(//div[contains(@class,"header")]//source[contains(@data-srcset,"1536")]/@data-srcset)[1]')
            if cover:
                images['push'](cover)

        for image_url in details_page_elements.xpath('//div[contains(@class,"photos")]//source/@data-srcset').getall():
            images['push']((image_url or '').strip())

        metadata.art = images['list']
