from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class PlexImage(_Model):
    url: str
    type: str
    priority: bool | None = None
    rotate: int | None = None
    locked: bool | None = None


class PlexRole(_Model):
    tag: str
    role: str | None = None
    thumb: str | None = None
    gender: str | None = None
    order: int | None = None


class PlexGenre(_Model):
    tag: str


class PlexRating(_Model):
    type: str
    value: float
    image: str | None = None


class PlexGuid(_Model):
    id: str


class PlexData18(_Model):
    type: Literal['scene', 'movie']
    id: str
    manual: bool | None = None
    also: list[str] | None = None


class PlexCollection(_Model):
    tag: str


class PlexCountry(_Model):
    tag: str


class PlexMatchResult(_Model):
    ratingKey: str
    guid: str
    type: Literal['movie', 'show', 'season', 'episode']
    title: str
    originallyAvailableAt: str | None = None
    thumb: str | None = None
    contentRating: str | None = None
    year: int | None = None
    score: float | None = None
    Guid: list[PlexGuid] | None = None


class _MatchContainer(_Model):
    offset: int
    totalSize: int
    identifier: str
    size: int
    Metadata: list[PlexMatchResult]


class PlexMatchResponse(_Model):
    MediaContainer: _MatchContainer


class PlexMetadata(_Model):
    type: Literal['movie', 'show', 'season', 'episode']
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


class _MetadataContainer(_Model):
    identifier: str
    size: int
    Metadata: list[PlexMetadata]


class PlexMetadataResponse(_Model):
    MediaContainer: _MetadataContainer
