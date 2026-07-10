from __future__ import annotations

import re

_PUNCTUATION = {
    '‘': "'",  # left single curly quote
    '’': "'",  # right single curly quote / apostrophe
    '′': "'",  # prime
    '`': "'",  # backtick
    '“': '"',  # left double curly quote
    '”': '"',  # right double curly quote
    '„': '"',  # low double curly quote
    '″': '"',  # double prime
    '…': '...',  # ellipsis
}

_PUNCTUATION_RE = re.compile('|'.join(re.escape(c) for c in _PUNCTUATION))
_HORIZONTAL_WS_RE = re.compile(r'[^\S\n]+')
_AROUND_NEWLINE_RE = re.compile(r'[^\S\n]*\n[^\S\n]*')
_SPACED_DOTS_RE = re.compile(r'\.[ \t]*\.[ \t]*\.')


def normalize_text(text: str | None) -> str:
    """Straighten typographic punctuation and tidy horizontal whitespace. Newlines survive:
    summaries carry paragraph breaks."""
    if not text:
        return ''
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = _PUNCTUATION_RE.sub(lambda m: _PUNCTUATION[m.group(0)], text)
    text = _HORIZONTAL_WS_RE.sub(' ', text)
    text = _SPACED_DOTS_RE.sub('...', text)
    text = _AROUND_NEWLINE_RE.sub('\n', text)
    return text.strip()
