from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.config.env import env
from phoenixadult.mappers.metadata_mapper import MetadataMapper
from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.metadata import PlexMetadata, PlexMetadataResponse, PlexRole
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.models.scrape import SceneContext, SceneDetail, SearchContext
from phoenixadult.registry import ResolvedSiteInfo, canonical_site_display, find_site, get_all_providers, get_sites_for_provider, normalize_site_key
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.services.metadata_service import refresh_cached_snapshot
from phoenixadult.services.scraper_router import ScraperRouter
from phoenixadult.utils import cache as metadata_cache
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.helpers.ids import embed_subsite, split_subsite
from phoenixadult.utils.helpers.scoring import title_distance_score
from phoenixadult.utils.http.ssrf_guard import ensure_fetchable_url
from phoenixadult.utils.logging.log_capture import begin_capture
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.orchestrator_logs import (
    log_detail_summary,
    log_search_count,
    log_search_data,
    log_update_header,
    log_update_provider,
)
from phoenixadult.utils.logging.response_trace import begin_body_capture
from phoenixadult.utils.people import filter_male_actors
from phoenixadult.utils.plex.rating_key import parse_rating_key, to_rating_key
from phoenixadult.utils.processors.filename_parser import get_site_name_from_registry
from phoenixadult.utils.processors.search_query import build_search_pieces
from phoenixadult.utils.processors.title_case import title_case


async def dev_ui_guard() -> None:
    if not env.dev_ui_enabled:
        raise HTTPException(status_code=404, detail='Not Found')


router = APIRouter(dependencies=[Depends(dev_ui_guard), Depends(user_auth_guard), Depends(csrf_guard), Depends(admin_auth_guard)])

_URL_IN_LABEL_RE = re.compile(r'https?://\S+')

scraper = ScraperRouter()
mapper = MetadataMapper()


def _serialize_captures(caps: list[RawCaptureEntry]) -> list[dict[str, Any]]:
    return [{'label': c.label, 'contentType': c.content_type, 'body': c.body} for c in caps]


def _lap_timer() -> Callable[[], int]:
    last = time.monotonic()

    def lap() -> int:
        nonlocal last
        now = time.monotonic()
        ms = round((now - last) * 1000)
        last = now
        return ms

    return lap


def _metadata_field_diff(direct: dict[str, Any], reassembled: dict[str, Any]) -> list[str]:
    md_direct = ((direct.get('MediaContainer') or {}).get('Metadata') or [{}])[0]
    md_re = ((reassembled.get('MediaContainer') or {}).get('Metadata') or [{}])[0]

    def norm(value: Any) -> Any:
        return None if value == [] else value

    return sorted(k for k in {*md_direct, *md_re} if norm(md_direct.get(k)) != norm(md_re.get(k)))


async def _db_roundtrip_step(site_name: str, cur_id: str, direct: dict[str, Any], written: bool, lap: Callable[[], int]) -> dict[str, Any]:
    step = '6. DB round-trip'
    if not metadata_cache.enabled():
        return {
            'step': step,
            'ok': True,
            'data': {'cacheEnabled': False, 'note': 'METADATA_CACHE_ENABLE is off — snapshot not written'},
            'durationMs': lap(),
        }
    if not written:
        return {
            'step': step,
            'ok': False,
            'data': {'cacheEnabled': True, 'written': False},
            'error': 'Snapshot write failed or was skipped — nothing to re-read',
            'durationMs': lap(),
        }
    reassembled = await run_in('store', metadata_cache.read, site_name, cur_id)
    if reassembled is None:
        return {
            'step': step,
            'ok': False,
            'data': {'cacheEnabled': True, 'written': True},
            'error': 'Snapshot re-read returned nothing',
            'durationMs': lap(),
        }
    diff = _metadata_field_diff(direct, reassembled)
    return {
        'step': step,
        'ok': True,
        'data': {'cacheEnabled': True, 'written': True, 'identical': not diff, 'diffFields': diff, 'reassembled': reassembled},
        'durationMs': lap(),
    }


# ── POST /Dev/Test ────────────────────────────────────────────────────────────


