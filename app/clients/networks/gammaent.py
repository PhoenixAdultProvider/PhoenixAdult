from __future__ import annotations

import asyncio
import re
from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.concurrency.coalescer import coalesce_future
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date
from app.utils.helpers.html_helpers import first_attr

_HOUSE_ACTORS = ['Rocco Siffredi', 'Peter North']
_SEARCH_DISABLED = {'Tera Patrick'}

_ACTOR_SEL = (
    '//div[contains(@class,"sceneCol") and contains(@class,"sceneColActors")]//a'
    ' | //div[contains(@class,"sceneCol") and contains(@class,"sceneActors")]//a'
    ' | //div[contains(@class,"pornstarNameBox")]//a[contains(@class,"pornstarName")]'
    ' | //div[@id="slick_DVDInfoActorCarousel"]//a'
    ' | //div[@id="slick_sceneInfoPlayerActorCarousel"]//a'
)
_GENRE_SEL = (
    '//div[contains(@class,"sceneCol") and contains(@class,"sceneColCategories")]//a'
    ' | //div[contains(@class,"sceneCategories")]//a'
    ' | //p[contains(@class,"dvdCol")]//a'
)
_PIC_PREVIEW_RE = re.compile(r'"picPreview"\s*:\s*"([^"]+)"')
_DATE_PUBLISHED_RE = re.compile(r'"datePublished"\s*:\s*"([^"]+)"')
_SCENE_ACTORS_RE = re.compile(r'"sceneActors"\s*:\s*(\[[^\]]*\])')
_ACTOR_PAIR_RE = re.compile(r'"actorId"\s*:\s*"?([^",}\s]+)"?[\s\S]*?"actorName"\s*:\s*"([^"]+)"')
_BR_RE = re.compile(r'<\s*/?\s*br\s*/?\s*>', re.IGNORECASE)


