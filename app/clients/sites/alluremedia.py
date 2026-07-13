from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, decensor, iso_date, join_url, load_site_json, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Allure Media'
_TABLES: dict[str, Any] = load_site_json(__file__, 'alluremedia_tables')
_CENSORED: dict[str, str] = _TABLES['censoredWords']
_SCENE_ACTORS: list[str] = _TABLES['sceneActors']

_USEIMAGE_RE = re.compile(r'useimage\s*=\s*"([^"]+)"')
_SETID_RE = re.compile(r'setid:\s*"([^"]+)"')
_GALLERY_RE = re.compile(r'(.*/contentthumbs/)(\d+)/(\d+)/(\d+)-\d+x\.jpg', re.IGNORECASE)


def _search_url_for(site: ResolvedSiteInfo, query: str) -> str:
    return site.base_url.rstrip('/') + site.search_path.replace('{query}', quote(query))


def _ptx_srcs(script: str, key: str) -> list[str]:
    return re.findall(rf'ptx\["{key}"\]\[\d+\]\s*=\s*\{{[^}}]*?src:\s*"([^"]+)"', script)


class AllureMediaClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        search_url = _search_url_for(ctx.site_info, ctx.title)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search "{ctx.title}"')
        if not loaded:
            return

        swallow_salon = ctx.site_info.name == 'Swallow Salon'
        for card in loaded['sel'].xpath('//div[contains(@class,"update_details")]'):
            if swallow_salon:
                anchor = card.xpath('(.//a)[2]')
                title = first_attr(anchor)
                href = first_attr(anchor, '@href')
            else:
                title = (card.xpath('(.//div[contains(@class,"update_title")]//a)[1]').xpath('string(.)').get() or '').strip()
                href = first_attr(card, '(.//a)[1]/@href')
            if not title or not href:
                continue
            raw_date = (card.xpath('(.//div[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').split(':')[-1].strip()
            date = iso_date(raw_date, '%m/%d/%Y') if raw_date else None
            scene_url = absolute_url(href, ctx.site_info.base_url)
            results.append(
                build_search_result(
                    title=title, scene_url=scene_url, query=ctx.title, display_date=date, search_date=ctx.search_date, cur_id=pack_cur_id([scene_url])
                )
            )

    # ── Detail field hooks ────────────────────────────────────────────────────

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = (scene.sel.xpath('(//span[contains(@class,"update_description")])[1]').xpath('string(.)').get() or '').strip() or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//div[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()
        metadata.release_date = iso_date(raw) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for el in scene.sel.xpath('//span[contains(@class,"update_tags")]//a'):
            g = decensor(first_attr(el), _CENSORED).lower()
            if g and g not in genres:
                genres.append(g)
        if 'Amateur' not in genres:
            genres.append('Amateur')
        metadata.genres = genres or []

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        title = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        summary = (scene.sel.xpath('(//span[contains(@class,"update_description")])[1]').xpath('string(.)').get() or '').strip()

        actors: list[ActorResult] = []
        seen: set[str] = set()
        for el in scene.sel.xpath('//div[contains(@class,"backgroundcolor_info")]//span[contains(@class,"update_models")]//a'):
            name = first_attr(el)
            href = first_attr(el, '@href')
            if not name or name in seen:
                continue
            seen.add(name)
            photo = ''
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), FetchCtx(capture=scene.capture), f'[{scene.site.name}] actor {name}')
                img = first_attr(page['sel'], '(//div[contains(@class,"cell_top") and contains(@class,"cell_thumb")]//img)[1]/@src') if page else ''
                photo = (absolute_url(img, base)) if img else ''
            actors.append(ActorResult(name=name, photo_url=photo.replace('1x', '3x')))

        for name in _SCENE_ACTORS:
            if (name in title or name in summary) and name not in seen:
                seen.add(name)
                actors.append(ActorResult(name=name))
        metadata.actors = actors or []

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url.rstrip('/')
        coll = self.image_collector(lambda u: join_url(u, base))
        title = (scene.sel.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()

        df_script = scene.sel.xpath('//script[contains(.,"df_movie")]').xpath('string(.)').get() or ''
        use_image = _USEIMAGE_RE.search(df_script)
        if use_image:
            coll['push'](use_image.group(1))

        set_id = _SETID_RE.search(df_script)
        if set_id:
            search_page = await self.fetch_and_load(
                _search_url_for(scene.site, title), FetchCtx(capture=scene.capture), f'[{scene.site.name}] set-target lookup'
            )
            if search_page:
                node = search_page['sel'].xpath(f'(//*[@id="set-target-{set_id.group(1)}"])[1]')
                coll['push'](node.xpath('@src').get() or '')
                for i in range(7):
                    coll['push'](node.xpath(f'@src{i}_1x').get() or '')

        thumbs: list[str] = []
        for selector, attrs in (
            ('//div[contains(@class,"photo_gallery_block")]//img', ('src',)),
            ('//div[contains(@class,"columns") and contains(@class,"mb")]//img', ('src0_2x', 'src')),
        ):
            for el in scene.sel.xpath(selector):
                src = next((v for a in attrs if (v := el.xpath(f'@{a}').get())), '')
                if src:
                    thumbs.append(src)
        last_thumb = thumbs[-1] if thumbs else ''
        gallery = _GALLERY_RE.match(last_thumb)
        if gallery:
            path_prefix, xx, yy, file_id = gallery.groups()
            id_prefix = file_id[: len(file_id) - (len(xx) + len(yy))]
            count = int(yy)
            for n in range(max(1, count - 20), count + 1):
                nn = str(n).zfill(2)
                coll['push'](f'{path_prefix}{xx}/{nn}/{id_prefix}{xx}{nn}-3x.jpg')

        photos_href = ''
        for a in scene.sel.xpath('//div[contains(@class,"cell") and contains(@class,"content_tab")]//a'):
            if first_attr(a) == 'Photos':
                photos_href = first_attr(a, '@href')
                break
        photos_url = (absolute_url(photos_href, scene.site.base_url)) if photos_href else ''
        metadata.raw_image_referer = photos_url or scene.url

        if photos_url:
            photos_page = await self.fetch_and_load(photos_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] photos page')
            if photos_page:
                ptx = photos_page['sel'].xpath('//script[contains(.,"var ptx")]').xpath('string(.)').get() or ''
                for u in _ptx_srcs(ptx, '1600'):
                    coll['push'](u)
                for u in _ptx_srcs(ptx, 'jpg'):
                    coll['push'](u)

        images: list[str] = coll['list']
        metadata.art = images or []
