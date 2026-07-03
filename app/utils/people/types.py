from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Gender = Literal['male', 'female', 'trans', '']
Role = Literal['actor', 'director', 'producer']

# Gendered suffix values a cache filename may carry (Gender minus the empty string).
GENDER_SUFFIXES = ('male', 'female', 'trans')


def parse_person_filename(filename: str) -> tuple[str, str, Gender]:
    """(role, slug, gender) from a `role.slug[_gender].ext` cache filename. slug keeps
    hyphens; gender is '' when absent; role is '' if there's no `role.` prefix."""
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
    source: str = ''


class PersonSource(Protocol):
    name: str

    async def find(self, actor_name: str, ctx: PersonLookupContext) -> PhotoHit | None: ...
