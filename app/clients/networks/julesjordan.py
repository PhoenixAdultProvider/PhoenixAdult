from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, join_url, pack_cur_id

STUDIO = 'Jules Jordan'


def _desc_row(sel: Any, label: str) -> str:
    return (sel.xpath(f'(//div[contains(@class,"player-scene-description")]//span[contains(text(),"{label}")]/..)[1]').xpath('string(.)').get() or '').strip()


class JulesJordanClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        # 1. Direct slug guess.
        direct_url = f'{base}/trial/scenes/{"-".join(ctx.title.lower().split())}_vids.html'
        direct = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {direct_url}')
        if direct:
            seen.add(direct_url)
            results.append(
                build_search_result(
                    title=ctx.title,
                    scene_url=direct_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (direct_url, ctx.search_date) if x]),
                )
            )

        # 2. On-site search.
        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//div[contains(@class,"grid-item")]'):
                a = card.xpath('(.//a)[1]')
                href = (a.xpath('@href').get() or '').strip()
                title = (a.xpath('(.//img)[1]/@alt').get() or '').strip()
                if not href or not title:
                    continue
                scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                results.append(
                    build_search_result(
                        title=title,
                        scene_url=scene_url,
                        query=ctx.title,
                        search_date=ctx.search_date,
                        cur_id=pack_cur_id([x for x in (scene_url, ctx.search_date) if x]),
                    )
                )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"movie_title")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _desc_row(scene.sel, 'Description:').replace('Description:', '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return _desc_row(scene.sel, 'Movie:').replace('Movie:', '').replace('Feature: ', '').strip() or None

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [STUDIO]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        if scene.scene_date:
            return scene.scene_date
        raw = _desc_row(scene.sel, 'Date:').replace('Date:', '').strip()
        return iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//span[contains(text(),"Categories")]//a'):
            g = (a.xpath('normalize-space(.)').get() or '').strip().lower()
            if g and g not in genres:
                genres.append(g)
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        if scene.site.name == 'GirlGirl':
            anchors = scene.sel.xpath('//div[contains(@class,"item")]//span//div//a')
        else:
            anchors = scene.sel.xpath('//div[contains(@class,"player-scene-description")]//span[contains(text(),"Starring:")]/..//a')
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in anchors:
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                actor_url = href if href.startswith('http') else absolute_url(href, base)
                page = await self.fetch_and_load(actor_url, None, f'GET {actor_url} (actor)')
                raw = (page['sel'].xpath('(//img[contains(@class,"model_bio_thumb")])[1]/@src0_3x').get() or '').strip() if page else ''
                if raw:
                    photo = raw if raw.startswith('http') else absolute_url(raw, base)
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        images: list[str] = []

        def push(raw: str) -> None:
            if not raw:
                return
            abs_url = join_url(raw, base)
            if abs_url not in images:
                images.append(abs_url)

        push((scene.sel.xpath('(//video[@id="video-player"])[1]/@poster').get() or '').strip())

        title = (scene.sel.xpath('(//div[contains(@class,"movie_title")])[1]').xpath('string(.)').get() or '').strip()
        if title:
            search_url = base + scene.site.search_path.replace('{query}', quote(title))
            loaded = await self.fetch_and_load(search_url, None, f'GET {search_url} (slideshow)')
            if loaded:
                img = loaded['sel'].xpath('(//img[contains(@id,"set-target")])[1]')
                for i in range(7):
                    push((img.xpath(f'@src{i}_1x').get() or '').strip())
        return images or None
