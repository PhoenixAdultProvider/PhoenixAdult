from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr


class WankzVRClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'sst=ulang-en'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        tokens = ctx.title.strip().split()
        scene_id = tokens[0] if tokens and tokens[0].isdigit() else None

        if scene_id and len(tokens) == 1:
            scene_url = f'{base}/{scene_id}'
            loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if not loaded:
                return
            title = (loaded['sel'].xpath('(//h1[contains(@class,"detail__title")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return
            date = iso_date((loaded['sel'].xpath('(//span[contains(@class,"detail__date")])[1]').xpath('string(.)').get() or '').strip())
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([scene_url]),
                )
            )
            return

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded.replace('%20', '+'))
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//ul[contains(@class,"cards-list")]//li'):
            texts = card.xpath('(.//div[contains(@class,"card__footer")]//div[contains(@class,"card__h")])[1]/text()').getall()
            title = next((t.strip() for t in texts if t.strip()), '')
            href = first_attr(card, '(.//a)[1]/@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            date = iso_date((card.xpath('(.//div[contains(@class,"card__date")])[1]').xpath('string(.)').get() or '').strip())
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1[contains(@class,"detail__title")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[contains(@class,"detail__txt")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[contains(@class,"detail__date")])[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = iso_date(raw) or scene.scene_date

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        values: list[str | None] = [el.xpath('normalize-space(.)').get() for el in scene.sel.xpath('//div[contains(@class,"tag-list")]//a')]
        metadata.genres = self.dedup_strings(values) or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//div[contains(@class,"detail__models")]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                if page:
                    srcset = first_attr(page['sel'], '(//div[contains(@class,"person__avatar")]//source)[2]/@srcset')
                    well_formed = len(page['sel'].xpath('/html/*')) == 2
                    if srcset and well_formed:
                        photo = srcset.replace('.webp', '.jpg')
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//meta[@property="og:image"])[1]/@content')
        if not raw:
            return
        metadata.raw_image_urls = [raw.replace('cover', 'hero').replace('medium.jpg', 'large.jpg')]
