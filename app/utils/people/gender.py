from __future__ import annotations

from app.config.env import env
from app.utils.people.sources.iafd import iafd_best_match
from app.utils.people.types import Gender


def gender_detect_enabled() -> bool:
    return env.gender_detect_enabled


async def iafd_gender_check(actor_name: str) -> Gender:
    """Resolve a performer's gender via IAFD's comprehensive search.

    Thin wrapper over the shared IAFD matcher (same search + anti-bot bypass used
    for headshot lookup); returns '' on no match / any failure.
    """
    match = await iafd_best_match(actor_name)
    return match[1] if match else ''
