from __future__ import annotations

from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, date_distance_score, iso_date, load_site_json, title_distance_score
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Femdom Empire'
_DATE_FMT = '%B %d, %Y'

_MANUAL_MATCHES: dict[str, dict[str, str]] = load_site_json(__file__, 'femdomempire_manual_matches')


class FemdomEmpireClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')

        def parse_rows(sel: Any) -> None:
            for row in sel.xpath('//div[contains(@class,"item-info")]'):
                a = row.xpath('(.//a)[1]')
                title = first_attr(a)
                href = first_attr(a, '@href')
                if not title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                date_raw = (row.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').strip()
                date_iso = iso_date(date_raw) if date_raw else None
                score = date_distance_score(ctx.search_date, date_iso) if ctx.search_date and date_iso else title_distance_score(ctx.title, title)
                results.append(
                    build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date, score=score)
                )

        adv = await self.fetch_and_load(
            base + ctx.site_info.search_path.replace('{query}', ctx.encoded), FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] advanced'
        )
        if adv:
            parse_rows(adv['sel'])

        manual = _MANUAL_MATCHES.get(ctx.title.strip())
        if manual:
            results.append(build_search_result(title=manual['title'], scene_url=manual['url'], query=ctx.title, score=101))

        if results:
            return

        std = await self.fetch_and_load(f'{base}/tour/search.php?query={ctx.encoded}', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] standard')
        if std:
            parse_rows(std['sel'])

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//div[contains(@class,"videoDetails")]//h3)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[contains(@class,"videoDetails")]//p)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (
            (scene.sel.xpath('(//div[contains(@class,"videoInfo") and contains(@class,"clear")]//p)[1]').xpath('string(.)').get() or '')
            .replace('Date Added:', '')
            .strip()
        )
        metadata.release_date = iso_date(raw, _DATE_FMT) if raw else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('(//div[contains(@class,"featuring")])[2]//ul//li'):
            g = first_attr(el).lower().replace('categories:', '').replace('tags:', '').strip()
            if g:
                genres.append(g)
        if 'Femdom' not in genres:
            genres.append('Femdom')
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('(//div[contains(@class,"featuring")])[1]/ul/li'):
            name = (el.xpath('string(.)').get() or '').replace('Featuring:', '').strip()
            if name:
                actors.append(ActorResult(name=name))
        title = (scene.sel.xpath('(//div[contains(@class,"videoDetails")]//h3)[1]').xpath('string(.)').get() or '').strip()
        if title == 'Owned by Alexis' and not any(a.name == 'Alexis Monroe' for a in actors):
            actors.append(ActorResult(name='Alexis Monroe'))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for raw in scene.sel.xpath('//a[contains(@class,"fake_trailer")]//img/@src0_1x').getall():
            coll['push'](raw)
        metadata.raw_image_urls = coll['list'] or []
