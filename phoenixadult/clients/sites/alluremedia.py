from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from parsel import Selector

from phoenixadult.clients.base import Client, FetchCtx, LoadedScene
from phoenixadult.models.scrape import ActorResult, SceneDetail, SearchContext, SearchResult
from phoenixadult.registry import ResolvedSiteInfo
from phoenixadult.utils.helpers.helpers import absolute_url, build_search_result, decensor, iso_date, join_url, load_data, pack_cur_id
from phoenixadult.utils.helpers.html_helpers import first_attr, script_match

STUDIO = 'Allure Media'
_TABLES: dict[str, Any] = load_data(__file__, 'alluremedia_tables')
_CENSORED: dict[str, str] = _TABLES['censoredWords']
_SCENE_ACTORS: list[str] = _TABLES['sceneActors']

_USEIMAGE_RE = re.compile(r'useimage\s*=\s*"([^"]+)"')
_SETID_RE = re.compile(r'setid:\s*"([^"]+)"')
_GALLERY_RE = re.compile(r'(.*/contentthumbs/)(\d+)/(\d+)/(\d+)-\d+x\.jpg', re.IGNORECASE)


def _search_url_for(site: ResolvedSiteInfo, query: str) -> str:
    return site.search_url(quote(query))


def _ptx_srcs(script: str, key: str) -> list[str]:
    return re.findall(rf'ptx\["{key}"\]\[\d+\]\s*=\s*\{{[^}}]*?src:\s*"([^"]+)"', script)


class AllureMediaClient(Client):
    title_xpath = '(//title)[1]'
    summary_xpath = '(//span[contains(@class,"update_description")])[1]'

    async def search(self, results: list[SearchResult], search_data: SearchContext) -> None:
        search_url = _search_url_for(search_data.site_info, search_data.title)
        search_results = await self.fetch_and_load(
            search_url, FetchCtx(capture=search_data.capture), f'[{search_data.site_info.name}] search "{search_data.title}"'
        )
        if not search_results:
            return

        swallow_salon = search_data.site_info.name == 'Swallow Salon'
        for search_result in search_results['sel'].xpath('//div[contains(@class,"update_details")]'):
            if swallow_salon:
                anchor = search_result.xpath('(.//a)[2]')
                title = first_attr(anchor)
                href = first_attr(anchor, '@href')
            else:
                title = (search_result.xpath('(.//div[contains(@class,"update_title")]//a)[1]').xpath('string(.)').get() or '').strip()
                href = first_attr(search_result, '(.//a)[1]/@href')

            if not title or not href:
                continue

            raw_date = (search_result.xpath('(.//div[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').split(':')[-1].strip()
            date = iso_date(raw_date, '%m/%d/%Y') if raw_date else None
            scene_url = absolute_url(href, search_data.site_info.base_url)

            results.append(
                build_search_result(
                    site=search_data.site_info,
                    title=title,
                    scene_url=scene_url,
                    query=search_data.title,
                    display_date=date,
                    search_date=search_data.search_date,
                    cur_id=pack_cur_id([scene_url]),
                )
            )

    # ── Update Field Hooks ────────────────────────────────────────────────────

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = scene.site.name

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        date = (details_page_elements.xpath('(//div[contains(@class,"update_date")])[1]').xpath('string(.)').get() or '').strip()

        metadata.release_date = iso_date(date) or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        genres: list[str] = []
        for genre_link in details_page_elements.xpath('//span[contains(@class,"update_tags")]//a'):
            genre_name = decensor(first_attr(genre_link), _CENSORED).lower()
            if genre_name and genre_name not in genres:
                genres.append(genre_name)

        if 'Amateur' not in genres:
            genres.append('Amateur')

        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url
        title = (details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()
        summary = (details_page_elements.xpath('(//span[contains(@class,"update_description")])[1]').xpath('string(.)').get() or '').strip()

        def extract_photo(sel: Selector) -> str:
            img = first_attr(sel, '(//div[contains(@class,"cell_top") and contains(@class,"cell_thumb")]//img)[1]/@src')
            return absolute_url(img, base) if img else ''

        refs: list[tuple[str, str]] = []
        for actor_link in details_page_elements.xpath('//div[contains(@class,"backgroundcolor_info")]//span[contains(@class,"update_models")]//a'):
            actor_name = first_attr(actor_link)
            href = first_attr(actor_link, '@href')
            if actor_name:
                refs.append((actor_name, absolute_url(href, base) if href else ''))

        resolved = await self.resolve_actor_photos(refs, extract_photo, capture=scene.capture, label=scene.site.name)
        actors = [ActorResult(name=a.name, photo_url=a.photo_url.replace('1x', '3x')) for a in resolved]
        seen = {a.name for a in actors}

        for actor_name in _SCENE_ACTORS:
            if (actor_name in title or actor_name in summary) and actor_name not in seen:
                seen.add(actor_name)
                actors.append(ActorResult(name=actor_name))

        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        details_page_elements = scene.require_sel()

        base = scene.site.base_url.rstrip('/')
        images = self.image_collector(lambda image: join_url(image, base))
        title = (details_page_elements.xpath('(//title)[1]').xpath('string(.)').get() or '').strip()

        df_script = details_page_elements.xpath('//script[contains(.,"df_movie")]').xpath('string(.)').get() or ''
        images.push(script_match(df_script, _USEIMAGE_RE))

        set_id = script_match(df_script, _SETID_RE)
        if set_id:
            search_results = await self.fetch_and_load(
                _search_url_for(scene.site, title), FetchCtx(capture=scene.capture), f'[{scene.site.name}] set-target lookup'
            )
            if search_results:
                node = search_results['sel'].xpath(f'(//*[@id="set-target-{set_id}"])[1]')
                images.push(node.xpath('@src').get() or '')
                for i in range(7):
                    images.push(node.xpath(f'@src{i}_1x').get() or '')

        thumbs: list[str] = []
        for selector, attrs in (
            ('//div[contains(@class,"photo_gallery_block")]//img', ('src',)),
            ('//div[contains(@class,"columns") and contains(@class,"mb")]//img', ('src0_2x', 'src')),
        ):
            for row in details_page_elements.xpath(selector):
                src = next((v for a in attrs if (v := row.xpath(f'@{a}').get())), '')
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
                images.push(f'{path_prefix}{xx}/{nn}/{id_prefix}{xx}{nn}-3x.jpg')

        photos_href = ''
        for a in details_page_elements.xpath('//div[contains(@class,"cell") and contains(@class,"content_tab")]//a'):
            if first_attr(a) == 'Photos':
                photos_href = first_attr(a, '@href')
                break

        photos_url = (absolute_url(photos_href, scene.site.base_url)) if photos_href else ''
        metadata.art_referer = photos_url or scene.url

        if photos_url:
            photos_page_elements = await self.fetch_and_load(photos_url, FetchCtx(capture=scene.capture), f'[{scene.site.name}] photos page')
            if photos_page_elements:
                ptx = photos_page_elements['sel'].xpath('//script[contains(.,"var ptx")]').xpath('string(.)').get() or ''
                for u in _ptx_srcs(ptx, '1600'):
                    images.push(u)

                for u in _ptx_srcs(ptx, 'jpg'):
                    images.push(u)

        metadata.art = images.items
