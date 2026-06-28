from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json

_STUDIO_OVERRIDES: dict[str, str] = load_site_json(__file__, 'interracialpass_studios')
_TITLE_SELECTORS: dict[str, str] = load_site_json(__file__, 'interracialpass_title_selectors')


def _studio_for(site_name: str) -> str:
    return _STUDIO_OVERRIDES.get(site_name, site_name)


def _title_selector_for(site_name: str) -> str:
    return _TITLE_SELECTORS.get(site_name, 'h2')


class InterracialPassClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        results: list[SearchResult] = []
        seen: set[str] = set()

        # 1. Direct trailer-URL guess.
        direct_url = f'{base}/t1/trailers/{ctx.title.strip().replace(" ", "-")}.html'
        direct = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] directScene {direct_url}')
        if direct:
            title = (
                direct['sel'].xpath('(//div[contains(@class,"video-player")]//h2[contains(@class,"section-title")])[1]').xpath('string(.)').get() or ''
            ).strip()
            if title:
                raw_date = (
                    (direct['sel'].xpath('(//div[contains(@class,"update-info-row")])[1]').xpath('string(.)').get() or '').replace('Released:', '').strip()
                )
                seen.add(direct_url)
                results.append(
                    build_search_result(title=title, scene_url=direct_url, query=ctx.title, display_date=iso_date(raw_date), search_date=ctx.search_date)
                )

        # 2. On-site search.
        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.title.strip().replace(' ', '+'))
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//div[contains(@class,"item-video")]'):
                a = card.xpath('(.//a)[1]')
                title = (a.xpath('@title').get() or '').strip()
                href = (a.xpath('@href').get() or '').strip()
                if not title or not href:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date_tok = (card.xpath('(.//div[contains(@class,"more-info-div")])[1]').xpath('string(.)').get() or '').split('|')[-1].strip()
                results.append(
                    build_search_result(
                        title=title, scene_url=scene_url, query=ctx.title, display_date=iso_date(date_tok) if date_tok else None, search_date=ctx.search_date
                    )
                )
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        tag = _title_selector_for(scene.site.name)
        return (
            scene.sel.xpath(f'(//div[contains(@class,"video-player")]//{tag}[contains(@class,"section-title")])[1]').xpath('string(.)').get() or ''
        ).strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return (scene.sel.xpath('(//div[contains(@class,"update-info-block")])[2]').xpath('string(.)').get() or '').replace('Description:', '').strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return _studio_for(scene.site.name)

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"update-info-row")])[1]').xpath('string(.)').get() or '').replace('Released:', '').strip()
        return (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('string(.)').get() or '' for a in scene.sel.xpath('//ul[contains(@class,"tags")]//li//a')]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        is_bbc = scene.site.name == 'BBC Surprise'
        actors: list[ActorResult] = []
        for li in scene.sel.xpath('//div[contains(@class,"models-list-thumbs")]//li'):
            name = (li.xpath('(.//span)[1]').xpath('string(.)').get() or '').strip()
            if not name:
                continue
            raw = (li.xpath('(.//img)[1]/@src0_3x').get() or '').strip()
            photo = (raw if raw.startswith('http') else base + raw) if raw else ''
            if is_bbc and name == 'Twins':
                actors.append(ActorResult(name='Joey White', photo_url=photo))
                actors.append(ActorResult(name='Sami White', photo_url=photo))
            else:
                actors.append(ActorResult(name=name, photo_url=photo))
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda raw: raw if raw.startswith('http') else base + raw)
        for src in scene.sel.xpath('//div[contains(@class,"player-thumb")]//img/@src0_1x').getall():
            coll['push'](src)
        images: list[str] = coll['list']
        return images or None
