from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from phoenixadult.utils.helpers.helpers import load_data
from phoenixadult.utils.logging.logger import logger

_MODEL_PATH: Path = load_data(__file__, 'face_detection_yunet_2023mar.onnx', kind='path')

_DETECT_SCORE = 0.5
_CROP_SCORE = 0.6
_JPEG_QUALITY = 92

_CROP_SIDE_FACES = 3.0
_CROP_SIDE_WIDTHS = 2.2
_CROP_HEADROOM = 0.5
_CROP_MIN_FACES = 1.8

_cv2: Any = None
_np: Any = None
_unavailable_reason: str | None = None
_libs_lock = threading.Lock()


def _libs() -> tuple[Any, Any] | None:
    global _cv2, _np, _unavailable_reason
    with _libs_lock:
        if _cv2 is not None and _np is not None:
            return _cv2, _np
        if _unavailable_reason is not None:
            return None
        try:
            import cv2  # noqa: PLC0415
            import numpy as np  # noqa: PLC0415
        except ImportError as err:
            _unavailable_reason = f'opencv/numpy not installed ({err}); install opencv-python-headless to enable'
            logger.warn('face-crop', _unavailable_reason)
            return None
        if not hasattr(cv2, 'FaceDetectorYN'):
            _unavailable_reason = f'cv2 {cv2.__version__} lacks FaceDetectorYN (need >= 4.5.4)'
            logger.warn('face-crop', _unavailable_reason)
            return None
        if not _MODEL_PATH.exists():
            _unavailable_reason = f'YuNet model missing at {_MODEL_PATH}'
            logger.warn('face-crop', _unavailable_reason)
            return None
        _cv2, _np = cv2, np
        return _cv2, _np


def available() -> bool:
    return _libs() is not None


def _rotation_codes(cv2: Any) -> dict[int, Any]:
    return {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def _best_face(cv2: Any, img: Any) -> tuple[Any, tuple[int, int, int, int], float] | None:
    best: tuple[Any, tuple[int, int, int, int], float] | None = None
    detector = cv2.FaceDetectorYN.create(str(_MODEL_PATH), '', (320, 320), _DETECT_SCORE, 0.3, 5000)
    for code in _rotation_codes(cv2).values():
        rimg = img if code is None else cv2.rotate(img, code)
        h, w = rimg.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(rimg)
        if faces is None:
            continue
        for f in faces:
            score = float(f[14])
            box = (int(f[0]), int(f[1]), int(f[2]), int(f[3]))
            if box[2] <= 0 or box[3] <= 0:
                continue
            if best is None or score > best[2]:
                best = (rimg, box, score)
    return best


def _headshot_crop(np: Any, img: Any, box: tuple[int, int, int, int]) -> Any | None:
    height, width = img.shape[:2]
    x, y, w, h = box
    cx = x + w / 2.0

    side = max(_CROP_SIDE_FACES * h, _CROP_SIDE_WIDTHS * w)
    side = min(side, width, height)
    if side < _CROP_MIN_FACES * h:
        return None

    left = max(0.0, min(cx - side / 2.0, width - side))
    top = max(0.0, min(y - _CROP_HEADROOM * h, height - side))

    x1, y1 = int(round(left)), int(round(top))
    x2, y2 = min(x1 + int(round(side)), width), min(y1 + int(round(side)), height)
    if x2 - x1 < 32 or y2 - y1 < 32 or not (x1 <= cx <= x2):
        return None
    crop = img[y1:y2, x1:x2]
    return crop if crop.size else None


def crop_to_headshot(data: bytes) -> bytes | None:
    libs = _libs()
    if libs is None:
        return None
    cv2, np = libs
    try:
        buf = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if img is None:
            return None
        best = _best_face(cv2, img)
        if best is None or best[2] < _CROP_SCORE:
            return None
        upright, box, _score = best
        crop = _headshot_crop(np, upright, box)
        if crop is None:
            return None
        ok, out = cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY])
        return bytes(out) if ok else None
    except Exception as err:  # noqa: BLE001 - cropping must never break caching
        logger.warn('face-crop', f'crop failed, keeping original: {err}')
        return None
