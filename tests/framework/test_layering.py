from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / 'phoenixadult'

_LAYERS = ('models', 'config', 'utils', 'registry', 'clients', 'mappers', 'services', 'routes')
_RANK = {name: i for i, name in enumerate(_LAYERS)}

_KNOWN_UPWARD = {
    ('utils', 'registry'): {
        'utils/auth/hook_middleware.py',
        'utils/cache/layout.py',
        'utils/cache/listing.py',
        'utils/cache/metadata.py',
        'utils/cache/people_backfill.py',
        'utils/processors/studio_name.py',
    },
    ('config', 'utils'): {'config/env_overrides.py'},
}


def _layer(module: str) -> str | None:
    parts = module.split('.')
    return parts[1] if len(parts) > 1 and parts[0] == 'phoenixadult' and parts[1] in _RANK else None


def _runtime_imports(path: Path) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    pending: list[ast.AST] = [ast.parse(path.read_text(encoding='utf-8'))]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.If) and 'TYPE_CHECKING' in ast.unparse(node.test):
            pending.extend(node.orelse)
            continue
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            out.extend((alias.name, node.lineno) for alias in node.names)
        pending.extend(ast.iter_child_nodes(node))
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
        for module, line in _runtime_imports(path):
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
    assert len(remaining) == 7, 'this only goes down, except when a module split moves one edge into the files that actually use it'


def test_models_depends_on_nothing_above_it() -> None:
    for path in sorted((_ROOT / 'models').rglob('*.py')):
        for module, line in _runtime_imports(path):
            target = _layer(module)
            assert target in (None, 'models'), f'models/{path.name}:{line} imports {module}'
