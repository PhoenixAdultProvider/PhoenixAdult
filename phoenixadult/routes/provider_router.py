from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic.main import IncEx

from phoenixadult.models.media_provider import MediaProviderResponse
from phoenixadult.models.provider_info import ProviderInfo
from phoenixadult.routes import plex_json, read_json_body
from phoenixadult.routes.provider_guard import provider_guard
from phoenixadult.services import scrape_queue
from phoenixadult.services.match_service import MatchRequest, MatchService
from phoenixadult.services.metadata_service import MetadataService
from phoenixadult.services.provider_errors import MalformedRequestError, ProviderUnavailableError
from phoenixadult.utils.logging.logger import logger
from phoenixadult.utils.logging.request_trace import trace_body
from phoenixadult.utils.plex.media_type import plex_media_type_id
from phoenixadult.utils.plex.responses import empty_media_container, media_container

_INTERNAL_IMAGE_FIELDS: set[str] = {'locked', 'rotate'}
_HIDDEN_IMAGE_ITEMS: dict[str, IncEx | bool] = {'__all__': _INTERNAL_IMAGE_FIELDS}
_HIDDEN_METADATA_FIELDS: dict[str, IncEx | bool] = {'sourceRef': True, 'data18': True, 'Image': _HIDDEN_IMAGE_ITEMS}
_HIDDEN_METADATA_ITEMS: dict[str, IncEx | bool] = {'__all__': _HIDDEN_METADATA_FIELDS}
_HIDDEN_CONTAINER: dict[str, IncEx | bool] = {'Metadata': _HIDDEN_METADATA_ITEMS}
_INTERNAL_METADATA_FIELDS: dict[str, IncEx | bool] = {'MediaContainer': _HIDDEN_CONTAINER}

_SERVICES: list[tuple[ProviderInfo, MatchService, MetadataService]] = []


def service_for(provider_id: str) -> tuple[ProviderInfo, MetadataService] | None:
    for provider, _match_service, metadata_service in _SERVICES:
        if provider.id == provider_id:
            return provider, metadata_service
    return None


def match_service_for(provider_id: str) -> tuple[ProviderInfo, MatchService] | None:
    for provider, match_service, _metadata_service in _SERVICES:
        if provider.id == provider_id:
            return provider, match_service
    return None


async def restore_queue() -> None:
    replays = await scrape_queue.take_replays()
    restored = 0
    for replay in replays.values():
        for provider, match_service, metadata_service in _SERVICES:
            if provider.id != replay.get('provider'):
                continue
            if replay.get('kind') == 'update' and replay.get('rating_key'):
                rescrape = bool(replay.get('rescrape'))
                metadata_service.queue_snapshot(
                    str(replay['rating_key']), provider, replay.get('language'), label=replay.get('label'), force=rescrape, rescrape=rescrape
                )
                restored += 1
            elif replay.get('kind') == 'search':
                match_service.requeue_search(replay, provider)
                restored += 1
    if restored:
        logger.info('scrape-queue', f'restored {restored} queued background job(s) from disk')


async def _answer(provider: ProviderInfo, label: str, respond: Callable[[], Awaitable[JSONResponse]]) -> JSONResponse:
    try:
        return await respond()
    except MalformedRequestError as err:
        logger.warn(provider.id, f'{label} 400: {err}')
        return JSONResponse({'error': f'Bad request: {err}'}, status_code=400)
    except ProviderUnavailableError as err:
        logger.warn(provider.id, f'{label} 500: {err}')
        return JSONResponse({'error': str(err)}, status_code=500)
    except Exception:  # noqa: BLE001
        logger.error(provider.id, f'{label} error', exc_info=True)
        return JSONResponse({'error': 'Internal server error'}, status_code=500)


def _describe(provider: ProviderInfo) -> MediaProviderResponse:
    return MediaProviderResponse.model_validate(
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


def _match_request(body: dict[str, Any]) -> MatchRequest:
    try:
        media_type = int(body.get('type', 1))
    except (TypeError, ValueError):
        raise MalformedRequestError(f'type must be an integer, got {body.get("type")!r}') from None
    fields = ('title', 'year', 'guid', 'filename', 'manual', 'includeAdult', 'duration', 'ohash')
    return MatchRequest(type=media_type, **{name: body.get(name) for name in fields})


def create_provider_router(provider: ProviderInfo) -> APIRouter:
    router = APIRouter(dependencies=[Depends(provider_guard)])
    metadata_service = MetadataService()
    match_service = MatchService(metadata_service)
    _SERVICES.append((provider, match_service, metadata_service))

    def _empty_container() -> JSONResponse:
        return JSONResponse(empty_media_container(provider.plex_identifier))

    @router.get('')
    @router.get('/')
    async def describe() -> JSONResponse:
        return plex_json(_describe(provider))

    @router.post('/library/metadata/matches')
    async def match(request: Request) -> JSONResponse:
        body = await read_json_body(request)
        trace_body(provider.id, request, body)
        language = request.headers.get('x-plex-language')

        async def respond() -> JSONResponse:
            return plex_json(await match_service.match(_match_request(body), provider, language))

        return await _answer(provider, 'Match', respond)

    @router.get('/library/metadata/{rating_key}/images')
    async def images(rating_key: str, request: Request) -> JSONResponse:
        async def respond() -> JSONResponse:
            result = await metadata_service.get_metadata(rating_key, provider, request.headers.get('x-plex-language'))
            if not result:
                return JSONResponse({'error': 'Not found'}, status_code=404)
            image_list = result.MediaContainer.Metadata[0].Image or []
            images = [img.model_dump(by_alias=True, exclude_none=True, exclude=_INTERNAL_IMAGE_FIELDS) for img in image_list]
            return JSONResponse(media_container(provider.plex_identifier, images, key='Image'))

        return await _answer(provider, 'Images', respond)

    @router.get('/library/metadata/{rating_key}/{sub}')
    async def empty_sub(rating_key: str, sub: str) -> JSONResponse:
        logger.info(provider.id, f'empty sub-resource: /library/metadata/{rating_key}/{sub}')
        return _empty_container()

    @router.get('/library/metadata/{rating_key}')
    async def metadata(rating_key: str, request: Request) -> JSONResponse:
        async def respond() -> JSONResponse:
            result = await metadata_service.get_metadata(rating_key, provider, request.headers.get('x-plex-language'), is_refresh=True)
            if not result:
                return JSONResponse({'error': 'Not found'}, status_code=404)
            return JSONResponse(result.model_dump(by_alias=True, exclude_none=True, exclude=_INTERNAL_METADATA_FIELDS))

        return await _answer(provider, 'Metadata', respond)

    return router
