from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_OPTIONAL = {'cv2', 'numpy', 'playwright', 'curl_cffi', 'cairosvg'}
_LOCAL = {'phoenixadult', 'tests', 'scripts'}
_IMPORT_NAMES = {
    'Pillow': 'PIL',
    'python-dotenv': 'dotenv',
    'python-slugify': 'slugify',
    'python-dateutil': 'dateutil',
    'text-unidecode': 'text_unidecode',
    'argon2-cffi': 'argon2',
    'pytest-httpx2': 'pytest_httpx2',
    'pytest-asyncio': 'pytest_asyncio',
    'pytest-cov': 'pytest_cov',
}


def _declared(section: list[str]) -> set[str]:
    names = set()
    for spec in section:
        raw = spec.split(';')[0].split('[')[0]
        for sep in ('>=', '==', '<=', '~=', '>', '<', '!='):
            raw = raw.split(sep)[0]
        name = raw.strip()
        names.add(_IMPORT_NAMES.get(name, name.replace('-', '_')).lower())
    return names


def _imports(*roots: str) -> dict[str, set[str]]:
    stdlib = set(sys.stdlib_module_names)
    found: dict[str, set[str]] = {}
    for root in roots:
        for path in (_ROOT / root).rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mods = [node.module]
                else:
                    continue
                for module in mods:
                    top = module.split('.')[0]
                    if top and top not in stdlib and top not in _LOCAL and top not in _OPTIONAL:
                        found.setdefault(top, set()).add(str(path.relative_to(_ROOT)))
    return found


def _pyproject() -> dict:
    return tomllib.loads((_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))


def test_runtime_imports_are_declared_dependencies() -> None:
    declared = _declared(_pyproject()['project']['dependencies'])
    undeclared = {mod: files for mod, files in _imports('phoenixadult', 'scripts').items() if mod.lower() not in declared}
    assert not undeclared, f'runtime imports missing from [project.dependencies]: { {k: sorted(v)[:2] for k, v in undeclared.items()} }'


def test_test_suite_imports_are_declared_somewhere() -> None:
    project = _pyproject()['project']
    declared = _declared(project['dependencies']) | _declared(project['optional-dependencies']['dev'])
    undeclared = {mod: files for mod, files in _imports('tests').items() if mod.lower() not in declared}
    assert not undeclared, f'test imports missing from dependencies or the dev extra: { {k: sorted(v)[:2] for k, v in undeclared.items()} }'


def _optional_import_nodes(tree: ast.AST) -> set[int]:
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            mods = [node.module]
        else:
            continue
        if any(m.split('.')[0] in _OPTIONAL for m in mods):
            nodes.add(id(node))
    return nodes


def test_optional_imports_stay_behind_a_guard() -> None:
    for path in (_ROOT / 'phoenixadult').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        optional = _optional_import_nodes(tree)
        if not optional:
            continue
        guarded: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and any(isinstance(h.type, ast.Name) and h.type.id == 'ImportError' for h in node.handlers):
                for stmt in node.body:
                    guarded |= _optional_import_nodes(stmt)
        unguarded = optional - guarded
        assert not unguarded, f'{path.relative_to(_ROOT)} imports an optional package without an ImportError guard'
