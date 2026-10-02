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
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.cache import metadata as metadata_cache
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
    if not env.metadata_cache_enabled:
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


class _Steps:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self._capture = begin_capture()
        self.lap = _lap_timer()

    def add(self, step: str, ok: bool, data: Any = None, error: str | None = None) -> None:
        self.items.append({'step': step, 'ok': ok, 'data': data, 'error': error, 'durationMs': self.lap()})

    def fail(self, step: str, error: str, data: Any = None) -> None:
        self.add(step, False, data, error)

    def extend(self, items: list[dict[str, Any]]) -> None:
        self.items.extend(items)

    def send(self, **payload: Any) -> JSONResponse:
        return JSONResponse({**payload, 'steps': self.items, 'logs': self._capture.end()})


@dataclasses.dataclass
class _SearchPlan:
    filename: str
    parsed: Any
    site: ResolvedSiteInfo
    provider: ProviderInfo
    pieces: Any
    query_data: dict[str, Any]


def _site_data(site: ResolvedSiteInfo) -> dict[str, Any]:
    return {
        'name': site.name,
        'providerId': site.provider_id,
        'baseUrl': site.base_url,
        'contentType': site.content_type,
        'scraperType': site.scraper_config.type,
        'aliases': site.aliases,
    }


def _plan_search(steps: _Steps, filename: str) -> _SearchPlan | None:
    parsed = get_site_name_from_registry(filename, lambda token: find_site(token) is not None)
    if parsed is None:
        steps.fail('1. Parse filename', 'Could not parse filename — check format')
        return None
    steps.add('1. Parse filename', True, dataclasses.asdict(parsed))
    site = find_site(parsed.site_token)
    assert site is not None
    steps.add('2. Site lookup', True, _site_data(site))
    provider = next((p for p in get_all_providers() if p.id == site.provider_id), None)
    if provider is None:
        steps.fail('3. Provider lookup', f'Provider "{site.provider_id}" not found')
        return None
    steps.add('3. Provider lookup', True, {'id': provider.id, 'title': provider.title, 'plexIdentifier': provider.plex_identifier})
    pieces = build_search_pieces(site.content_type, parsed)
    query_data: dict[str, Any] = {'query': pieces.query, 'searchURL': ''}
    if not pieces.query:
        steps.fail('4. Search query', 'Could not build search query from parsed filename', query_data)
        return None
    steps.add('4. Search query', True, query_data)
    return _SearchPlan(filename, parsed, site, provider, pieces, query_data)


def _year(year_override: Any) -> int | None:
    trimmed = (year_override or '').strip()
    return int(trimmed) if len(trimmed) == 4 and trimmed.isdigit() else None


async def _run_search(plan: _SearchPlan, year: int | None, captures: list[RawCaptureEntry]) -> list[Any] | None:
    bodies = begin_body_capture(captures)
    try:
        return await scraper.search(
            SearchContext(
                title=plan.pieces.query,
                encoded=plan.pieces.query,
                search_site=plan.parsed.site_token,
                site_info=plan.site,
                search_date=plan.parsed.date,
                year=year,
                capture=captures,
                scene_id=plan.pieces.scene_id,
                full_title=plan.pieces.full_title,
            )
        )
    finally:
        bodies.end()


async def _search_step(steps: _Steps, plan: _SearchPlan, year: int | None) -> None:
    site, provider, query = plan.site, plan.provider, plan.pieces.query
    log_search_data(
        provider.id,
        source=plan.filename,
        query=query,
        date=plan.parsed.date,
        filename=plan.filename,
        site_name=site.name,
        scraper_type=site.scraper_config.type,
    )
    steps.lap()
    captures: list[RawCaptureEntry] = []
    try:
        raw_results = await _run_search(plan, year, captures)
        plan.query_data['searchURL'] = _searched_url(raw_results, captures)
        if raw_results is None:
            steps.add('5. Search results', False, {'captures': _serialize_captures(captures)}, f'No scraper registered for type "{site.scraper_config.type}"')
            return
        log_search_count(provider.id, site.name, query, len(raw_results))
        scored = _score_results(raw_results, site=site, parsed=plan.parsed, query=query, provider_id=provider.id)
        data = {'searchDate': plan.parsed.date, 'count': len(scored), 'results': scored, 'captures': _serialize_captures(captures)}
        steps.add('5. Search results', len(scored) > 0, data, None if scored else 'No results returned from upstream')
    except Exception:  # noqa: BLE001
        logger.error('dev', 'search step failed', exc_info=True)
        steps.add('5. Search results', False, error='Internal error — see the server log')


