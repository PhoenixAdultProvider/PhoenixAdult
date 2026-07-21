from __future__ import annotations

from app.config.env import env
from app.registry import normalize_site_key
from app.utils.helpers.helpers import title_distance_score


def enabled_for(site_name: str) -> bool:
    """Whether SEARCH_STRIP_ACTORS lists this site (names compared registry-normalized)."""
    raw = env.search_strip_actors_raw or ''
    if not raw.strip():
        return False
    want = normalize_site_key(site_name)
    return any(normalize_site_key(part) == want for part in raw.split(',') if part.strip())


def split_actor_prefix(title: str) -> tuple[str, str]:
    """(actors, rest): the first two words, extended past a following "and First Last"."""
    words = title.split()
    cut = 2
    if len(words) > cut and words[cut].lower() == 'and':
        cut += 3
    return ' '.join(words[:cut]), ' '.join(words[cut:])


def strip_actor_prefix(title: str) -> str:
    """The primary stripped candidate, for callers that need a single query string."""
    return split_actor_prefix(title)[1]


def actor_strip_candidates(title: str) -> list[str]:
    """Scoring candidates: the original title first, then variants dropping 1-4 leading
    words (1-word stage names through 3-word names), each also extended past a following
    "and <1-3 word name>". The best candidate wins on distance, so a wrong strip can
    never lower a score."""
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


def best_title_score(query: str, title: str, site_name: str) -> int:
    """title_distance_score, taking the best over actor-stripped query candidates when
    SEARCH_STRIP_ACTORS enables the site; plain scoring otherwise."""
    if not enabled_for(site_name):
        return title_distance_score(query, title)
    return max(title_distance_score(q, title) for q in actor_strip_candidates(query))
