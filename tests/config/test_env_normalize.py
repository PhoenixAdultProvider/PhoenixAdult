from __future__ import annotations

import pytest

from phoenixadult.config.env_catalog import EnvVarSpec, normalize_env_value


def _spec(kind: str, **extra: object) -> EnvVarSpec:
    return EnvVarSpec(key='X', group='g', kind=kind, **extra)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ('spec', 'raw', 'expected'),
    [
        (_spec('boolean'), ' true ', (True, 'true')),
        (_spec('boolean'), 'yes', (False, 'X must be On or Off')),
        (_spec('number', min=1, max=10), '007', (True, '7')),
        (_spec('number'), '-3', (True, '-3')),
        (_spec('number'), '1.5', (False, 'X must be an integer')),
        (_spec('number', min=1), '0', (False, 'X must be ≥ 1')),
        (_spec('number', max=10), '11', (False, 'X must be ≤ 10')),
        (_spec('bytes'), '2K', (True, '2048')),
        (_spec('bytes'), 'lots', (False, 'X must be a size like 20M, 2000K or 100B')),
        (_spec('enum', options=['a', 'b']), 'b', (True, 'b')),
        (_spec('enum', options=['a', 'b']), 'c', (False, 'X must be one of: a, b')),
        (_spec('enum'), 'anything', (True, 'anything')),
        (_spec('list'), ' a , ,b(', (True, 'a,b(')),
        (_spec('list', pattern_items=True), 'a, b(', (False, "X entry 'b(' is not a valid pattern: missing ), unterminated subpattern at position 1")),
        (_spec('string'), '  kept as is ', (True, 'kept as is')),
    ],
)
def test_each_kind_normalizes_or_explains(spec: EnvVarSpec, raw: str, expected: tuple[bool, str]) -> None:
    assert normalize_env_value(spec, raw) == expected
