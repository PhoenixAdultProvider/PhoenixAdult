from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class MediaProviderScheme(_Model):
    scheme: str


class MediaProviderType(_Model):
    type: int
    Scheme: list[MediaProviderScheme]


class MediaProviderFeature(_Model):
    type: str
    key: str


class MediaProviderDefinition(_Model):
    identifier: str
    title: str
    version: str
    Types: list[MediaProviderType]
    Feature: list[MediaProviderFeature]


class MediaProviderResponse(_Model):
    MediaProvider: MediaProviderDefinition
