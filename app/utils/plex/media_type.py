from __future__ import annotations

from app.models.provider_info import PlexMediaType, ProviderInfo


def plex_media_type_id(media_type: PlexMediaType) -> int:
    return {'movie': 1, 'show': 2, 'season': 3, 'episode': 4}[media_type]


def media_type_route_slug(media_type: PlexMediaType) -> str:
    return {'movie': 'movies', 'show': 'tvshows', 'season': 'tvshows', 'episode': 'tvshows'}[media_type]


def provider_mount_path(provider: ProviderInfo) -> str:
    return f'/{provider.namespace or provider.id}/{media_type_route_slug(provider.media_type)}'
