from __future__ import annotations

import tomllib
from pathlib import Path

import phoenixadult
from phoenixadult.registry import PROVIDER_DEFINITIONS

_PYPROJECT = Path(__file__).resolve().parent.parent / 'pyproject.toml'


def _project() -> dict[str, object]:
    return dict(tomllib.loads(_PYPROJECT.read_text(encoding='utf-8'))['project'])


def test_pyproject_derives_its_version_from_the_package() -> None:
    project = _project()
    assert 'version' not in project, 'a literal version in pyproject.toml would drift from phoenixadult.__version__'
    assert 'version' in project['dynamic'], 'pyproject must declare the version dynamic'


def test_setuptools_points_at_the_one_literal() -> None:
    tools = tomllib.loads(_PYPROJECT.read_text(encoding='utf-8'))['tool']['setuptools']
    assert tools['dynamic']['version'] == {'attr': 'phoenixadult.__version__'}


def test_plex_is_told_the_same_version_the_package_carries() -> None:
    assert PROVIDER_DEFINITIONS[0].version == phoenixadult.provider_version()


def test_the_plex_form_spells_the_alpha_out() -> None:
    assert phoenixadult.provider_version().startswith(phoenixadult.__version__.split('a')[0] + '-alpha.')
    assert phoenixadult.provider_version().rsplit('.', 1)[1] == phoenixadult.__version__.rsplit('a', 1)[1]


def test_no_module_hardcodes_a_version_string() -> None:
    import re

    root = _PYPROJECT.parent / 'phoenixadult'
    pattern = re.compile(r"""version\s*=\s*['"]\d+\.\d+\.\d+""")
    offenders = [
        f'{path.relative_to(root).as_posix()}:{n}'
        for path in root.rglob('*.py')
        if path.name != '__init__.py' or path.parent != root
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1)
        if pattern.search(line)
    ]
    assert not offenders, f'these hardcode a version instead of deriving it from __version__: {offenders}'


def test_the_asgi_app_reports_the_package_version() -> None:
    from phoenixadult.app_factory import create_app

    assert create_app().version == phoenixadult.__version__
