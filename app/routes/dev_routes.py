from __future__ import annotations

import dataclasses
import html
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.clients.base import RawCaptureEntry, SceneContext, SearchContext
from app.mappers.metadata_mapper import MetadataMapper
from app.models.metadata import PlexMetadataResponse
from app.registry import find_site, get_all_providers, get_sites_for_provider
from app.routes import read_json_body
from app.services.scraper_router import ScraperRouter
from app.utils import cache as metadata_cache
from app.utils.auth.env_auth import csrf_guard, env_auth_guard
from app.utils.helpers.helpers import title_distance_score
from app.utils.http.ssrf_guard import ensure_fetchable_url
from app.utils.logging.log_capture import begin_capture
from app.utils.logging.logger import logger
from app.utils.logging.orchestrator_logs import (
    log_detail_summary,
    log_search_count,
    log_search_data,
    log_update_header,
    log_update_provider,
)
from app.utils.people import filter_male_actors
from app.utils.plex.rating_key import parse_rating_key, to_rating_key
from app.utils.processors.filename_parser import get_site_name_from_registry
from app.utils.processors.search_query import build_search_pieces
from app.utils.processors.title_case import title_case

router = APIRouter(dependencies=[Depends(env_auth_guard), Depends(csrf_guard)])

scraper = ScraperRouter()
mapper = MetadataMapper()


def _serialize_captures(caps: list[RawCaptureEntry]) -> list[dict[str, Any]]:
    return [{'label': c.label, 'contentType': c.content_type, 'body': c.body} for c in caps]


def _lap_timer() -> Callable[[], int]:
    """Returns a closure that yields elapsed ms since the previous call."""
    last = time.monotonic()

    def lap() -> int:
        nonlocal last
        now = time.monotonic()
        ms = round((now - last) * 1000)
        last = now
        return ms

    return lap


# ── POST /dev/test ────────────────────────────────────────────────────────────


