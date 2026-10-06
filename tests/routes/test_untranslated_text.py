from __future__ import annotations

import gettext
import re
from html.parser import HTMLParser

import pytest

from phoenixadult import i18n

MARK = '¤'
WORD = re.compile(r'[A-Za-z]{2,}')
ATTRS = {'title', 'placeholder', 'aria-label', 'alt', 'label'}
NOT_PROSE = re.compile(r'^(JSON|YYYY|X-Plex-Client-Identifier…|[\w.{}…-]+\.\w+|https?://\S*)$')
DATA_TAGS = {'script', 'style', 'tbody', 'code'}


class _Marked(gettext.NullTranslations):
    def gettext(self, message: str) -> str:
        return MARK

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return MARK


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skipping: list[str] = []
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DATA_TAGS or (tag == 'a' and dict(attrs).get('class') == 'nav-user'):
            self.skipping.append(tag)
        if not self.skipping:
            self.found += [f'{tag}@{k}={v.strip()}' for k, v in attrs if k in ATTRS and v and _prose(v)]

    def handle_endtag(self, tag: str) -> None:
        if self.skipping and self.skipping[-1] == tag:
            self.skipping.pop()

    def handle_data(self, data: str) -> None:
        if not self.skipping and _prose(data):
            self.found.append(data.strip())


def _prose(text: str) -> bool:
    text = text.replace('PhoenixAdult', '').strip()
    return bool(WORD.search(text)) and not NOT_PROSE.match(text)


def _untranslated(html: str) -> list[str]:
    parser = _Text()
    parser.feed(html)
    return parser.found


@pytest.fixture
def marked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(i18n, 'translations', lambda language: _Marked())


def test_every_visible_page_string_comes_from_the_strings_file(marked: None, pages: dict[str, str]) -> None:
    assert all(MARK in html for html in pages.values()), 'pages rendered without the marked catalog'
    leaks = {name: found for name, html in pages.items() if (found := _untranslated(html))}
    assert not leaks, f'text not routed through phoenixadult/i18n/en.po: {leaks}'


def test_the_guard_catches_a_hardcoded_label() -> None:
    assert _untranslated('<button title="Save it">¤</button><p>Hello there</p>') == ['button@title=Save it', 'Hello there']
