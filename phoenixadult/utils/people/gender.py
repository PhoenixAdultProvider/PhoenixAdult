from __future__ import annotations

from phoenixadult.config.env import env
from phoenixadult.utils.people.sources.iafd import iafd_best_match
from phoenixadult.utils.people.types import Gender


def gender_detect_enabled() -> bool:
    return env.gender_detect_enabled


async def iafd_gender_check(actor_name: str) -> Gender:
    match = await iafd_best_match(actor_name)
    return match[1] if match else ''
