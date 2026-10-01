from __future__ import annotations

from phoenixadult.models.metadata import PlexModel


class MediaProviderScheme(PlexModel):
    scheme: str


class MediaProviderType(PlexModel):
    type: int
    Scheme: list[MediaProviderScheme]


class MediaProviderFeature(PlexModel):
    type: str
    key: str


class MediaProviderDefinition(PlexModel):
    identifier: str
    title: str
    version: str
    Types: list[MediaProviderType]
    Feature: list[MediaProviderFeature]


class MediaProviderResponse(PlexModel):
    MediaProvider: MediaProviderDefinition
