from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.registry import ResolvedSiteInfo


def resolve_image_referers(site: ResolvedSiteInfo, scene_url: str | None = None) -> list[str]:
    out: list[str] = []
    for spec in site.image_referers or []:
        token = spec.lower()
        if token == 'baseurl':
            out.append(site.base_url)
        elif token == 'sceneurl':
            if scene_url:
                out.append(scene_url)
        else:
            out.append(spec)
    return out


def resolve_image_cookies(site: ResolvedSiteInfo) -> list[str]:
    return list(site.image_cookies or [])
