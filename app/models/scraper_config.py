from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScraperConfig:
    type: str
    data18_enrichment: bool = False
