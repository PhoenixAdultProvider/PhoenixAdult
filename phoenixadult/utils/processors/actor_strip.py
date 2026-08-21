from __future__ import annotations

from typing import TYPE_CHECKING

from phoenixadult.config.env import env
from phoenixadult.utils.helpers.helpers import title_distance_score
from phoenixadult.utils.processors.site_key import normalize_site_key

if TYPE_CHECKING:
    from phoenixadult.registry import ResolvedSiteInfo


def enabled_for(site: ResolvedSiteInfo) -> bool:
    raw = env.search_strip_actors_raw or ''
    if not raw.strip():
        return False
    tokens = {normalize_site_key(part) for part in raw.split(',') if part.strip()}
    return any(normalize_site_key(name) in tokens for name in (site.name, site.sub_group, site.provider_name) if name)


def split_actor_prefix(title: str) -> tuple[str, str]:
    words = title.split()
    cut = 2
    if len(words) > cut and words[cut].lower() == 'and':
        cut += 3
    return ' '.join(words[:cut]), ' '.join(words[cut:])


def strip_actor_prefix(title: str) -> str:
    return split_actor_prefix(title)[1]


def actor_strip_candidates(title: str) -> list[str]:
    words = title.split()
    out = [title]
    for n in (1, 2, 3, 4):
        if len(words) <= n:
            break
        rest = words[n:]
        out.append(' '.join(rest))
        if rest[0].lower() == 'and':
            out.extend(' '.join(rest[m:]) for m in (2, 3, 4) if len(rest) > m)
    return list(dict.fromkeys(c for c in out if c))


def best_title_score(query: str, title: str, site: ResolvedSiteInfo) -> int:
    if not enabled_for(site):
        return title_distance_score(query, title)
    return max(title_distance_score(q, title) for q in actor_strip_candidates(query))
