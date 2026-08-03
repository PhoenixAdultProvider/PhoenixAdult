from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from text2digits import text2digits

from phoenixadult.utils.processors.text_normalize import normalize_text

_MAX_TITLE_LENGTH = 1000


# ── Exceptions ────────────────────────────────────────────────────────────────
# fmt: off
_LOWER_EXCEPTIONS = frozenset({
    'a', 'y', 'n', 'an', 'of', 'the', 'and', 'for', 'to', 'onto', 'but', 'or', 'nor', 'at', 'with', 'vs',
    'in', 'on', 'by', 'as',
})

_TLD_FRAGMENTS = frozenset({'co', 'com', 'org', 'net', 'tv'})

_UPPER_EXCEPTIONS = frozenset({
    'bbc', 'xxx', 'bbw', 'bf', 'bff', 'bts', 'pov', 'dp', 'gf', 'bj', 'wtf', 'cfnm', 'bwc', 'fm', 'tv',
    'hd', 'milf', 'gilf', 'dilf', 'dtf', 'zz', 'xxxl', 'usa', 'nsa', 'hr', 'ii', 'iii', 'iv', 'bbq',
    'avn', 'xtc', 'atv', 'joi', 'rpg', 'wunf', 'uk', 'asap', 'sss', 'nf', 'pawg', 'ama', 'bdsm', 'oc'
})

_SPANISH_LOWER_EXCEPTIONS = frozenset({'de', 'del', 'con', 'en', 'la', 'el', 'los', 'las', 'mi', 'al', 'por', 'para', 'un', 'una', 'unos', 'unas'})

_SPANISH_SITE_KEYS = frozenset({'fakings', 'putalocura', 'sexmex', 'oyeloca'})

_TITLE_LOWER_EXCEPTIONS = frozenset({'de', 'del', 'en', 'el', 'los', 'las', 'mi', 'por', 'para', 'un', 'una', 'unos', 'unas'})

_NAME_EXCEPTIONS = frozenset({'ai'})

_NAME_EXCEPTION_SITES = frozenset({'JavBus', 'JavLibrary', 'TeamSkeet X JavHub', 'JAVDatabase', 'JAV888'})


# ── Corrections ───────────────────────────────────────────────────────────────
_MANUAL_CORRECTIONS: dict[str, str] = {
    'im': "I'm", 'theyll': "They'll", 'cant': "Can't", 'ive': "I've", 'shes': "She's", 'theyre': "They're",
    'tshirt': 'T-Shirt', 'dont': "Don't", 'wasnt': "Wasn't", 'youre': "You're", 'ill': "I'll", 'whats': "What's",
    'didnt': "Didn't", 'isnt': "Isn't", 'senor': 'Señor', 'senorita': 'Señorita', 'thats': "That's",
    'gstring': 'G-String', 'milfs': 'MILFs', 'oreilly': "O'Reilly", 'bangbros': 'BangBros', 'bday': 'B-Day',
    'dms': 'DMs', 'bffs': 'BFFs', 'ohmy': 'OhMy', 'wont': "Won't", 'whos': "Who's", 'shouldnt': "Shouldn't",
    'lasirena': 'LaSirena', 'espanol': 'Español', 'jmac': 'J-Mac', 'youd': "You'd", 'redwolf': 'RedWolf',
    'mccray': 'McCray', 'mccullough': 'McCullough', 'mccall': 'McCall', 'mccarthy': 'McCarthy', 'coachs': "Coach's",
    'escandalo': 'Escándalo', 'desilva': 'DeSilva', 'weve': "We've", 'icock': 'iCock', 'youve': "You've", 'creme': "Crème",
    'nino': 'Niño', 'que': 'Qué', 'mccoy': 'McCoy'
}

_KEEP_LOWER_FIRST = sorted(v for v in _MANUAL_CORRECTIONS.values() if v[:1].islower() and any(c.isupper() for c in v[1:]))
_KEEP_LOWER_RE = re.compile(r'\b(' + '|'.join(re.escape(v) for v in _KEEP_LOWER_FIRST) + r')\b', re.IGNORECASE) if _KEEP_LOWER_FIRST else None
_KEEP_LOWER_BY_KEY = {v.lower(): v for v in _KEEP_LOWER_FIRST}

