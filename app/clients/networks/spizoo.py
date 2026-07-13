from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Spizoo'
_PROFILES: dict[str, dict[str, Any]] = load_site_json(__file__, 'spizoo_profiles')

_PROFILE_KEYS = {
    'Raw Attack': 'rawattack',
    'Mr. Lucky POV': 'mrluckypov',
    'Mr. Lucky RAW': 'mrluckyraw',
    'Mr. Lucky LIFE': 'mrluckylife',
    'Cream Her': 'creamher',
    'DR. Daddy POV': 'drdaddypov',
    'Goth Girlfriends': 'gothgirlfriends',
}


def _strip_4k(title: str) -> str:
    return title[:-3].strip() if title.lower().endswith(' 4k') else title


class SpizooClient(Client):
    def _profile(self, site_name: str) -> dict[str, Any]:
        return _PROFILES[_PROFILE_KEYS.get(site_name, 'default')]

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        p = self._profile(ctx.site_info.name)
        quoted = quote(f'"{ctx.title}"', safe='')
        search_url = base + ctx.site_info.search_path.replace('{query}', quoted)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return

        seen: set[str] = set()
        for row in loaded['sel'].xpath(f'//{p["search_results"]}'):
            raw_title = (row.xpath(f'(.//{p["search_title"]})[1]').xpath('string(.)').get() or '').strip()
            href = first_attr(row, '(.//a)[1]/@href')
            if not raw_title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            if scene_url in seen:
                continue
            seen.add(scene_url)
            date = None
            if p['search_date']:
                date_el = row.xpath(f'(.//{p["search_date"]})[last()]')
                raw_date = ''.join(date_el.xpath('.//text()[not(ancestor::h4)]').getall()).strip()
                if raw_date:
                    date = iso_date(raw_date)
            results.append(
                build_search_result(
                    title=_strip_4k(raw_title),
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url, date or '']),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        p = self._profile(scene.site.name)
        raw = (sel.xpath(f'(//{p["detail_title"]})[1]').xpath('string(.)').get() or '').strip()
        if not raw:
            raw = first_attr(sel, '(//video)[1]/@data-video')
        metadata.title = _strip_4k(raw) if raw else ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        summary_xpaths = (
            '//p[contains(@class,"description") and not(contains(@class,"description-scene"))]',
            '//p[contains(@class,"description-scene")]',
            '(//h2)[1]/following-sibling::p[1]',
        )
        for xpath in summary_xpaths:
            text = (sel.xpath(f'({xpath})[1]').xpath('string(.)').get() or '').strip()
            if text:
                metadata.summary = text
                return
        metadata.summary = ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        sel = scene.require_sel()
        inline = first_attr(sel, '(//i[@id="site"])[1]/@value')
        if inline:
            return inline
        return scene.site.name if 'Spizoo' not in scene.site.name else STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = (sel.xpath('(//p[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            head = raw[:10]
            parsed = iso_date(head, '%Y-%m-%d') or iso_date(head)
            if parsed:
                metadata.release_date = parsed
                return
        metadata.release_date = (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres: list[str] = []
        genre_xpaths = ('//div[contains(@class,"categories-holder")]//a', '//div[h3[contains(.,"Categories")]]//a')
        for xpath in genre_xpaths:
            for el in sel.xpath(xpath):
                for part in (el.xpath('string(.)').get() or '').split(','):
                    g = part.strip().lower()
                    if g and g not in genres:
                        genres.append(g)
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        p = self._profile(scene.site.name)
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in sel.xpath(f'//{p["actor_container"]}'):
            name = (el.xpath('string(.)').get() or '').replace('.', '').strip()
            href = first_attr(el, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'[{scene.site.name}] actor {name}')
                if page:
                    for xp, attr in p['model_photo']:
                        raw = (page['sel'].xpath(f'(//{xp})[1]/@{attr}').get() or '').strip()
                        if raw:
                            photo = absolute_url(raw, base)
                            break
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        coll = self.image_collector(lambda raw: absolute_url(raw, scene.site.base_url))
        xpaths = (
            '//section[@id="photos-tour"]//img[contains(@class,"update_thumb") and contains(@class,"thumbs")]/@src',
            '//section[@id="scene"]//div[@id="noMore"]//img/@alt',
            '//section[@id="scene"]//video[@id="the-video"]/@poster',
            '//div[contains(@class,"row") and contains(@class,"photos-holder")]//img/@src',
            '//div[contains(@class,"content-block-video")]//img/@alt',
            '//div[@id="block-content"]//img[@class]/@src',
        )
        for xpath in xpaths:
            for raw in sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        metadata.art = images or []