def _searched_url(raw_results: list[Any] | None, captures: list[RawCaptureEntry]) -> str:
    direct = next((r.search_url for r in raw_results if r.search_url), None) if raw_results else None
    if direct:
        return str(direct)
    gets = [c for c in captures if c.label.startswith('GET ')]
    for capture in gets or captures:
        found = _URL_IN_LABEL_RE.search(capture.label)
        if found:
            return found.group(0)
    return ''


def _score_results(raw_results: list[Any], *, site: Any, parsed: Any, query: str, provider_id: str) -> list[dict[str, Any]]:
    filename_site = canonical_site_display(parsed.site_token)

    def rating_key(cur_id: str, sub: str | None) -> str:
        sub = sub if sub and normalize_site_key(sub) != normalize_site_key(site.name) else None
        return to_rating_key(embed_subsite(cur_id, sub), site.name, parsed.date)

    scored = [
        {
            'title': title_case(r.title, site_name=site.name, scraper_type=site.scraper_config.type),
            'sceneURL': r.scene_url,
            'curID': r.cur_id,
            'displayDate': r.display_date,
            'thumbUrl': r.thumb_url,
            'score': r.score if r.score is not None else title_distance_score(query, r.title),
            'ratingKey': rating_key(r.cur_id, r.subsite or filename_site),
            'providerId': provider_id,
        }
        for r in raw_results
    ]
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored


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

    lap()
    try:
        captures: list[RawCaptureEntry] = []
        bodies = begin_body_capture(captures)
        try:
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
        finally:
            bodies.end()

        step4_data['searchURL'] = _searched_url(raw_results, captures)

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

        scored = _score_results(raw_results, site=site, parsed=parsed, query=pieces.query, provider_id=provider.id)

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


# ── POST /Dev/Metadata ────────────────────────────────────────────────────────


