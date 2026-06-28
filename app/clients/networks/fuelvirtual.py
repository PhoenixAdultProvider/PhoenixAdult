from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import build_search_result, iso_date, load_site_json
from app.utils.helpers.html_helpers import first_attr, first_string

STUDIO = 'FuelVirtual'
_IMG_SCRIPT_RE = re.compile(r'image:\s*"(.+)"')
_SCENE_ID_RE = re.compile(r'id=(\d+)')

_ACTOR_DB: dict[str, dict[str, list[str]]] = load_site_json(__file__, 'fuelvirtual_actors')


def _server_path(site_name: str) -> str:
    return '/tour/newgirlpov/' if site_name == 'NewGirlPOV' else '/membersarea/'


def _actors_for_scene(site_name: str, scene_id: str) -> list[str] | None:
    return _ACTOR_DB.get(site_name, {}).get(scene_id)


class FuelVirtualClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        sp = _server_path(ctx.site_info.name)
        loaded = await self.fetch_and_load(base + ctx.site_info.search_path + ctx.encoded, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search')
        if not loaded:
            return []
        results: list[SearchResult] = []
        for row in loaded['sel'].xpath('//div[@align="left"]'):
            a = row.xpath('(.//td[@valign="top"])[2]//a[1]')
            title = first_string(a)
            href = first_attr(a, '@href')
            if not title or not href:
                continue
            date_raw = (row.xpath('(.//span[@class="date"])[1]').xpath('string(.)').get() or '').replace('Added', '').strip()
            date_iso = iso_date(date_raw) if date_raw else None
            scene_url = f'{base}{sp}{href}'
            results.append(build_search_result(title=title, scene_url=scene_url, query=ctx.title, display_date=date_iso, search_date=ctx.search_date))
        return results

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or ''
        if scene.site.name == 'NewGirlPOV':
            parts = raw.split(' ')
            return (parts[1].strip() if len(parts) > 1 else '') or None
        return raw.split('-')[0].strip() or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        genres = [
            g
            for g in (
                first_attr(a, 'normalize-space(.)') for a in scene.sel.xpath('//td[contains(@class,"plaintext")]//a[contains(@class,"model_category_link")]')
            )
            if g
        ]
        if scene.site.name != 'NewGirlPOV':
            genres.append('18-Year-Old')
        cast = len(scene.sel.xpath('//div[@id="description"]//td[@align="left"]//a'))
        if cast == 3:
            genres.append('Threesome')
        elif cast == 4:
            genres.append('Foursome')
        elif cast > 4:
            genres.append('Orgy')
        return genres or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actor_els = scene.sel.xpath('//div[@id="description"]//td[@align="left"]//a')
        if not actor_els:
            return None
        m = _SCENE_ID_RE.search(scene.url)
        db_names = _actors_for_scene(scene.site.name, m.group(1)) if m else None
        if db_names is not None:
            return [ActorResult(name=n) for n in db_names]
        actors = [ActorResult(name=name) for name in (first_attr(a, 'normalize-space(.)') for a in actor_els) if name]
        return actors or None

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        out: list[str] = []

        def push(u: str) -> None:
            if u and u not in out:
                out.append(u)

        for src in scene.sel.xpath('//a[contains(@class,"jqModal")]//img/@src | //div[@id="overallthumb"]//a//img/@src').getall():
            if not src:
                continue
            push(base + src if src.startswith('/') else f'{base}/tour/newgirlpov/{src}')

        photo_url = scene.url.replace('vids', 'highres')
        if photo_url != scene.url:
            photo = await self.fetch_and_load(photo_url, None, f'GET {photo_url} (highres)')
            if photo:
                for src in photo['sel'].xpath('//a[contains(@class,"jqModal")]//img/@src').getall():
                    if src:
                        push(base + src)

        for script in scene.sel.xpath('//div[@id="mediabox"]//script'):
            m = _IMG_SCRIPT_RE.search(script.xpath('string(.)').get() or '')
            if m:
                push(base + m.group(1))
        return out or None
