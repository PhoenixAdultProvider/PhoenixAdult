from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent / 'phoenixadult'

_LAYERS = ('models', 'config', 'utils', 'registry', 'clients', 'mappers', 'services', 'routes')
_RANK = {name: i for i, name in enumerate(_LAYERS)}

_KNOWN_UPWARD = {
    ('utils', 'services'): {'utils/auth/provider_guard.py'},
    ('utils', 'clients'): {'utils/cache/search_store.py', 'utils/helpers/graphql_client.py'},
    ('utils', 'registry'): {'utils/cache/__init__.py'},
    ('config', 'utils'): {'config/env_overrides.py'},
}


def _layer(module: str) -> str | None:
    parts = module.split('.')
    return parts[1] if len(parts) > 1 and parts[0] == 'phoenixadult' and parts[1] in _RANK else None


def _module_scope_imports(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    out: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            out.extend((alias.name, node.lineno) for alias in node.names)
    return out


def test_no_new_upward_dependencies() -> None:
    violations: list[str] = []
    for path in sorted(_ROOT.rglob('*.py')):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith(('graveyard/', 'local/')):
            continue
        source = _layer(f'phoenixadult.{rel.split("/")[0]}')
        if source is None:
            continue
        for module, line in _module_scope_imports(path):
            target = _layer(module)
            if target is None or _RANK[target] <= _RANK[source]:
                continue
            if rel in _KNOWN_UPWARD.get((source, target), set()):
                continue
            violations.append(f'{rel}:{line} imports {module} ({source} -> {target})')
    assert not violations, 'a lower layer reached upward:\n  ' + '\n  '.join(violations)


def test_the_known_upward_edges_are_still_the_only_ones() -> None:
    remaining = {f for files in _KNOWN_UPWARD.values() for f in files}
    for rel in remaining:
        assert (_ROOT / rel).exists(), f'{rel} is gone — drop it from _KNOWN_UPWARD so the list stays honest'
    assert len(remaining) == 5, 'this count only goes down; update it when an edge is removed'


def test_models_depends_on_nothing_above_it() -> None:
    for path in sorted((_ROOT / 'models').rglob('*.py')):
        for module, line in _module_scope_imports(path):
            target = _layer(module)
            assert target in (None, 'models'), f'models/{path.name}:{line} imports {module}'