@router.post('/test')
async def dev_test(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    filename = body.get('filename')
    year_override = body.get('yearOverride')
    steps: list[dict[str, Any]] = []

    if not filename:
        return JSONResponse({'error': 'filename is required'}, status_code=400)

    cap = begin_capture()
    lap = _lap_timer()

    def send(payload: dict[str, Any]) -> JSONResponse:
        return JSONResponse({**payload, 'logs': cap.end()})

    # Step 1: Parse
    parsed = get_site_name_from_registry(filename, lambda token: find_site(token) is not None)
    year_trimmed = (year_override or '').strip()
    year_num = int(year_trimmed) if len(year_trimmed) == 4 and year_trimmed.isdigit() else None
    steps.append(
        {
            'step': '1. Parse filename',
            'ok': bool(parsed),
            'data': dataclasses.asdict(parsed) if parsed else None,
            'error': None if parsed else 'Could not parse filename — check format',
            'durationMs': lap(),
        }
    )
    if not parsed:
        return send({'filename': filename, 'steps': steps})

    # Step 2: Site lookup
    site = find_site(parsed.site_token)
    assert site is not None
    steps.append(
        {
            'step': '2. Site lookup',
            'ok': True,
            'data': {
                'name': site.name,
                'providerId': site.provider_id,
                'baseUrl': site.base_url,
                'contentType': site.content_type,
                'scraperType': site.scraper_config.type,
                'aliases': site.aliases,
            },
            'durationMs': lap(),
        }
    )

    # Step 3: Provider lookup
    provider = next((p for p in get_all_providers() if p.id == site.provider_id), None)
    steps.append(
        {
            'step': '3. Provider lookup',
            'ok': bool(provider),
            'data': {'id': provider.id, 'title': provider.title, 'plexIdentifier': provider.plex_identifier} if provider else None,
            'error': None if provider else f'Provider "{site.provider_id}" not found',
            'durationMs': lap(),
        }
    )
    if not provider:
        return send({'filename': filename, 'steps': steps})

    # Step 4: Build search query
    pieces = build_search_pieces(site.content_type, parsed)
    step4_data: dict[str, Any] = {'query': pieces.query, 'searchURL': ''}
    steps.append(
        {
            'step': '4. Search query',
            'ok': bool(pieces.query),
            'data': step4_data,
            'error': None if pieces.query else 'Could not build search query from parsed filename',
            'durationMs': lap(),
        }
    )
    if not pieces.query:
        return send({'filename': filename, 'steps': steps})

    log_search_data(
        provider.id,
        source=filename,
        query=pieces.query,
        date=parsed.date,
        filename=filename,
        site_name=site.name,
        scraper_type=site.scraper_config.type,
    )

    # Step 5: Search
    lap()  # reset baseline so the duration reflects the upstream search only
    try:
        captures: list[RawCaptureEntry] = []
        raw_results = await scraper.search(
            SearchContext(
                title=pieces.query,
                encoded=pieces.query,
                search_site=parsed.site_token,
                site_info=site,
                search_date=parsed.date,
                year=year_num,
                capture=captures,
                scene_id=pieces.scene_id,
                full_title=pieces.full_title,
            )
        )

        from_result = next((r.search_url for r in raw_results if r.search_url), None) if raw_results else None
        resolved = from_result or ''
        if not resolved:
            first_get = next((c for c in captures if c.label.startswith('GET ')), None)
            if first_get:
                resolved = first_get.label[4:].split(' ')[0].strip()
        step4_data['searchURL'] = resolved

        if raw_results is None:
            steps.append(
                {
                    'step': '5. Search results',
                    'ok': False,
                    'error': f'No scraper registered for type "{site.scraper_config.type}"',
                    'data': {'captures': _serialize_captures(captures)},
                    'durationMs': lap(),
                }
            )
            return send({'filename': filename, 'steps': steps})

        log_search_count(provider.id, site.name, pieces.query, len(raw_results))

        scored: list[dict[str, Any]] = [
            {
                'title': title_case(r.title, site_name=site.name, scraper_type=site.scraper_config.type),
                'sceneURL': r.scene_url,
                'curID': r.cur_id,
                'displayDate': r.display_date,
                'thumbUrl': r.thumb_url,
                'score': r.score if r.score is not None else title_distance_score(pieces.query, r.title),
                'ratingKey': to_rating_key(r.cur_id, site.name, parsed.date),
                'providerId': provider.id,
            }
            for r in raw_results
        ]
        scored.sort(key=lambda x: x['score'], reverse=True)

        steps.append(
            {
                'step': '5. Search results',
                'ok': len(scored) > 0,
                'data': {'searchDate': parsed.date, 'count': len(scored), 'results': scored, 'captures': _serialize_captures(captures)},
                'error': None if scored else 'No results returned from upstream',
                'durationMs': lap(),
            }
        )
    except Exception:  # noqa: BLE001
        logger.error('dev', 'search step failed', exc_info=True)
        steps.append({'step': '5. Search results', 'ok': False, 'error': 'Internal error — see the server log', 'durationMs': lap()})

    return send({'filename': filename, 'steps': steps})


# ── POST /dev/metadata ────────────────────────────────────────────────────────


@router.post('/metadata')
async def dev_metadata(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rating_key = body.get('ratingKey')
    provider_id = body.get('providerId')
    filename = body.get('filename')
    result_score = body.get('resultScore')
    force = bool(body.get('force'))  # re-scrape upstream, bypassing the snapshot
    steps: list[dict[str, Any]] = []

    if not rating_key or not provider_id:
        return JSONResponse({'error': 'ratingKey and providerId are required'}, status_code=400)

    cap = begin_capture()
    lap = _lap_timer()

    def send(payload: dict[str, Any]) -> JSONResponse:
        return JSONResponse({**payload, 'logs': cap.end()})

    log_update_header(provider_id, rating_key)

    # Step 1: Parse ratingKey
    parsed = parse_rating_key(rating_key)
    steps.append(
        {
            'step': '1. Parse ratingKey',
            'ok': bool(parsed),
            'data': parsed,
            'error': None if parsed else f'Could not parse ratingKey: "{rating_key}"',
            'durationMs': lap(),
        }
    )
    if not parsed:
        return send({'ratingKey': rating_key, 'steps': steps})

    # Step 2: Site lookup
    site = find_site(parsed['site_name'] or '')
    steps.append(
        {
            'step': '2. Site lookup',
            'ok': bool(site),
            'data': {'name': site.name, 'scraperType': site.scraper_config.type} if site else None,
            'error': None if site else f'No site found for "{parsed["site_name"]}"',
            'durationMs': lap(),
        }
    )
    if not site:
        return send({'ratingKey': rating_key, 'steps': steps})

    # Step 3: Provider lookup
    provider = next((p for p in get_all_providers() if p.id == provider_id), None)
    steps.append(
        {
            'step': '3. Provider lookup',
            'ok': bool(provider),
            'data': {'id': provider.id, 'title': provider.title} if provider else None,
            'error': None if provider else f'Provider "{provider_id}" not found',
            'durationMs': lap(),
        }
    )
    if not provider:
        return send({'ratingKey': rating_key, 'steps': steps})

    log_update_provider(provider.id, site.name, site.scraper_config.type)

    # Step 4: Decode sceneURL / videoId
    cur_id = parsed['cur_id'] or ''
    scene_url = scraper.decode(cur_id)
    steps.append({'step': '4. Decode identifier', 'ok': bool(scene_url), 'data': {'curID': cur_id, 'sceneURL': scene_url}, 'durationMs': lap()})
    if not scene_url:
        return send({'ratingKey': rating_key, 'steps': steps})
    try:
        await ensure_fetchable_url(scene_url)  # mirror MetadataService's SSRF guard
    except ValueError as err:
        steps.append({'step': '4. Decode identifier', 'ok': False, 'error': f'sceneURL blocked: {err}', 'durationMs': lap()})
        return send({'ratingKey': rating_key, 'steps': steps})

    # Snapshot cache-first: mirror MetadataService — a frozen snapshot is served
    # without touching the source (only when METADATA_CACHE_ENABLE is on).
    cached = None if force else metadata_cache.read(site.name, cur_id)
    if cached is not None:
        response = PlexMetadataResponse.model_validate(cached)
        backfilled = await metadata_cache.backfill_people_images(response, site.name)
        reapplied = metadata_cache.reapply_text_rules(response, site.scraper_config.type)  # re-apply current text rules
        if metadata_cache.backfill_metadata_attrs(response):
            backfilled = True
        if backfilled or reapplied:
            await metadata_cache.write(site.name, cur_id, response)
        filter_male_actors(response)  # serve-time filter (after any cache write); mirrors MetadataService
        md = response.MediaContainer.Metadata[0].model_dump(by_alias=True, exclude_none=True)
        steps.append(
            {
                'step': '5. Fetch metadata',
                'ok': True,
                'data': {
                    'servedFrom': 'snapshot',
                    'backfilled': backfilled,
                    'reapplied': reapplied,
                    'title': md.get('title'),
                    'summary': md.get('summary'),
                    'tagline': md.get('tagline'),
                    'studio': md.get('studio'),
                    'contentRating': md.get('contentRating'),
                    'releaseDate': md.get('originallyAvailableAt'),
                    'year': md.get('year'),
                    'genres': [g.get('tag') for g in md.get('Genre', [])],
                    'actors': [{'name': r.get('tag'), 'gender': r.get('gender') or '', 'photoURL': r.get('thumb')} for r in md.get('Role', [])],
                    'directors': [{'name': r.get('tag'), 'gender': r.get('gender') or '', 'photoURL': r.get('thumb')} for r in md.get('Director', [])],
                    'producers': [{'name': r.get('tag'), 'gender': r.get('gender') or '', 'photoURL': r.get('thumb')} for r in md.get('Producer', [])],
                    'collections': [c.get('tag') for c in md.get('Collection', [])],
                    'thumb': md.get('thumb'),
                    'art': md.get('art'),
                    'images': [{'url': i.get('url'), 'type': i.get('type')} for i in md.get('Image', [])],
                    'captures': [],
                },
                'durationMs': lap(),
            }
        )
        return send({'ratingKey': rating_key, 'steps': steps})

    # Step 5: Fetch detail
    lap()  # reset baseline so the duration reflects the upstream fetch only
    try:
        captures: list[RawCaptureEntry] = []
        detail = await scraper.fetch_scene_detail(scene_url, site, SceneContext(capture=captures, subsite=parsed.get('subsite')))
        if not detail:
            steps.append(
                {
                    'step': '5. Fetch metadata',
                    'ok': False,
                    'error': 'Scraper returned no SceneDetail (transport error or unsupported flow). See captures for upstream responses.',
                    'data': {'captures': _serialize_captures(captures)},
                    'durationMs': lap(),
                }
            )
            return send({'ratingKey': rating_key, 'steps': steps})

        log_detail_summary(provider.id, site.name, detail)
        metadata = await mapper.to_metadata(detail, rating_key, provider.plex_identifier, parsed['release_date'], site, filename_site=parsed.get('subsite'))

        # Freeze a snapshot for next time (no-op unless METADATA_CACHE_ENABLE).
        response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})
        snapshot_saved = await metadata_cache.write(site.name, cur_id, response)
        filter_male_actors(response)  # hide male actors from the preview (after the write — snapshot keeps them)

        roles = response.MediaContainer.Metadata[0].Role or []
        directors = metadata.Director or []
        producers = metadata.Producer or []
        collections = metadata.Collection or []
        genres = metadata.Genre or []
        images = metadata.Image or []

        fixture = {
            'site': site.name,
            'filename': filename or '',
            'expect': {
                'title': metadata.title or '',
                'studio': metadata.studio or '',
                'tagline': metadata.tagline or '',
                'scenedate': metadata.originallyAvailableAt or '',
                'summary': metadata.summary or '',
                'actors': [{'name': r.tag, 'gender': r.gender or ''} for r in roles],
                'directors': [d.tag for d in directors],
                'producers': [p.tag for p in producers],
                'collections': [c.tag for c in collections],
                'genres': [g.tag for g in genres],
                'minImages': max(1, min(2, len(images))),
                'score': result_score if isinstance(result_score, (int, float)) else 80,
            },
        }

        steps.append(
            {
                'step': '5. Fetch metadata',
                'ok': True,
                'data': {
                    'servedFrom': 'live',
                    'snapshotEnabled': metadata_cache.enabled(),
                    'snapshotSaved': snapshot_saved,
                    'title': metadata.title,
                    'summary': metadata.summary,
                    'tagline': metadata.tagline,
                    'studio': metadata.studio,
                    'contentRating': metadata.contentRating,
                    'releaseDate': metadata.originallyAvailableAt,
                    'year': metadata.year,
                    'genres': [g.tag for g in genres],
                    'actors': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in roles],
                    'directors': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in directors],
                    'producers': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in producers],
                    'collections': [c.tag for c in collections],
                    'thumb': metadata.thumb,
                    'art': metadata.art,
                    'images': [{'url': img.url, 'type': img.type} for img in images],
                    'rawImageCount': len(detail.raw_image_urls),
                    'captures': _serialize_captures(captures),
                    'fixture': fixture,
                },
                'durationMs': lap(),
            }
        )
    except Exception:  # noqa: BLE001
        logger.error('dev', 'metadata step failed', exc_info=True)
        steps.append({'step': '5. Fetch metadata', 'ok': False, 'error': 'Internal error — see the server log', 'durationMs': lap()})

    return send({'ratingKey': rating_key, 'steps': steps})


