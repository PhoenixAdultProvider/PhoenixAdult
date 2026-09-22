from __future__ import annotations

from typing import Any

from phoenixadult.utils.helpers.data_files import load_data

_RAW: dict[str, dict[str, Any]] = load_data(__file__, 'reptyle_networks')


def _entries(network: dict[str, Any]) -> list[dict[str, Any]]:
    return [{'name': e} if isinstance(e, str) else e for e in network['sites']]


def reptyle_subnetworks() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, network in _RAW.items():
        if network.get('subnetwork') is False:
            continue
        out[name] = [e['name'] for e in _entries(network) if e.get('subsite') is not False]
    return out


def reptyle_aliases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {name: [] for name in _RAW}
    for name, network in _RAW.items():
        for entry in _entries(network):
            site = entry.get('site', name)
            alias = entry.get('alias', entry['name'])
            if site is False or alias is False:
                continue
            out[site].append(alias)
    return {name: sorted(aliases) for name, aliases in out.items()}
