from __future__ import annotations

from phoenixadult.config.env import env
from phoenixadult.config.env_catalog import DEFAULT_FEMALE_IMAGE_URL, DEFAULT_MALE_IMAGE_URL
from phoenixadult.utils.people.types import Gender


def generic_image_enabled() -> bool:
    return env.generic_image_enabled


def generic_image_url(gender: Gender) -> str:
    if gender == 'female':
        return env.generic_female_url_raw or DEFAULT_FEMALE_IMAGE_URL
    if gender == 'male':
        return env.generic_male_url_raw or DEFAULT_MALE_IMAGE_URL
    return ''


def gender_skip_male_enabled() -> bool:
    return env.gender_skip_male_enabled
