from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

HttpMethod = Literal['GET', 'POST', 'HEAD']


@dataclass
class BypassRequest:
    url: str
    method: HttpMethod = 'GET'
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    timeout_ms: int | None = None


@dataclass
class BypassResponse:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    cookies: dict[str, str] = field(default_factory=dict)
    final_url: str = ''
    user_agent: str = ''


class BypassBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...

    async def request(self, req: BypassRequest) -> BypassResponse | None: ...
