from __future__ import annotations

import importlib
import inspect
import pkgutil

from phoenixadult.clients.base import Client, Enricher, set_enricher_factory
from phoenixadult.registry import SITE_DEFINITIONS

_NOT_A_SCRAPER = {'phoenixadult.clients.aggregators.data18'}


def _owned_public_classes(module: object, name: str) -> list[type]:
    return [value for key, value in vars(module).items() if inspect.isclass(value) and value.__module__ == name and not key.startswith('_')]


def _discover() -> dict[str, Client]:
    found: dict[str, Client] = {}
    origin: dict[str, str] = {}
    for name in sorted(info.name for info in pkgutil.walk_packages(__path__, f'{__name__}.') if not info.ispkg):
        if any(part.startswith('_') for part in name.split('.')):
            continue

        module = importlib.import_module(name)
        owned = _owned_public_classes(module, name)
        clients: list[type[Client]] = [cls for cls in owned if issubclass(cls, Client) and cls is not Client]
        strays = [cls.__name__ for cls in owned if cls not in clients and cls is not Client and cls.__name__.endswith('Client')]
        if strays:
            raise RuntimeError(f'{name} defines {strays}, which do not subclass Client, so they would never be registered')

        if name in _NOT_A_SCRAPER or not clients:
            continue

        if len(clients) > 1:
            raise RuntimeError(f'{name} defines {[cls.__name__ for cls in clients]}; a client module must own exactly one scraper class')

        cls = clients[0]
        key = cls.scraper_type or name.rsplit('.', 1)[-1]
        if key in origin:
            raise RuntimeError(f'scraper_type "{key}" is claimed by both {origin[key]} and {name}')

        origin[key] = name
        found[key] = cls()

    return found


CLIENT_REGISTRY: dict[str, Client] = _discover()


def get_client(scraper_type: str) -> Client | None:
    return CLIENT_REGISTRY.get(scraper_type)


def is_paced(scraper_type: str) -> bool:
    client = CLIENT_REGISTRY.get(scraper_type)
    return client is not None and client.pacer is not None


def _assert_registry_consistent() -> None:
    missing = sorted({s.scraper_config.type for s in SITE_DEFINITIONS} - CLIENT_REGISTRY.keys())
    if missing:
        raise RuntimeError(f'selector scraper_type(s) with no registered client: {", ".join(missing)}')


_assert_registry_consistent()


def _make_enricher() -> Enricher:
    from phoenixadult.clients.aggregators import data18

    return data18.Data18Client()


set_enricher_factory(_make_enricher)
