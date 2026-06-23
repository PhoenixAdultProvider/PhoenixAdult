from __future__ import annotations

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_text

_LI_XP = '//div[contains(@class,"videoContent")]//ul/li'


class MeanaWolfClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return []
        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//div[contains(@class,"videoBlock")]'):
            anchor = card.xpath('(.//p/a)[1]')
            title = (anchor.xpath('normalize-space(.)').get() or '').strip()
            href = (anchor.xpath('@href').get() or '').strip()
            if not title or not href:
                continue
            scene_url = href if href.startswith('http') else absolute_url(href, ctx.site_info.base_url)
            poster = (card.xpath('(.//img[contains(@class,"video_placeholder")]/@src)[1]').get() or '').strip()
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([scene_url, poster]),
                )
            )
        return results

    # ── Context loader (curID packs the search-card poster) ───────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        poster = payload[pipe + 1 :].strip() if pipe >= 0 else ''
        loaded = await self.fetch_and_load(url, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {url}')
        if not loaded:
            return None
        return LoadedScene(url=url, site=site, capture=ctx.capture if ctx else None, sel=loaded['sel'], html=loaded['html'], extra={'poster': poster})

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"trailerArea")]//h3') or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        return first_text(scene.sel, '//div[contains(@class,"trailerContent")]//p') or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return 'Meana Wolf'

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = first_text(scene.sel, f'({_LI_XP})[2]').replace('ADDED:', '').strip()
        return iso_date(raw, '%B %d, %Y') if raw else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [a.xpath('normalize-space(.)').get() for a in scene.sel.xpath(f'({_LI_XP})[last()]//a')]
        return self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        actors: list[ActorResult] = []
        for el in scene.sel.xpath(f'({_LI_XP})[3]//a'):
            name = (el.xpath('normalize-space(.)').get() or '').strip()
            if not name:
                continue
            photo = ''
            href = (el.xpath('@href').get() or '').strip()
            if href:
                loaded = await self.fetch_and_load(absolute_url(href, scene.site.base_url), FetchCtx(capture=scene.capture), f'GET {href} (actor)')
                raw = (loaded['sel'].xpath('(//div[contains(@class,"modelBioPic")]//img/@src0_3x)[1]').get() or '').strip() if loaded else ''
                photo = (raw if raw.startswith('http') else absolute_url(raw, scene.site.base_url)) if raw else ''
            actors.append(ActorResult(name=name, photo_url=photo))
        return actors

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        poster = scene.extra.get('poster', '') if isinstance(scene.extra, dict) else ''
        if not poster:
            return []
        return [poster if poster.startswith('http') else absolute_url(poster, scene.site.base_url)]
