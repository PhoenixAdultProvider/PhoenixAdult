"""Check and maintain the web UI string files.

phoenixadult/i18n/en.po holds every string the web pages show, by key, in
sections that follow the pages. Code only ever names the key.

    python -m scripts.i18n check          missing keys, unused keys, bad placeholders
    python -m scripts.i18n init <lang>    start <lang>.po from en.po, English as comments
    python -m scripts.i18n update         add new keys to / drop removed keys from every <lang>.po
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

from babel.messages.extract import extract_from_file
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'phoenixadult'
STRINGS_DIR = PACKAGE / 'i18n'
ENGLISH = STRINGS_DIR / 'en.po'
KEY = re.compile(r'^[a-z0-9_]+(\.[a-z0-9_]+)+$')
PLACEHOLDER = re.compile(r'%\(\w+\)s|\{\w+\}')
BARE_PERCENT = re.compile(r'%(?!\(\w+\)s|%)')
SECTION = re.compile(r'^# ── (.+) ──$')
STRINGS_CALL = re.compile(r'strings\(([^)]*)\)')
SCRIPT_REF = re.compile(r'\bT\.([a-z0-9_]+)\b')


def _sources() -> Iterator[Path]:
    for path in sorted(PACKAGE.rglob('*')):
        if 'graveyard' in path.parts or '__pycache__' in path.parts:
            continue
        if path.suffix in ('.py', '.html'):
            yield path


def used_keys() -> dict[str, list[str]]:
    from phoenixadult.config.env_catalog import ENV_CATALOG

    used: dict[str, list[str]] = {}
    for path in _sources():
        method = 'jinja2.ext.babel_extract' if path.suffix == '.html' else 'python'
        for _lineno, message, _comments, _context in extract_from_file(method, path):
            for key in message if isinstance(message, tuple) else (message,):
                if key:
                    used.setdefault(key, []).append(path.relative_to(ROOT).as_posix())
    for spec in ENV_CATALOG:
        for key in spec.text_keys():
            used.setdefault(key, []).append('phoenixadult/config/env_catalog.py')
    return used


def read_strings(path: Path) -> dict[str, str]:
    with path.open('rb') as fp:
        return {str(m.id): str(m.string) for m in read_po(fp) if m.id}


def script_keys(english: dict[str, str]) -> tuple[dict[str, list[str]], list[str]]:
    used: dict[str, list[str]] = {}
    errors: list[str] = []
    for path in _sources():
        if path.suffix != '.html':
            continue
        source = path.read_text(encoding='utf-8')
        sections = [s for call in STRINGS_CALL.findall(source) for s in re.findall(r"'([a-z0-9_]+)'", call)]
        where = path.relative_to(ROOT).as_posix()
        for name in sorted(set(SCRIPT_REF.findall(source))):
            found = [f'{section}.{name}' for section in sections if f'{section}.{name}' in english]
            if len(found) == 1:
                used.setdefault(found[0], []).append(where)
            else:
                errors.append(f'{where}: T.{name} is {"ambiguous" if found else "missing"} in strings({", ".join(sections)})')
    return used, errors


def problems() -> list[str]:
    english = read_strings(ENGLISH)
    used = used_keys()
    scripted, out = script_keys(english)
    for key, where in scripted.items():
        used.setdefault(key, []).extend(where)
    out += [f'not a key: {key!r} in {", ".join(sorted(set(where)))}' for key, where in used.items() if not KEY.match(key)]
    out += [f'missing from en.po: {key} (used in {", ".join(sorted(set(where)))})' for key, where in used.items() if KEY.match(key) and key not in english]
    out += [f'unused in en.po: {key}' for key in english if key not in used]
    out += [f'empty text in en.po: {key}' for key, text in english.items() if not text.strip()]
    out += [f'bare % in en.po (write %% for a literal percent): {key}' for key, text in english.items() if BARE_PERCENT.search(text)]
    for other in sorted(STRINGS_DIR.glob('*.po')):
        if other == ENGLISH:
            continue
        for key, text in read_strings(other).items():
            if key not in english:
                out.append(f'{other.name}: {key} no longer exists in en.po')
            elif text and sorted(PLACEHOLDER.findall(text)) != sorted(PLACEHOLDER.findall(english[key])):
                out.append(f'{other.name}: {key} placeholders differ from English')
    return out


def _translation_file(language: str, existing: dict[str, str]) -> str:
    lines = [
        f'# PhoenixAdult web UI strings: {language}. Each English original sits in the comment above its key.\n',
        'msgid ""\n',
        'msgstr ""\n',
        f'"Language: {language}\\n"\n',
        '"Content-Type: text/plain; charset=utf-8\\n"\n',
    ]
    pending_key = ''
    for raw in ENGLISH.read_text(encoding='utf-8').splitlines():
        if SECTION.match(raw):
            lines.append(f'\n{raw}\n')
        elif raw.startswith('msgid "') and raw != 'msgid ""':
            pending_key = raw
        elif raw.startswith('msgstr "') and pending_key:
            key = pending_key[len('msgid "') : -1]
            translated = existing.get(key, '').replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'#. {raw[len("msgstr ") :]}\n{pending_key}\nmsgstr "{translated}"\n')
            pending_key = ''
    return ''.join(lines)


def init(language: str) -> None:
    target = STRINGS_DIR / f'{language}.po'
    if target.exists():
        raise SystemExit(f'{target.name} already exists; use `update`')
    target.write_text(_translation_file(language, {}), encoding='utf-8', newline='\n')
    print(f'wrote {target.relative_to(ROOT)}; add {language!r} to LANGUAGES in phoenixadult/i18n/__init__.py')


def update() -> None:
    for path in sorted(STRINGS_DIR.glob('*.po')):
        if path != ENGLISH:
            path.write_text(_translation_file(path.stem, read_strings(path)), encoding='utf-8', newline='\n')
            print(f'updated {path.name}')


def main(argv: list[str]) -> int:
    command = argv[0] if argv else ''
    if command == 'check':
        found = problems()
        for line in found:
            print(line)
        return 1 if found else 0
    if command == 'init' and len(argv) == 2:
        init(argv[1])
        return 0
    if command == 'update':
        update()
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
