from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

_DATE_FMT = '%Y %B %d'
_ROSTER: set[str] = set(load_site_json(__file__, 'queensnake_actors'))


def _is_qs_actor(tag: str) -> bool:
    return tag.strip().lower() in _ROSTER


class QueenSnakeClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'cLegalAge=true'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        slug = ctx.title.strip().replace(' ', '-').lower()
        search_url = f'{base}/previewmovie/{slug}/'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return

        pager = loaded['sel'].xpath('(//div[@class="pagerWrapper"]//a)[1]/@href').get() or ''
        if '/previewmovies/0' in pager:
            return

        for card in loaded['sel'].xpath('//div[@class="contentBlock"]'):
            title = (card.xpath('(.//span[@class="contentFilmName"])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                continue
            raw_date = (card.xpath('(.//span[@class="contentFileDate"])[1]').xpath('string(.)').get() or '').strip().split(' • ')[0]
            date = iso_date(raw_date, _DATE_FMT) if raw_date else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=search_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (search_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//span[@class="contentFilmName"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[@class="contentPreviewDescription"])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[@class="contentFileDate"])[1]').xpath('string(.)').get() or '').strip().split(' • ')[0]
        metadata.release_date = (iso_date(raw, _DATE_FMT) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = ['BDSM', 'S&M']
        for a in scene.sel.xpath('//div[@class="contentPreviewTags"]//a'):
            g = first_attr(a, 'normalize-space(.)')
            if g and g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for a in scene.sel.xpath('//div[@class="contentPreviewTags"]//a'):
            name = first_attr(a, 'normalize-space(.)')
            if not name or name in seen or not _is_qs_actor(name):
                continue
            seen.add(name)
            actors.append(ActorResult(name=name))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        for src in scene.sel.xpath('//div[@class="contentBlock"]//img[contains(@src,"preview")]/@src').getall():
            coll['push'](src)
        images: list[str] = coll['list']
        metadata.art = images or []
