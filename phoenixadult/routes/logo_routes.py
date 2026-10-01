from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from phoenixadult.registry import canonical_site_display, find_site, get_all_providers, get_sites_for_provider
from phoenixadult.routes import nav_username, read_json_body, render_page
from phoenixadult.utils.auth.user_auth import admin_auth_guard, csrf_guard, user_auth_guard
from phoenixadult.utils.concurrency.pools import run_in
from phoenixadult.utils.http.ssrf_guard import guard_target
from phoenixadult.utils.images import logo_cache, logo_template
from phoenixadult.utils.images.image_fetcher import fetch_image
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.processors.title_case import title_case

_UPLOAD = File(...)
_SUFFIX_BY_TYPE = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp', 'image/svg+xml': '.svg'}

router = APIRouter(dependencies=[Depends(user_auth_guard), Depends(csrf_guard)])
_admin = [Depends(admin_auth_guard)]


def _state() -> dict[str, object]:
    entries = logo_cache.entries()
    by_folder = {logo_cache.logo_slug(studio): studio for studio in _site_catalog()}
    counts: Counter[str] = Counter()
    for e in entries:
        e['site'] = canonical_site_display(str(e['slug'])) or ''
        folder = str(e['folder'])
        e['studio'] = by_folder.get(logo_cache.logo_slug(folder)) or (title_case(folder.replace('-', ' ')) if folder else 'Loose Files')
        counts[str(e['studio'])] += 1
    studios = [{'name': name, 'count': counts[name]} for name in sorted(counts, key=str.casefold)]
    return {'dir': str(logo_cache.cache_dir()), 'logos': entries, 'studios': studios}


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


def _missing_for(subs: list[str], taken: set[str]) -> list[str]:
    return [s for s in subs if logo_cache.logo_slug(s) not in taken]


def _add_state() -> dict[str, object]:
    taken = _taken_slugs()
    studios = [studio for studio, subs in _site_catalog().items() if logo_cache.logo_slug(studio) not in taken or _missing_for(subs, taken)]
    return {'studios': sorted(studios, key=str.casefold), 'placeholders': [{'token': t, 'note': n} for t, n in logo_template.PLACEHOLDERS]}


@router.get('/add', response_class=HTMLResponse, dependencies=_admin)
async def add_page(request: Request) -> HTMLResponse:
    return HTMLResponse(render_page('logo_add', active='logos', username=nav_username(request), state=await run_in('store', _add_state)))


@router.get('/api/aliases', dependencies=_admin)
async def aliases(studio: str = '') -> JSONResponse:
    def _read() -> dict[str, object]:
        if not studio:
            return {'aliases': [], 'studioTaken': False, 'template': ''}
        taken = _taken_slugs()
        subs = _site_catalog().get(studio, [])
        return {
            'aliases': _missing_for(subs, taken),
            'studioTaken': logo_cache.logo_slug(studio) in taken,
            'template': logo_template.templates().get(studio, ''),
        }

    return JSONResponse(await run_in('store', _read))


def _base_url_for(alias: str) -> str:
    site = find_site(alias)
    return site.base_url if site is not None else ''


@router.get('/api/expand', dependencies=_admin)
async def expand(studio: str = '', template: str = '') -> JSONResponse:
    def _build() -> dict[str, object]:
        taken = _taken_slugs()
        subs = _missing_for(_site_catalog().get(studio, []), taken)
        return {'rows': [{'alias': alias, 'urls': logo_template.expand(template, studio, alias, _base_url_for(alias))} for alias in subs]}

    if not studio:
        return JSONResponse({'error': 'Pick a studio first.'}, status_code=400)
    if not template.strip():
        return JSONResponse({'error': 'Enter a template first.'}, status_code=400)
    try:
        return JSONResponse(await run_in('store', _build))
    except ValueError as err:
        return JSONResponse({'error': str(err)}, status_code=400)


@router.post('/api/template', dependencies=_admin)
async def save_template(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    studio, template = str(body.get('studio') or ''), str(body.get('template') or '').strip()
    if not studio or not template:
        return JSONResponse({'ok': False, 'error': 'studio and template required'}, status_code=400)
    await run_in('fs', logo_template.remember, studio, template)
    return JSONResponse({'ok': True})


def _slugs(studio: str, alias: str) -> tuple[str, str]:
    folder = logo_cache.logo_slug(studio)
    name = logo_cache.logo_slug(alias or studio)
    return folder, name


def _saved(rel: str) -> dict[str, object]:
    path = logo_cache.cache_dir() / rel
    try:
        url = logo_cache.local_url(path, path.stat().st_mtime) or ''
    except OSError:
        url = ''
    return {'ok': True, 'rel': rel, 'url': url}


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
    return JSONResponse(_saved(rel))


async def _first_image(urls: list[str]) -> tuple[bytes, str, str]:
    problems: list[str] = []
    for url in urls:
        try:
            await guard_target(url)
            got = await fetch_image(url)
        except Exception as err:  # noqa: BLE001 - report why the whole chain gave up
            problems.append(f'{url} ({err})')
            continue
        if got.data:
            return got.data, got.content_type, url
        problems.append(f'{url} (empty image)')
    raise ValueError('; '.join(problems))


def _requested_urls(body: dict[str, Any]) -> list[str]:
    raw = body.get('urls')
    if isinstance(raw, list):
        return [str(u).strip() for u in raw if str(u).strip()]
    single = str(body.get('url') or '').strip()
    return [single] if single else []


@router.post('/api/add-url', dependencies=_admin)
async def add_url(request: Request) -> JSONResponse:
    body = await read_json_body(request)
    studio, alias = str(body.get('studio') or ''), str(body.get('alias') or '')
    urls = _requested_urls(body)
    folder, name = _slugs(studio, alias)
    if not name:
        return JSONResponse({'ok': False, 'error': 'Pick a studio first.'}, status_code=400)
    if not urls or not all(url.startswith(('http://', 'https://')) for url in urls):
        return JSONResponse({'ok': False, 'error': 'Enter a http:// or https:// address.'}, status_code=400)
    try:
        data, content_type, used = await _first_image(urls)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': f'Could not fetch that URL: {err}'}, status_code=502)
    suffix = Path(urlsplit(used).path).suffix.lower() or _SUFFIX_BY_TYPE.get(content_type.split(';')[0].strip(), '')
    try:
        rel = await run_in('store', logo_cache.save_logo, folder, name, data, suffix)
    except ValueError as err:
        return JSONResponse({'ok': False, 'error': str(err)}, status_code=400)
    logger.info('logo-cache', f'added {rel} from {used}')
    return JSONResponse(_saved(rel))
