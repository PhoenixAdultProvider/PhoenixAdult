from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.data_files import load_data
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, strip_tags
from phoenixadult.utils.helpers.ids import pack_cur_id
from phoenixadult.utils.helpers.scoring import date_distance_score
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url
from phoenixadult.utils.logging.logger import logger

_KINK_COOKIES = {'age_gate_accepted': '1', 'viewing-preferences': 'straight%2Cgay'}
_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_WS_RE = re.compile(r'\s+')
_DATE_RE = re.compile(r'^[A-Z][a-z]{2} \d{1,2}, \d{4}$')
_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
_WORD_RE = re.compile(r"[a-z0-9']+")
_CARD_WORD_RE = re.compile(r"[^a-z0-9'*]")
_PAGE_SIZE = 24
_MAX_PROBES = 12
_SAFE_IMAGES = '/safe-images/'

_CARD_XPATH = '//div[contains(concat(" ", normalize-space(@class), " "), " shoot-thumbnail ")]'
_TOTAL_XPATH = '//h1/following-sibling::span[contains(@class, "text-primary")]/text()'
_LEGEND_DATE_XPATH = '//div[contains(@class,"shoot-detail-legend")]//span[contains(@class,"text-muted")]'

_CHANNELS = load_data(__file__, 'kink_channels')
_TAGLINE_BY_CHANNEL: dict[str, str] = _CHANNELS['taglineByChannel']
_STUDIO_BY_TAGLINE: dict[str, str] = _CHANNELS['studioByTagline']
_CHANNEL_KEYS = sorted(_TAGLINE_BY_CHANNEL.keys(), key=len, reverse=True)


def _kink_tagline(channel: str, fallback: str) -> str:
    hay = channel.lower()
    for key in _CHANNEL_KEYS:
        if key in hay:
            return _TAGLINE_BY_CHANNEL[key]

    return fallback


def _video_ld(sel: Selector) -> dict[str, Any]:
    for block in sel.xpath('//script[@type="application/ld+json"]/text()').getall():
        try:
            data = json.loads(block)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get('@type') == 'VideoObject':
            return data

    return {}


def _legend_dates(sel: Selector) -> list[str]:
    texts = (span.xpath('string(.)').get() or '' for span in sel.xpath(_LEGEND_DATE_XPATH))
    return [text.strip() for text in texts if _DATE_RE.match(text.strip())]


def _card_date(card: Selector) -> str | None:
    for text in card.xpath('.//div[contains(@class,"shoot-thumbnail-footer")]//text()').getall():
        if _DATE_RE.match(text.strip()):
            return iso_date(text.strip())

    return None


def _title_fits(search_title: str, card_title: str) -> bool:
    wanted = _WORD_RE.findall(search_title.lower())
    if not wanted:
        return True
    card_words = [_CARD_WORD_RE.sub('', word) for word in card_title.lower().split()]
    hits = 0
    for word in wanted:
        for card_word in card_words:
            if card_word == word or (card_word and '*' in card_word and card_word[0] == word[0]):
                hits += 1
                break

    return hits * 2 >= len(wanted)


