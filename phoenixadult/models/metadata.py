from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from phoenixadult.models.provider_info import PlexMediaType


class PlexModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


CAST_FIELDS = ('Role', 'Director', 'Producer')
CREDIT_FIELDS = (*CAST_FIELDS, 'Writer')


class PlexImage(PlexModel):
    url: str
    type: str
    priority: bool | None = None
    rotate: int | None = None
    locked: bool | None = None


class PlexRole(PlexModel):
    tag: str
    role: str | None = None
    thumb: str | None = None
    gender: str | None = None
    order: int | None = None


class PlexGenre(PlexModel):
    tag: str


class PlexRating(PlexModel):
    type: str
    value: float
    image: str | None = None


class PlexGuid(PlexModel):
    id: str


class PlexData18(PlexModel):
    type: Literal['scene', 'movie']
    id: str
    manual: bool | None = None
    also: list[str] | None = None


class PlexSource(PlexModel):
    url: str | None = None
    kind: str | None = None
    data: Any = None


class PlexCollection(PlexModel):
    tag: str


class PlexCountry(PlexModel):
    tag: str


class PlexMatchResult(PlexModel):
    ratingKey: str
    guid: str
    type: PlexMediaType
    title: str
    originallyAvailableAt: str | None = None
    thumb: str | None = None
    contentRating: str | None = None
    year: int | None = None
    score: float | None = None
    Guid: list[PlexGuid] | None = None


class _MatchContainer(PlexModel):
    offset: int
    totalSize: int
    identifier: str
    size: int
    Metadata: list[PlexMatchResult]


class PlexMatchResponse(PlexModel):
    MediaContainer: _MatchContainer


class PlexMetadata(PlexModel):
    type: PlexMediaType
    ratingKey: str
    key: str | None = None
    guid: str
    title: str
    titleSort: str | None = None
    originalTitle: str | None = None
    year: int | None = None
    summary: str | None = None
    tagline: str | None = None
    data18: PlexData18 | None = None
    sourceRef: PlexSource | None = None
    contentRating: str | None = None
    isAdult: bool | None = None
    audienceRating: float | None = None
    rating: float | None = None
    duration: int | None = None
    originallyAvailableAt: str | None = None
    thumb: str | None = None
    art: str | None = None
    studio: str | None = None
    Genre: list[PlexGenre] | None = None
    Role: list[PlexRole] | None = None
    Director: list[PlexRole] | None = None
    Writer: list[PlexRole] | None = None
    Producer: list[PlexRole] | None = None
    Image: list[PlexImage] | None = None
    Guid: list[PlexGuid] | None = None
    Rating: list[PlexRating] | None = None
    Collection: list[PlexCollection] | None = None
    Country: list[PlexCountry] | None = None


class _MetadataContainer(PlexModel):
    identifier: str
    size: int
    Metadata: list[PlexMetadata]


class PlexMetadataResponse(PlexModel):
    MediaContainer: _MetadataContainer
