import re

__version__ = '1.0.0a491'


def provider_version() -> str:
    return re.sub(r'a(\d+)$', r'-alpha.\1', __version__)
