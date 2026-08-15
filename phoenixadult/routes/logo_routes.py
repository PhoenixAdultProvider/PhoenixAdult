from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.registry import canonical_site_display
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.images import logo_cache
from phoenixadult.utils.logging.logger import logger

_UPLOAD = File(...)
_SUFFIX_BY_TYPE = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/svg+xml': '.svg'}

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]


def _state() -> dict[str, object]:
    entries = logo_cache.entries()
    for e in entries:
        e['site'] = canonical_site_display(str(e['slug'])) or ''
    return {'dir': str(logo_cache.cache_dir()), 'logos': entries}


@router.get('', response_class=HTMLResponse)
@router.get('/', response_class=HTMLResponse)
async def page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('logos_ui', active='logos', username=nav_username(request), state=await run_in('store', _state)))


@router.get('/api/list')
async def list_logos() -> JSONResponse:
    return JSONResponse(await run_in('store', _state))


@router.post('/api/purge', dependencies=_admin)
async def purge(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    rel = str(body.get('rel') or '')
    if not rel:
        return JSONResponse({'error': 'rel required'}, status_code=400)
    if not await run_in('fs', logo_cache.purge, rel):
        return JSONResponse({'error': 'not found'}, status_code=404)
    return JSONResponse({'ok': True})


@router.post('/api/purge-all', dependencies=_admin)
async def purge_all() -> JSONResponse:
    return JSONResponse({'ok': True, 'purged': await run_in('fs', logo_cache.purge_all)})


@router.post('/api/rescan', dependencies=_admin)
async def rescan() -> JSONResponse:
    return JSONResponse({'ok': True, 'count': await run_in('fs', logo_cache.rescan)})


def _site_catalog() -> dict[str, list[str]]:
    from phoenixadult.registry import get_all_providers, get_sites_for_provider

    groups: dict[str, set[str]] = {}
    for provider in get_all_providers():
        for site in get_sites_for_provider(provider.id):
            studio = (site.provider_name or '').strip() or site.name
            names = groups.setdefault(studio, set())
            names.add(site.name)
            sub = (site.sub_group or '').strip()
            if sub:
                names.add(sub)
    return {studio: sorted(names - {studio}, key=str.casefold) for studio, names in groups.items()}


def _taken_slugs() -> set[str]:
    return {str(e['slug']) for e in logo_cache.entries()}


def _missing_for(studio: str, subs: list[str], taken: set[str]) -> list[str]:
    return [s for s in subs if logo_cache.logo_slug(s) not in taken]


def _add_state() -> dict[str, object]:
    taken = _taken_slugs()
    studios = [studio for studio, subs in _site_catalog().items() if logo_cache.logo_slug(studio) not in taken or _missing_for(studio, subs, taken)]
    return {'studios': sorted(studios, key=str.casefold)}


@router.get('/add', response_class=HTMLResponse, dependencies=_admin)
async def add_page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('logo_add', active='logos', username=nav_username(request), state=await run_in('store', _add_state)))


@router.get('/api/aliases', dependencies=_admin)
async def aliases(studio: str = '') -> JSONResponse:
    def _read() -> dict[str, object]:
        if not studio:
            return {'aliases': [], 'studioTaken': False}
        taken = _taken_slugs()
        subs = _site_catalog().get(studio, [])
        return {'aliases': _missing_for(studio, subs, taken), 'studioTaken': logo_cache.logo_slug(studio) in taken}

    return JSONResponse(await run_in('store', _read))


def _slugs(studio: str, alias: str) -> tuple[str, str]:
    folder = logo_cache.logo_slug(studio)
    name = logo_cache.logo_slug(alias or studio)
    return folder, name


@router.post('/api/add-upload', dependencies=_admin)
async def add_upload(studio: str = Form(''), alias: str = Form(''), file: UploadFile = _UPLOAD) -> JSONResponse:
    folder, name = _slugs(studio, alias)
    if not name:
        return JSONResponse({'ok': False, 'error': 'Pick a studio first.'}, status_code=400)
    suffix = Path(file.filename or '').suffix.lower()
    data = await file.read()
    if not data:
        return JSONResponse({'ok': False, 'error': 'That file was empty.'}, status_code=400)
    try:
        rel = await run_in('store', logo_cache.save_logo, folder, name, data, suffix)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': str(err)}, status_code=400)
    logger.info('logo-cache', f'added {rel} from an upload')
    return JSONResponse({'ok': True, 'rel': rel})


@router.post('/api/add-url', dependencies=_admin)
async def add_url(request: Request) -> JSONResponse:
    from phoenixadult.utils.images.image_fetcher import fetch_image

    body = await read_json_body(request)
    studio, alias = str(body.get('studio') or ''), str(body.get('alias') or '')
    url = str(body.get('url') or '').strip()
    folder, name = _slugs(studio, alias)
    if not name:
        return JSONResponse({'ok': False, 'error': 'Pick a studio first.'}, status_code=400)
    if not url.startswith(('http://', 'https://')):
        return JSONResponse({'ok': False, 'error': 'Enter a http:// or https:// address.'}, status_code=400)
    try:
        got = await fetch_image(url)
    except Exception as err:  # noqa: BLE001 - report why the whole chain gave up
        return JSONResponse({'ok': False, 'error': f'Could not fetch that URL: {err}'}, status_code=502)
    if not got.data:
        return JSONResponse({'ok': False, 'error': 'That URL returned an empty image.'}, status_code=502)
    suffix = Path(urlsplit(url).path).suffix.lower() or _SUFFIX_BY_TYPE.get(got.content_type.split(';')[0].strip(), '')
    try:
        rel = await run_in('store', logo_cache.save_logo, folder, name, got.data, suffix)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': str(err)}, status_code=400)
    logger.info('logo-cache', f'added {rel} from {url}')
    return JSONResponse({'ok': True, 'rel': rel})
