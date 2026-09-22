from __future__ import annotations

import re

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.utils.helpers.dates import iso_date
from phoenixadult.utils.helpers.html_helpers import first_attr, web_search_urls
from phoenixadult.utils.helpers.search_results import build_search_result
from phoenixadult.utils.helpers.urls import absolute_url

_URL_CONTAINS = '/session/'
_QUOTED_URL_RE = re.compile(r"""['"]([^'"]+\.(?:jpg|jpeg|png|webp))['"]""", re.IGNORECASE)
_NAME_SPLIT_RE = re.compile(r',|&|/| And ', re.IGNORECASE)
_NURSE_RE = re.compile(r'\bNurses?\b')


class DerangedDollarsClient(Client):
    title_xpath = '(//h3[contains(@class,"mas_title")])[1]'
    summary_xpath = '(//p[contains(@class,"mas_longdescription")])[1]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        candidates = await web_search_urls(search_data.title, search_data.site_info, include=[_URL_CONTAINS])

        for url, details_page_elements in await self.fetch_candidate_pages(
            candidates, FetchCtx(capture=search_data.capture), lambda url: f'[{search_data.site_info.name}] candidate {url}'
        ):
            if not details_page_elements:
                continue

            title = (details_page_elements['sel'].xpath('(//h3[contains(@class,"mas_title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue

            lch = (details_page_elements['sel'].xpath('(//div[contains(@class,"lch")]//span)[1]').xpath('string(.)').get() or '').strip()
            date_raw = ','.join(lch.split(',')[-2:]).strip()
            date_iso = iso_date(date_raw) if date_raw else None

            results.append(
                build_search_result(
                    site=search_data.site_info, title=title, scene_url=url, query=search_data.title, display_date=date_iso, search_date=search_data.search_date
                )
            )

    # ── Update Field Hook Helpers ─────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str | None:
        details_page_elements = scene.require_sel()

        raw = details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or ''
        segments = [s.strip() for s in raw.split('|')]
        if len(segments) < 2:
            return None

        return re.sub(r'\.com$', '', segments[1], flags=re.IGNORECASE).strip() or None

    async def _load_model_directory(self, scene: LoadedScene) -> list[tuple[str, str, str]]:
        base = scene.site.base_url.rstrip('/')
        entries: list[tuple[str, str, str]] = []
        for url in (f'{base}/?models', f'{base}/?models/2'):
            model_page_elements = await self.fetch_and_load(url, None, f'models page {url}')
            if not model_page_elements:
                continue

            for director_link in model_page_elements['sel'].xpath('//div[contains(@class,"item")]'):
                raw = first_attr(director_link)
                if not raw:
                    continue

                director_name = raw.split(':', 1)[1].strip() if ':' in raw else raw
                photo_rel = first_attr(director_link, '(.//img)[1]/@src')
                photo = absolute_url(photo_rel, scene.site.base_url) if photo_rel else ''
                entries.append((director_name, director_name, photo))

        return entries

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or ''

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline(scene)

        metadata.collections = [tag] if tag else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.genres = [
            genre_name
            for genre_name in (first_attr(genre_link, 'normalize-space(.)') for genre_link in details_page_elements.xpath('//p[contains(@class,"tags")]//a'))
            if genre_name
        ]

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        lch = (details_page_elements.xpath('(//div[contains(@class,"lch")]//span)[1]').xpath('string(.)').get() or '').strip()
        blob = ','.join(lch.split(',')[:-2]).strip()
        if not blob:
            return

        if ':' in blob:
            blob = blob.split(':', 1)[1].strip()

        raw_names = [n for n in (_NURSE_RE.sub('', re.sub(r'\W+', ' ', s)).strip() for s in _NAME_SPLIT_RE.split(blob)) if n]
        if not raw_names:
            return

        model_dir = await self._load_model_directory(scene)
        out: list[ActorResult] = []
        for raw_name in raw_names:
            actor_name, photo = raw_name, ''
            for match_text, display_name, photo_url in model_dir:
                if raw_name.lower() in match_text.lower():
                    actor_name, photo = display_name, photo_url
                    break

            out.append(ActorResult(name=actor_name, photo_url=photo))

        metadata.actors = out

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        images = self.image_collector(lambda image: absolute_url(image, base))
        for src in details_page_elements.xpath('//div[contains(@class,"stills") and contains(@class,"clearfix")]//img/@src').getall():
            images.push(src)

        for script in details_page_elements.xpath('//div[contains(@class,"mainpic")]//script'):
            text = script.xpath('string(.)').get() or ''
            for m in _QUOTED_URL_RE.findall(text):
                images.push(m)

        metadata.art = images.items
