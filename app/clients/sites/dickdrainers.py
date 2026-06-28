from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_text, web_search_urls
from app.utils.processors.title_case import title_case

_SLUG_ACTORS: dict[str, list[str]] = load_site_json(__file__, 'dickdrainers_slug_actors')

_CARD_XP = '//div[contains(@class,"item-video") and contains(@class,"hover")]'
_SRC0_3X_RE = re.compile(r'src0_3x="([^"]+)"')
_SLUG_RE = re.compile(r'/s/([^/]+)\.html$')


class DickDrainersClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        onsite_query = re.sub(r'\s+', '+', ctx.title.strip().lower())
        onsite_url = base + ctx.site_info.search_path.replace('{query}', onsite_query)

        results: list[SearchResult] = []
        onsite_hrefs: set[str] = set()

        loaded = await self.fetch_and_load(onsite_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if loaded:
            for card in loaded['sel'].xpath(_CARD_XP):
                raw_title = first_text(card, './/h4')
                href = (card.xpath('(.//h4//a/@href)[1]').get() or '').strip()
                if not raw_title or not href:
                    continue
                scene_url = absolute_url(href, base)
                onsite_hrefs.add(scene_url)
                raw_date = first_text(card, './/div[contains(@class,"date")]')
                date = iso_date(raw_date) if raw_date else None
                results.append(self._result(raw_title, scene_url, ctx, date))

        # Web-search fallback — only /trailers/ URLs the on-site search missed.
        for scene_url in await web_search_urls(ctx.title, ctx.site_info, include=['/trailers/']):
            if scene_url in onsite_hrefs:
                continue
            detail = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] fallback {scene_url}')
            if not detail:
                continue
            raw_title = first_text(detail['sel'], '//h3')
            if not raw_title:
                continue
            raw_date = (detail['sel'].xpath('(//div[contains(@class,"videoInfo") and contains(@class,"clear")]/p/text())[1]').get() or '').strip()
            date = iso_date(raw_date) if raw_date else None
            results.append(self._result(raw_title, scene_url, ctx, date))

        return results

    def _result(self, title: str, scene_url: str, ctx: SearchContext, date: str | None) -> SearchResult:
        return build_search_result(
            title=title,
            scene_url=scene_url,
            query=ctx.title,
            display_date=date,
            search_date=ctx.search_date,
            cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//h3') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        parts = [
            s.xpath('normalize-space(.)').get() or '' for s in scene.sel.xpath('//div[contains(@class,"videoDetails") and contains(@class,"clear")]//p/span')
        ]
        parts = [p for p in parts if p]
        if not parts:
            return None
        joined = ' '.join(parts).replace('FULL VIDEO', '').strip()
        return joined or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        if scene.scene_date:
            return iso_date(scene.scene_date) or scene.scene_date
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"videoInfo") and contains(@class,"clear")]/p/text())[1]').get() or '').strip()
        return iso_date(raw) if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//li[contains(.,"Tags")]/following-sibling::ul[1]//a'):
            raw = (a.xpath('normalize-space(.)').get() or '').strip()
            if not raw:
                continue
            g = title_case(raw, site_name=scene.site.name)
            if g not in genres:
                genres.append(g)
        return genres

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        items = scene.sel.xpath('//li[contains(@class,"update_models")]')
        if not items:
            m = _SLUG_RE.search(scene.url)
            if m:
                return [ActorResult(name=name) for name in _SLUG_ACTORS.get(m.group(1).lower(), [])]
            return []

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for li in items:
            name = (li.xpath('normalize-space(.)').get() or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            href = (li.xpath('(.//a/@href)[1]').get() or '').strip()
            photo = ''
            if href:
                actor_url = absolute_url(href, scene.site.base_url)
                actor_page = await self.fetch_and_load(actor_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                if actor_page:
                    raw = (actor_page['sel'].xpath('(//div[contains(@class,"profile-pic")]//img/@src0_3x)[1]').get() or '').strip()
                    photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        images: list[str] = []

        def push(raw: str) -> None:
            raw = (raw or '').strip()
            if not raw:
                return
            abs_url = absolute_url(raw, scene.site.base_url)
            if abs_url not in images:
                images.append(abs_url)

        for el in scene.sel.xpath('//div[contains(@class,"player_thumbs")]'):
            push(el.xpath('@src0_3x').get() or '')
            for child in el.xpath('.//*[@src0_3x]'):
                push(child.xpath('@src0_3x').get() or '')

        for script in scene.sel.xpath('//div[contains(@class,"player") and contains(@class,"full_width")]//script'):
            text = script.xpath('string(.)').get() or ''
            for m in _SRC0_3X_RE.finditer(text):
                push(m.group(1))

        return images
