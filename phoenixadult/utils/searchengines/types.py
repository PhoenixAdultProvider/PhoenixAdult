from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SearchOptions:
    query: str
    site: str
    num: int | None = None
    language: str | None = None
    safe_search: bool = False
    region: str | None = None


class SearchEngineClient(Protocol):
    name: str

    def available(self) -> bool: ...

    async def search(self, opts: SearchOptions) -> list[str]: ...
