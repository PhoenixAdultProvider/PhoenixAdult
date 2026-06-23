from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.clients.base import ActorResult, Client, FetchCtx, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id

STUDIO = 'Clips4Sale'
_DATA = Path(__file__).parent / '_data' / 'json'
_STUDIOS: list[dict[str, Any]] = json.loads((_DATA / 'clips4sale_studios.json').read_text(encoding='utf-8'))
_REMIX_RE = re.compile(r'window\.__remixContext\s*=\s*(\{.*?\});', re.DOTALL)

_FILE_TYPES = ['mp4', 'wmv', 'avi']
_QUALITIES = ['standard', 'hd', '720p', '1080p', '4k']
_FORMAT_TEMPLATES = [
    '(%(quality)s - %(quality)s)',
    '(%(quality)s %(fileType)s)',
    '%(quality)s %(fileType)s',
    '- %(quality)s;',
    '(.%(fileType)s)',
    '(%(quality)s)',
    '(%(fileType)s)',
    '.%(fileType)s',
    '%(quality)s',
    '%(fileType)s',
]


def _clean_title(title: str) -> str:
    out = title
    for f in _FORMAT_TEMPLATES:
        for q in _QUALITIES:
            for t in _FILE_TYPES:
                for qf in (q.lower(), q.upper()):
                    for tf in (t.lower(), t.upper()):
                        out = ''.join(out.split(f.replace('%(quality)s', qf).replace('%(fileType)s', tf)))
    return out.strip()


def _remix_context(html: str) -> Any:
    m = _REMIX_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (ValueError, TypeError):
        return None


def _clip_from_context(ctx: Any) -> dict[str, Any] | None:
    routes = (ctx or {}).get('state', {}).get('loaderData') if isinstance(ctx, dict) else None
    if not isinstance(routes, dict):
        return None
    clip_route = routes.get('routes/($lang).studio.$id_.$clipId.$clipSlug')
    clip = clip_route.get('clip') if isinstance(clip_route, dict) else None
    return clip if isinstance(clip, dict) else None


def _apply_rules(user_id: str, tagline: str, title: str, summary: str, genre_list: list[str], keywords: list[str]) -> dict[str, Any]:
    seen: set[str] = set()
    actors: list[str] = []

    def add_actor(name: str) -> None:
        n = name.strip()
        if n and n not in seen:
            seen.add(n)
            actors.append(n)

    genres = list(genre_list)
    tagline_override: str | None = None
    matched = False

    for rule in _STUDIOS:
        hit_user = rule.get('userID') and rule['userID'] in user_id
        hit_tag = rule.get('tagline') and rule['tagline'] in tagline
        if not hit_user and not hit_tag:
            continue
        matched = True

        if rule.get('dropFirstGenre') and genres:
            genres = genres[1:]

        if rule.get('allKeywordsAsActors'):
            for k in keywords:
                add_actor(k)
                genres = [g for g in genres if g != k.lower()]
        for n in rule.get('alwaysActors', []):
            add_actor(n)
        for g in rule.get('fixedGenres', []):
            if g not in genres:
                genres.append(g)

        # genreActors: each matched genre token is also removed from the list.
        for actor, needles in (rule.get('genreActors') or {}).items():
            for token in needles:
                if token.lower() in genres:
                    add_actor(actor)
                    genres = [g for g in genres if g != token.lower()]
        for actor, needles in (rule.get('titleActors') or {}).items():
            if any(needle in title for needle in needles):
                add_actor(actor)
        for actor, needles in (rule.get('summaryActors') or {}).items():
            if any(needle in summary for needle in needles):
                add_actor(actor)

        if rule.get('removeGenres'):
            remove = rule['removeGenres']
            genres = [g for g in genres if g not in remove]

        for rewrite in rule.get('titleRewrites', []):
            try:
                title = re.sub(rewrite['pattern'], rewrite['replacement'], title, flags=re.IGNORECASE if 'i' in rewrite.get('flags', '') else 0)
            except re.error:
                pass

        if rule.get('taglineOverride'):
            tagline_override = rule['taglineOverride']

    if not matched and tagline:
        add_actor(tagline)
        t = tagline.lower()
        genres = [g for g in genres if g != t]

    return {'actors': actors, 'genres': genres, 'title': title, 'tagline_override': tagline_override}


