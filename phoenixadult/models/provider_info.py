from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PlexMediaType = Literal['movie', 'show', 'season', 'episode']


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    plex_identifier: str
    title: str
    version: str
    media_type: PlexMediaType
    namespace: str | None = None
