from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id

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

    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        p = self._profile(ctx.site_info.name)
        quoted = quote(f'"{ctx.title}"', safe='')
        search_url = base + ctx.site_info.search_path.replace('{query}', quoted)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()
        for row in loaded['sel'].xpath(f'//{p["search_results"]}'):
            raw_title = (row.xpath(f'(.//{p["search_title"]})[1]').xpath('string(.)').get() or '').strip()
            href = (row.xpath('(.//a)[1]/@href').get() or '').strip()
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
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        raw = (scene.sel.xpath(f'(//{p["detail_title"]})[1]').xpath('string(.)').get() or '').strip()
        if not raw:
            raw = (scene.sel.xpath('(//video)[1]/@data-video').get() or '').strip()
        return _strip_4k(raw) or None if raw else None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        summary_xpaths = (
            '//p[contains(@class,"description") and not(contains(@class,"description-scene"))]',
            '//p[contains(@class,"description-scene")]',
            '(//h2)[1]/following-sibling::p[1]',
        )
        for xpath in summary_xpaths:
            text = (scene.sel.xpath(f'({xpath})[1]').xpath('string(.)').get() or '').strip()
            if text:
                return text
        return None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        inline = (scene.sel.xpath('(//i[@id="site"])[1]/@value').get() or '').strip()
        if inline:
            return inline
        return scene.site.name if 'Spizoo' not in scene.site.name else STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//p[contains(@class,"date")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            head = raw[:10]
            parsed = iso_date(head, '%Y-%m-%d') or iso_date(head)
            if parsed:
                return parsed
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        genre_xpaths = ('//div[contains(@class,"categories-holder")]//a', '//div[h3[contains(.,"Categories")]]//a')
        for xpath in genre_xpaths:
            for el in scene.sel.xpath(xpath):
                for part in (el.xpath('string(.)').get() or '').split(','):
                    g = part.strip().lower()
                    if g and g not in genres:
                        genres.append(g)
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        p = self._profile(scene.site.name)
        base = scene.site.base_url
        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath(f'//{p["actor_container"]}'):
            name = (el.xpath('string(.)').get() or '').replace('.', '').strip()
            href = (el.xpath('@href').get() or '').strip()
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
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
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
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
