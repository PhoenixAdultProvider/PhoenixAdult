from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id

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

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = re.sub(r'\s+', '-', ctx.title.strip())

        search_loaded = await self.fetch_and_load(
            f'{base}{ctx.site_info.search_path}{slug}/', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model search {slug}'
        )
        if not search_loaded:
            return []
        model_href = (search_loaded['sel'].xpath('(//div[contains(@class,"item-inside")]//a)[1]/@href').get() or '').strip()
        if not model_href:
            return []

        model_loaded = await self.fetch_and_load(
            absolute_url(model_href, ctx.site_info.base_url), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] model page'
        )
        if not model_loaded:
            return []

        results: list[SearchResult] = []
        for card in model_loaded['sel'].xpath('//div[contains(@class,"listing-videos")]//div[contains(@class,"item")]'):
            title = (card.xpath(f'(.//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip()
            href = (card.xpath('(.//a)[1]/@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            date = iso_date(_de_ordinal((card.xpath(f'(.//span[{_cls("date")}])[1]').xpath('string(.)').get() or '').strip()))
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])
                )
            )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    def _tagline_of(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//h1//span[contains(@class,"sup-title")]//span)[1]').xpath('string(.)').get() or '').strip() or scene.site.name

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath(f'(//h1//span[{_cls("title")}])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"content-information-description")]//p)[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline_of(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline_of(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        tagline = self._tagline_of(scene)
        raw = (
            (scene.sel.xpath(f'(//span[{_cls("date")}]//span[{_cls("content")}])[1]').xpath('string(.)').get() or '')
            .replace(tagline, '')
            .replace('Video added on', '')
            .strip()
        )
        return (iso_date(_de_ordinal(raw)) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        tagline = self._tagline_of(scene)
        if tagline == 'KarupsHA':
            return ['Amateur']
        if tagline == 'KarupsOW':
            return ['MILF']
        return None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//span[contains(@class,"models")]//a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name:
                continue
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                raw = (page['sel'].xpath('(//div[contains(@class,"model-thumb")]//img)[1]/@src').get() or '').strip() if page else ''
                if raw:
                    photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url))
        xpaths = (
            '(//div[contains(@class,"video-player")]//video)[1]/@poster',
            '//img[contains(@class,"poster")]/@src',
            '//div[contains(@class,"video-thumbs")]//img/@src',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
