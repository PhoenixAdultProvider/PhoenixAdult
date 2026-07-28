from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Gender = Literal['male', 'female', 'trans', '']
PersonType = Literal['actor', 'director', 'producer']

GENDER_SUFFIXES = ('male', 'female', 'trans')


def parse_person_filename(filename: str) -> tuple[str, str, Gender]:
    stem = Path(filename).stem
    role, sep, rest = stem.partition('.')
    if not sep:
        rest, role = role, ''
    head, _, tail = rest.rpartition('_')
    if tail in GENDER_SUFFIXES and head:
        return role, head, tail  # type: ignore[return-value]
    return role, rest, ''


@dataclass
class PersonInput:
    name: str
    photo: str = ''
    gender: Gender = ''
    role: str = ''


@dataclass
class ResolvedPerson:
    name: str
    photo: str
    role: str
    gender: Gender
    type: PersonType


@dataclass
class PersonLookupContext:
    type: PersonType
    studio: str = ''
    site_name: str = ''


@dataclass
class PhotoHit:
    url: str
    gender: Gender = ''
    source: str = ''


class PersonSource(Protocol):
    name: str

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None: ...
