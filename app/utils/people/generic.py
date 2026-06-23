from __future__ import annotations

from app.config.env import env
from app.utils.people.types import Gender

_DEFAULT_FEMALE_URL = 'https://t3.ftcdn.net/jpg/00/97/03/72/360_F_97037264_ZZfCG8aa12o7NEZmnhVHGW49VOdfYcxy.jpg'
_DEFAULT_MALE_URL = 'https://t3.ftcdn.net/jpg/01/13/46/18/240_F_113461869_W12s5AqhOOZF0YT3n3izlwQLzj82MGsj.jpg'


def generic_image_enabled() -> bool:
    return env.generic_image_enabled


def generic_image_url(gender: Gender) -> str:
    if gender == 'female':
        return env.generic_female_url_raw or _DEFAULT_FEMALE_URL
    if gender == 'male':
        return env.generic_male_url_raw or _DEFAULT_MALE_URL
    return ''


def gender_enabled() -> bool:
    return env.gender_enabled
