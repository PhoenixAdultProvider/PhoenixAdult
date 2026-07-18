#!/usr/bin/env python3
"""Fail if a diff adds a disallowed ``#`` comment under app/ or tests/.

The zero-comment policy allows only docstrings, tooling pragmas (type:/noqa/…),
and section banners; all other rationale goes in the commit message. This gate
flags newly added comment lines so they are removed before the commit lands.

Usage:
    check_comments.py                 # check staged changes (pre-commit)
    check_comments.py <base>..<head>  # check a commit range (CI)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tokenize
from io import StringIO

_ALLOWED_PREFIXES = ('type:', 'noqa', 'fmt:', 'ruff:', 'mypy:', 'pylint', 'pragma', 'isort:', 'nosec')
_BOX_DRAWING = set('─═')
_ASCII_DIVIDER = set('-=~*·•#. ')
_HUNK = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@')


def _git(*args: str) -> str:
    return subprocess.run(['git', *args], capture_output=True, encoding='utf-8', check=True).stdout


def _is_allowed(comment: str) -> bool:
    body = comment.lstrip('#').strip()
    if not body:
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


def main() -> int:
    rng = sys.argv[1] if len(sys.argv) > 1 else None
    diff_args = [rng] if rng else ['--cached']
    files = [
        f
        for f in _git('diff', *diff_args, '--name-only', '--diff-filter=ACM').splitlines()
        if f.endswith('.py') and (f.startswith('app/') or f.startswith('tests/'))
    ]

    violations: list[str] = []
    for path in files:
        spec = f'{rng.split("..")[-1]}:{path}' if rng else f':{path}'
        try:
            src = _git('show', spec)
        except subprocess.CalledProcessError:
            continue
        added = _added_lines(diff_args, path)
        for lineno, text in _comment_lines(src).items():
            if lineno in added and not _is_allowed(text):
                violations.append(f'{path}:{lineno}: {text.strip()}')

    if violations:
        sys.stderr.write('Disallowed comments added (remove them; put rationale in the commit message):\n')
        for v in violations:
            sys.stderr.write(f'  {v}\n')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