_PHRASE_CORRECTIONS: dict[str, str] = {
    'straight a': 'Straight A',
    'strap-on': 'Strap-On',
    'kill la kill': 'Kill la Kill',
    'cruella de vil': 'Cruella de Vil',
    'los angeles': 'Los Angeles',
    'las vegas': 'Las Vegas',
    'el dorado': 'El Dorado',
    'el paso': 'El Paso',
    'en garde': 'En Garde',
    'anna de ville': 'Anna de Ville',
}

_IDIOM_CORRECTIONS: tuple[tuple[str, str], ...] = (
    (r'\b(cr[eè]me)\s+de\s+la\s+(cr[eè]me)\b', r'\1 de la \2'),
    (r'\b((?:her|his|your|their|my|our)\s+)a(\s+game\b)', r'\1A\2'),
)

_SCRAPER_PHRASE_CORRECTIONS: dict[str, dict[str, str]] = {
    'strike3': {'a game': 'A Game'},
}


# ── Word-Type Sets ────────────────────────────────────────────────────────────
_ACRONYMS = frozenset({'ai', 'vr', 'hd', 'uhd', 'sd', 'hdr', '4k', '3d', '2d'})

_CONTRACTIONS = frozenset({'re', 't', 's', 'd', 'll', 've', 'm', 'am', 'ed'})

_HONORIFICS = frozenset({
    'mr', 'mrs', 'ms', 'mx', 'mz', 'dr', 'prof', 'sr', 'jr', 'st', 'rev', 'fr',
    'sgt', 'capt', 'lt', 'col', 'gov', 'hon', 'esq', 'maj', 'cmdr', 'adm', 'det',
})

_NAME_ANYWHERE_HONORIFICS = frozenset({'st'})

_ROMAN_NUMERALS = frozenset({
    'I', 'II', 'III', 'IV', 'VI', 'VII', 'VIII', 'IX', 'X',
    'XI', 'XII', 'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX',
})

_SIZE_CODES = frozenset({'xs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl', 'xxxxl'})
# fmt: on

_INITIAL_PAIRS = frozenset({'aj', 'tj'})
_INITIAL_PAIR_RE = re.compile(
    r'(?<![\w.])(' + '|'.join(sorted(_INITIAL_PAIRS)) + r")(?='[sS](?![\w.])|\s|$)",
    re.IGNORECASE,
)
_INITIAL_PAIR_COLLAPSE_RE = re.compile(r'(?<![\w.])([A-Za-z])\.\s+([A-Za-z])\.(?![\w.])')


def collapse_initial_pairs(text: str) -> str:
    return _INITIAL_PAIR_COLLAPSE_RE.sub(lambda m: f'{m.group(1).upper()}.{m.group(2).upper()}.', text)


def expand_initial_pairs(text: str) -> str:
    return _INITIAL_PAIR_RE.sub(lambda m: '.'.join(m.group(1).upper()) + '.', text)


# ── Patterns ──────────────────────────────────────────────────────────────────
_SEQ_MARKERS = r'(?:part|pt\.?|volume|vol\.?|scene|episode|ep\.?|chapter)'
_SEQ_COLON_MARKERS = r'(?:part|pt\.?|volume|vol\.?|episode|ep\.?|chapter)'
_CONTRACTION_ALT = '|'.join(sorted(_CONTRACTIONS, key=len, reverse=True))
_SEQ_PHRASE = rf'(?P<phrase>{_SEQ_MARKERS}\s+(?P<num>\w+))'
_SEQ_COLON_PHRASE = rf'(?P<phrase>{_SEQ_COLON_MARKERS}\s+(?P<num>\w+))'

