from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

_FIXED_GENRES_DATA = Path(__file__).parent / '_data' / 'json' / 'dorcelclub_fixed_genres.json'
_FIXED_GENRES: list[str] = json.loads(_FIXED_GENRES_DATA.read_text(encoding='utf-8'))

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
    # Mirror the TS port's JS split('_', 3).pop() semantics (first 3 fields, take the 3rd).
    first3 = value.split('_')[:3]
    key = first3[-1].split('.')[0] if first3 else ''
    return value.replace(f'_{key}', '', 1)


class DorcelClubClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', quote(ctx.title))
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []
        sel = loaded['sel']
        results: list[SearchResult] = []

        def card_result(title: str, scene_url: str) -> SearchResult:
            return build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))

        # (1) Direct scene cards.
        for card in sel.xpath(_SCENE_CARD_XP):
            title = first_text(card, './/div[contains(@class,"textual")]/a')
            href = (card.xpath('(.//a[contains(@class,"title")]/@href)[1]').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            results.append(card_result(title, scene_url))

        # (2) Movie cards — the movie is a result and its sub-scenes are appended.
        for card in sel.xpath(_MOVIE_CARD_XP):
            movie_title = first_text(card, './h2')
            movie_href = (card.xpath('@href').get() or '').strip()
            if not movie_title or not movie_href:
                continue
            movie_url = movie_href if movie_href.startswith('http') else absolute_url(movie_href, ctx.site_info.base_url)
            results.append(card_result(f'{movie_title} - Full Movie', movie_url))

            movie_page = await self.fetch_and_load(movie_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] movie {movie_title}')
            if not movie_page:
                continue
            for scene in movie_page['sel'].xpath(_MOVIE_SUBSCENE_XP):
                scene_title = first_text(scene, './/div[contains(@class,"textual")]/a')
                scene_href = (scene.xpath('(.//a[contains(@class,"title")]/@href)[1]').get() or '').strip()
                if not scene_title or not scene_href:
                    continue
                scene_url = scene_href if scene_href.startswith('http') else absolute_url(scene_href, ctx.site_info.base_url)
                results.append(card_result(scene_title, scene_url))

        return results

    # ── Detail field hooks (branch on movie vs scene URL) ─────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h1') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//span[contains(@class,"full")]') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        out = [scene.site.name]
        movie_name = first_text(scene.sel, '//span[contains(@class,"movie")]/a')
        if movie_name:
            out.append(movie_name)
        return out

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        if _is_movie_url(scene.url):
            raw = first_text(scene.sel, '//span[contains(@class,"out_date")]').replace('Year :', '').strip()
        else:
            raw = first_text(scene.sel, '//span[contains(@class,"publish_date")]')
        return iso_date(raw) or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = list(_FIXED_GENRES)
        if not _is_movie_url(scene.url):
            count = len(scene.sel.xpath('//div[contains(@class,"actress")]/a'))
            if count == 3:
                genres.append('Threesome')
            elif count == 4:
                genres.append('Foursome')
            elif count > 4:
                genres.append('Orgy')
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        if _is_movie_url(scene.url):
            els = scene.sel.xpath('//div[contains(@class,"actor") and contains(@class,"thumbnail")]/a/div[contains(@class,"name")]')
        else:
            els = scene.sel.xpath('//div[contains(@class,"actress")]/a')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in els:
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            actors.append(ActorResult(name=name))
        return actors

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, '//span[contains(@class,"director")]').replace('Director :', '').strip()
        return [ActorResult(name=raw)] if raw else None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def add(raw: str) -> None:
            cleaned = _clean_srcset_image(raw)
            if cleaned and cleaned not in images:
                images.append(cleaned)

        if _is_movie_url(scene.url):
            cover = (scene.sel.xpath('(//div[contains(@class,"header")]//source[contains(@data-srcset,"1536")]/@data-srcset)[1]').get() or '').strip()
            if cover:
                add(cover)
        for raw in scene.sel.xpath('//div[contains(@class,"photos")]//source/@data-srcset').getall():
            add((raw or '').strip())
        return images
