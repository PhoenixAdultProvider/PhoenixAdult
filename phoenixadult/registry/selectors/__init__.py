from __future__ import annotations

import importlib
import pkgutil

from phoenixadult.models.site_info import SiteInfo

_MERGED_SEPARATELY = {'phoenixadult.registry.selectors.aggregators.archive'}


def _site_lists(module: object) -> list[str]:
    return [name for name, value in vars(module).items() if isinstance(value, list) and value and isinstance(value[0], SiteInfo)]


def _discover() -> list[SiteInfo]:
    found: list[SiteInfo] = []
    names = sorted(info.name for info in pkgutil.walk_packages(__path__, f'{__name__}.') if not info.ispkg)
    for name in names:
        leaf = name.rsplit('.', 1)[-1]
        if leaf.startswith('_') or name in _MERGED_SEPARATELY:
            continue
        module = importlib.import_module(name)
        sites = getattr(module, 'SITES', None)
        if sites is None:
            stray = _site_lists(module)
            if stray:
                raise RuntimeError(f'{name} defines {stray} but exports no SITES, so its sites would never be registered')
            continue
        found.extend(sites)
    return found


SITE_DEFINITIONS: list[SiteInfo] = _discover()
