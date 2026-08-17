from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops

from phoenixadult.utils.logging.logger import logger

MIN_SIDE = 4

_SAVE_ARGS: dict[str, dict[str, object]] = {
    'PNG': {'optimize': True},
    'WEBP': {'quality': 90, 'method': 6},
    'JPEG': {'quality': 92, 'subsampling': 0},
}


def _has_alpha(im: Image.Image) -> bool:
    return im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)


def content_box(im: Image.Image) -> tuple[int, int, int, int] | None:
    if _has_alpha(im):
        alpha = im.convert('RGBA').getchannel('A')
        if alpha.histogram()[255] < alpha.width * alpha.height:
            return alpha.getbbox()
    rgb = im.convert('RGB')
    w, h = rgb.size
    corners = {rgb.getpixel((0, 0)), rgb.getpixel((w - 1, 0)), rgb.getpixel((0, h - 1)), rgb.getpixel((w - 1, h - 1))}
    if len(corners) != 1:
        return None
    return ImageChops.difference(rgb, Image.new('RGB', rgb.size, corners.pop())).getbbox()


def trim(path: Path) -> tuple[tuple[int, int], tuple[int, int]] | None:
    try:
        with Image.open(path) as im:
            im.load()
            fmt = im.format
            if getattr(im, 'n_frames', 1) > 1 or fmt not in _SAVE_ARGS:
                return None
            before = im.size
            box = content_box(im)
            if box is None or box == (0, 0, *before):
                return None
            after = (box[2] - box[0], box[3] - box[1])
            if min(after) < MIN_SIDE:
                return None
            out = im.convert('RGBA') if _has_alpha(im) else im
            out.crop(box).save(path, format=fmt, **_SAVE_ARGS[fmt])
    except (OSError, ValueError) as exc:
        logger.warn('logo-cache', f'could not trim {path.name}: {exc}')
        return None
    return before, after