_NON_WORD_RE = re.compile(r'\W', re.UNICODE)
_ALNUM_RE = re.compile(r'[^\W_]')
_WORD_RE = re.compile(r'[A-Za-z]+')
_PURE_NUMBER_RE = re.compile(r'\d+')
_ARTICLE_RE = re.compile(r'^(the|a|an)\s+', re.IGNORECASE)
_A_BEFORE_VOWEL_RE = re.compile(r'\b([Aa])(?=\s+([AEIOUaeiou][\w.]*))')
_AN_BEFORE_WORD_RE = re.compile(r'\b([Aa])n\b(?=\s+([\w.]+))')
_A_STAYS_RE = re.compile(r'^(?:uni|use|usu|ubi|ur[ie]|u\.|uk$|ufo|eu|one$|once$|ewe)', re.IGNORECASE)
_HONORIFIC_ALT = '|'.join(sorted(_HONORIFICS, key=len, reverse=True))
_HONORIFIC_RE = re.compile(r'\b(' + _HONORIFIC_ALT + r')\b(?!\.)', re.IGNORECASE)
_LEADING_HONORIFIC_RE = re.compile(r'^(' + _HONORIFIC_ALT + r')\b(?!\.)', re.IGNORECASE)
_NAME_ANYWHERE_HONORIFIC_RE = re.compile(r'\b(' + '|'.join(sorted(_NAME_ANYWHERE_HONORIFICS, key=len, reverse=True)) + r')\b(?!\.)', re.IGNORECASE)
_OPEN_QUOTE_RE = re.compile(r"(?<=\S)('(?!(?:" + _CONTRACTION_ALT + r")\b)\S+)(?=.*')")
_SEQ_MARKER_RE = re.compile(rf'\b{_SEQ_MARKERS}(?=\s|$)', re.IGNORECASE)
_BEFORE_RUN_RE = re.compile(r'([A-Za-z]+(?:[\s-]+[A-Za-z]+)*)\s+$')
_AFTER_RUN_RE = re.compile(r'\s+([A-Za-z]+(?:[\s-]+[A-Za-z]+)*)')
_SEQ_PAREN_RE = re.compile(rf'(?<=\S)\s*\(\s*{_SEQ_PHRASE}\s*\)', re.IGNORECASE)
_SEQ_SEP_RE = re.compile(rf'(?<=\S)\s*[:,–—-]\s*{_SEQ_PHRASE}', re.IGNORECASE)
_SEQ_SPACE_RE = re.compile(rf'(?<=[\w\'"])\s+{_SEQ_COLON_PHRASE}', re.IGNORECASE)
_INITIALISM_RE = re.compile(r'(?<![A-Za-z])(?:[A-Za-z]\.\s+){2,}[A-Za-z]\.?(?![A-Za-z])')
_VS_RE = re.compile(r'(?i)(?<![A-Za-z])(vs)\.*(?=\s|$)')
_POSSESSIVE_S_RE = re.compile(r"(?i)(?<=s)'s\b")
_TRAILING_INITIAL_RE = re.compile(r'(?<![A-Za-z])[A-Za-z]\.$')
_TRAILING_INITIALISM_RE = re.compile(r'(?<![A-Za-z])(?:[A-Za-z]\.\s*){2,}$')
_UNDOTTED_INITIALISM_RE = re.compile(r'(?<![\w.])((?:[A-Za-z]\.)+[A-Za-z])$')
_PARTICLE_LA_RE = re.compile(r'\b(de|en|a)(\s+)La\b')
_TLD_GUARD = '|'.join(sorted((*_TLD_FRAGMENTS, 'porn', 'xxx'), key=len, reverse=True))
_MARK_SPLIT_RE = re.compile(rf'(?i)([!:?])(?=\w)(?!(?:{_TLD_GUARD})\b|E\d)')
_DOT_SPLIT_RE = re.compile(rf'(?i)\.(?=[A-Za-z])(?!(?:{_TLD_GUARD})\b|E\d)')

_T2D = text2digits.Text2Digits()


# ── Helpers ───────────────────────────────────────────────────────────────────
def _strip_non_word(s: str) -> str:
    return _NON_WORD_RE.sub('', s)


def _is_alnum(ch: str) -> bool:
    return bool(_ALNUM_RE.match(ch))


def _restore_brand_case(output: str) -> str:
    if _KEEP_LOWER_RE is None:
        return output
    return _KEEP_LOWER_RE.sub(lambda m: _KEEP_LOWER_BY_KEY[m.group(1).lower()], output)


def _capitalize(s: str) -> str:
    return s[0].upper() + s[1:] if s else s


# ── Title-Case Engine ─────────────────────────────────────────────────────────
_TokenKind = Literal['word', 'space', 'symbol', 'punct']


@dataclass
class _Token:
    text: str
    kind: _TokenKind
    normalized: str | None = None