# ── GET /dev — Test UI ────────────────────────────────────────────────────────


@router.get('')
@router.get('/')
async def page() -> HTMLResponse:
    sites = [
        {
            'name': s.name,
            'providerId': p.id,
            'providerName': s.provider_name or '',
            'contentType': s.content_type,
            'scraperType': s.scraper_config.type,
            'aliases': s.aliases,
        }
        for p in get_all_providers()
        for s in get_sites_for_provider(p.id)
    ]
    return HTMLResponse(_render_ui(sites))


def _render_ui(sites: list[dict[str, Any]]) -> str:
    own: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for s in sites:
        if s['aliases'] or not s['providerName']:
            own.append(s)
            continue
        grouped.setdefault(s['providerName'], []).append(s)

    display: list[dict[str, Any]] = [{**s, 'grouped': False} for s in own]
    for provider_name, group in grouped.items():
        head = group[0]
        display.append(
            {
                'name': provider_name,
                'providerId': head['providerId'],
                'providerName': provider_name,
                'contentType': head['contentType'],
                'scraperType': head['scraperType'],
                'aliases': [g['name'] for g in group],
                'grouped': True,
            }
        )
    display.sort(key=lambda x: x['name'].lower())

    rows: list[str] = []
    for s in display:
        name_cell = (
            f'<strong>{html.escape(s["name"])}</strong> <span class="group-badge">{len(s["aliases"])} sites</span>' if s['grouped'] else html.escape(s['name'])
        )
        if s['aliases']:
            n = len(s['aliases'])
            noun = 'site' if s['grouped'] else 'alias'
            plural = '' if n == 1 else 's' if s['grouped'] else 'es'
            chips = ''.join(f'<span class="alias-chip">{html.escape(a)}</span>' for a in s['aliases'])
            alias_cell = f'<details><summary>{n} {noun}{plural}</summary><div class="alias-list">{chips}</div></details>'
        else:
            alias_cell = '—'
        tr_class = ' class="group-row"' if s['grouped'] else ''
        rows.append(
            f'<tr{tr_class}>\n'
            f'      <td>{name_cell}</td>\n'
            f'      <td><code>{html.escape(s["contentType"])}</code></td>\n'
            f'      <td><code>{html.escape(s["scraperType"])}</code></td>\n'
            f'      <td>{alias_cell}</td>\n'
            f'    </tr>'
        )

    return _DEV_HTML.replace('__SITE_ROWS__', ''.join(rows))


_DEV_HTML = (Path(__file__).parent / 'html' / 'dev_ui.html').read_text(encoding='utf-8')
