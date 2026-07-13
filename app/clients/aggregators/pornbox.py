from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, LoadedScene, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id
from app.utils.processors.title_case import collapse_initial_pairs, expand_initial_pairs, title_case

_MATCH_ID_RE = re.compile(r'(\w+\d)$')
_TAG_RE = re.compile(r'<[^>]*>')


def _clean_summary(summary: str) -> str:
    """Pornbox summaries arrive shouting; lower-case then rebuild sentence casing
    (the legacy bundle's PAutils.cleanSummary)."""
    s = summary.lower().capitalize()
    s = s.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'").replace('\xa0', ' ')
    s = re.sub(r'(?i)(?<![A-Za-z])W/', 'w/', s)
    s = re.sub(r'(?i)([!:?.])(?=\w)(?!(?:co|net|com|org|porn|xxx)\b)(?!E\d)', r'\1 ', s)
    s = re.sub(r"\s+(?=[.,!:')])", '', s)
    s = re.sub(r'(?<=[#(])\s+', '', s)
    s = re.sub(r'(?<!vs\.)([!:?.])(\s)(\S)', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), s)
    s = collapse_initial_pairs(s)
    s = expand_initial_pairs(s)
    if not re.search(r'[!.?]$', s):
        s += '.'
    return s


class PornboxClient(Client):
    async def search(self, results: list[SearchResult], ctx: SearchContext) -> None:
        base = ctx.site_info.base_url.rstrip('/')
        tokens = ctx.title.strip().split()
        source_id = ctx.scene_id or (tokens[0] if tokens and re.fullmatch(r'\d+', tokens[0]) else None)
        seen: set[str] = set()

        def push(scene: dict[str, Any], content_id: Any, score: float | None = None, prefix: str = '') -> None:
            scene_url = f'{base}/contents/{content_id}'
            if scene_url in seen:
                return
            seen.add(scene_url)
            date = iso_date(scene['publish_date']) if scene.get('publish_date') else None
            results.append(
                build_search_result(
                    title=f'{prefix}{scene.get("scene_name") or ""}'.strip(),
                    scene_url=scene_url,
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=score,
                    cur_id=pack_cur_id([p for p in (scene_url, date) if p]),
                )
            )

        if source_id:
            scene = await self.fetch_json(f'{base}/contents/{source_id}', FetchCtx(capture=ctx.capture))
            if isinstance(scene, dict) and scene.get('scene_name'):
                push(scene, source_id, 100)

        body = await self.fetch_json(f'{base}{ctx.site_info.search_path.replace("{query}", ctx.encoded)}', FetchCtx(capture=ctx.capture))
        contents = ((body or {}).get('content') or {}).get('contents') or [] if isinstance(body, dict) else []
        for scene in contents:
            title = scene.get('scene_name') or ''
            prefix = ''
            score: float | None = None
            m = _MATCH_ID_RE.search(title)
            if m:
                match_id = m.group(1)
                title = re.sub(r'\w+\d$', '', title).strip()
                prefix = f'[{match_id}] '
                if tokens and tokens[0].lower() == match_id.lower():
                    score = 100
            if source_id and str(source_id) == str(scene.get('source_id')):
                score = 100
            cid = scene.get('content_id') or ''
            if cid:
                push({**scene, 'scene_name': title}, cid, score, prefix)

    # ── Context loader (JSON detail) ──────────────────────────────────────────

    async def load_scene_context(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> LoadedScene | None:
        url, _, tail = payload.partition('|')
        scene = await self.fetch_json(url, FetchCtx(capture=ctx.capture if ctx else None))
        if not isinstance(scene, dict):
            return None
        return LoadedScene(url=url, site=site, scene_date=tail.strip() or None, capture=ctx.capture if ctx else None, extra=scene)

    def _data(self, scene: LoadedScene) -> dict[str, Any]:
        return scene.extra if isinstance(scene.extra, dict) else {}

    # ── Detail field hooks ────────────────────────────────────────────────────

    def _tagline(self, scene: LoadedScene) -> str | None:
        raw = (self._data(scene).get('studio') or '').strip()
        return title_case(raw) if raw else None

    async def fetch_title(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.title = (self._data(scene).get('scene_name') or '').strip() or ''

    async def fetch_summary(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        raw = self._data(scene).get('small_description')
        if not raw:
            return
        stripped = _TAG_RE.sub('', raw).strip()
        metadata.summary = _clean_summary(stripped) if stripped else ''

    async def fetch_studio(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.studio = 'Pornbox'

    async def fetch_tagline(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        metadata.tagline = self._tagline(scene)

    async def fetch_collections(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene)
        metadata.collections = [tagline] if tagline else None

    async def fetch_release_date(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        raw = self._data(scene).get('publish_date')
        metadata.release_date = (iso_date(raw) if raw else None) or scene.scene_date or None

    async def fetch_genres(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        values: list[str | None] = [n.get('niche') for n in (self._data(scene).get('niches') or [])]
        metadata.genres = self.dedup_strings(values)

    async def fetch_actors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        base = scene.site.base_url.rstrip('/')
        data = self._data(scene)
        models = [*(data.get('models') or []), *(data.get('male_models') or [])]
        actors: list[ActorResult] = []
        for m in models:
            name = (m.get('model_name') or '').strip()
            if not name:
                continue
            photo = ''
            if m.get('model_id') is not None:
                info = await self.fetch_json(f'{base}/model/info/{m["model_id"]}', FetchCtx(capture=scene.capture))
                if isinstance(info, dict) and info.get('headshot'):
                    photo = info['headshot']
            actors.append(ActorResult(name=name, photo_url=photo))
        metadata.actors = actors

    async def fetch_directors(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        tagline = self._tagline(scene) or ''
        if tagline == 'Giorgio Grandi' or "Giorgio's Lab" in tagline:
            metadata.directors = [ActorResult(name='Giorgio Grandi')]

    async def fetch_image_urls(self, scene: LoadedScene, metadata: SceneDetail) -> None:
        data = self._data(scene)
        coll = self.image_collector()
        if data.get('player_poster'):
            coll['push'](data['player_poster'])
        shots = data.get('screenshots') or []
        for x in range(1, len(shots)):
            if len(shots) > 50 and x % 10 != 0:
                continue
            coll['push'](shots[x].get('xga_size'))
        metadata.raw_image_urls = coll['list']
