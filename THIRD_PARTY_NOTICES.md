# Third-Party Notices

This project is licensed GPLv3+ (see [LICENSE](LICENSE)) and began as a port of
the original PhoenixAdult Plex agent bundle, credited in
[README.md](README.md). The following bundled files come from other projects:

## YuNet Face-Detection Model

`phoenixadult/utils/images/_data/face_detection_yunet_2023mar.onnx` is the
`face_detection_yunet_2023mar` model from the
[OpenCV Zoo](https://github.com/opencv/opencv_zoo), copyright the OpenCV team
and the YuNet authors (Shiqi Yu et al.), licensed under the Apache License 2.0.
A copy of that license is distributed alongside the model as
`face_detection_yunet_2023mar.onnx.LICENSE`. The model is redistributed
unmodified.

## Favicon

`phoenixadult/routes/html/favicon.svg` (and the derived `favicon.ico`) is the
["Mode Standard Phoenix"](https://www.svgrepo.com/svg/355420/mode-standard-phoenix)
icon from the Hearthsim Game Icons collection, distributed by
[SVG Repo](https://www.svgrepo.com/) under the
[CC0 license](https://www.svgrepo.com/page/licensing/#CC0).

Python dependencies are declared in `pyproject.toml` and installed from PyPI —
they are not vendored into this repository and carry their own licenses.