@router.post('/metadata')
async def dev_metadata(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rating_key = body.get('ratingKey')
    provider_id = body.get('providerId')
    filename = body.get('filename')
    result_score = body.get('resultScore')
    force = bool(body.get('force'))
    full_pipeline = bool(body.get('fullPipeline'))
    steps: list[dict[str, Any]] = []

    if not rating_key or not provider_id:
        return JSONResponse({'error': 'ratingKey and providerId are required'}, status_code=400)

    cap = begin_capture()
    lap = _lap_timer()

    def send(payload: dict[str, Any]) -> JSONResponse:
        return JSONResponse({**payload, 'logs': cap.end()})

    log_update_header(provider_id, rating_key)

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

    cur_id = parsed['cur_id'] or ''
    scene_url, subsite = split_subsite(scraper.decode(cur_id))
    steps.append({'step': '4. Decode identifier', 'ok': bool(scene_url), 'data': {'curID': cur_id, 'sceneURL': scene_url}, 'durationMs': lap()})
    if not scene_url:
        return send({'ratingKey': rating_key, 'steps': steps})
    try:
        await ensure_fetchable_url(scene_url)
    except ValueError as err:
        steps.append({'step': '4. Decode identifier', 'ok': False, 'error': f'sceneURL blocked: {err}', 'durationMs': lap()})
        return send({'ratingKey': rating_key, 'steps': steps})

    cached = None if force else await run_in('store', metadata_cache.read, site.name, cur_id)
    response = PlexMetadataResponse.model_validate(cached) if cached is not None else None
    if response is not None and metadata_cache.data18_remap_needed(response, site.name):
        response = None
    if response is not None and metadata_cache.data18_backfill_needed(response, site.name):
        response = None
    if response is not None:
        steps.extend(await _cached_metadata_steps(response, site, cur_id, scene_url, subsite, full_pipeline, lap))
    else:
        steps.extend(await _live_metadata_steps(rating_key, provider, site, cur_id, scene_url, subsite, parsed, filename, result_score, full_pipeline, lap))
    return send({'ratingKey': rating_key, 'steps': steps})


async def _cached_metadata_steps(
    response: PlexMetadataResponse,
    site: ResolvedSiteInfo,
    cur_id: str,
    scene_url: str,
    subsite: str | None,
    full_pipeline: bool,
    lap: Callable[[], int],
) -> list[dict[str, Any]]:

    async def _fetch_detail() -> SceneDetail | None:
        return await scraper.fetch_scene_detail(scene_url, site, SceneContext(subsite=subsite)) if scene_url else None

    refreshed = await refresh_cached_snapshot(response, site, cur_id, fetch_detail=_fetch_detail)
    filter_male_actors(response)
    md = response.MediaContainer.Metadata[0].model_dump(by_alias=True, exclude_none=True)
    steps: list[dict[str, Any]] = [
        {
            'step': '5. Fetch metadata',
            'ok': True,
            'data': {
                'servedFrom': 'snapshot',
                'refreshed': refreshed,
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
    ]
    if full_pipeline:
        steps.append(
            {
                'step': '6. DB round-trip',
                'ok': True,
                'data': {'cacheEnabled': True, 'note': 'Served from snapshot — this response already came through the DB reassembly path'},
                'durationMs': lap(),
            }
        )
    return steps


def _live_fixture(metadata: PlexMetadata, site: ResolvedSiteInfo, filename: str | None, result_score: Any, roles: list[PlexRole]) -> dict[str, Any]:
    return {
        'site': site.name,
        'filename': filename or '',
        'expect': {
            'title': metadata.title or '',
            'studio': metadata.studio or '',
            'tagline': metadata.tagline or '',
            'scenedate': metadata.originallyAvailableAt or '',
            'summary': metadata.summary or '',
            'actors': [{'name': r.tag, 'gender': r.gender or ''} for r in roles],
            'directors': [d.tag for d in metadata.Director or []],
            'producers': [p.tag for p in metadata.Producer or []],
            'collections': [c.tag for c in metadata.Collection or []],
            'genres': [g.tag for g in metadata.Genre or []],
            'minImages': max(1, min(2, len(metadata.Image or []))),
            'score': result_score if isinstance(result_score, (int, float)) else 80,
        },
    }


async def _live_metadata_steps(
    rating_key: str,
    provider: ProviderInfo,
    site: ResolvedSiteInfo,
    cur_id: str,
    scene_url: str,
    subsite: str | None,
    parsed: dict[str, Any],
    filename: str | None,
    result_score: Any,
    full_pipeline: bool,
    lap: Callable[[], int],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    lap()
    try:
        captures: list[RawCaptureEntry] = []
        bodies = begin_body_capture(captures)
        try:
            detail = await scraper.fetch_scene_detail(scene_url, site, SceneContext(capture=captures, subsite=subsite))
        finally:
            bodies.end()
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
            return steps

        log_detail_summary(provider.id, site.name, detail)
        metadata = await mapper.to_metadata(detail, rating_key, provider.plex_identifier, parsed['release_date'], site, filename_site=subsite)

        response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})
        direct_payload = response.model_dump(by_alias=True, exclude_none=True) if full_pipeline else None
        snapshot_saved = await metadata_cache.write(site.name, cur_id, response)
        filter_male_actors(response)

        roles = response.MediaContainer.Metadata[0].Role or []
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
                    'genres': [g.tag for g in metadata.Genre or []],
                    'actors': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in roles],
                    'directors': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in metadata.Director or []],
                    'producers': [{'name': r.tag, 'gender': r.gender or '', 'photoURL': r.thumb} for r in metadata.Producer or []],
                    'collections': [c.tag for c in metadata.Collection or []],
                    'thumb': metadata.thumb,
                    'art': metadata.art,
                    'images': [{'url': img.url, 'type': img.type} for img in metadata.Image or []],
                    'rawImageCount': len(detail.art),
                    'captures': _serialize_captures(captures),
                    'fixture': _live_fixture(metadata, site, filename, result_score, roles),
                },
                'durationMs': lap(),
            }
        )
        if full_pipeline:
            steps.append(await _db_roundtrip_step(site.name, cur_id, direct_payload or {}, snapshot_saved, lap))
    except Exception:  # noqa: BLE001
        logger.error('dev', 'metadata step failed', exc_info=True)
        steps.append({'step': '5. Fetch metadata', 'ok': False, 'error': 'Internal error — see the server log', 'durationMs': lap()})

    return steps


# ── GET /Dev — Test UI ────────────────────────────────────────────────────────


@router.get('')
@router.get('/')
async def page(request: Request) -> HTMLResponse:
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
    return HTMLResponse(_render_ui(sites, nav_username(request)))


def _render_ui(sites: list[dict[str, Any]], username: str) -> str:
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
    return render_page('dev_ui', active='dev', username=username, sites=display)
