from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / 'phoenixadult'


def _default_executor_calls(tree: ast.AST) -> list[int]:
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == 'to_thread':
            lines.append(node.lineno)
        elif node.func.attr == 'run_in_executor' and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is None:
            lines.append(node.lineno)
    return lines


def test_the_default_executor_is_left_to_dns_lookups() -> None:
    found = {
        str(path.relative_to(PACKAGE.parent)): lines
        for path in PACKAGE.rglob('*.py')
        if 'graveyard' not in path.parts and (lines := _default_executor_calls(ast.parse(path.read_text(encoding='utf-8'))))
    }
    assert not found, f'use pools.run_in(<pool>, ...) instead: {found}'
