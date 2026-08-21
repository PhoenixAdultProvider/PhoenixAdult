from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / 'phoenixadult'
_CURSOR_CALLS = ('execute', 'executemany', 'executescript')


def _sql_literals(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr not in _CURSOR_CALLS:
            continue
        for arg in node.args[:1]:
            for piece in ast.walk(arg):
                if isinstance(piece, ast.Constant) and isinstance(piece.value, str):
                    found.append((node.lineno, piece.value))
    return found


def test_sql_never_quotes_a_literal_with_double_quotes() -> None:
    offenders: list[str] = []
    for path in sorted(_ROOT.rglob('*.py')):
        if path.parts[path.parts.index('phoenixadult') + 1] == 'graveyard':
            continue
        for line, sql in _sql_literals(ast.parse(path.read_text(encoding='utf-8'))):
            if '"' in sql:
                offenders.append(f'{path.relative_to(_ROOT).as_posix()}:{line}: {sql.strip()[:90]}')

    assert not offenders, (
        'SQLite reads "x" as an identifier first and only falls back to a string literal when the build allows it; '
        'FreeBSD builds with SQLITE_DQS=0 and raises instead. Use single quotes:\n' + '\n'.join(offenders)
    )