class KinkClient(Client):
    default_cookies: ClassVar[dict[str, str]] = _KINK_COOKIES

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        if search_data.scene_id:
            await self._search_shoot(results, search_data)
            return

        search_url = search_data.search_url()
        attempts = [search_url]
        if search_data.search_date and 'channelIds=' in search_url:
            attempts.append(search_data.search_url(''))

        for url in attempts:
            if await self._search_pages(results, search_data, url):
                break

    async def _search_shoot(self, results: list[SearchResult], search_data: SearchContext) -> None:
        scene_url = f'{search_data.site_info.base_url.rstrip("/")}/shoot/{search_data.scene_id}'
        direct_page_elements = await self.fetch_and_load(
            scene_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] directScene {scene_url}'
        )
        if not direct_page_elements:
            return

        details_page_elements = direct_page_elements['sel']
        video = _video_ld(details_page_elements)
        heading = (details_page_elements.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        if video.get('name'):
            title = str(video['name']).strip()
        elif details_page_elements.xpath('//div[contains(@class,"shoot-detail-legend")]') and heading:
            title = heading
        else:
            logger.info('Kink', f'Shoot {search_data.scene_id}: no scene data on {scene_url} (retired or redirected); not offering it')
            return

        legend_dates = _legend_dates(details_page_elements)
        if video.get('uploadDate'):
            release_date = iso_date(str(video['uploadDate'])[:10])
        else:
            release_date = iso_date(legend_dates[0]) if legend_dates else None

        results.append(
            build_search_result(
                site=search_data.site_info,
                title=title,
                scene_url=scene_url,
                query=search_data.title,
                display_date=release_date,
                search_date=search_data.search_date,
                score=100,
                cur_id=pack_cur_id([scene_url]),
            )
        )

    async def _page(self, search_data: SearchContext, search_url: str, page: int) -> tuple[list[Selector], int | None]:
        url = f'{search_url}&page={page}'
        page_elements = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search {url}')
        if not page_elements:
            return [], None

        sel = page_elements['sel']
        total = None
        for total_text in sel.xpath(_TOTAL_XPATH).getall():
            digits = total_text.strip().replace(',', '')
            if digits.isdigit():
                total = int(digits)
                break

        return list(sel.xpath(_CARD_XPATH)), total

    def _add_cards(self, results: list[SearchResult], search_data: SearchContext, cards: list[Selector], only_exact_date: bool) -> bool:
        exact_date = False
        for card in cards:
            href = first_attr(card, '(.//a[contains(@href,"/shoot/")])[1]/@href')
            if not href:
                continue
            shoot_id = href.rstrip('/').split('/')[-1]
            title = first_attr(card, '(.//a[contains(@href,"/shoot/")]/@title)[1]').strip() or shoot_id
            card_date = _card_date(card)

            score = None
            if search_data.search_date and card_date:
                if only_exact_date and card_date != search_data.search_date:
                    continue
                fits = _title_fits(search_data.title, title)
                score = date_distance_score(search_data.search_date, card_date) - (0 if fits else 10)
                exact_date = exact_date or (card_date == search_data.search_date and fits)

            scene_url = absolute_url(href, search_data.site_info.base_url)
            release_date = card_date or search_data.search_date
            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=card_date,
                    search_date=search_data.search_date,
                    score=score,
                    cur_id=pack_cur_id([x for x in (scene_url, release_date) if x]),
                )
            )

        return exact_date

    async def _search_pages(self, results: list[SearchResult], search_data: SearchContext, search_url: str) -> bool:
        cards, total = await self._page(search_data, search_url, 1)
        if not cards:
            return False
        if self._add_cards(results, search_data, cards, False):
            return True
        target = search_data.search_date
        if not target:
            return True

        oldest = _card_date(cards[-1])
        if not total or not oldest or target >= oldest:
            return False

        lo, hi = 2, (total + _PAGE_SIZE - 1) // _PAGE_SIZE
        for _ in range(_MAX_PROBES):
            if lo > hi:
                break
            mid = (lo + hi) // 2
            cards, _total = await self._page(search_data, search_url, mid)
            if not cards:
                hi = mid - 1
                continue
            newest, oldest = _card_date(cards[0]), _card_date(cards[-1])
            if newest and target > newest:
                hi = mid - 1
            elif oldest and target < oldest:
                lo = mid + 1
            else:
                found = self._add_cards(results, search_data, cards, True)
                if not found and target == newest and mid > 1:
                    found = self._add_cards(results, search_data, (await self._page(search_data, search_url, mid - 1))[0], True)
                if not found and target == oldest:
                    found = self._add_cards(results, search_data, (await self._page(search_data, search_url, mid + 1))[0], True)
                return found

        return False

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        href = first_attr(details_page_elements, '(//div[contains(@class,"shoot-detail-legend")]//a[contains(@href,"/channel/")])[1]/@href')
        channel = href.split('/channel/')[-1].replace('-', '').lower() if href else ''
        return _kink_tagline(channel, scene.site.name)

    async def _collect_people(self, scene: LoadedScene, xp: str) -> list[ActorResult]:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            xpaths = (
                '//div[contains(@class,"biography-container")]//img/@src',
                '//div[contains(@class,"kink-slider-images")]//img/@src',
                '//div[contains(@class,"kink-slider-images")]//img/@data-src',
            )
            for xpath in xpaths:
                for src in sel.xpath(xpath).getall():
                    if _SAFE_IMAGES not in src:
                        return src
            return ''

        refs: list[tuple[str, str]] = []
        for row in details_page_elements.xpath(xp):
            name = (row.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            href = first_attr(row, '@href')
            if name:
                refs.append((name, absolute_url(href, base) if href else ''))

        return await self.resolve_actor_photos(refs, extract_photo, capture=None)

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        name = _video_ld(details_page_elements).get('name')
        metadata.title = str(name).strip() if name else self.first_of(details_page_elements, '(//h1)[1]')

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        description = _video_ld(details_page_elements).get('description')
        if description:
            metadata.summary = _MD_LINK_RE.sub(r'\1', str(description)).replace('**', '').replace('\n', ' ').strip()
            return

        span_html = details_page_elements.xpath('(//div[contains(@class,"description")]//span[contains(@class,"fw-200")])[1]').get() or ''
        if not span_html:
            return

        text = strip_tags(_BR_RE.sub(' ', span_html))

        metadata.summary = _WS_RE.sub(' ', text).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _STUDIO_BY_TAGLINE.get(self._tagline(scene), 'Kink')

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        upload_date = _video_ld(details_page_elements).get('uploadDate')
        if upload_date:
            metadata.release_date = iso_date(str(upload_date)[:10])
            return

        legend_dates = _legend_dates(details_page_elements)
        if legend_dates:
            metadata.release_date = iso_date(legend_dates[0])
            return

        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        names: list[str | None] = []
        for genre_link in details_page_elements.xpath(
            '//p[normalize-space()="Categories"]/ancestor::div[contains(@class, "container")][1]//a[contains(@href,"/tag/")]'
        ):
            genre_name = (genre_link.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            if '*' in genre_name:
                slug = re.sub(r'-bdsm$', '', first_attr(genre_link, '@href').rstrip('/').split('/tag/')[-1])
                genre_name = slug.replace('-', ' ').title()
            names.append(genre_name)

        genres = self.dedup_strings(names)
        cast = len(details_page_elements.xpath('//span[contains(@class,"text-primary")]//a[contains(@href,"/model/")]'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = await self._collect_people(scene, '//span[contains(@class,"text-primary")]//a[contains(@href,"/model/")]')

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.directors = await self._collect_people(scene, '//span[contains(@class,"director-name")]//a') or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector()
        xpaths = (
            '//video/@poster',
            '//div[contains(@class,"player")]/div/@poster',
            '//div[@id="galleryWrapper"]//img/@data-image-file',
            '//img[contains(@class, "gallery-img")]/@data-image-file',
        )
        for xpath in xpaths:
            for image_url in details_page_elements.xpath(xpath).getall():
                if _SAFE_IMAGES not in image_url:
                    images.push(image_url)

        metadata.art = images.items
