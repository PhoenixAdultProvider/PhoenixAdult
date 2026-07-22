from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.models.media_provider import MediaProviderResponse
from app.models.provider_info import ProviderInfo
from app.routes import plex_json, read_json_body
from app.services import scrape_queue
from app.services.match_service import MatchRequest, MatchService
from app.services.metadata_service import MetadataService
from app.utils.logging.logger import logger
from app.utils.plex.media_type import plex_media_type_id
from app.utils.plex.responses import empty_media_container, media_container

_SERVICES: list[tuple[ProviderInfo, MatchService, MetadataService]] = []


async def restore_queue() -> None:
    """Re-enqueue background jobs persisted before the last shutdown."""
    replays = scrape_queue.take_replays()
    restored = 0
    for replay in replays.values():
        for provider, match_service, metadata_service in _SERVICES:
            if provider.id != replay.get('provider'):
                continue
            if replay.get('kind') == 'update' and replay.get('rating_key'):
                metadata_service.queue_snapshot(str(replay['rating_key']), provider, replay.get('language'))
                restored += 1
            elif replay.get('kind') == 'search':
                match_service.requeue_search(replay, provider)
                restored += 1
    if restored:
        logger.info('scrape-queue', f'restored {restored} queued background job(s) from disk')


def create_provider_router(provider: ProviderInfo) -> APIRouter:
    router = APIRouter()
    match_service = MatchService()
    metadata_service = MetadataService()
    match_service.metadata_service = metadata_service
    _SERVICES.append((provider, match_service, metadata_service))

    def _empty_container() -> JSONResponse:
        return JSONResponse(empty_media_container(provider.plex_identifier))

    @router.get('')
    @router.get('/')
    async def describe() -> JSONResponse:
        response = MediaProviderResponse.model_validate(
            {
                'MediaProvider': {
                    'identifier': provider.plex_identifier,
                    'title': provider.title,
                    'version': provider.version,
                    'Types': [{'type': plex_media_type_id(provider.media_type), 'Scheme': [{'scheme': provider.plex_identifier}]}],
                    'Feature': [
                        {'type': 'match', 'key': '/library/metadata/matches'},
                        {'type': 'metadata', 'key': '/library/metadata'},
                    ],
                }
            }
        )
        return plex_json(response)

    @router.post('/library/metadata/matches')
    async def match(request: Request) -> JSONResponse:
        body = await read_json_body(request)
        language = request.headers.get('x-plex-language')
        try:
            req = MatchRequest(
                type=int(body.get('type', 1)),
                title=body.get('title'),
                year=body.get('year'),
                guid=body.get('guid'),
                filename=body.get('filename'),
                manual=body.get('manual'),
                includeAdult=body.get('includeAdult'),
                duration=body.get('duration'),
                ohash=body.get('ohash'),
            )
            result = await match_service.match(req, provider, language)
            return plex_json(result)
        except Exception:  # noqa: BLE001
            logger.error(provider.id, 'Match error', exc_info=True)
            return JSONResponse({'error': 'Internal server error'}, status_code=500)

    @router.get('/library/metadata/{rating_key}/images')
    async def images(rating_key: str, request: Request) -> JSONResponse:
        try:
            language = request.headers.get('x-plex-language')
            result = await metadata_service.get_metadata(rating_key, provider, language)
            if not result:
                return JSONResponse({'error': 'Not found'}, status_code=404)
            image_list = result.MediaContainer.Metadata[0].Image or []
            images = [img.model_dump(by_alias=True, exclude_none=True) for img in image_list]
            return JSONResponse(media_container(provider.plex_identifier, images, key='Image'))
        except Exception:  # noqa: BLE001
            logger.error(provider.id, 'Images error', exc_info=True)
            return JSONResponse({'error': 'Internal server error'}, status_code=500)

    @router.get('/library/metadata/{rating_key}/{sub}')
    async def empty_sub(rating_key: str, sub: str) -> JSONResponse:
        logger.info(provider.id, f'empty sub-resource: /library/metadata/{rating_key}/{sub}')
        return _empty_container()

    @router.get('/library/metadata/{rating_key}')
    async def metadata(rating_key: str, request: Request) -> JSONResponse:
        try:
            language = request.headers.get('x-plex-language')
            result = await metadata_service.get_metadata(rating_key, provider, language, is_refresh=True)
            if not result:
                return JSONResponse({'error': 'Not found'}, status_code=404)
            return plex_json(result)
        except Exception:  # noqa: BLE001
            logger.error(provider.id, 'Metadata error', exc_info=True)
            return JSONResponse({'error': 'Internal server error'}, status_code=500)

    return router
