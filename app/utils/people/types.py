from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Gender = Literal['male', 'female', 'trans', '']
Role = Literal['actor', 'director', 'producer']


@dataclass
class PersonInput:
    name: str
    photo: str = ''
    gender: Gender = ''


@dataclass
class ResolvedPerson:
    name: str
    photo: str
    gender: Gender
    role: Role


@dataclass
class PersonLookupContext:
    role: Role
    studio: str = ''
    site_name: str = ''


@dataclass
class PhotoHit:
    url: str
    gender: Gender = ''


class PersonSource(Protocol):
    name: str

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None: ...
