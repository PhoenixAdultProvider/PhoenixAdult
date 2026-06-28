from __future__ import annotations

from typing import Any


def empty_media_container(identifier: str) -> dict[str, Any]:
    """An empty Plex MediaContainer envelope (no results)."""
    return {'MediaContainer': {'offset': 0, 'totalSize': 0, 'identifier': identifier, 'size': 0, 'Metadata': []}}
