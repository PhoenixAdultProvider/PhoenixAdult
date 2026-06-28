from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, slugify
from app.utils.logging.logger import logger

STUDIO = 'Adult Empire Cash'
_DATE_FMT = '%b %d, %Y'

Variant = Literal['standard', 'imgFullFluid', 'sceneTitleP']

_VARIANTS: dict[str, str] = load_site_json(__file__, 'adultempirecash_variants')
_STUDIO_OVERRIDES: dict[str, str] = load_site_json(__file__, 'adultempirecash_studios')

# Per-subsite genre-source override (XPath). Default reads div.tags; Elegant Angel
# carries categories under an "Attributes" block instead.
_GENRE_XPATH_OVERRIDES: dict[str, str] = {
    'Elegant Angel': '//div[strong[contains(.,"Attributes")]]/a',
}
_DEFAULT_GENRE_XPATH = '//div[contains(@class,"tags")]//a'


def _variant_for(name: str) -> Variant:
    return cast(Variant, _VARIANTS.get(name, 'standard'))


def _studio_for(name: str) -> str:
    return _STUDIO_OVERRIDES.get(name, STUDIO)


def _upgrade_image(src: str) -> str:
    return src.replace('/320/', '/3840/').replace('/10/', '/3840/').replace('_320c.jpg', '_10.jpg')


def _row_title_href(row: Any, variant: Variant) -> tuple[str, str]:
    if variant == 'imgFullFluid':
        title = (row.xpath('.//img[contains(@class,"img-full-fluid")]/@title').get() or '').strip()
        href = (row.xpath('.//article[contains(@class,"scene-update")]/a/@href').get() or '').strip()
    elif variant == 'sceneTitleP':
        raw = row.xpath('(.//a[@class="scene-title"]/p)[1]/text()').get() or ''
        title = raw.split(' | ')[0].strip()
        href = (row.xpath('.//a[@class="scene-title"]/@href').get() or '').strip()
    else:
        title = (row.xpath('(.//a[@class="scene-title"]/h6)[1]/text()').get() or '').strip()
        href = (row.xpath('.//a[@class="scene-title"]/@href').get() or '').strip()
    return title, href


__testing__ = {
    'upgrade_image': _upgrade_image,
    'row_title_href': _row_title_href,
    'variant_for': _variant_for,
    'studio_for': _studio_for,
    'GENRE_XPATH_OVERRIDES': _GENRE_XPATH_OVERRIDES,
}


class AdultEmpireCashClient(Client):
    def __init__(self) -> None:
        super().__init__()
        # AEC pages are age-gated per host; the gate binds ageConfirmed to a
        # server-issued etoken session, so a static cookie isn't enough — we run
        # the confirm handshake once per host and let the jar carry the session.
        self._confirmed: set[str] = set()
        self._age_lock = asyncio.Lock()

    async def _ensure_age_confirmed(self, base: str) -> None:
        if base in self._confirmed:
            return
        async with self._age_lock:
            if base in self._confirmed:
                return
            try:
                await self.http.get(f'{base}/')  # prime: receive the guest etoken cookie
                await self.http.get(f'{base}/Account/AgeConfirmation?ageConfirmationClicked=true')
                logger.debug('AdultEmpireCash', f'age-confirm handshake done for {base}')
            except Exception as err:  # noqa: BLE001 - best-effort; proceed regardless
                logger.debug('AdultEmpireCash', f'age-confirm handshake failed for {base}: {err}')
            self._confirmed.add(base)

    # ── Search (full override: direct sceneID lookup + per-variant rows) ─────────

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        await self._ensure_age_confirmed(base)
        variant = _variant_for(ctx.site_info.name)
        results: list[SearchResult] = []

        # Direct numeric lookup at /<id>/<slug>.html
        if ctx.scene_id:
            direct_url = f'{base}/{ctx.scene_id}/{slugify(ctx.title)}.html'
            loaded = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'GET {direct_url}')
            if loaded:
                title = (loaded['sel'].xpath('(//h1[@class="description"])[1]/text()').get() or '').strip()
                if title:
                    results.append(build_search_result(title=title, scene_url=direct_url, query=ctx.title, score=100))

        # Standard keyword search.
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'GET {url}')
        if loaded:
            rows = loaded['sel'].xpath('//div[contains(@class,"item-grid")]/div[contains(concat(" ",normalize-space(@class)," ")," grid-item ")]')
            for row in rows:
                title, href = _row_title_href(row, variant)
                if not title or not href:
                    continue
                abs_url = absolute_url(href, ctx.site_info.base_url)
                date_raw = (row.xpath('(.//span[@class="date"])[1]/text()').get() or '').strip()
                date_iso = iso_date(date_raw, _DATE_FMT) if date_raw else None
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=abs_url,
                        query=ctx.title,
                        display_date=date_iso,
                        search_date=ctx.search_date,
                    )
                )
        return results

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        await self._ensure_age_confirmed(site.base_url.rstrip('/'))
        return await super().load_scene_context(payload, site, ctx)

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1[@class="description"])[1]/text()').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@class="synopsis"]/p)[1]/text()').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[@class="studio"]//span)[2]/text()').get() or '').strip() or None

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[@class="release-date"])[1]/text()').get() or '').strip()
        return iso_date(raw) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        xp = _GENRE_XPATH_OVERRIDES.get(scene.site.name, _DEFAULT_GENRE_XPATH)
        genres: list[str] = []
        for a in scene.sel.xpath(xp):
            g = (a.xpath('normalize-space(.)').get() or '').strip()
            if g:
                genres.extend(p.strip() for p in g.split('/') if p.strip())
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for img in scene.sel.xpath('//div[@class="video-performer"]//img'):
            name = (img.xpath('@title').get() or '').strip()
            photo = (img.xpath('@data-bgsrc').get() or '').strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                actors.append(ActorResult(name=name, photo_url=photo))
        for a in scene.sel.xpath('(//div[contains(@class,"video-performer-container")])[2]/a'):
            name = (a.xpath('normalize-space(.)').get() or '').strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                actors.append(ActorResult(name=name))
        return actors or None

    async def fetch_directors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        # TS reads the whole "Director: Name" text and slices after the colon.
        raw = scene.sel.xpath('string((//div[@class="director"])[1])').get() or ''
        name = raw.split(':')[-1].strip()
        return [ActorResult(name=name)] if name else None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        tagline = await self.fetch_tagline(scene)
        if tagline:
            return [tagline]
        return [_studio_for(scene.site.name)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(_upgrade_image)
        for raw in scene.sel.xpath('//div[@id="dv_frames"]//img/@src').getall():
            coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
