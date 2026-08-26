__version__ = '1.0.0a472'


def provider_version() -> str:
    import re

    return re.sub(r'a(\d+)$', r'-alpha.\1', __version__)
