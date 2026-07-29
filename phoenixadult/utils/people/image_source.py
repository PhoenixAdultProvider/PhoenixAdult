from __future__ import annotations

from urllib.parse import urlsplit

SCENE_SOURCE = 'Scene'
GENERIC_SOURCE = 'Generic'

_BY_HOST: dict[str, str] = {
    'iafd.com': 'IAFD',
    'adultempire.com': 'AdultDVDEmpire',
    'adultdvdempire.com': 'AdultDVDEmpire',
    'indexxx.com': 'Indexxx',
    'babepedia.com': 'Babepedia',
    'babesandstars.com': 'Babes and Stars',
    'boobpedia.com': 'Boobpedia',
    'javdatabase.com': 'JAVDatabase',
    'javbus.com': 'JAVBus',
    'freeones.com': 'Freeones',
}


KNOWN_SOURCES: tuple[str, ...] = (SCENE_SOURCE, GENERIC_SOURCE, *sorted(set(_BY_HOST.values())))


def _registrable(host: str) -> str:
    parts = host.lower().split(':')[0].split('.')
    return '.'.join(parts[-2:]) if len(parts) >= 2 else ''


def source_for_url(url: str) -> str:
    from phoenixadult.utils.people.generic import generic_image_url

    if not url:
        return ''
    if url in {generic_image_url('female'), generic_image_url('male')}:
        return GENERIC_SOURCE
    host = urlsplit(url).hostname or ''
    return _BY_HOST.get(_registrable(host), '')
