from __future__ import annotations

import re

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

_VIEWING_COOKIE = 'viewing-preferences=straight%2Cgay'
_BR_RE = re.compile(r'<br\s*/?>', re.IGNORECASE)
_TAG_RE = re.compile(r'<[^>]+>')
_WS_RE = re.compile(r'\s+')

_CHANNELS = load_site_json(__file__, 'kink_channels')
_TAGLINE_BY_CHANNEL: dict[str, str] = _CHANNELS['taglineByChannel']
_STUDIO_BY_TAGLINE: dict[str, str] = _CHANNELS['studioByTagline']
_CHANNEL_KEYS = sorted(_TAGLINE_BY_CHANNEL.keys(), key=len, reverse=True)


def _kink_tagline(channel_text: str, fallback: str) -> str:
    hay = channel_text.lower()
    for key in _CHANNEL_KEYS:
        if key in hay:
            return _TAGLINE_BY_CHANNEL[key]
    return fallback


class KinkClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': _VIEWING_COOKIE})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')

        if ctx.scene_id:
            scene_url = f'{base}/shoot/{ctx.scene_id}'
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if not page:
                return
            title = (page['sel'].xpath('(//h1[contains(@class,"fs-0")])[1]').xpath('string(.)').get() or '').strip()
            if not title:
                return
            results.append(
                build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=100, cur_id=pack_cur_id([scene_url]))
            )
            return

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//div[contains(@class,"shoot-card") and contains(@class,"scene")]'):
            title = first_attr(card, '(.//img)[1]/@alt')
            href = first_attr(card, '(.//a[contains(@class,"shoot-link")])[1]/@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            raw_date = (card.xpath('(.//div[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
            date = iso_date(raw_date) if raw_date else ctx.search_date
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline_for(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        link = scene.sel.xpath('(//div[contains(@class,"shoot-detail-legend")]//a[contains(@href,"/channel/")])[1]')
        channel_text = f'{link.xpath("string(.)").get() or ""} {link.xpath("@href").get() or ""}'
        return _kink_tagline(channel_text, scene.site.name)

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1[contains(@class,"fs-0")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        span_html = scene.sel.xpath('(//div[contains(@class,"description")]//span[contains(@class,"fw-200")])[1]').get() or ''
        if not span_html:
            return
        text = _TAG_RE.sub('', _BR_RE.sub(' ', span_html))
        metadata.summary = _WS_RE.sub(' ', text).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = _STUDIO_BY_TAGLINE.get(self._tagline_for(scene), 'Kink')

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_for(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_for(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (
            scene.sel.xpath('(//div[contains(@class,"shoot-detail-legend")]//span[contains(@class,"text-muted")])[1]').xpath('string(.)').get() or ''
        ).strip()
        if raw:
            metadata.release_date = iso_date(raw)
            return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres = self.dedup_strings(
            [(a.xpath('normalize-space(.)').get() or '').replace(',', '').strip() for a in scene.sel.xpath('//a[contains(@href,"/tag/")]')]
        )
        cast = len(scene.sel.xpath('//span[contains(@class,"text-primary")]//a[contains(@href,"/model/")]'))
        if (group := self.group_genre_for(cast)) and group not in genres:
            genres.append(group)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.actors = await self._collect_people(scene, '//span[contains(@class,"text-primary")]//a[contains(@href,"/model/")]')

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.directors = await self._collect_people(scene, '//span[contains(@class,"director-name")]//a') or None

    async def _collect_people(self, scene: LoadedScene, xp: str) -> list[ActorResult]:
        assert scene.sel is not None
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            return first_attr(sel, '(//div[contains(@class,"biography-container")]//img)[1]/@src')

        refs: list[tuple[str, str]] = []
        for el in scene.sel.xpath(xp):
            name = (el.xpath('normalize-space(.)').get() or '').replace(',', '').strip()
            href = first_attr(el, '@href')
            if name:
                refs.append((name, absolute_url(href, base) if href else ''))
        return await self.resolve_actor_photos(refs, extract_photo, capture=None)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()
        xpaths = (
            '//video/@poster',
            '//div[contains(@class,"player")]/div/@poster',
            '//div[@id="galleryWrapper"]//img/@data-image-file',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.raw_image_urls = images