class Clips4SaleClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')
        parts = ctx.title.strip().split()
        if len(parts) < 2:
            return []
        user_id = parts[0]
        rest = ' '.join(parts[1:])
        direct_id = parts[1] if parts[1].isdigit() and int(parts[1]) > 10_000_000 else ''

        if direct_id:
            clip_url = f'{base}{ctx.site_info.search_path}{user_id}/{direct_id}/'
            loaded = await self.fetch_and_load(clip_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] direct clip {direct_id}')
            if not loaded:
                return []
            clip = _clip_from_context(_remix_context(loaded['html']))
            if not clip or not clip.get('title'):
                return []
            date = iso_date((clip.get('dateDisplay') or '').split(' ')[0], '%m/%d/%y')
            return [
                build_search_result(
                    title=_clean_title(clip['title']),
                    scene_url=clip_url,
                    query=rest,
                    display_date=date,
                    search_date=ctx.search_date,
                    score=100,
                    cur_id=pack_cur_id([clip_url]),
                )
            ]

        search_url = f'{base}{ctx.site_info.search_path}{user_id}/{quote(rest)}'
        loaded = await self.fetch_and_load(search_url, FetchCtx(capture=ctx.capture), f'[{ctx.site_info.name}] studio {user_id} "{rest}"')
        if not loaded:
            return []
        remix = _remix_context(loaded['html'])
        loader = (remix or {}).get('state', {}).get('loaderData', {}) if isinstance(remix, dict) else {}
        studio_route = loader.get('routes/($lang).studio.$id_.$studioSlug.$') if isinstance(loader, dict) else None
        clips = studio_route.get('clips', []) if isinstance(studio_route, dict) else []

        results: list[SearchResult] = []
        for c in clips:
            if not c.get('clipId') or not c.get('title'):
                continue
            clip_url = f'{base}{ctx.site_info.search_path}{user_id}/{c["clipId"]}/{c.get("urlSlug") or ""}'
            date = iso_date((c.get('dateDisplay') or '').split(' ')[0], '%m/%d/%y')
            results.append(
                build_search_result(
                    title=_clean_title(c['title']),
                    scene_url=clip_url,
                    query=rest,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([clip_url]),
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        loaded = await self.fetch_and_load(payload, FetchCtx(capture=ctx.capture if ctx else None), f'[{site.name}] detail {payload}')
        if not loaded:
            return None
        clip = _clip_from_context(_remix_context(loaded['html']))
        if not clip or not clip.get('title'):
            return None

        user_id = payload.split('/studio/')[1].split('/')[0] if '/studio/' in payload else ''

        summary = re.sub(r'<[^>]+>', '', clip.get('description') or '').split('--SCREEN SIZE')[0].split('--SREEN SIZE')[0].strip()
        summary = summary.split('window.NREUM')[0].replace('**TOP 50 CLIP**', '').replace('1920x1080 (HD1080)', '').strip()

        genre_list: list[str] = []

        def add(g: str) -> None:
            t = g.strip().lower()
            if t and t not in genre_list:
                genre_list.append(t)

        if clip.get('category_name'):
            add(clip['category_name'])
        for r in clip.get('related_category_links', []):
            add(r.get('category', ''))
        keywords: list[str] = []
        for k in clip.get('keyword_links', []):
            add(k.get('keyword', ''))
            keywords.append((k.get('keyword') or '').strip())

        ruled = _apply_rules(user_id, clip.get('studioTitle') or '', _clean_title(clip['title']), summary, genre_list, keywords)
        actors = [ActorResult(name=n) for n in ruled['actors']]
        release_date = iso_date((clip.get('dateDisplay') or '').split(' ')[0], '%m/%d/%y') or None

        coll = self.image_collector()
        coll['push'](clip.get('preview_screencap_image_path'))
        coll['push'](clip.get('screencap_image_path'))
        clip_id = payload.split('/studio/')[1].split('/')[1] if '/studio/' in payload and len(payload.split('/studio/')[1].split('/')) > 1 else ''
        if user_id and clip_id.isdigit():
            coll['push'](f'http://imagecdn.clips4sale.com/accounts99/{user_id}/clip_images/previewlg_{clip_id}.jpg')

        tagline_override = ruled['tagline_override']
        tagline = tagline_override or clip.get('studioTitle') or None
        collections = [tagline_override] if tagline_override else ([clip['studioTitle']] if clip.get('studioTitle') else None)

        return SceneDetail(
            title=ruled['title'],
            summary=summary,
            studio=STUDIO,
            tagline=tagline,
            collections=collections,
            release_date=release_date,
            genres=ruled['genres'],
            actors=actors,
            raw_image_urls=coll['list'],
            scene_url=payload,
        )
