from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, load_site_json, title_distance_score
from app.utils.searchengines import SearchOptions, web_search, web_search_available, web_search_filtered

STUDIO = 'First Time Videos'

_PHOTO_LOOKUP: dict[str, list[str]] = load_site_json(__file__, 'ftv_photo_lookup')

_GENRES: dict[str, list[str]] = {
    'FTVGirls': ['Teen', 'Solo', 'Public'],
    'FTVMilfs': ['MILF', 'Solo', 'Public'],
}

_POSTER_RULES: list[str] = [
    '//img[@id="Magazine"]/@src',
    '//div[contains(@class,"gallery")]//div[contains(@class,"row")]//*[@href]/@href',
    '//div[contains(@class,"thumbs_horizontal")]//*[@href]/@href',
    '//a[.//img[contains(@class,"t")]]/@href',
]
_SCENE_ID_RE = re.compile(r'-(\d+)\.')


def _photo_lookup(scene_id: int) -> list[str]:
    return _PHOTO_LOOKUP.get(str(scene_id), ['none'])


def _parse_title_and_date(sel: Any) -> tuple[str, str | None]:
    raw = sel.xpath('(//title)[1]').xpath('string(.)').get() or ''
    segments = raw.split('Released')
    title = segments[0].strip()
    date_raw = segments[-1].replace('!', '').strip()
    return title, (iso_date(date_raw) if date_raw else None)


def _collect_images(sel: Any) -> list[str]:
    out: list[str] = []
    for xp in _POSTER_RULES:
        out.extend(v for v in sel.xpath(xp).getall() if v)
    return out


__testing__ = {'photo_lookup': _photo_lookup, 'parse_title_and_date': _parse_title_and_date}


class FTVClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        host = urlsplit(ctx.site_info.base_url).netloc.removeprefix('www.')
        candidates: list[str] = []
        if ctx.scene_id:
            candidates.append(f'{base}{ctx.site_info.search_path}{ctx.scene_id}.html')
        if web_search_available():
            try:
                for url in await web_search_filtered(SearchOptions(query=ctx.title, site=host, num=10), url_contains='/update/'):
                    if url not in candidates:
                        candidates.append(url)
            except Exception:  # noqa: BLE001 - best-effort
                pass

        results: list[SearchResult] = []
        for scene_url in candidates:
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] candidate {scene_url}')
            if not loaded:
                continue
            title, date_iso = _parse_title_and_date(loaded['sel'])
            if not title:
                continue
            score = date_distance_score(ctx.search_date, date_iso) if ctx.search_date and date_iso else title_distance_score(ctx.title, title)
            results.append(
                build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date, score=score)
            )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _cast_base_names(self, scene: LoadedScene) -> list[str]:
        assert scene.sel is not None
        names = []
        for el in scene.sel.xpath('//div[@id="ModelDescription"]//h1'):
            n = (el.xpath('string(.)').get() or '').replace("'s Statistics", '').strip()
            if n:
                names.append(n)
        return names

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _parse_title_and_date(scene.sel)[0] or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@id="Bio"])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _parse_title_and_date(scene.sel)[1] or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        return _GENRES.get(scene.site.name) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        summary = (scene.sel.xpath('(//div[@id="Bio"])[1]').xpath('string(.)').get() or '').strip()
        thumbs = scene.sel.xpath('//div[@id="Thumbs"]//img/@src').getall()
        actors: list[ActorResult] = []
        for idx, el in enumerate(scene.sel.xpath('//div[@id="ModelDescription"]//h1')):
            base_name = (el.xpath('string(.)').get() or '').replace("'s Statistics", '').strip()
            if not base_name:
                continue
            name = base_name
            m = re.search(rf'\s({re.escape(base_name)} [A-Z]\w+)\s', summary)
            if m:
                name = m.group(1)
            photo_raw = thumbs[idx] if idx < len(thumbs) else ''
            actors.append(ActorResult(name=name, photo_url=absolute_url(photo_raw, base) if photo_raw else ''))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        out: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            abs_url = absolute_url(raw, base)
            if abs_url not in out:
                out.append(abs_url)

        m = _SCENE_ID_RE.search(scene.url)
        scene_id = int(m.group(1)) if m else 0
        slugs = _photo_lookup(scene_id)
        cast_query = ' '.join(self._cast_base_names(scene)).strip()
        if cast_query and web_search_available():
            host = urlsplit(base).netloc.removeprefix('www.')
            try:
                gallery_results = await web_search(SearchOptions(query=cast_query, site=host, num=10))
            except Exception:  # noqa: BLE001 - best-effort
                gallery_results = []
            for photo_url in gallery_results:
                is_gallery = 'galleries' in photo_url or 'preview' in photo_url
                slug_match = any(s == 'none' or s in photo_url for s in slugs)
                if not is_gallery or not slug_match:
                    continue
                g = await self.fetch_and_load(photo_url, None, f'GET {photo_url} (gallery)')
                if g:
                    for raw in _collect_images(g['sel']):
                        push(raw)

        for raw in _collect_images(scene.sel):
            push(raw)
        return out or None
