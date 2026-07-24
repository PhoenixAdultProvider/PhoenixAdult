from __future__ import annotations

from typing import Any


def empty_media_container(identifier: str) -> dict[str, Any]:
    """An empty Plex MediaContainer envelope (no results)."""
    return media_container(identifier, [])


def media_container(identifier: str, items: list[Any], key: str = 'Metadata') -> dict[str, Any]:
    """A Plex MediaContainer envelope wrapping `items` under `key` (e.g. 'Metadata' or 'Image')."""
    return {'MediaContainer': {'offset': 0, 'totalSize': len(items), 'identifier': identifier, 'size': len(items), key: items}}