class GammaEntClient(Client):
    # ── Search ────────────────────────────────────────────────────────────────

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        if ctx.site_info.name in _SEARCH_DISABLED:
            return
        base = ctx.site_info.base_url.rstrip('/')
        encoded = ctx.encoded.replace('%27', '').replace('%3F', '').replace('%2C', '')
        search_base = base + ctx.site_info.search_path

        def harvest(sel: Any) -> list[dict[str, str]]:
            out: list[dict[str, str]] = []
            for row in sel.xpath('//div[contains(@class,"tlcDetails")]'):
                a = row.xpath('(.//a)[1]')
                href = first_attr(a, '@href')
                if not href:
                    continue
                title = first_attr(a).replace('BONUS-', 'BONUS - ').replace('BTS-', 'BTS - ')
                date_raw = (
                    row.xpath('(.//div[contains(@class,"tlcSpecs")]//span[contains(@class,"tlcSpecsDate")]//span[contains(@class,"tlcDetailsValue")])[1]')
                    .xpath('string(.)')
                    .get()
                    or ''
                ).strip()
                out.append({'title': title, 'scene_url': absolute_url(href, ctx.site_info.base_url), 'date_raw': date_raw})
            return out

        page1 = await self.fetch_and_load(f'{search_base}{encoded}', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search')
        rows1 = harvest(page1['sel']) if page1 else []
        page2 = await self.fetch_and_load(f'{search_base}{encoded}/2', FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search p2')
        rows2 = harvest(page2['sel']) if page2 else []
        if rows2 and rows1 and rows2[0]['scene_url'] == rows1[0]['scene_url']:
            rows2 = []

        seen: set[str] = set()
        for row in [*rows1, *rows2]:
            if not row['title'] or row['scene_url'] in seen:
                continue
            seen.add(row['scene_url'])
            date_iso = iso_date(row['date_raw']) if row['date_raw'] else None
            if not date_iso:
                d = await self.fetch_and_load(row['scene_url'], FetchCtx(capture=ctx.capture), f'GET {row["scene_url"]} (date)')
                raw = (d['sel'].xpath('(//*[contains(@class,"updatedDate")])[1]').xpath('string(.)').get() or '').strip() if d else ''
                if raw:
                    date_iso = iso_date(raw)
            results.append(
                build_search_result(title=row['title'], scene_url=row['scene_url'], query=ctx.title, display_date=date_iso, search_date=ctx.search_date)
            )

    # ── Detail ──────────────────────────────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        scene = await super().load_scene_context(payload, site, ctx)
        if scene:
            scene.extra = {}
        return scene

    def _tagline_of(self, scene: LoadedScene) -> str:
        sel = scene.require_sel()
        return (sel.xpath('(//div[contains(@class,"studioLink")])[1]').xpath('string(.)').get() or '').strip() or scene.site.name

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        title = (
            first_attr(sel, '(//meta[@name="twitter:title"])[1]/@content')
            or (sel.xpath('(//h3[contains(@class,"dvdTitle")])[1]').xpath('string(.)').get() or '').strip()
            or (sel.xpath('(//h1[contains(@class,"sceneTitle")])[1]').xpath('string(.)').get() or '').strip()
            or (sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        )
        page_title = (sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        if 'Scene #' in page_title and 'Scene #' not in title:
            a = page_title.find('Scene') + 6
            o = page_title.find(' ', a)
            scene_num = (page_title[a:o] if o >= 0 else page_title[a:]).strip()
            title = f'{title} - Scene {scene_num}'.replace('#0', '').replace('#', '')
        if 'BONUS' in title or 'BTS' in title:
            names = [a.name for a in await self._resolve_actors_cached(scene) if a.name not in _HOUSE_ACTORS]
            if names:
                title = f'{title} - {", ".join(names)}'
        metadata.title = title.replace('BONUS-', 'BONUS - ').replace('BTS-', 'BTS - ').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        summary = first_attr(sel, '(//meta[@name="twitter:description"])[1]/@content')
        if not summary:
            show_more = (
                sel.xpath('(//div[contains(@class,"sceneDesc") and contains(@class,"bioToRight") and contains(@class,"showMore")])[1]').xpath('string(.)').get()
                or ''
            ).strip()
            if show_more:
                summary = show_more[20:]
            else:
                summary = (sel.xpath('(//div[contains(@class,"sceneDescText")])[1]').xpath('string(.)').get() or '').strip() or (
                    sel.xpath('(//p[contains(@class,"descriptionText")])[1]').xpath('string(.)').get() or ''
                ).strip()
        metadata.summary = _BR_RE.sub('\n', summary).strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = scene.site.sub_group or scene.site.name

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_of(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_of(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        updated = (sel.xpath('(//*[contains(@class,"updatedDate")])[1]').xpath('string(.)').get() or '').replace('|', '').strip()
        if updated and iso_date(updated):
            metadata.release_date = iso_date(updated)
            return
        updated_on = (sel.xpath('(//*[contains(@class,"updatedOn")])[1]').xpath('string(.)').get() or '').strip()
        if updated_on and iso_date(updated_on[8:].strip()):
            metadata.release_date = iso_date(updated_on[8:].strip())
            return
        m = _DATE_PUBLISHED_RE.search(scene.html or '')
        if m and iso_date(m.group(1)):
            metadata.release_date = iso_date(m.group(1))
            return
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        genres = [g for g in (first_attr(a, 'normalize-space(.)').lower() for a in sel.xpath(_GENRE_SEL)) if g]
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        actors = await self._resolve_actors_cached(scene)
        metadata.actors = actors or []

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        directors = [
            ActorResult(name=n)
            for n in (
                first_attr(a, 'normalize-space(.)')
                for a in sel.xpath(
                    '//div[contains(@class,"sceneCol") and contains(@class,"sceneColDirectors")]//a | //ul[contains(@class,"directedBy")]//li//a'
                )
            )
            if n
        ]
        metadata.directors = directors or None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        sel = scene.require_sel()
        base = scene.site.base_url
        coll = self.image_collector(lambda u: absolute_url(u, base))

        coll['push'](sel.xpath('(//meta[@name="twitter:image"])[1]/@content').get())
        pic = _PIC_PREVIEW_RE.search(scene.html or '')
        if pic:
            coll['push'](pic.group(1).replace('\\', ''))
        coll['push'](sel.xpath('(//img[contains(@class,"sceneImage")])[1]/@src').get())

        photo_href = first_attr(sel, '(//a[contains(@class,"GA_Track_Action_Pictures")])[1]/@href')
        if photo_href:
            photo = await self.fetch_and_load(absolute_url(photo_href, base), None, 'photo page')
            if photo:
                coll['push'](photo['sel'].xpath('(//div[contains(@class,"previewImage")]//img)[1]/@src').get())
                for h in photo['sel'].xpath('//a[contains(@class,"imgLink")]/@href').getall():
                    coll['push'](h)

        if '/movie/' in scene.url:
            coll['push'](sel.xpath('(//a[contains(@class,"frontCoverImg")])[1]/@href').get())
            coll['push'](sel.xpath('(//a[contains(@class,"backCoverImg")])[1]/@href').get())
            xpaths = (
                '//img[contains(@class,"tlcImageItem") and contains(@class,"img")]/@src',
                '//img[contains(@class,"img") and contains(@class,"lazy")]/@data-original',
            )
            for xpath in xpaths:
                for raw in sel.xpath(xpath).getall():
                    coll['push'](raw)
        metadata.art = coll['list'] or []

    # ── Internals ─────────────────────────────────────────────────────────────

    def _resolve_actors_cached(self, scene: LoadedScene) -> asyncio.Future[list[ActorResult]]:
        cache: dict[str, Any] = scene.extra if isinstance(scene.extra, dict) else {}
        scene.extra = cache
        return coalesce_future(cache, 'actor_task', lambda: self._resolve_actors(scene))

    async def _resolve_actors(self, scene: LoadedScene) -> list[ActorResult]:
        sel = scene.require_sel()
        base = scene.site.base_url

        def extract_photo(sel: Selector) -> str:
            raw = (
                sel.xpath('(//img[contains(@class,"actorPicture")])[1]/@src').get()
                or sel.xpath('(//span[contains(@class,"removeAvatarParent")]//img)[1]/@src').get()
                or ''
            ).strip()
            return absolute_url(raw, base) if raw else ''

        refs: list[tuple[str, str]] = []
        for el in sel.xpath(_ACTOR_SEL):
            name = first_attr(el, 'normalize-space(.)')
            href = first_attr(el, '@href')
            if name and href:
                refs.append((name, href))

        if not refs:
            mobile = await self.fetch_and_load(scene.url.replace('www', 'm'), None, 'mobile page')
            if mobile:
                for el in mobile['sel'].xpath('//a[contains(@class,"pornstarName")] | //a[contains(@class,"pornstarImageLink")]'):
                    name = first_attr(el, 'normalize-space(.)')
                    href = first_attr(el, '@href')
                    if name and href:
                        refs.append((name, href))

        if not refs:
            arr = _SCENE_ACTORS_RE.search(scene.html or '')
            if arr:
                for m in _ACTOR_PAIR_RE.finditer(arr.group(1)):
                    actor_id, name = m.group(1).strip(), m.group(2).strip()
                    refs.append((name, f'/en/pornstar/{name.replace(" ", "-")}/{actor_id}'))

        refs = [(name, absolute_url(href, base)) for name, href in refs]
        return await self.resolve_actor_photos(refs, extract_photo)
