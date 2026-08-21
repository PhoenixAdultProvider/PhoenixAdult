from __future__ import annotations

from pathlib import Path

from phoenixadult.utils.images import logo_cache

_HOSTILE = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="10" height="10">
  <image xlink:href="file:///etc/passwd" width="10" height="10"/>
  <image href="http://169.254.169.254/latest/meta-data" width="10" height="10"/>
  <script>fetch('http://attacker.test')</script>
  <foreignObject><body xmlns="http://www.w3.org/1999/xhtml">x</body></foreignObject>
  <rect width="10" height="10" onload="alert(1)" fill="#000"/>
  <use xlink:href="#ok"/>
</svg>
"""


def test_external_references_are_stripped_before_any_renderer_sees_it(tmp_path: Path) -> None:
    svg = tmp_path / 'logo.svg'
    svg.write_text(_HOSTILE, encoding='utf-8')
    assert logo_cache._sanitize_svg(svg) is True
    cleaned = svg.read_text(encoding='utf-8')

    assert 'file:///etc/passwd' not in cleaned, 'a local-file reference would be read by the renderer'
    assert '169.254.169.254' not in cleaned, 'an http reference makes the renderer an SSRF client'
    assert 'onload' not in cleaned
    assert '<script' not in cleaned and 'foreignObject' not in cleaned


def test_a_fragment_reference_is_kept(tmp_path: Path) -> None:
    svg = tmp_path / 'logo.svg'
    svg.write_text(_HOSTILE, encoding='utf-8')
    logo_cache._sanitize_svg(svg)
    assert '#ok' in svg.read_text(encoding='utf-8'), 'internal references are how real logos reuse shapes'


def test_an_embedded_data_image_survives(tmp_path: Path) -> None:
    svg = tmp_path / 'logo.svg'
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"><image href="data:image/png;base64,iVBORw0KGgo=" width="1" height="1"/></svg>',
        encoding='utf-8',
    )
    logo_cache._sanitize_svg(svg)
    assert 'data:image/png' in svg.read_text(encoding='utf-8')


def test_unparseable_svg_is_refused(tmp_path: Path) -> None:
    svg = tmp_path / 'logo.svg'
    svg.write_text('<svg><unclosed>', encoding='utf-8')
    assert logo_cache._sanitize_svg(svg) is False
