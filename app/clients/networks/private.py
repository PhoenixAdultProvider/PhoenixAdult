from __future__ import annotations

from typing import Any

from parsel import Selector

from app.clients.base import ActorResult, Client, LoadedScene, RawCaptureEntry, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, pack_cur_id
from app.utils.helpers.html_helpers import first_attr

STUDIO = 'Private'
_SUPPORTED_LANGS = {'en', 'de', 'fr', 'es', 'nl'}


def _lang_headers(language: str | None) -> dict[str, str]:
    primary = (language or '').lower().split('-')[0]
    return {'Accept-Language': primary} if primary in _SUPPORTED_LANGS else {}


class PrivateClient(Client):
    async def _fetch_localized(self, url: str, language: str | None, capture: list[RawCaptureEntry] | None, label: str) -> dict[str, Any] | None:
        try:
            r = await self.http.get(url, headers=_lang_headers(language))
        except Exception:  # noqa: BLE001 - network failure yields no page
            return None
        if r.status_code >= 400:
            return None
        if capture is not None:
            capture.append(RawCaptureEntry(label, 'html', r.text))
        return {'sel': Selector(text=r.text), 'html': r.text}

    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        search_url = base + ctx.site_info.search_path.replace('{query}', ctx.encoded)
        loaded = await self._fetch_localized(search_url, ctx.language, ctx.capture, f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return

        for card in loaded['sel'].xpath('//ul[@id="search_results"]//li[@class="card"]'):
            anchor = card.xpath('(.//h3/a)[1]')
            title = first_attr(anchor)
            href = first_attr(anchor, '@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            date = iso_date((card.xpath('(.//span[@class="scene-date"])[1]').xpath('string(.)').get() or '').strip())
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

    # ── Context loader (localized detail fetch) ─────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        pipe = payload.find('|')
        url = payload[:pipe] if pipe >= 0 else payload
        fallback = payload[pipe + 1 :].strip() if pipe >= 0 else None
        language = ctx.language if ctx else None
        loaded = await self._fetch_localized(url, language, ctx.capture if ctx else None, f'GET {url}')
        if not loaded:
            return None
        return LoadedScene(
            url=url,
            site=site,
            scene_date=fallback or None,
            capture=ctx.capture if ctx else None,
            sel=loaded['sel'],
            html=loaded['html'],
            extra={'language': language},
        )

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline_for(self, scene: LoadedScene) -> str:
        assert scene.sel is not None
        return (scene.sel.xpath('(//li[@class="tag-sites"]//a)[1]').xpath('string(.)').get() or '').strip() or scene.site.name

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.title = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        metadata.summary = first_attr(scene.sel, '(//meta[@itemprop="description"])[1]/@content') or ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = STUDIO

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline_for(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.collections = [self._tagline_for(scene)]

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        raw = first_attr(scene.sel, '(//meta[@itemprop="uploadDate"])[1]/@content')
        metadata.release_date = (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        genres: list[str] = []
        for a in scene.sel.xpath('//li[@class="tag-tags"]//a'):
            g = first_attr(a, 'normalize-space(.)').lower()
            if g and g not in genres:
                genres.append(g)
        metadata.genres = genres

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        base = scene.site.base_url
        actors: list[ActorResult] = []
        for el in scene.sel.xpath('//li[@class="tag-models"]//a'):
            name = first_attr(el, 'normalize-space(.)')
            if not name:
                continue
            photo = ''
            href = first_attr(el, '@href')
            if href:
                page = await self.fetch_and_load(absolute_url(href, base), None, f'GET {href} (actor)')
                srcset = (page['sel'].xpath('(//img[@srcset])[1]/@srcset').get() or '') if page else ''
                last = srcset.split(',')[-1].strip() if srcset else ''
                if last:
                    photo = last.split()[0]
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        assert scene.sel is not None
        coll = self.image_collector()
        coll['push'](scene.sel.xpath('(//meta[@itemprop="thumbnailUrl"])[1]/@content').get())

        scene_id = next((s for s in reversed(scene.url.split('/')) if s), '')
        if scene_id:
            base = scene.site.base_url.rstrip('/')
            gallery_url = f'{base}/gallery.php?type=highres&id={scene_id}&langx=en'
            language = (scene.extra or {}).get('language')
            gallery = await self._fetch_localized(gallery_url, language, scene.capture, f'GET {gallery_url} (gallery)')
            if gallery:
                for href in gallery['sel'].xpath('//a/@href').getall():
                    coll['push'](href)

        content_url = first_attr(scene.sel, '(//meta[@itemprop="contentURL"])[1]/@content')
        j = content_url.rfind('upload/')
        k = content_url.rfind('trailers/')
        if j >= 0 and k >= 0:
            watermark_id = (content_url[j + 7 : k - 1].split('/')[-1] or '').lower()
            prefix = content_url[:k] + 'Fullwatermarked/'
            for i in range(1, 10):
                n = f'{i * 5:03d}'
                coll['push'](f'{prefix}{watermark_id}_{n}.jpg'.replace('pcoms', 'pcom'))

        images: list[str] = coll['list']
        metadata.raw_image_urls = images
