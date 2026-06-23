from __future__ import annotations

import glob
import json
import os

WIDTH = 110


def _compact(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(', ', ': '))


def _fmt_array(arr: list, indent: int) -> str:
    if not arr:
        return '[]'
    pad = ' ' * (indent + 2)
    # Arrays of scalars fill to the line width; arrays of arrays/objects (1-to-1
    # mappings like the abbreviations table) get one element per line.
    if any(isinstance(e, (list, dict)) for e in arr):
        lines = []
        for i, e in enumerate(arr):
            comma = ',' if i < len(arr) - 1 else ''
            rendered = _compact(e) if not isinstance(e, dict) else _fmt_object(e, indent + 2)
            lines.append(f'{pad}{rendered}{comma}')
        return '[\n' + '\n'.join(lines) + '\n' + ' ' * indent + ']'

    items = [_compact(e) for e in arr]
    lines = []
    cur = pad
    for i, item in enumerate(items):
        piece = item + (',' if i < len(items) - 1 else '')
        if cur != pad and len(cur) + 1 + len(piece) > WIDTH:
            lines.append(cur)
            cur = pad
        cur += piece if cur == pad else ' ' + piece
    if cur.strip():
        lines.append(cur)
    return '[\n' + '\n'.join(lines) + '\n' + ' ' * indent + ']'


def _fmt_value(value: object, indent: int) -> str:
    if isinstance(value, dict):
        return _fmt_object(value, indent)
    if isinstance(value, list):
        return _fmt_array(value, indent)
    return _compact(value)


def _fmt_object(obj: dict, indent: int) -> str:
    pad = ' ' * (indent + 2)
    keys = list(obj.keys())
    lines: list[str] = []
    for i, key in enumerate(keys):
        val = obj[key]
        key_s = json.dumps(key, ensure_ascii=False)
        comma = ',' if i < len(keys) - 1 else ''
        inline = f'{pad}{key_s}: {_compact(val)}{comma}'
        if not isinstance(val, dict) and len(inline) <= WIDTH:
            lines.append(inline)
        else:
            lines.append(f'{pad}{key_s}: {_fmt_value(val, indent + 2)}{comma}')
    return '{\n' + '\n'.join(lines) + '\n' + ' ' * indent + '}'


def format_file(path: str) -> None:
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    out = _fmt_value(data, 0) + '\n'
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(out)
    print(f'formatted {path}')


def main() -> None:
    root = os.path.join(os.path.dirname(__file__), '..', 'app')
    for path in sorted(glob.glob(os.path.join(root, '**', '_data', 'json', '*.json'), recursive=True)):
        format_file(path)


if __name__ == '__main__':
    main()
