from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

import phoenixadult

PACKAGE_DIR = Path(phoenixadult.__file__).parent
PYPROJECT = PACKAGE_DIR.parent / 'pyproject.toml'


def test_every_runtime_data_file_is_covered_by_package_data() -> None:
    patterns = tomllib.loads(PYPROJECT.read_text(encoding='utf-8'))['tool']['setuptools']['package-data']['phoenixadult']
    data_files = [
        f
        for f in PACKAGE_DIR.rglob('*')
        if f.is_file()
        and f.suffix not in ('.py', '.pyc')
        and '__pycache__' not in f.parts
        and f.relative_to(PACKAGE_DIR).parts[0] not in ('local', 'graveyard')
    ]
    for f in data_files:
        rel = f.relative_to(PACKAGE_DIR).as_posix()
        assert any(fnmatch.fnmatch(rel, p.replace('**/', '*')) or fnmatch.fnmatch(rel, p) for p in patterns), (
            f'{rel} is not covered by [tool.setuptools.package-data] — installed packages would miss it'
        )
