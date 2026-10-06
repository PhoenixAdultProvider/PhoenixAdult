from __future__ import annotations

import gettext as _gettext
import os
from functools import cache
from io import BytesIO
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

STRINGS_DIR = Path(__file__).parent
DEFAULT_LANGUAGE = 'en'
LANGUAGES: dict[str, str] = {'en': 'English'}


def N_(key: str) -> str:
    return key


def current_language() -> str:
    code = (os.environ.get('UI_LANGUAGE') or DEFAULT_LANGUAGE).strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def _load(language: str) -> _gettext.GNUTranslations:
    with (STRINGS_DIR / f'{language}.po').open('rb') as fp:
        catalog = read_po(fp, locale=language)
    compiled = BytesIO()
    write_mo(compiled, catalog)
    compiled.seek(0)
    return _gettext.GNUTranslations(compiled)


@cache
def translations(language: str) -> _gettext.NullTranslations:
    english = _load(DEFAULT_LANGUAGE)
    if language == DEFAULT_LANGUAGE:
        return english
    chosen = _load(language)
    chosen.add_fallback(english)
    return chosen


@cache
def _english_keys() -> tuple[str, ...]:
    with (STRINGS_DIR / f'{DEFAULT_LANGUAGE}.po').open('rb') as fp:
        return tuple(str(m.id) for m in read_po(fp) if m.id)


def gettext(key: str) -> str:
    return translations(current_language()).gettext(key)


def strings(*sections: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in _english_keys():
        section, _, name = key.partition('.')
        if section in sections and '.' not in name:
            out[name] = gettext(key)
    return out


def ngettext(singular: str, plural: str, n: int) -> str:
    return translations(current_language()).ngettext(singular, plural, n)
