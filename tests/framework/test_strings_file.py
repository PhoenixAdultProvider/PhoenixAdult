from __future__ import annotations

from scripts import i18n as strings_tool


def test_the_strings_file_matches_the_code() -> None:
    assert strings_tool.problems() == [], 'run `python -m scripts.i18n check` for details'
