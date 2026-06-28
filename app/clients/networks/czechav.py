from __future__ import annotations

import re
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SearchContext, SearchResult
from app.utils.helpers.helpers import absolute_url, build_search_result, iso_date, title_distance_score
from app.utils.helpers.html_helpers import first_attr, first_string

STUDIO = 'Czech Authentic Videos'
_CASTING_HOST = 'czechcasting.com'
_TRAILING_ID_RE = re.compile(r'-(\d+)$')


class CzechAVClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        slug = quote(ctx.title.strip(), safe='')
        search_url = base + ctx.site_info.search_path.replace('{query}', slug)
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] search {search_url}')
        if not loaded:
            return []

        results: list[SearchResult] = []
        for card in loaded['sel'].xpath('//*[contains(@class,"search-item")][.//h2]'):
            a = card.xpath('(.//a[.//h2])[1]')
            title = first_string(a)
            href = first_attr(a, '@href')
            if not title or not href:
                continue
            scene_url = absolute_url(href, ctx.site_info.base_url)
            thumb = first_attr(card, '(.//img)[1]/@src')

            m = _TRAILING_ID_RE.search(scene_url.rstrip('/'))
            search_id = int(m.group(1)) if m else 0
            if ctx.scene_id and ctx.scene_id.isdigit() and int(ctx.scene_id) == search_id:
                score: float = 80
            else:
                score = title_distance_score(ctx.title, title)

            results.append(
                build_search_result(title=title, scene_url=scene_url, query=ctx.title, search_date=ctx.search_date, score=score, thumb_url=thumb or None)
            )
        return results

    # ── Detail field hooks ────────────────────────────────────────────────────

    @staticmethod
    def _is_casting(scene: LoadedScene) -> bool:
        return _CASTING_HOST in scene.site.base_url

    async def fetch_title(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        raw = (scene.sel.xpath('(//h1)[1]').xpath('string(.)').get() or '').strip()
        return raw.split(':')[-1].strip() or None

    async def fetch_summary(self, scene: LoadedScene) -> str | None:
        assert scene.sel is not None
        ps = scene.sel.xpath('//div[contains(@class,"read-more")]//p')
        if not ps:
            return None
        second = first_string(ps[1]) if len(ps) > 1 else ''
        first = first_string(ps[0])
        return second or first or None

    async def fetch_studio(self, scene: LoadedScene) -> str | None:
        return STUDIO

    async def fetch_tagline(self, scene: LoadedScene) -> str | None:
        return scene.site.name

    async def fetch_collections(self, scene: LoadedScene) -> list[str] | None:
        return [scene.site.name]

    async def fetch_release_date(self, scene: LoadedScene) -> str | None:
        return (iso_date(scene.scene_date) or scene.scene_date) if scene.scene_date else None

    async def fetch_genres(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        values: list[str | None] = [
            el.xpath('string(.)').get() or '' for el in scene.sel.xpath('//ul[contains(@class,"tags")]//li | //ul//li[contains(@class,"tag")]')
        ]
        return self.dedup_strings(values) or None

    async def fetch_actors(self, scene: LoadedScene) -> list[ActorResult] | None:
        assert scene.sel is not None
        if not self._is_casting(scene):
            return None
        name = (scene.sel.xpath('(//span[@class="name"])[1]').xpath('string(.)').get() or '').strip()
        if not name:
            return None
        age = (scene.sel.xpath('(//span[@class="age"])[1]').xpath('string(.)').get() or '').strip()
        full_name = f'{name} {age}' if age else name
        photo = first_attr(scene.sel, '(//div[contains(@class,"gallery")]//a)[1]/@href')
        return [ActorResult(name=full_name, photo_url=photo)]

    async def fetch_image_urls(self, scene: LoadedScene) -> list[str] | None:
        assert scene.sel is not None
        base = scene.site.base_url
        coll = self.image_collector(lambda raw: absolute_url(raw, base))
        xpaths = (
            '//meta[@property="og:image"]/@content',
            '//img[contains(@class,"thumb")]/@src',
        )
        for xpath in xpaths:
            for raw in scene.sel.xpath(xpath).getall():
                coll['push'](raw)
        images: list[str] = coll['list']
        return images or None
