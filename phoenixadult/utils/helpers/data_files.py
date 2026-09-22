from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, overload


@overload
def load_data(caller_file: str, name: str, kind: Literal['json'] = 'json') -> Any: ...


@overload
def load_data(caller_file: str, name: str, kind: Literal['html']) -> str: ...


@overload
def load_data(caller_file: str, name: str, kind: Literal['path']) -> Path: ...


def load_data(caller_file: str, name: str, kind: Literal['json', 'html', 'path'] = 'json') -> Any:
    folder = Path(caller_file).parent
    if kind == 'html':
        return (folder / 'html' / f'{name}.html').read_text(encoding='utf-8')
    if kind == 'path':
        return folder / '_data' / name
    return json.loads((folder / '_data' / 'json' / f'{name}.json').read_text(encoding='utf-8'))
