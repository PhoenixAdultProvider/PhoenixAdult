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


def _add_state() -> dict[str, object]:
    from phoenixadult.utils import cache as metadata_cache

    return {'studios': metadata_cache.studios(), 'folders': logo_cache.folders()}


@router.get('/add', response_class=HTMLResponse, dependencies=_admin)
async def add_page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('logo_add', active='logos', username=nav_username(request), state=await run_in('store', _add_state)))


@router.get('/api/aliases', dependencies=_admin)
async def aliases(studio: str = '') -> JSONResponse:
    from phoenixadult.utils import cache as metadata_cache

    def _read() -> list[str]:
        values = metadata_cache.facets(studio=studio) if studio else {}
        return [str(t) for t in (values.get('taglines') or []) if str(t) and str(t) != studio]

    return JSONResponse({'aliases': await run_in('store', _read)})


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
    got = None
    last: Exception | None = None
    for pinned in (False, True):
        try:
            got = await fetch_image(url, pinned=pinned)
            break
        except Exception as err:  # noqa: BLE001 - a blocked host retries pinned, then gives up with the reason
            last = err
    if got is None or not got.data:
        return JSONResponse({'ok': False, 'error': f'Could not fetch that URL, including a pinned retry: {last}'}, status_code=502)
    suffix = Path(urlsplit(url).path).suffix.lower() or _SUFFIX_BY_TYPE.get(got.content_type.split(';')[0].strip(), '')
    try:
        rel = await run_in('store', logo_cache.save_logo, folder, name, got.data, suffix)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': str(err)}, status_code=400)
    logger.info('logo-cache', f'added {rel} from {url}')
    return JSONResponse({'ok': True, 'rel': rel})
