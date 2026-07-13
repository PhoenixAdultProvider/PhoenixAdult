from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Karups'
_ORDINAL_RE = re.compile(r'(\d+)(st|nd|rd|th)\b', re.IGNORECASE)


def _cls(name: str) -> str:
    # Whole-class-token match (avoids "title" matching "sup-title", etc.).
    return f'contains(concat(" ",normalize-space(@class)," ")," {name} ")'


def _de_ordinal(raw: str) -> str:
    return _ORDINAL_RE.sub(r'\1', raw).strip()


class KarupsClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'warningHidden=hide'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = re.sub(r'\s+', '-', ctx.title.strip())

        search_loaded = await self.fetch_and_load(
            f'{base}{ctx.site_info.search_path}{slug}/', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model search {slug}'
        )
        if not search_loaded:
            return
        model_href = first_attr(search_loaded['sel'], '(//div[contains(@class,"item-inside")]//a)[1]/@href')
        if not model_href:
            return

        model_loaded = await self.fetch_and_load(
            absolute_url(model_href, ctx.site_info.base_url), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model page'
        )
        if not model_loaded:
            return

        for card in model_loaded['sel'].xpath('//div[contains(@class,"listing-videos")]//div[contains(@class,"item")]'):
            title = (card.xpath(f'(.//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(card, '(.//a)[1]/@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            date = iso_date(_de_ordinal((card.xpath(f'(.//span[{_cls("date")}])[1]').xpath('string(.)').get() or '').strip()))
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])
                )
            )

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        sel = scene.require_sel()
        return (sel.xpath('(//h1//span[contains(@class,"sup-title")]//span)[1]').xpath('string(.)').get() or '').strip() or scene.site.name

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = (sel.xpath(f'(//h1//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = (sel.xpath('(//div[contains(@class,"content-information-description")]//p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_of(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_of(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        tagline = self._tagline_of(scene)
        raw = (
            (sel.xpath(f'(//span[{_cls("date")}]//span[{_cls("content")}])[1]').xpath('string(.)').get() or '')
            .replace(tagline, '')
            .replace('Video added on', '')
            .strip()
        )
        metadata.release_date = (iso_date(_de_ordinal(raw)) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline_of(scene)
        if tagline == 'KarupsHA':
            metadata.genres = ['Amateur']
        elif tagline == 'KarupsOW':
            metadata.genres = ['MILF']

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for el in sel.xpath('//span[contains(@class,"models")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                raw = first_attr(page['sel'], '(//div[contains(@class,"model-thumb")]//img)[1]/@src') if page else ''
                if raw:
                    photo = absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        xpaths = (
            '(//div[contains(@class,"video-player")]//video)[1]/@poster',
            '//img[contains(@class,"poster")]/@src',
            '//div[contains(@class,"video-thumbs")]//img/@src',
        )
        for xpath in xpaths:
            for raw in sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.art = images
