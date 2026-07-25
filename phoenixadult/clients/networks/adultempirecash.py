from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_data, slugify
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.logging.logger import logger

STUDIO = 'Adult Empire Cash'
_DATE_FMT = '%b %d, %Y'

Variant = Literal['standard', 'imgFullFluid', 'sceneTitleP']

_VARIANTS: dict[str, str] = load_data(__file__, 'adultempirecash_variants')
_STUDIO_OVERRIDES: dict[str, str] = {'Horny Household': 'Horny Household'}

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
        title = first_attr(row, './/img[contains(@class,"img-full-fluid")]/@title')
        href = first_attr(row, './/article[contains(@class,"scene-update")]/a/@href')
    elif variant == 'sceneTitleP':
        raw = row.xpath('(.//a[@class="scene-title"]/p)[1]/text()').get() or ''
        title = raw.split(' | ')[0].strip()
        href = first_attr(row, './/a[@class="scene-title"]/@href')
    else:
        title = first_attr(row, '(.//a[@class="scene-title"]/h6)[1]/text()')
        href = first_attr(row, './/a[@class="scene-title"]/@href')

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
        self._confirmed: set[str] = set()
        self._age_lock = asyncio.Lock()

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')
        await self._ensure_age_confirmed(base)
        variant = _variant_for(search_data.site_info.name)

        if search_data.scene_id:
            direct_url = f'{base}/{search_data.scene_id}/{slugify(search_data.title)}.html'
            search_results = await self.fetch_and_load(direct_url, FetchCtx(capture=search_data.capture), f'GET {direct_url}')
            if search_results:
                title = first_attr(search_results['sel'], '(//h1[@class="description"])[1]/text()')
                if title:
                    results.append(build_search_result(title=title, scene_url=direct_url, query=search_data.title, score=100))

        url = base + search_data.site_info.search_path.replace('{query}', search_data.encoded)
        search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'GET {url}')
        if search_results:
            rows = search_results['sel'].xpath('//div[contains(@class,"item-grid")]/div[contains(concat(" ",normalize-space(@class)," ")," grid-item ")]')
            for row in rows:
                title, href = _row_title_href(row, variant)
                if not title or not href:
                    continue

                abs_url = absolute_url(href, search_data.site_info.base_url)
                date_raw = first_attr(row, '(.//span[@class="date"])[1]/text()')
                date_iso = iso_date(date_raw, _DATE_FMT) if date_raw else None

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=abs_url,
                        query=search_data.title,
                        display_date=date_iso,
                        search_date=search_data.search_date,
                    )
                )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        await self._ensure_age_confirmed(site.base_url.rstrip('/'))
        return await super().load_scene_context(payload, site, ctx)

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    async def _ensure_age_confirmed(self, base: str) -> None:
        """The age gate binds ageConfirmed to a server-issued etoken session (a static cookie
        isn't enough) — run the confirm handshake once per host and let the jar carry it."""
        if base in self._confirmed:
            return

        async with self._age_lock:
            if base in self._confirmed:
                return

            try:
                await self.http.get(f'{base}/')
                await self.http.get(f'{base}/Account/AgeConfirmation?ageConfirmationClicked=true')
                logger.debug('AdultEmpireCash', f'age-confirm handshake done for {base}')
            except Exception as err:  # noqa: BLE001 - best-effort; proceed regardless
                logger.debug('AdultEmpireCash', f'age-confirm handshake failed for {base}: {err}')

            self._confirmed.add(base)

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return first_attr(details_page_elements, '(//div[@class="studio"]//span)[2]/text()')

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = first_attr(details_page_elements, '(//h1[@class="description"])[1]/text()') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.summary = first_attr(details_page_elements, '(//div[@class="synopsis"]/p)[1]/text()') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)

        metadata.collections = [tagline] if tagline else [_studio_for(scene.site.name)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = first_attr(details_page_elements, '(//div[@class="release-date"])[1]/text()')

        metadata.release_date = iso_date(date) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        xp = _GENRE_XPATH_OVERRIDES.get(scene.site.name, _DEFAULT_GENRE_XPATH)
        genres: list[str] = []
        for genre_link in details_page_elements.xpath(xp):
            genre_name = first_attr(genre_link, 'normalize-space(.)')
            if genre_name:
                genres.extend(p.strip() for p in genre_name.split('/') if p.strip())

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for img in details_page_elements.xpath('//div[@class="video-performer"]//img'):
            actor_name = first_attr(img, '@title')
            photo = first_attr(img, '@data-bgsrc')
            if actor_name and actor_name.lower() not in seen:
                seen.add(actor_name.lower())
                actors.append(ActorResult(name=actor_name, photo_url=photo))

        for actor_link in details_page_elements.xpath('(//div[contains(@class,"video-performer-container")])[2]/a'):
            actor_name = first_attr(actor_link, 'normalize-space(.)')
            if actor_name and actor_name.lower() not in seen:
                seen.add(actor_name.lower())
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('string((//div[@class="director"])[1])').get() or ''
        director_name = raw.split(':')[-1].strip()

        metadata.directors = [ActorResult(name=director_name)] if director_name else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(_upgrade_image)
        for image_url in details_page_elements.xpath('//div[@id="dv_frames"]//img/@src').getall():
            images['push'](image_url)

        metadata.art = images['list']
