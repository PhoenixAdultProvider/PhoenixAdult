from __future__ import annotations

from typing import Any
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

STUDIO = 'Spizoo'
_PROFILES: dict[str, dict[str, Any]] = load_data(__file__, 'spizoo_profiles')

_PROFILE_KEYS = {
    'Raw Attack': 'rawattack',
    'Mr. Lucky POV': 'mrluckypov',
    'Mr. Lucky RAW': 'mrluckyraw',
    'Mr. Lucky LIFE': 'mrluckylife',
    'Cream Her': 'creamher',
    'DR. Daddy POV': 'drdaddypov',
    'Goth Girlfriends': 'gothgirlfriends',
}


def _strip_4k(title: str) -> str:
    return title[:-3].strip() if title.lower().endswith(' 4k') else title


class SpizooClient(Client):
    def _profile(self, site_name: str) -> dict[str, Any]:
        return _PROFILES[_PROFILE_KEYS.get(site_name, 'default')]

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        p = self._profile(search_data.site_info.name)
        quoted = quote(f'"{search_data.title}"', safe='')
        search_url = search_data.search_url(quoted)
        search_results = await self.fetch_and_load(
            search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if not search_results:
            return

        seen: set[str] = set()
        for search_result in search_results['sel'].xpath(f'//{p["search_results"]}'):
            raw_title = (search_result.xpath(f'(.//{p["search_title"]})[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(search_result, '(.//a)[1]/@href')
            if not raw_title or not href:
                continue

            scene_url = absolute_url(href, search_data.site_info.base_url)
            if scene_url in seen:
                continue

            seen.add(scene_url)
            date = None
            if p['search_date']:
                date_el = search_result.xpath(f'(.//{p["search_date"]})[last()]')
                raw_date = ''.join(date_el.xpath('.//text()[not(ancestor::h4)]').getall()).strip()
                if raw_date:
                    date = iso_date(raw_date)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=_strip_4k(raw_title),
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url, date or '']),
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        inline = first_attr(details_page_elements, '(//i[@id="site"])[1]/@value')
        if inline:
            return inline

        return scene.site.name if 'Spizoo' not in scene.site.name else STUDIO

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)
        raw = (details_page_elements.xpath(f'(//{p["detail_title"]})[1]').xpath('string(.)').get() or '').strip()
        if not raw:
            raw = first_attr(details_page_elements, '(//video)[1]/@data-video')

        metadata.title = _strip_4k(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        summary_xpaths = (
            '//p[contains(@class,"description") and not(contains(@class,"description-scene"))]',
            '//p[contains(@class,"description-scene")]',
            '(//h2)[1]/following-sibling::p[1]',
        )
        for xpath in summary_xpaths:
            text = (details_page_elements.xpath(f'({xpath})[1]').xpath('string(.)').get() or '').strip()
            if text:
                metadata.summary = text
                return

        metadata.summary = ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//p[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
        if date:
            head = date[:10]
            parsed = iso_date(head, '%Y-%m-%d') or iso_date(head)
            if parsed:
                metadata.release_date = parsed
                return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        genre_xpaths = ('//div[contains(@class,"categories-holder")]//a', '//div[h3[contains(.,"Categories")]]//a')
        for xpath in genre_xpaths:
            for genre_link in details_page_elements.xpath(xpath):
                for part in (genre_link.xpath('string(.)').get() or '').split(','):
                    genre_name = part.strip().lower()
                    if genre_name and genre_name not in genres:
                        genres.append(genre_name)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        p = self._profile(scene.site.name)
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            for xp, attr in p['model_photo']:
                raw = (sel.xpath(f'(//{xp})[1]/@{attr}').get() or '').strip()
                if raw:
                    return absolute_url(raw, base)
            return ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath(f'//{p["actor_container"]}'):
            actor_name = (actor_link.xpath('string(.)').get() or '').replace('.', '').strip()
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        metadata.actors = await self.resolve_actor_photos(refs, extract_photo, label='actor')

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        xpaths = (
            '//section[@id="photos-tour"]//img[contains(@class,"update_thumb") and contains(@class,"thumbs")]/@src',
            '//section[@id="scene"]//div[@id="noMore"]//img/@alt',
            '//section[@id="scene"]//video[@id="the-video"]/@poster',
            '//div[contains(@class,"row") and contains(@class,"photos-holder")]//img/@src',
            '//div[contains(@class,"content-block-video")]//img/@alt',
            '//div[@id="block-content"]//img[@class]/@src',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                images.push(image_url)

        metadata.art = images.items
