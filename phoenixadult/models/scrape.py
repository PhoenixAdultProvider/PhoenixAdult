from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from phoenixadult.models.capture import RawCaptureEntry
from phoenixadult.models.site_info import ResolvedSiteInfo

# ── Phase Contexts ────────────────────────────────────────────────────────────


@dataclass
class SearchContext:
    title: str
    encoded: str
    search_site: str
    site_info: ResolvedSiteInfo
    search_date: str | None = None
    year: int | None = None
    duration: str | None = None
    ohash: str | None = None
    capture: list[RawCaptureEntry] | None = None
    language: str | None = None
    scene_id: str | None = None
    full_title: str | None = None
    allow_slow: bool = False

    def search_url(self, query: str | None = None) -> str:
        return self.site_info.search_url(self.encoded if query is None else query)


@dataclass
class SceneContext:
    capture: list[RawCaptureEntry] | None = None
    language: str | None = None
    subsite: str | None = None
    allow_slow: bool = False


# ── Results ───────────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    title: str
    scene_url: str
    cur_id: str
    thumb_url: str | None = None
    release_date: str | None = None
    display_date: str | None = None
    score: float | None = None
    search_url: str | None = None
    subsite: str | None = None


@dataclass
class ActorResult:
    name: str
    photo_url: str = ''
    gender: str = ''
    role: str = ''


@dataclass
class SceneDetail:
    title: str = ''
    summary: str = ''
    studio: str = ''
    tagline: str = ''
    genres: list[str] = field(default_factory=list)
    actors: list[ActorResult] = field(default_factory=list)
    art: list[str] = field(default_factory=list)
    art_priority: list[str] = field(default_factory=list)
    art_referer: str | None = None
    art_cookie: str | None = None
    release_date: str | None = None
    year: int | None = None
    collections: list[str] | None = None
    directors: list[ActorResult] | None = None
    producers: list[ActorResult] | None = None
    scene_url: str | None = None
    original_title: str | None = None
    data18_url: str | None = None
    duration: int | None = None
    countries: list[str] | None = None
    rating: float | None = None
    audience_rating: float | None = None
    source_kind: str | None = None
    source_json: Any | None = None
