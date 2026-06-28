from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, join_url, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_string

STUDIO = 'VIP4K'
_GENRES: dict[str, list[str]] = load_site_json(__file__, 'vip4k_genres')


def _clean_title(raw: str) -> str:
    return raw.split('|')[-1].strip() if raw else raw


class VIP4KClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        scene_id = ctx.scene_id or ''
        if scene_id.isdigit() and int(scene_id) > 10:
            scene_url = f'{base}/en/videos/{scene_id}'
            page = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {scene_url}')
            if page:
                title = _clean_title(page['sel'].xpath('(//title)[1]').xpath('string(.)').get() or '')
                if title:
                    return [
                        build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url]))
                    ]

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"item__description")]'):
            anchor = card.xpath('(.//a[contains(@class,"item__title")])[1]')
            raw_title = first_string(anchor)
            href = first_attr(anchor, '@href')
            if not raw_title or not href:
                continue
            scene_url = join_url(href, base)
            raw_date = (card.xpath('(.//div[contains(@class,"item__date")])[1]').xpath('string(.)').get() or '').strip()
            date = (iso_date(raw_date) if raw_date else None) or ctx.search_date
            results.append(
                build_search_result(
                    title=raw_title,
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
        return _clean_title(scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"player-description__text")])[1]').xpath('string(.)').get() or '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    def _tagline(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        raw = (
            scene.sel.xpath('(//a[contains(@class,"player-additional__site") and contains(@class,"ph_register")])[1]').xpath('string(.)').get() or ''
        ).strip()
        return raw.replace('Sis', 'Sis.Porn') if raw else scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [self._tagline(scene)]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//span[contains(@class,"player-additional__text")])[1]').xpath('string(.)').get() or '').strip()
        if raw:
            return iso_date(raw)
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = list(_GENRES.get(scene.site.name, []))
        for el in scene.sel.xpath('//div[contains(@class,"tags")]//a'):
            g = (el.xpath('string(.)').get() or '').replace('#', '').strip()
            if g and g not in genres:
                genres.append(g)
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        entries = [
            ActorResult(name=(el.xpath('(.//div[contains(@class,"model__name")])[1]').xpath('string(.)').get() or '').strip())
            for el in scene.sel.xpath('//a[contains(@class,"player-description__model") and contains(@class,"model") and contains(@class,"ph_register")]')
        ]
        return self.dedup_people(entries) or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else (f'https:{raw}' if raw.startswith('//') else raw))
        for el in scene.sel.xpath('//div[contains(@class,"player-item__block")]//img'):
            coll['push']((el.xpath('@data-src').get() or el.xpath('@src').get() or '').strip())
        images: list[str] = coll['list']
        return images or None
