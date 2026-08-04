#!/usr/bin/env python3
"""Fail if a diff adds a disallowed ``#`` comment or any docstring under
phoenixadult/ or tests/.

The zero-comment policy allows only tooling pragmas (type:/noqa/…) and section
banners; docstrings are not allowed at all, and every other rationale goes in the
commit message. This gate flags newly added violations so they are removed before
the commit lands. Diff mode judges only added lines, so docstrings already in the
tree are left alone until the code around them is rewritten; --all reports every
one of them.

Usage:
    check_comments.py                 # check staged changes (pre-commit)
    check_comments.py <base>..<head>  # check a commit range (CI)
    check_comments.py --all           # check every file in the repo
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tokenize
from io import StringIO
from pathlib import Path

_ALLOWED_PREFIXES = ('type:', 'noqa', 'fmt:', 'ruff:', 'mypy:', 'pylint', 'pragma', 'isort:', 'nosec')
_BOX_DRAWING = set('─═')
_ASCII_DIVIDER = set('-=~*·•#. ')
_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')
# Structural field markers labeling sections of a wholesale update() body are part of
# the client-structure convention and always allowed.
_FIELD_MARKERS = frozenset(
    {
        'title',
        'summary',
        'studio',
        'tagline',
        'release date',
        'genres',
        'actor(s)',
        'actors',
        'director(s)',
        'directors',
        'producer(s)',
        'producers',
        'collection(s)',
        'collections',
        'tagline and collection(s)',
        'posters',
        'posters from data18',
        'images',
        'trailer',
        'duration',
        'rating',
    }
)


def _git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, encoding='utf-8', check=True).stdout


def _is_allowed(comment: str) -> bool:
    body = comment.lstrip('#').strip()
    if not body:
        return True
    if body.lower() in _FIELD_MARKERS:
        return True
    if any(body.lower().startswith(p) for p in _ALLOWED_PREFIXES):
        return True
    if _BOX_DRAWING & set(body):
        return True
    return all(c in _ASCII_DIVIDER for c in body)


def _added_lines(diff_args: list[str], path: str) -> set[int]:
    out: set[int] = set()
    for raw in _git('diff', *diff_args, '--unified=0', '--', path).splitlines():
        m = _HUNK.match(raw)
        if m:
            start, count = int(m.group(1)), int(m.group(2) or '1')
            out.update(range(start, start + count))
    return out


def _comment_lines(src: str) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out[tok.start[0]] = tok.string
    except (tokenize.TokenError, IndentationError):
        pass
    return out


def _docstrings(src: str) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in [tree, *ast.walk(tree)]:
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (
            node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str)
        ):
            continue
        expr = node.body[0]
        out.append((expr.lineno, expr.end_lineno or expr.lineno, (expr.end_lineno or expr.lineno) - expr.lineno + 1))
    return out


def _changed_files(diff_args: list[str]) -> list[str]:
    return [
        f
        for f in _git('diff', *diff_args, '--name-only', '--diff-filter=ACM').splitlines()
        if f.endswith('.py') and (f.startswith('phoenixadult/') or f.startswith('tests/'))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description='Fail if a diff adds a disallowed comment or any docstring.')
    parser.add_argument('range', nargs='?', help='commit range to check (default: staged changes)')
    parser.add_argument('--all', action='store_true', help='check every file in the repo')
    opts = parser.parse_args()
    rng, scan_all = opts.range, opts.all
    if scan_all:
        rng = None
        diff_args = []
        files = sorted(str(p).replace('\\', '/') for base in ('phoenixadult', 'tests') for p in Path(base).rglob('*.py'))
    else:
        diff_args = [rng] if rng else ['--cached']
        files = _changed_files(diff_args)
        if not rng and not files:
            # Nothing staged: check the working tree instead of vacuously passing.
            diff_args = []
            files = _changed_files(diff_args)

    violations: list[str] = []
    for path in files:
        try:
            if scan_all or not diff_args:
                src = Path(path).read_text(encoding='utf-8')
            elif rng:
                src = _git('show', f'{rng.split("..")[-1]}:{path}')
            else:
                src = _git('show', f':{path}')
        except (subprocess.CalledProcessError, OSError):
            continue
        added = None if scan_all else _added_lines(diff_args, path)
        for lineno, text in _comment_lines(src).items():
            if (added is None or lineno in added) and not _is_allowed(text):
                violations.append(f'{path}:{lineno}: {text.strip()}')
        for start, end, lines in _docstrings(src):
            if added is None or added & set(range(start, end + 1)):
                violations.append(f'{path}:{start}: docstring ({lines} line(s)) - docstrings are not allowed')

    if violations:
        sys.stderr.write('Disallowed comments added (remove them; put rationale in the commit message):\n')
        for v in violations:
            sys.stderr.write(f'  {v}\n')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
