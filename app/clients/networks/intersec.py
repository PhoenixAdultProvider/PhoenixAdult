from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Intersec Interactive'
_TAGLINE_FALLBACK = 'Intersex'

_TAGLINES: dict[str, str] = load_site_json(__file__, 'intersec_taglines')


def _resolve_tagline(link_text: str) -> str:
    hay = link_text.lower()
    for key, label in _TAGLINES.items():
        if key in hay:
            return label
    return _TAGLINE_FALLBACK


class IntersecClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        scene_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {scene_url}')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"is-multiline")]/div[contains(@class,"column")]'):
            href = first_attr(card, '(.//a)[1]/@href')
            title = (card.xpath('(.//div[contains(@class,"has-text-weight-bold")])[1]').xpath('string(.)').get() or '').strip()
            if not href or not title:
                continue
            if href.startswith('http'):
                detail_url = href
            else:
                cleaned = href.lstrip('/')
                cleaned = cleaned[4:] if cleaned.startswith('iod/') else cleaned
                detail_url = f'{base}/iod/{cleaned}'
            raw_date = (card.xpath('(.//span[contains(@class,"tag")])[1]').xpath('string(.)').get() or '').strip()
            date = iso_date(raw_date) if raw_date else ctx.search_date
            cover = first_attr(card, '(.//img)[1]/@src')
            cover_packed = self.encode(cover) if cover else ''
            results.append(
                build_search_result(
                    title=title,
                    scene_url=detail_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([detail_url, f'{date or ""}|{cover_packed}']),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        links = scene.sel.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        if not links:
            return _TAGLINE_FALLBACK
        last = links[-1]
        link_text = f'{last.xpath("string(.)").get() or ""} {last.xpath("@href").get() or ""}'
        return _resolve_tagline(link_text)

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//div[contains(@class,"has-text-weight-bold")])[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//div[contains(@class,"has-text-white-ter")])[3]').xpath('string(.)').get() or '').strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tag = self._tagline(scene)
        metadata.collections = [tag] if tag else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//span[contains(@class,"is-dark")][1]').xpath('string(.)').get() or '').strip()
        if raw:
            metadata.release_date = iso_date(raw)
        else:
            metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = ['BDSM']
        dark = scene.sel.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        actor_count = max(0, len(dark) - 1)
        if (group := self.group_genre_for(actor_count)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        dark = scene.sel.xpath('(//div[contains(@class,"has-text-white-ter")])[1]//a[contains(@class,"is-dark")]')
        entries = [ActorResult(name=first_attr(el)) for el in dark[:-1]]
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()

        if scene.scene_date and '|' in scene.scene_date:
            cover_b64 = scene.scene_date.split('|', 1)[1]
            if cover_b64:
                try:
                    cover = self.decode(cover_b64)
                except Exception:  # noqa: BLE001 - decode failures are non-fatal
                    cover = ''
                if cover:
                    coll['push'](cover)

        xpaths = ('//video-js/@poster', '//figure//img/@src')
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.raw_image_urls = images
