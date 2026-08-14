from __future__ import annotations

import re

import ftfy

_FTFY_CONFIG = ftfy.TextFixerConfig(fix_character_width=False, normalization=None)

_PUNCTUATION = {
    '‘': "'",
    '’': "'",
    '′': "'",
    '`': "'",
    '“': '"',
    '”': '"',
    '„': '"',
    '″': '"',
    '…': '...',
}

_PRIVATE_USE = {
    '': '☺',
    '': '😐',
    '': '☹',
    '': '▪',
    '': '•',
    '': '➢',
    '': '✉',
    '': '✗',
    '': '✔',
}

_PRIVATE_USE_RE = re.compile(r'[-]')
_MOJIBAKE_EM_DASH_RE = re.compile('â€"')
_ORPHAN_NBSP_RE = re.compile(r'Â(?![A-Za-z])')
_LOST_APOSTROPHE_RE = re.compile(r'(?<=[0-9A-Za-z])�(?=[0-9A-Za-z])')
_PUNCTUATION_RE = re.compile('|'.join(re.escape(c) for c in _PUNCTUATION))
_QUOTE_APOSTROPHE_RE = re.compile(r'(?<=[A-Za-z])"(?=(?:t|s|d|m|ll|re|ve)\b)')
_HORIZONTAL_WS_RE = re.compile(r'[^\S\n]+')
_AROUND_NEWLINE_RE = re.compile(r'[^\S\n]*\n[^\S\n]*')
_SPACED_DOTS_RE = re.compile(r'\.[ \t]*\.[ \t]*\.')


def normalize_text(text: str | None) -> str:
    if not text:
        return ''
    text = ftfy.fix_text(text, _FTFY_CONFIG)
    text = _PRIVATE_USE_RE.sub(lambda m: _PRIVATE_USE.get(m.group(0), ''), text)
    text = _MOJIBAKE_EM_DASH_RE.sub('—', text)
    text = _ORPHAN_NBSP_RE.sub('', text)
    text = _LOST_APOSTROPHE_RE.sub("'", text).replace('�', '')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _PUNCTUATION_RE.sub(lambda m: _PUNCTUATION[m.group(0)], text)
    text = _QUOTE_APOSTROPHE_RE.sub("'", text)
    text = _HORIZONTAL_WS_RE.sub(' ', text)
    text = _SPACED_DOTS_RE.sub('...', text)
    text = _AROUND_NEWLINE_RE.sub('\n', text)
    return text.strip()