@router.post('/test')
async def dev_test(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    filename = body.get('filename')
    if not filename:
        return JSONResponse({'error': 'filename is required'}, status_code=400)
    steps = _Steps()
    plan = _plan_search(steps, filename)
    if plan is not None:
        await _search_step(steps, plan, _year(body.get('yearOverride')))
    return steps.send(filename=filename)


# ── POST /Dev/Metadata ────────────────────────────────────────────────────────


@dataclasses.dataclass
class _MetadataTarget:
    rating_key: str
    parsed: dict[str, Any]
    site: ResolvedSiteInfo
    provider: ProviderInfo
    cur_id: str
    scene_url: str
    subsite: str | None


@dataclasses.dataclass
class _MetadataOptions:
    filename: str | None
    result_score: Any
    force: bool
    full_pipeline: bool


def _resolve_lookups(steps: _Steps, rating_key: str, provider_id: str) -> tuple[dict[str, Any], ResolvedSiteInfo, ProviderInfo] | None:
    parsed = parse_rating_key(rating_key)
    if not parsed:
        steps.fail('1. Parse ratingKey', f'Could not parse ratingKey: "{rating_key}"', parsed)
        return None
    steps.add('1. Parse ratingKey', True, parsed)
    site = find_site(parsed['site_name'] or '')
    if site is None:
        steps.fail('2. Site lookup', f'No site found for "{parsed["site_name"]}"')
        return None
    steps.add('2. Site lookup', True, {'name': site.name, 'scraperType': site.scraper_config.type})
    provider = next((p for p in get_all_providers() if p.id == provider_id), None)
    if provider is None:
        steps.fail('3. Provider lookup', f'Provider "{provider_id}" not found')
        return None
    steps.add('3. Provider lookup', True, {'id': provider.id, 'title': provider.title})
    return parsed, site, provider


async def _resolve_target(steps: _Steps, rating_key: str, provider_id: str) -> _MetadataTarget | None:
    lookups = _resolve_lookups(steps, rating_key, provider_id)
    if lookups is None:
        return None
    parsed, site, provider = lookups
    log_update_provider(provider.id, site.name, site.scraper_config.type)
    cur_id = parsed['cur_id'] or ''
    scene_url, subsite = split_subsite(scraper.decode(cur_id))
    steps.add('4. Decode identifier', bool(scene_url), {'curID': cur_id, 'sceneURL': scene_url})
    if not scene_url:
        return None
    try:
        await ensure_fetchable_url(scene_url)
    except ValueError as err:
        steps.add('4. Decode identifier', False, error=f'sceneURL blocked: {err}')
        return None
    return _MetadataTarget(rating_key, parsed, site, provider, cur_id, scene_url, subsite)


async def _usable_snapshot(target: _MetadataTarget, force: bool) -> PlexMetadataResponse | None:
    cached = None if force else await run_in('store', metadata_cache.read, target.site.name, target.cur_id)
    response = PlexMetadataResponse.model_validate(cached) if cached is not None else None
    if response is None:
        return None
    stale = metadata_cache.data18_remap_needed(response, target.site.name) or metadata_cache.data18_backfill_needed(response, target.site.name)
    return None if stale else response


@router.post('/metadata')
async def dev_metadata(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rating_key = body.get('ratingKey')
    provider_id = body.get('providerId')
    if not rating_key or not provider_id:
        return JSONResponse({'error': 'ratingKey and providerId are required'}, status_code=400)
    steps = _Steps()
    log_update_header(provider_id, rating_key)
    target = await _resolve_target(steps, rating_key, provider_id)
    if target is None:
        return steps.send(ratingKey=rating_key)
    options = _MetadataOptions(body.get('filename'), body.get('resultScore'), bool(body.get('force')), bool(body.get('fullPipeline')))
    response = await _usable_snapshot(target, options.force)
    if response is not None:
        steps.extend(await _cached_metadata_steps(response, target, options.full_pipeline, steps.lap))
    else:
        steps.extend(await _live_metadata_steps(target, options, steps.lap))
    return steps.send(ratingKey=rating_key)


def _people(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'name': r.get('tag'), 'gender': r.get('gender') or '', 'photoURL': r.get('thumb')} for r in rows]


def _snapshot_summary(md: dict[str, Any], refreshed: Any) -> dict[str, Any]:
    return {
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
        'actors': _people(md.get('Role', [])),
        'directors': _people(md.get('Director', [])),
        'producers': _people(md.get('Producer', [])),
        'collections': [c.get('tag') for c in md.get('Collection', [])],
        'thumb': md.get('thumb'),
        'art': md.get('art'),
        'images': [{'url': i.get('url'), 'type': i.get('type')} for i in md.get('Image', [])],
        'captures': [],
    }


async def _cached_metadata_steps(response: PlexMetadataResponse, target: _MetadataTarget, full_pipeline: bool, lap: Callable[[], int]) -> list[dict[str, Any]]:
    async def _fetch_detail() -> SceneDetail | None:
        return await scraper.fetch_scene_detail(target.scene_url, target.site, SceneContext(subsite=target.subsite)) if target.scene_url else None

    refreshed = await refresh_cached_snapshot(response, target.site, target.cur_id, fetch_detail=_fetch_detail)
    filter_male_actors(response)
    md = response.MediaContainer.Metadata[0].model_dump(by_alias=True, exclude_none=True)
    steps: list[dict[str, Any]] = [{'step': '5. Fetch metadata', 'ok': True, 'data': _snapshot_summary(md, refreshed), 'durationMs': lap()}]
    if full_pipeline:
        note = 'Served from snapshot — this response already came through the DB reassembly path'
        steps.append({'step': '6. DB round-trip', 'ok': True, 'data': {'cacheEnabled': True, 'note': note}, 'durationMs': lap()})
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


def _live_summary(metadata: PlexMetadata, roles: list[PlexRole], snapshot_saved: bool, raw_image_count: int) -> dict[str, Any]:
    return {
        'servedFrom': 'live',
        'snapshotEnabled': env.metadata_cache_enabled,
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
        'rawImageCount': raw_image_count,
    }


async def _fetch_live_detail(target: _MetadataTarget, captures: list[RawCaptureEntry]) -> SceneDetail | None:
    bodies = begin_body_capture(captures)
    try:
        return await scraper.fetch_scene_detail(target.scene_url, target.site, SceneContext(capture=captures, subsite=target.subsite))
    finally:
        bodies.end()


async def _live_metadata_steps(target: _MetadataTarget, options: _MetadataOptions, lap: Callable[[], int]) -> list[dict[str, Any]]:
    lap()
    captures: list[RawCaptureEntry] = []
    try:
        detail = await _fetch_live_detail(target, captures)
        if not detail:
            error = 'Scraper returned no SceneDetail (transport error or unsupported flow). See captures for upstream responses.'
            return [{'step': '5. Fetch metadata', 'ok': False, 'error': error, 'data': {'captures': _serialize_captures(captures)}, 'durationMs': lap()}]
        return await _live_steps_for(detail, target, options, captures, lap)
    except Exception:  # noqa: BLE001
        logger.error('dev', 'metadata step failed', exc_info=True)
        return [{'step': '5. Fetch metadata', 'ok': False, 'error': 'Internal error — see the server log', 'durationMs': lap()}]


async def _live_steps_for(
    detail: SceneDetail, target: _MetadataTarget, options: _MetadataOptions, captures: list[RawCaptureEntry], lap: Callable[[], int]
) -> list[dict[str, Any]]:
    site, provider = target.site, target.provider
    log_detail_summary(provider.id, site.name, detail)
    metadata = await mapper.to_metadata(detail, target.rating_key, provider.plex_identifier, target.parsed['release_date'], site, filename_site=target.subsite)
    response = PlexMetadataResponse.model_validate({'MediaContainer': {'identifier': provider.plex_identifier, 'size': 1, 'Metadata': [metadata]}})
    direct_payload = response.model_dump(by_alias=True, exclude_none=True) if options.full_pipeline else None
    snapshot_saved = await metadata_cache.write(site.name, target.cur_id, response)
    filter_male_actors(response)
    roles = response.MediaContainer.Metadata[0].Role or []
    data = {
        **_live_summary(metadata, roles, snapshot_saved, len(detail.art)),
        'captures': _serialize_captures(captures),
        'fixture': _live_fixture(metadata, site, options.filename, options.result_score, roles),
    }
    steps = [{'step': '5. Fetch metadata', 'ok': True, 'data': data, 'durationMs': lap()}]
    if options.full_pipeline:
        steps.append(await _db_roundtrip_step(site.name, target.cur_id, direct_payload or {}, snapshot_saved, lap))
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
