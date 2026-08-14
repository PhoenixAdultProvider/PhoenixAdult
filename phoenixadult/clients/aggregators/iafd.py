from __future__ import annotations

import re
from dataclasses import dataclass, field

from parsel import Selector

from phoenixadult.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, title_distance_score
from phoenixadult.utils.helpers.html_helpers import first_attr, first_text

BASE_URL = 'https://www.iafd.com'

_LISTING_ROWS = '//table[@id="studio" or @id="distable"]//tr'
_RELEASE_DATE = '//p[contains(.,"Release Date")]/following-sibling::p[contains(@class,"biodata")][1]'
_CAST_LINKS = '//div[contains(@class,"castbox")]//a'
_SYNOPSIS = '//div[@id="synopsis"]//div[contains(@class,"padded-panel")]'
_YEAR_RE = re.compile(r'^(19|20)\d{2}$')
_YEAR_SUFFIX_RE = re.compile(r'\s*\((19|20)\d{2}\)\s*$')
_MAX_RESULTS = 20


@dataclass
class IafdEntry:
    title: str
    year: str
    url: str


@dataclass
class IafdScene:
    title: str
    release_date: str | None = None
    summary: str = ''
    actors: list[ActorResult] = field(default_factory=list)
    directors: list[ActorResult] = field(default_factory=list)


def scene_url(href: str) -> str:
    return href if href.startswith('http') else f'{BASE_URL}{href}'


def listing_entries(sel: Selector) -> list[IafdEntry]:
    entries: list[IafdEntry] = []
    for row in sel.xpath(_LISTING_ROWS):
        raw_title = (row.xpath('(.//a)[1]/text()').get() or '').split('(')[0].strip()
        href = first_attr(row, '(.//a/@href)[1]')
        if not raw_title or not href:
            continue

        cells = [cell.strip() for cell in row.xpath('.//td//text()').getall() if cell.strip()]
        year = next((cell for cell in reversed(cells) if _YEAR_RE.match(cell)), '')
        entries.append(IafdEntry(title=raw_title, year=year, url=scene_url(href)))
    return entries


def _people(sel: Selector, xpath: str) -> list[ActorResult]:
    people: list[ActorResult] = []
    for link in sel.xpath(xpath):
        name = first_attr(link, 'normalize-space(.)')
        if not name:
            continue

        people.append(ActorResult(name=name, photo_url=first_attr(link, '(.//img/@src)[1]')))
    return people


def parse_scene(sel: Selector) -> IafdScene:
    raw_date = first_text(sel, _RELEASE_DATE)
    summary = first_attr(sel, f'normalize-space({_SYNOPSIS})')
    return IafdScene(
        title=_YEAR_SUFFIX_RE.sub('', first_attr(sel, 'normalize-space(//h1)')).strip(),
        release_date=(iso_date(raw_date, '%b %d, %Y') or iso_date(raw_date)) if raw_date else None,
        summary=summary,
        actors=_people(sel, _CAST_LINKS),
        directors=_people(sel, '//p[contains(.,"Director")]/following-sibling::p[contains(@class,"biodata")][1]//a'),
    )


def _iafd_ctx(fetch_ctx: FetchCtx) -> FetchCtx:
    return FetchCtx(capture=fetch_ctx.capture, use_bypass=True, headers=fetch_ctx.headers)


async def fetch_listing(client: Client, listing_url: str, fetch_ctx: FetchCtx, label: str) -> list[IafdEntry]:
    listing_page_elements = await client.fetch_and_load(listing_url, _iafd_ctx(fetch_ctx), f'{label} IAFD listing')
    return listing_entries(listing_page_elements['sel']) if listing_page_elements else []


async def fetch_scene(client: Client, url: str, fetch_ctx: FetchCtx, label: str) -> IafdScene | None:
    scene_page_elements = await client.fetch_and_load(url, _iafd_ctx(fetch_ctx), f'{label} IAFD scene')
    return parse_scene(scene_page_elements['sel']) if scene_page_elements else None


async def supplement(client: Client, listing_url: str, title: str, fetch_ctx: FetchCtx, label: str) -> tuple[str | None, list[ActorResult]]:
    want = title.strip().lower()
    entry = next((e for e in await fetch_listing(client, listing_url, fetch_ctx, label) if e.title.lower() == want), None)
    if entry is None:
        return None, []

    scene = await fetch_scene(client, entry.url, fetch_ctx, label)
    return (scene.release_date, scene.actors) if scene else (None, [])


class IAFDClient(Client):
    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        fetch_ctx = FetchCtx(capture=search_data.capture, use_bypass=search_data.site_info.use_bypass)
        label = f'[{search_data.site_info.name}]'

        if search_data.scene_id:
            url = scene_url(f'/title.rme/id={search_data.scene_id}')
            scene = await fetch_scene(self, url, fetch_ctx, label)
            if scene and scene.title:
                results.append(
                    build_search_result(
                        site=search_data.site_info,
                        title=scene.title,
                        scene_url=url,
                        query=search_data.title,
                        search_date=search_data.search_date,
                        display_date=scene.release_date,
                        cur_id=pack_cur_id([url]),
                    )
                )
            return

        wanted_year = (search_data.search_date or '')[:4]
        entries = await fetch_listing(self, search_data.search_url(''), fetch_ctx, label)
        scored = sorted(entries, key=lambda entry: title_distance_score(search_data.title, entry.title), reverse=True)
        for entry in scored[:_MAX_RESULTS]:
            if wanted_year and entry.year and entry.year != wanted_year:
                continue

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=entry.title,
                    scene_url=entry.url,
                    query=search_data.title,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([entry.url]),
                )
            )

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        fetch_ctx = FetchCtx(capture=ctx.capture if ctx else None, use_bypass=site.use_bypass)
        scene_page_elements = await self.fetch_and_load(payload, fetch_ctx, f'[{site.name}] detail {payload}')
        if not scene_page_elements:
            return None

        return LoadedScene(
            url=payload,
            site=site,
            capture=fetch_ctx.capture,
            sel=scene_page_elements['sel'],
            html=scene_page_elements['html'],
            extra=parse_scene(scene_page_elements['sel']),
        )

    def _extra(self, scene: LoadedScene) -> IafdScene:
        assert isinstance(scene.extra, IafdScene)
        return scene.extra

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = self._extra(scene).title

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.summary = self._extra(scene).summary

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.release_date = self._extra(scene).release_date

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = self._extra(scene).actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.directors = self._extra(scene).directors

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.art = []
