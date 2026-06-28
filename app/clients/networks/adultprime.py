from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, iso_date, load_site_json

STUDIO = 'Adult Prime'

_STUDIO_OVERRIDES: dict[str, str] = load_site_json(__file__, 'adultprime_studios')
_SKIP_PREFIXES: list[str] = load_site_json(__file__, 'adultprime_skip_prefixes')

_EURO_DATE_RE = re.compile(r'(\d{2})\.(\d{2})\.(\d{4})')

# Date <b> guarded by a preceding calendar icon (legacy-faithful; avoids the
# Studio/Niches/Performer <b> the TS "first b" selector could grab).
_DATE_XP = '(//p[contains(@class,"update-info-line")]/b[preceding-sibling::i[contains(@class,"calendar")]])[1]'
_TITLE_XP = '(//h1)[1]'


def _studio_for(name: str) -> str:
    return _STUDIO_OVERRIDES.get(name, STUDIO)


def _parse_euro_date(s: str) -> str | None:
    m = _EURO_DATE_RE.search(s)
    return f'{m.group(3)}-{m.group(2)}-{m.group(1)}' if m else None


def _clean_title(raw: str) -> str:
    return raw.split(':')[-1].split('Full video by')[0].strip()


def _info_line_xp(label: str) -> str:
    return f'(//p[contains(@class,"update-info-line")][./b[contains(.,"{label}")]])[1]'


__testing__ = {
    'parse_euro_date': _parse_euro_date,
    'clean_title': _clean_title,
    'studio_for': _studio_for,
}


class AdultPrimeClient(Client):
    # ── Search (full override: direct sceneID lookup + video/performer search) ───

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        # Direct numeric lookup at /studios/video/<id>.
        if ctx.scene_id:
            url = f'{base}/studios/video/{ctx.scene_id}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'GET {url}')
            if loaded:
                title = _clean_title(loaded['sel'].xpath(f'string({_TITLE_XP})').get() or '')
                if title:
                    release = _parse_euro_date(loaded['sel'].xpath(f'string({_DATE_XP})').get() or '')
                    return [
                        build_search_result(
                            title=title,
                            scene_url=url,
                            query=ctx.title,
                            display_date=release,
                            search_date=ctx.search_date,
                            score=100,
                        )
                    ]

        # Video + performer keyword search.
        results: list[SearchResult] = []
        seen: set[str] = set()
        qplus = ctx.encoded.replace('%20', '+')
        search_base = base + ctx.site_info.search_path
        for kind in ('video', 'performer'):
            url = f'{search_base}{kind}&q={qplus}'
            loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'GET {url}')
            if not loaded:
                continue
            for li in loaded['sel'].xpath('//ul[@id="studio-videos-container"]/li'):
                title = (li.xpath('(.//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
                gallery_id = (li.xpath('.//div[contains(@class,"overlay") and contains(@class,"inline-preview")]/@data-id').get() or '').strip()
                if not title or not gallery_id:
                    continue
                scene_url = f'{base}/studios/video/{gallery_id}'
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date_raw = (li.xpath('(.//span[contains(@class,"releasedate")])[1]/text()').get() or '').strip()
                release = iso_date(date_raw) if date_raw else None
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        display_date=release,
                        search_date=ctx.search_date,
                    )
                )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _clean_title(scene.sel.xpath(f'string({_TITLE_XP})').get() or '') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        summary = (scene.sel.xpath('string((//p[contains(@class,"description")])[1])').get() or '').strip()
        if not summary:
            return None
        low = summary.lower()
        if any(low.startswith(p.lower()) for p in _SKIP_PREFIXES):
            return None
        return summary

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath(f'{_info_line_xp("Studio")}//a[1]/text()').get() or '').strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tagline = await self.fetch_tagline(scene)
        if tagline:
            return [tagline]
        return [_studio_for(scene.site.name)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath(f'string({_DATE_XP})').get() or ''
        return _parse_euro_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        text = scene.sel.xpath(f'string({_info_line_xp("Niches")})').get() or ''
        if ':' not in text:
            return None
        genres = [g.strip() for g in text.split(':')[-1].split(',') if g.strip()]
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        names: list[str] = []
        for a in scene.sel.xpath(f'{_info_line_xp("Performer")}/a'):
            n = (a.xpath('normalize-space(.)').get() or '').strip()
            if n and n not in names:
                names.append(n)
        actors: list[ActorResult] = []
        for name in names:
            q = quote(name, safe='').replace('%20', '+')
            url = f'{base}{scene.site.search_path}performer&q={q}'
            loaded = await self.fetch_and_load(url, None, f'GET {url} (actor)')
            style = (
                (loaded['sel'].xpath('(//div[contains(@class,"performer-container")]//div[contains(@class,"ratio-square")]/@style)[1]').get() or '')
                if loaded
                else ''
            )
            actors.append(ActorResult(name=name, photo_url=css_bg_image(style)))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//video[@id]/@poster').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
