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
_QUOTED_SPAN_RE = re.compile(r'"([ \t]*)([^"]*?)([ \t]*)"')
_UNPAIRED_QUOTE_RE = re.compile(r'(?<![^\s])"[ \t]+(?=[^"]*$)')
_CLOSE_FOLLOWERS = '.,;:!?)]}'
_HORIZONTAL_WS_RE = re.compile(r'[^\S\n]+')
_AROUND_NEWLINE_RE = re.compile(r'[^\S\n]*\n[^\S\n]*')
_SPACED_DOTS_RE = re.compile(r'\.[ \t]*\.[ \t]*\.')


def _tighten_span(m: re.Match[str]) -> str:
    lead, body, trail = m.group(1), m.group(2), m.group(3)
    if not body.strip():
        return m.group(0)
    src = m.string
    before = src[m.start() - 1] if m.start() else ' '
    after = src[m.end()] if m.end() < len(src) else ' '
    open_is_free = before.isspace()
    close_is_free = after.isspace() or after in _CLOSE_FOLLOWERS
    return '"' + ('' if open_is_free else lead) + body + ('' if close_is_free else trail) + '"'


def _tighten_quotes(text: str) -> str:
    text = _QUOTED_SPAN_RE.sub(_tighten_span, text)
    if text.count('"') % 2:
        text = _UNPAIRED_QUOTE_RE.sub('"', text)
    return text


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
    text = _tighten_quotes(text)
    text = _HORIZONTAL_WS_RE.sub(' ', text)
    text = _SPACED_DOTS_RE.sub('...', text)
    text = _AROUND_NEWLINE_RE.sub('\n', text)
    return text.strip()