class _TitleCaseEngine:
    def __init__(self, type: str | None, site_name: str | None, scraper_type: str | None = None) -> None:
        self.type = type or 'title'
        self.site_name = site_name or ''
        self.clean_site = _strip_non_word(re.sub(r'\s+', '', self.site_name)).lower()
        self.scraper_type = scraper_type or ''
        self.lower_exceptions = _LOWER_EXCEPTIONS | _SPANISH_LOWER_EXCEPTIONS if self.clean_site in _SPANISH_SITE_KEYS else _LOWER_EXCEPTIONS
        if self.type == 'title':
            self.lower_exceptions = self.lower_exceptions | _TITLE_LOWER_EXCEPTIONS
        self._manual_cache: dict[str, str] = {}

    def parse(self, text: str) -> str:
        s = self._pre_process(text)
        tokens = self._tokenize(s)
        self._apply_word_rules(tokens)
        s = ''.join(t.normalized if t.normalized is not None else t.text for t in tokens)
        return self._post_process(s)

    # ── Pre-Process ──────────────────────────────────────────────────────────
    def _pre_process(self, s: str) -> str:
        s = s.replace('_', ' ')
        s = re.sub(r'[’´]', "'", s)
        s = re.sub(r'(?i)\bw/(?!\s)', 'w/ ', s)
        s = re.sub(r'(?i)\bb day\b', 'bday', s)
        s = re.sub(r',(?![\s\d])', ', ', s)
        s = s.replace('\xa0', ' ')
        return _UNDOTTED_INITIALISM_RE.sub(r'\1.', s)

    # ── Tokenize ─────────────────────────────────────────────────────────────
    def _tokenize(self, s: str) -> list[_Token]:
        tokens: list[_Token] = []
        length = len(s)
        i = 0
        while i < length:
            ch = s[i]
            if ch.isspace():
                j = i + 1
                while j < length and s[j].isspace():
                    j += 1
                tokens.append(_Token(s[i:j], 'space'))
                i = j
                continue
            if _is_alnum(ch):
                j = i + 1
                while j < length and (_is_alnum(s[j]) or s[j] == "'"):
                    j += 1
                tokens.append(_Token(s[i:j], 'word'))
                i = j
                continue
            if ch == "'":
                if 0 < i and i + 1 < length and _is_alnum(s[i - 1]) and _is_alnum(s[i + 1]):
                    tokens[-1].text += "'"
                    i += 1
                    continue
                tokens.append(_Token("'", 'symbol'))
                i += 1
                continue
            tokens.append(_Token(ch, 'punct'))
            i += 1
        return tokens

    # ── Word Rules ───────────────────────────────────────────────────────────
    def _apply_word_rules(self, tokens: list[_Token]) -> None:
        for idx, token in enumerate(tokens):
            if token.kind != 'word':
                continue
            prev = tokens[idx - 1] if idx else None
            after_dot = prev is not None and prev.kind == 'punct' and prev.text == '.'
            token.normalized = self._normalize_word(token.text, after_dot=after_dot)
            if self._starts_hyphen_compound(tokens, idx) and token.normalized == token.normalized.lower():
                token.normalized = _capitalize(token.normalized)
        self._capitalize_first_word(tokens)

    def _starts_hyphen_compound(self, tokens: list[_Token], idx: int) -> bool:
        if idx and tokens[idx - 1].kind == 'punct' and tokens[idx - 1].text == '-':
            return False
        return idx + 2 < len(tokens) and tokens[idx + 1].kind == 'punct' and tokens[idx + 1].text == '-' and tokens[idx + 2].kind == 'word'

    def _normalize_word(self, word: str, *, after_dot: bool = False) -> str:
        clean_word = _strip_non_word(word)
        clean_lower = clean_word.lower()

        if self.clean_site and clean_lower == self.clean_site:
            return self._manual_word_fix(self.site_name)

        if "'" in word:
            return self._manual_word_fix(self._handle_contraction_word(word))

        if after_dot and clean_lower in _TLD_FRAGMENTS:
            return self._manual_word_fix(word.lower())

        if self.type == 'name' and len(clean_word) == 1 and clean_word.isupper():
            return self._manual_word_fix(word)

        is_special, special_val = self._is_acronym_or_size(clean_lower, clean_word)
        if is_special:
            assert special_val is not None
            return self._manual_word_fix(special_val)

        if clean_lower in _UPPER_EXCEPTIONS:
            return self._manual_word_fix(word.upper())

        if clean_word and clean_word == clean_word.upper() and clean_lower not in self.lower_exceptions:
            return self._manual_word_fix(word.upper())

        if clean_lower in self.lower_exceptions:
            return self._manual_word_fix(word.lower())

        has_lower = bool(re.search(r'[a-z]', word))
        has_upper = bool(re.search(r'[A-Z]', word))
        if has_lower and has_upper:
            return self._manual_word_fix(word)

        return self._manual_word_fix(_capitalize(word))

    def _is_acronym_or_size(self, clean_lower: str, clean_word: str) -> tuple[bool, str | None]:
        if clean_lower in _NAME_EXCEPTIONS and self.site_name in _NAME_EXCEPTION_SITES:
            return False, None
        if clean_lower in self.lower_exceptions:
            return False, None
        if self.type == 'name':
            return False, None
        if clean_lower in _SIZE_CODES:
            return True, clean_word.upper()
        if clean_lower in _ACRONYMS:
            return True, clean_word.upper()
        if 2 <= len(clean_word) <= 4 and clean_word == clean_word.upper():
            return True, clean_word.upper()
        return False, None

    def _handle_contraction_word(self, word: str) -> str:
        out: list[str] = []
        for idx, part in enumerate(word.split("'")):
            if not part:
                out.append(part)
                continue
            is_suffix = idx > 0 and _strip_non_word(part).lower() in _CONTRACTIONS
            norm = part.lower() if is_suffix else self._normalize_word(part)
            out.append(self._manual_word_fix(norm))
        return "'".join(out)

    def _capitalize_first_word(self, tokens: list[_Token]) -> None:
        for token in tokens:
            if token.kind != 'word':
                continue
            text = token.normalized if token.normalized is not None else token.text
            clean = _strip_non_word(text)
            if not clean:
                return
            token.normalized = text[0].upper() + text[1:] if len(clean) > 1 else text.upper()
            return

    def _manual_word_fix(self, word: str) -> str:
        cached = self._manual_cache.get(word)
        if cached is not None:
            return cached
        clean = _strip_non_word(word).lower()
        correction = _MANUAL_CORRECTIONS.get(clean)
        if correction:
            fixed = re.sub(re.escape(clean), lambda _m: correction, word, count=1, flags=re.IGNORECASE)
            self._manual_cache[word] = fixed
            return fixed
        self._manual_cache[word] = word
        return word

    # ── Post-Process ─────────────────────────────────────────────────────────
    def _post_process(self, output: str) -> str:
        output = self._normalize_quotes_and_articles(output)
        output = self._fix_spacing(output)
        output = self._capitalize_boundaries(output)
        output = self._normalize_initials(output)
        output = self._fix_grammar(output)
        return _restore_brand_case(self._finish_by_type(output))

    def _normalize_quotes_and_articles(self, output: str) -> str:
        output = output.replace('“', '"').replace('”', '"').replace('’', "'")
        return re.sub(r'(?i)^(.*?),\s*(the|a|an)$', lambda m: f'{_capitalize(m.group(2).lower())} {m.group(1)}', output)

    def _fix_spacing(self, output: str) -> str:
        output = _MARK_SPLIT_RE.sub(r'\1 ', output)
        output = _DOT_SPLIT_RE.sub('. ', output)
        keeps_period = _TRAILING_INITIALISM_RE.search(output) or (self.type == 'name' and _TRAILING_INITIAL_RE.search(output))
        if not keeps_period:
            output = re.sub(r'(?<!\.)\.$', '', output)
        output = re.sub(r"\s+(?=[.,!'):])", '', output)
        output = re.sub(r'(?<=\S)(\"\S+)', r' \1', output)
        output = _OPEN_QUOTE_RE.sub(lambda m: f' {m.group(1)[0]}{_capitalize(m.group(1)[1:])}', output)
        output = re.sub(r'(?<=[#("\[])\s+', '', output)
        return re.sub(r'"(?!\s)(?=(?:(?:[^"]*"){2})*[^"]*$)', '" ', output)

    def _capitalize_boundaries(self, output: str) -> str:
        output = re.sub(r'(?<!vs\.)([!:?.\-–](?:\s*[!:?.\-–])*)(\s)(\S)', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), output)
        output = re.sub(r'([\])])(\s)([a-z])', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), output)
        output = re.sub(r'(?<=[(|&"\[*~])([a-z])', lambda m: m.group(1).upper(), output)
        output = re.sub(r'\S+[\])"~:?!]', lambda m: _capitalize(m.group(0)), output)
        output = re.sub(r'\S+(?=\s[-–]\s)', lambda m: _capitalize(m.group(0)), output)
        return re.sub(r'\S+$', lambda m: _capitalize(m.group(0)), output)

    def _normalize_initials(self, output: str) -> str:
        output = re.sub(r'^\w\.\s\w$', lambda m: f'{m.group(0)}.', output)
        output = _INITIALISM_RE.sub(lambda m: re.sub(r'\s+', '', m.group(0)), output)
        output = _UNDOTTED_INITIALISM_RE.sub(r'\1.', output)
        output = collapse_initial_pairs(output)
        return _VS_RE.sub(lambda m: f'{m.group(1)}.', output)

    def _fix_grammar(self, output: str) -> str:
        output = _POSSESSIVE_S_RE.sub("'", output)
        if self.type != 'name':
            output = _A_BEFORE_VOWEL_RE.sub(lambda m: m.group(1) if _A_STAYS_RE.match(m.group(2)) else ('An' if m.group(1) == 'A' else 'an'), output)
            output = _AN_BEFORE_WORD_RE.sub(lambda m: m.group(1) if _A_STAYS_RE.match(m.group(2)) else f'{m.group(1)}n', output)
        honorifics = _LEADING_HONORIFIC_RE if self.type == 'name' else _HONORIFIC_RE
        output = honorifics.sub(lambda m: m.group(1).capitalize() + '.', output)
        if self.type == 'name':
            output = _NAME_ANYWHERE_HONORIFIC_RE.sub(lambda m: m.group(1).capitalize() + '.', output)
        return output

    def _finish_by_type(self, output: str) -> str:
        if self.type == 'title':
            output = normalize_sequence_separator(output)
            output = _PARTICLE_LA_RE.sub(r'\1\2la', output)
        output = expand_initial_pairs(output)
        output = re.sub(r'(?<![A-Za-z])W/', 'w/', output)
        for phrase, replacement in _PHRASE_CORRECTIONS.items():
            output = re.sub(rf'\b{re.escape(phrase)}\b', replacement, output, flags=re.IGNORECASE)
        for pattern, replacement in _IDIOM_CORRECTIONS:
            output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)
        for phrase, replacement in _SCRAPER_PHRASE_CORRECTIONS.get(self.scraper_type, {}).items():
            output = re.sub(re.escape(phrase), replacement, output, flags=re.IGNORECASE)
        return output


