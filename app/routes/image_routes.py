from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from app.config.env import env
from app.utils.fs.paths import safe_join
from app.utils.http.ssrf_guard import assert_fetchable_url
from app.utils.images.ext import IMAGE_EXTS
from app.utils.images.image_classifier import classify_image
from app.utils.images.image_fetcher import fetch_image
from app.utils.logging.logger import logger

router = APIRouter()
# Mounted at the site root (NOT under /images) so frozen snapshot image URLs are
# short and `images` doesn't appear in the path: GET /cache/<studio>/<sub>/<hash>/<file>.
cache_router = APIRouter()

_PROXY_CACHE_CONTROL = 'public, max-age=3600'


def _read_multi(request: Request, key: str) -> list[str]:
    return [v for v in request.query_params.getlist(key) if v]


@router.get('/local/{filepath:path}')
async def local_image(filepath: str) -> Response:
    # :path so people images can live in role/gender subfolders (actors/female/…).
    if Path(filepath).suffix.lower() not in IMAGE_EXTS:
        return JSONResponse({'error': 'Invalid file type'}, status_code=400)

    file_path = safe_join(env.image_dir, filepath)
    if not file_path:
        return JSONResponse({'error': 'Invalid path'}, status_code=400)
    if file_path.exists():
        return FileResponse(file_path)

    cached = safe_join(env.people_cache_dir, filepath)
    if cached and cached.exists():
        return FileResponse(cached)

    return JSONResponse({'error': 'Image not found'}, status_code=404)


@cache_router.get('/cache/{splat:path}')
async def cached_metadata_image(splat: str) -> Response:
    if Path(splat).suffix.lower() not in IMAGE_EXTS:
        return JSONResponse({'error': 'Invalid file type'}, status_code=400)
    file_path = safe_join(env.metadata_cache_dir, splat)
    if not file_path or not file_path.exists():
        return JSONResponse({'error': 'Image not found'}, status_code=404)
    return FileResponse(file_path)


@router.get('/manual-nfo/{splat:path}')
async def manual_nfo_image(splat: str) -> Response:
    segments = [s for s in splat.split('/') if s]
    if not segments:
        return JSONResponse({'error': 'Invalid path'}, status_code=400)
    if Path(segments[-1]).suffix.lower() not in IMAGE_EXTS:
        return JSONResponse({'error': 'Invalid file type'}, status_code=400)
    file_path = safe_join(env.manual_nfo_path, *segments)
    if not file_path:
        return JSONResponse({'error': 'Invalid path'}, status_code=400)
    if not file_path.exists():
        return JSONResponse({'error': 'Image not found'}, status_code=404)
    return FileResponse(file_path)


async def _proxy(request: Request, send_body: bool, *, classify: bool = False) -> Response:
    raw_url = request.query_params.get('url')
    if not raw_url:
        return JSONResponse({'error': 'Missing url'}, status_code=400)
    try:
        target = await assert_fetchable_url(raw_url)
    except ValueError:
        return JSONResponse({'error': 'Invalid url'}, status_code=400)
    try:
        entry = await fetch_image(target, _read_multi(request, 'referer'), _read_multi(request, 'cookie'), pinned=env.image_proxy_pin)
    except Exception as err:  # noqa: BLE001
        logger.warn('proxy-classified' if classify else 'proxy', f'502 {target} - {err}')
        return JSONResponse({'error': 'Failed to fetch upstream image'}, status_code=502)
    headers = {'Content-Length': str(len(entry.data)), 'Cache-Control': _PROXY_CACHE_CONTROL}
    if classify:
        result = classify_image(entry.width, entry.height)
        if result.image_class == 'unknown':
            return JSONResponse({'error': 'Image could not be classified as poster or background'}, status_code=404)
        headers['X-Image-Type'] = result.image_class
    body = entry.data if send_body else b''
    return Response(content=body, media_type=entry.content_type, headers=headers)


@router.get('/proxy')
async def proxy_get(request: Request) -> Response:
    return await _proxy(request, True)


@router.head('/proxy')
async def proxy_head(request: Request) -> Response:
    return await _proxy(request, False)


@router.get('/proxy-classified')
async def proxy_classified_get(request: Request) -> Response:
    return await _proxy(request, True, classify=True)


@router.head('/proxy-classified')
async def proxy_classified_head(request: Request) -> Response:
    return await _proxy(request, False, classify=True)
