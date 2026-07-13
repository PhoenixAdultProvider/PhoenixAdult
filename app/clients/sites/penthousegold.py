from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr, first_text

_H1_XP = '//div[contains(@class,"content-desc") and contains(@class,"content-new-scene")]//h1'
_UPLOAD_XP = '(//meta[@itemprop="uploadDate"]/@content)[1]'
_PREFIX_RE = re.compile(r'^(Video|Movie)\s*-\s*')


class PenthouseGoldClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        seen: set[str] = set()

        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if loaded:
            for card in loaded['sel'].xpath('//div[contains(@class,"scene")]'):
                anchor = card.xpath('(.//a[@data-track="TITLE_LINK"])[1]')
                href = first_attr(anchor, '@href')
                if '/scenes/' not in href:
                    continue
                title = first_attr(anchor, 'normalize-space(.)')
                if not title:
                    continue
                scene_url = absolute_url(href, ctx.site_info.base_url)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                date = iso_date(first_text(card, './/span[contains(@class,"scene-date")]'))
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

        slug = re.sub(r'\s+', '-', ctx.title.strip())
        for kind in ('video', 'movie'):
            scene_url = f'{base}/scenes/{kind}---{slug}_vids.html'
            if scene_url in seen:
                continue
            guess = await self.fetch_and_load(scene_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] guess {scene_url}')
            title = first_text(guess['sel'], _H1_XP) if guess else ''
            if not title:
                continue
            seen.add(scene_url)
            raw_date = (guess['sel'].xpath(_UPLOAD_XP).get() or '').strip() if guess else ''
            date = iso_date(raw_date, '%m/%d/%Y') if raw_date else None
            results.append(
                build_search_result(
                    title=title,
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([x for x in (scene_url, date) if x]),
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.title = _PREFIX_RE.sub('', first_text(sel, _H1_XP)).strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        metadata.summary = first_text(sel, '//div[contains(@class,"content-desc") and contains(@class,"content-new-scene")]//p')

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = (sel.xpath(_UPLOAD_XP).get() or '').strip()
        metadata.release_date = (iso_date(raw, '%m/%d/%Y') if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        values: list[str | None] = [first_attr(a, 'normalize-space(.)').lower() for a in sel.xpath('//ul[contains(@class,"scene-tags")]//li//a')]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        entries: list[ActorResult] = []
        for card in sel.xpath('//ul[@id="featured_pornstars"]//div[contains(@class,"model")]'):
            name = first_text(card, './/h3')
            raw = first_attr(card, '(.//img/@src)[1]')
            photo = (absolute_url(raw, scene.site.base_url)) if raw else ''
            entries.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = self.dedup_people(entries)

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        raw = first_attr(sel, '(//div[@id="trailer_player_finished"]//img/@src)[1]')
        if not raw:
            return
        metadata.art = [absolute_url(raw, scene.site.base_url)]
