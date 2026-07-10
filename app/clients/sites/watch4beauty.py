from __future__ import annotations

import re
from typing import Any

from app.clients.base import ActorResult, Client, FetchCtx, SceneContext, SceneDetail, SearchContext, SearchResult
from app.registry import ResolvedSiteInfo
from app.utils.helpers.helpers import build_search_result, iso_date, pack_cur_id, slugify
from app.utils.logging.logger import logger

STUDIO = 'Watch4Beauty'
TAGLINE = 'Watch4Beauty'
DIRECTOR = 'Mark'
ART_BASE = 'https://mh-c75c2d6726.watch4beauty.com/production/'


def _titleize(slug: str) -> str:
    return re.sub(r'\b\w', lambda m: m.group().upper(), slug.replace('-', ' '))


class Watch4BeautyClient(Client):
    async def search(self, ctx: SearchContext) -> list[SearchResult]:
        base = ctx.site_info.base_url.rstrip('/')

        model_strings: list[str] = []
        lowered = ctx.title.lower()
        if 'veronica da souza' in lowered:
            model_strings.append('veronica-da-souza')
        else:
            words = [w for w in lowered.split() if w]
            slice_: list[str] = []
            for i in range(min(2, len(words))):
                slice_.append(words[i])
                model_strings.append('-'.join(slice_))

        model_string = ''
        updates: list[Any] | None = None
        for candidate in model_strings:
            data = await self.fetch_json(
                f'{base}/api/models/{candidate}/updates', FetchCtx(capture=ctx.capture), label=f'[{ctx.site_info.name}] models/{candidate}/updates'
            )
            if isinstance(data, list) and data:
                model_string = candidate
                updates = data
                break

        if updates is None:
            title_slug = slugify(ctx.title, replacements=[("'", '')])
            data = await self.fetch_json(
                f'{base}/api/issues/{title_slug}/models', FetchCtx(capture=ctx.capture), label=f'[{ctx.site_info.name}] issues/{title_slug}/models'
            )
            fallback_slug = _first_model_nickname(data)
            if fallback_slug:
                model_string = fallback_slug
                u = await self.fetch_json(
                    f'{base}/api/models/{model_string}/updates', FetchCtx(capture=ctx.capture), label=f'[{ctx.site_info.name}] models/{model_string}/updates'
                )
                if isinstance(u, list) and u:
                    updates = u

        if updates is None:
            logger.info(ctx.site_info.name, f'Watch4Beauty search "{ctx.title}" → no model match')
            return []

        results: list[SearchResult] = []
        seen: set[str] = set()
        issues = updates[0].get('Issues') if isinstance(updates[0], dict) else None
        for issue in issues or []:
            scene_name = (issue.get('issue_title') or '').strip()
            scene_slug = (issue.get('issue_simple_title') or '').strip()
            if not scene_name or not scene_slug:
                continue
            date = iso_date(issue['issue_datetime']) if issue.get('issue_datetime') else None
            key = f'{model_string}|{scene_slug}'
            if key in seen:
                continue
            seen.add(key)
            results.append(
                build_search_result(
                    title=scene_name,
                    scene_url=f'{base}/api/issues/{scene_slug}',
                    query=ctx.title,
                    display_date=date,
                    search_date=ctx.search_date,
                    cur_id=pack_cur_id([model_string, scene_slug, date or '']),
                )
            )
        return results

    async def fetch_scene_detail(self, payload: str, site: ResolvedSiteInfo, ctx: SceneContext | None = None) -> SceneDetail | None:
        base = site.base_url.rstrip('/')
        model_slug = ''
        scene_slug = ''
        cur_id_date = ''
        if '|' in payload:
            parts = payload.split('|')
            model_slug = (parts[0] if len(parts) > 0 else '').strip()
            scene_slug = (parts[1] if len(parts) > 1 else '').strip()
            cur_id_date = (parts[2] if len(parts) > 2 else '').strip()
        elif '/api/issues/' in payload:
            m = re.search(r'/api/issues/([^/?#]+)', payload)
            scene_slug = m.group(1) if m else ''
        if not scene_slug:
            logger.warn(site.name, f'Watch4Beauty detail: unrecognized payload "{payload}"')
            return None

        scene_arr = await self.fetch_json(
            f'{base}/api/issues/{scene_slug}', FetchCtx(capture=ctx.capture if ctx else None), label=f'[{site.name}] issues/{scene_slug}'
        )
        scene = scene_arr[0] if isinstance(scene_arr, list) and scene_arr else None
        if not isinstance(scene, dict):
            return None

        title = (scene.get('issue_title') or '').strip()
        summary = (scene.get('issue_text') or '').strip()
        datetime = scene.get('issue_datetime') or ''
        release_date = (iso_date(datetime) or cur_id_date) if datetime else (cur_id_date or None)
        year = int(release_date[:4]) if release_date else None
        genres = self.dedup_strings(list((scene.get('issue_tags') or '').split(','))) if scene.get('issue_tags') else []

        date_compact = re.sub(r'[^0-9]', '', datetime)[:8] if datetime else (release_date or '').replace('-', '')
        art_prefix = f'{ART_BASE}{date_compact}' if date_compact else ART_BASE
        images = [
            f'{art_prefix}-issue-cover-1280.jpg',
            f'{art_prefix}-issue-video-cover-2560.jpg',
            f'{art_prefix}-issue-cover-wide-2560.jpg',
        ]

        actors: list[ActorResult] = []
        models_arr = await self.fetch_json(
            f'{base}/api/issues/{scene_slug}/models', FetchCtx(capture=ctx.capture if ctx else None), label=f'[{site.name}] issues/{scene_slug}/models'
        )
        models = models_arr[0].get('Models') if isinstance(models_arr, list) and models_arr and isinstance(models_arr[0], dict) else None
        for m in models or []:
            name = (m.get('model_nickname') or '').strip()
            slug = (m.get('model_simple_nickname') or '').strip()
            if not name:
                continue
            photo = f'{art_prefix}model-{slug}-320.jpg' if slug else ''
            actors.append(ActorResult(name=name, photo_url=photo))
            if slug:
                images.append(f'{ART_BASE}model-{slug}-wide-2560.jpg')
                images.append(f'{ART_BASE}model-{slug}-1280.jpg')

        if not actors and model_slug:
            actors.append(ActorResult(name=_titleize(model_slug)))

        return SceneDetail(
            title=title,
            summary=summary,
            studio=STUDIO,
            tagline=TAGLINE,
            collections=[TAGLINE],
            genres=genres,
            actors=actors,
            directors=[ActorResult(name=DIRECTOR)],
            raw_image_urls=images,
            release_date=release_date,
            year=year,
            scene_url=f'{base}/api/issues/{scene_slug}',
        )


def _first_model_nickname(data: Any) -> str:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        models = data[0].get('Models')
        if isinstance(models, list) and models and isinstance(models[0], dict):
            return (models[0].get('model_simple_nickname') or '').strip()
    return ''
