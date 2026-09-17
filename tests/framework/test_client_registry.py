from __future__ import annotations

import ast
import pathlib

import pytest

from phoenixadult.clients import CLIENT_REGISTRY
from phoenixadult.clients.base import Client
from phoenixadult.registry import SITE_DEFINITIONS, find_site

_CLIENTS = pathlib.Path(__file__).resolve().parents[2] / 'phoenixadult' / 'clients'

_A_SITE_FOR: dict[str, str] = {}
for _site in SITE_DEFINITIONS:
    _A_SITE_FOR.setdefault(_site.scraper_config.type, _site.name)


@pytest.mark.parametrize('scraper_type', sorted(CLIENT_REGISTRY))
def test_every_client_is_registered_under_the_key_it_claims(scraper_type: str) -> None:
    client = CLIENT_REGISTRY[scraper_type]
    assert isinstance(client, Client)
    declared = type(client).scraper_type
    inferred = type(client).__module__.rsplit('.', 1)[-1]
    assert scraper_type == (declared or inferred), f'{type(client).__name__} is filed under {scraper_type!r} but claims {declared or inferred!r}'


@pytest.mark.parametrize('scraper_type', sorted(CLIENT_REGISTRY))
def test_every_client_answers_for_one_of_its_sites(scraper_type: str) -> None:
    site = find_site(_A_SITE_FOR[scraper_type])
    assert site is not None
    client = CLIENT_REGISTRY[scraper_type]
    assert client.tag(site), f'{scraper_type} produced no tag for {site.name}'
    studio = client.studio_for(site)
    assert studio is None or studio.strip(), f'{scraper_type} produced a blank studio for {site.name}'


def test_no_client_module_imports_the_package_root() -> None:
    offenders: list[str] = []
    for path in sorted(_CLIENTS.rglob('*.py')):
        for node in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(node, ast.ImportFrom) and node.module == 'phoenixadult.clients' and node.level == 0:
                offenders.append(f'{path.name}:{node.lineno}')

    assert not offenders, f'these would re-enter a half-built package while discovery is still walking it: {offenders}'
