from __future__ import annotations

import re

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, sceneid_distance_score, strip_query, title_distance_score
from app.utils.helpers.html_helpers import first_attr

_SEARCH_SURFACES = (('Censored', 'search/'), ('Uncensored', 'uncensored/search/'))


def _javbus_id(url: str) -> str:
    return [p for p in strip_query(url).split('/') if p][-1] if [p for p in strip_query(url).split('/') if p] else ''


def _derive_cover_thumb(cover_url: str) -> str:
    filename = cover_url.split('/')[-1]
    code = filename.split('.')[0].split('_')[0] if filename else ''
    if not code:
        return ''
    host = '/'.join(cover_url.split('/')[:-2])
    if not host:
        return ''
    thumb = f'{host}/thumb/{code}.jpg'
    if len(re.findall(r'/images\.', thumb)) == 1:
        thumb = thumb.replace('/thumb/', '/thumbs/')
    return thumb


class JavBusClient(Client):
    def __init__(self) -> None:
        super().__init__({'Cookie': 'existmag=all; dv=1'})

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        parts = ctx.title.strip().split()
        javid = f'{parts[0]}-{parts[1]}' if len(parts) > 1 and re.fullmatch(r'\d+', parts[1]) else None
        encoded = javid or ctx.encoded

        seen: set[str] = set()

        for label, sub in _SEARCH_SURFACES:
            search_url = f'{base}/en/{sub}{encoded}'
            loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'GET {search_url}')
            if not loaded:
                continue
            for el in loaded['sel'].xpath('//a[contains(@class,"movie-box")]'):
                title = re.sub(r'\s+', ' ', ''.join(el.xpath('(.//span)[1]/text()').getall())).strip()
                jav_id = first_attr(el, '(.//date)[1]/text()')
                href = first_attr(el, '@href')
                if not title or not href:
                    continue
                scene_url = absolute_url(href, base)
                if scene_url in seen:
                    continue
                seen.add(scene_url)
                score = sceneid_distance_score(javid.lower(), jav_id.lower()) if javid else title_distance_score(ctx.title.lower(), title.lower())
                results.append(
                    build_search_result(
                        title=f'[{label}][{jav_id}] {title}',
                        scene_url=scene_url,
                        query=ctx.title,
                        search_date=ctx.search_date,
                        score=score,
                        thumb_url=first_attr(el, '(.//img/@src)[1]') or None,
                    )
                )

        if javid:
            direct_url = f'{base}/en/{javid}'
            loaded = await self.fetch_and_load(direct_url, FetchCtx(capture=ctx.capture), f'GET {direct_url} (direct)')
            if loaded and direct_url not in seen:
                jav_title = re.sub(r' - JavBus$', '', first_attr(loaded['sel'], '(//head//title)[1]/text()'))
                if jav_title:
                    seen.add(direct_url)
                    results.append(
                        build_search_result(
                            title=f'[Direct][{javid}] {jav_title}', scene_url=direct_url, query=ctx.title, search_date=ctx.search_date, score=100
                        )
                    )

    # ── Field hooks ───────────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        studio = first_attr(scene.sel, '(//p//a[contains(@href,"/studio/")])[1]/text()')
        jav_title = re.sub(r' - JavBus$', '', first_attr(scene.sel, '(//head//title)[1]/text()'))
        if not jav_title:
            return
        id_digits = re.sub(r'[-_ ]', '', _javbus_id(scene.url))
        if id_digits and re.fullmatch(r'\d+', id_digits):
            metadata.title = f'[{studio}] {jav_title}'.strip()
            return
        sp = jav_title.find(' ')
        jid = jav_title if sp < 0 else jav_title[:sp]
        rest = '' if sp < 0 else jav_title[sp + 1 :]
        metadata.title = f'[{jid}] {rest}'.strip()

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.studio = first_attr(scene.sel, '(//p//a[contains(@href,"/studio/")])[1]/text()') or ''

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        label = first_attr(scene.sel, '(//p//a[contains(@href,"/label/")])[1]/text()')
        if label:
            metadata.tagline = label
            return
        series = first_attr(scene.sel, '(//p//a[contains(@href,"/series/")])[1]/text()')
        metadata.tagline = f'Series: {series}' if series else None

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        label = first_attr(scene.sel, '(//p//a[contains(@href,"/label/")])[1]/text()')
        if label:
            metadata.collections = [label]
            return
        studio = first_attr(scene.sel, '(//p//a[contains(@href,"/studio/")])[1]/text()')
        metadata.collections = [studio] if studio else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = ''
        for p in scene.sel.xpath('//div[contains(@class,"col-md-3") and contains(@class,"info")]//p'):
            t = p.xpath('string(.)').get() or ''
            if re.search(r'Release Date', t, re.IGNORECASE):
                raw = re.sub(r'.*Release Date:\s*', '', t, flags=re.IGNORECASE).strip()
        if raw and raw != '0000-00-00':
            iso = iso_date(raw)
            if iso:
                metadata.release_date = iso
                return
        metadata.release_date = scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.genres = self.dedup_strings(
            [
                (el.xpath('normalize-space(.)').get() or '').lower().strip()
                for el in scene.sel.xpath('//span[contains(@class,"genre")]//a[contains(@href,"/genre/")]')
            ]
        )

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        out: list[ActorResult] = []
        for el in scene.sel.xpath('//a[contains(@class,"avatar-box")]'):
            name = first_attr(el, '(.//img/@title)[1]')
            if not name:
                continue
            photo = first_attr(el, '(.//img/@src)[1]')
            if photo:
                photo = absolute_url(photo, scene.site.base_url)
            if photo.split('/')[-1] == 'nowprinting.gif':
                photo = ''
            out.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = out

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        director = first_attr(scene.sel, '(//p//a[contains(@href,"/director/")])[1]/text()')
        metadata.directors = [ActorResult(name=director)] if director else None

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        out: list[str] = []

        def push(raw: str) -> None:
            if not raw or re.search(r'nowprinting', raw, re.IGNORECASE):
                return
            abs_url = absolute_url(raw, base)
            if abs_url not in out:
                out.append(abs_url)

        for href in scene.sel.xpath('//a[contains(@href,"/cover/")]/@href').getall():
            push(href)
        for href in scene.sel.xpath('//a[contains(@class,"sample-box")]/@href').getall():
            push(href)
        cover_raw = (scene.sel.xpath('(//a[contains(@href,"/cover/")]/@href)[1]').get() or '') or (
            scene.sel.xpath('(//img[contains(@src,"/sample/")]/@src)[1]').get() or ''
        )
        if cover_raw:
            push(_derive_cover_thumb(absolute_url(cover_raw, base)))
        metadata.art = out
