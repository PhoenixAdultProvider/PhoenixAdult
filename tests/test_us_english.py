from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UK_SPELLINGS = (
    'colour',
    'centre',
    'centred',
    'centring',
    'behaviour',
    'organise',
    'organisation',
    'normalisation',
    'recognise',
    'initialise',
    'analyse',
    'catalogue',
    'favourite',
    'licence',
    'defence',
    'programme',
    'labelled',
    'modelled',
    'travelled',
    'fulfil',
    'enrol',
    'apologise',
    'customise',
    'optimise',
    'summarise',
    'prioritise',
    'serialise',
    'sanitise',
)

# Verbatim third-party text and scraped site data keep whatever spelling they shipped with.
EXEMPT = (
    'LICENSE',
    'phoenixadult/routes/html/fonts/',
    'tests/health/fixtures.json',
    'phoenixadult/clients/',
    'phoenixadult/utils/genres/_data/',
    'tests/test_us_english.py',
    'package-lock.json',
)

_PATTERN = re.compile(r'\b(' + '|'.join(UK_SPELLINGS) + r')[a-z]*\b', re.IGNORECASE)


def _tracked_text_files() -> list[Path]:
    out = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    keep = ('.py', '.html', '.md', '.css', '.json', '.txt', '.toml', '.cfg')
    return [ROOT / line for line in out.splitlines() if line.endswith(keep) and not any(part in line for part in EXEMPT)]


def test_the_repo_uses_us_english() -> None:
    offenders: list[str] = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            found = _PATTERN.search(line)
            if found:
                offenders.append(f'{path.relative_to(ROOT).as_posix()}:{number}: {found.group(0)}')
    assert not offenders, 'use US English:\n' + '\n'.join(offenders[:25])
