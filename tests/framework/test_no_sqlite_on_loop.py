from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / 'phoenixadult'
STORES = {'scene_store', 'search_store', 'user_store', 'user_tokens', 'client_hits', 'plex_connections', 'face_crop_log', 'maintenance'}
WRAPPERS = {'run_in', 'to_thread', 'run_in_executor'}


def _store_calls(node: ast.AST) -> list[str]:
    found = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr in WRAPPERS or isinstance(func, ast.Name) and func.id in WRAPPERS:
                continue
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in STORES:
                found.append(f'{func.value.id}.{func.attr} @{child.lineno}')
        found += _store_calls(child)
    return found


def test_async_code_hands_sqlite_work_to_a_pool() -> None:
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE.rglob('*.py'):
        if 'graveyard' in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.AsyncFunctionDef) and (calls := _store_calls(node)):
                offenders[f'{path.relative_to(PACKAGE.parent)}:{node.name}'] = calls
    assert not offenders, f'a busy database stalls the whole event loop for up to busy_timeout; wrap these in run_in: {offenders}'
