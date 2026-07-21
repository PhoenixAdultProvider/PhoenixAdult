from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, css_bg_image, iso_date, load_data
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Adult Prime'

_STUDIO_OVERRIDES: dict[str, str] = {'Club Sweethearts': 'Club Sweethearts'}
_SKIP_PREFIXES: list[str] = load_data(__file__, 'adultprime_skip_prefixes')

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

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        base = search_data.site_info.base_url.rstrip('/')

        if search_data.scene_id:
            url = f'{base}/studios/video/{search_data.scene_id}'
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'GET {url}')
            if search_results:
                title = _clean_title(search_results['sel'].xpath(f'string({_TITLE_XP})').get() or '')
                if title:
                    release = _parse_euro_date(search_results['sel'].xpath(f'string({_DATE_XP})').get() or '')

                    results.append(
                        build_search_result(
                            title=title,
                            scene_url=url,
                            query=search_data.title,
                            display_date=release,
                            search_date=search_data.search_date,
                            score=100,
                        )
                    )
                    return

        seen: set[str] = set()
        qplus = search_data.encoded.replace('%20', '+')
        search_base = base + search_data.site_info.search_path
        for kind in ('video', 'performer'):
            url = f'{search_base}{kind}&q={qplus}'
            search_results = await self.fetch_and_load(url, FetchCtx(capture=search_data.capture), f'GET {url}')
            if not search_results:
                continue

            for search_result in search_results['sel'].xpath('//ul[@id="studio-videos-container"]/li'):
                title = (search_result.xpath('(.//span[contains(@class,"title")])[1]').xpath('string(.)').get() or '').strip()
                gallery_id = first_attr(search_result, './/div[contains(@class,"overlay") and contains(@class,"inline-preview")]/@data-id')
                if not title or not gallery_id:
                    continue

                scene_url = f'{base}/studios/video/{gallery_id}'
                if scene_url in seen:
                    continue

                seen.add(scene_url)
                date_raw = first_attr(search_result, '(.//span[contains(@class,"releasedate")])[1]/text()')
                release = iso_date(date_raw) if date_raw else None

                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=search_data.title,
                        display_date=release,
                        search_date=search_data.search_date,
                    )
                )

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        details_page_elements = scene.require_sel()

        return (details_page_elements.xpath(f'{_info_line_xp("Studio")}//a[1]/text()').get() or '').strip()

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        metadata.title = _clean_title(details_page_elements.xpath(f'string({_TITLE_XP})').get() or '') or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        summary = first_attr(details_page_elements, 'string((//p[contains(@class,"description")])[1])')
        if not summary:
            return

        low = summary.lower()
        if any(low.startswith(p.lower()) for p in _SKIP_PREFIXES):
            return

        metadata.summary = summary

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene) or None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)

        metadata.collections = [tagline] if tagline else [_studio_for(scene.site.name)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = details_page_elements.xpath(f'string({_DATE_XP})').get() or ''

        metadata.release_date = _parse_euro_date(date) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        text = details_page_elements.xpath(f'string({_info_line_xp("Niches")})').get() or ''
        if ':' not in text:
            return

        genres = [genre_name.strip() for genre_name in text.split(':')[-1].split(',') if genre_name.strip()]

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        names = self.dedup_strings(
            [first_attr(actor_link, 'normalize-space(.)') for actor_link in details_page_elements.xpath(f'{_info_line_xp("Performer")}/a')]
        )
        actors: list[ActorResult] = []
        for actor_name in names:
            q = quote(actor_name, safe='').replace('%20', '+')
            url = f'{base}{scene.site.search_path}performer&q={q}'
            model_page_elements = await self.fetch_and_load(url, None, f'GET {url} (actor)')
            style = (
                (
                    model_page_elements['sel'].xpath('(//div[contains(@class,"performer-container")]//div[contains(@class,"ratio-square")]/@style)[1]').get()
                    or ''
                )
                if model_page_elements
                else ''
            )
            actors.append(ActorResult(name=actor_name, photo_url=css_bg_image(style)))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        images = self.image_collector(lambda image: absolute_url(image, scene.site.base_url))
        for image_url in details_page_elements.xpath('//video[@id]/@poster').getall():
            images['push'](image_url)

        metadata.art = images['list']