def title_case(text: str, *, type: str | None = None, site_name: str | None = None, scraper_type: str | None = None) -> str:
    if not text:
        return text
    normalized = normalize_text(text)
    if not normalized:
        return normalized
    bounded = normalized[:_MAX_TITLE_LENGTH] if len(normalized) > _MAX_TITLE_LENGTH else normalized
    return _TitleCaseEngine(type, site_name, scraper_type).parse(bounded)


# ── Sequence Numbers ──────────────────────────────────────────────────────────
def _is_sequence_number(word: str) -> bool:
    if word.isdigit() or word in _ROMAN_NUMERALS:
        return True
    return bool(_PURE_NUMBER_RE.fullmatch(str(_T2D.convert(word.lower())).strip()))


def _sequence_colon(m: re.Match[str]) -> str:
    return f': {m.group("phrase")}' if _is_sequence_number(m.group('num')) else m.group(0)


def normalize_sequence_separator(title: str) -> str:
    title = _SEQ_PAREN_RE.sub(_sequence_colon, title)
    title = _SEQ_SEP_RE.sub(_sequence_colon, title)
    return _SEQ_SPACE_RE.sub(_sequence_colon, title)


def _convert_bounded_numbers(text: str) -> str:
    out: list[str] = []
    pos = 0
    for m in _SEQ_MARKER_RE.finditer(text):
        if m.start() < pos:
            continue

        replaced = False
        before = _BEFORE_RUN_RE.search(text[pos : m.start()])
        if before:
            window = before.group(1)
            window_start = pos + before.start(1)
            for word in _WORD_RE.finditer(window):
                converted = str(_T2D.convert(window[word.start() :])).strip()
                if _PURE_NUMBER_RE.fullmatch(converted):
                    out.append(text[pos : window_start + word.start()])
                    out.append(converted)
                    out.append(text[window_start + len(window) : m.end()])
                    replaced = True
                    break
        if not replaced:
            out.append(text[pos : m.end()])
        pos = m.end()

        after = _AFTER_RUN_RE.match(text, m.end())
        if after:
            window = after.group(1)
            window_start = after.start(1)
            for word in reversed(list(_WORD_RE.finditer(window))):
                converted = str(_T2D.convert(window[: word.end()])).strip()
                if _PURE_NUMBER_RE.fullmatch(converted):
                    out.append(text[pos:window_start])
                    out.append(converted)
                    pos = window_start + word.end()
                    break
    out.append(text[pos:])
    return ''.join(out)


def title_sort(title: str) -> str | None:
    stripped = _ARTICLE_RE.sub('', title).strip()
    converted = _convert_bounded_numbers(stripped).strip()
    return converted if converted and converted != title else None


def convert_sequence_numbers(title: str) -> str | None:
    converted = _convert_bounded_numbers(title).strip()
    return converted if converted and converted != title else None
