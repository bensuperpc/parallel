from dataclasses import dataclass
from typing import Callable

from common.task_names import ENCODE_PNG_TO_WEBP, ENCODE_VIDEO_TO_AV1


@dataclass(frozen=True)
class UploadParams:
    compression_level: int
    preset: int
    crf: int


@dataclass(frozen=True)
class MediaHandler:
    task_name: str
    output_extension: str | None  # None keeps the uploaded file's own extension
    build_args: Callable[[UploadParams], list[str]]


def _image_args(params: UploadParams) -> list[str]:
    return [str(params.compression_level)]


def _video_args(params: UploadParams) -> list[str]:
    return [str(params.preset), str(params.crf)]


_IMAGE_HANDLER = MediaHandler(task_name=ENCODE_PNG_TO_WEBP, output_extension=".webp", build_args=_image_args)
_VIDEO_HANDLER = MediaHandler(task_name=ENCODE_VIDEO_TO_AV1, output_extension=None, build_args=_video_args)

# Add one line per new extension to support a new format; add a new MediaHandler +
# task (see tasks/) if it needs its own encoder rather than reusing an existing one.
MEDIA_HANDLERS: dict[str, MediaHandler] = {
    ".png": _IMAGE_HANDLER,
    ".mp4": _VIDEO_HANDLER,
    ".mkv": _VIDEO_HANDLER,
    ".avi": _VIDEO_HANDLER,
    ".mov": _VIDEO_HANDLER,
}


def resolve_handler(filename: str) -> MediaHandler | None:
    lowered = filename.lower()
    for ext, handler in MEDIA_HANDLERS.items():
        if lowered.endswith(ext):
            return handler
    return None
