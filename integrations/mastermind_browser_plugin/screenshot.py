"""Bounded native screenshot content for the Browser MCP transport.

Image bytes are verified before they leave the owner boundary. The structured
and text result contains only image metadata; MCP carries the actual image once.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import io
from typing import Any

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8192
MAX_ENCODED_IMAGE_BYTES = 4 * ((MAX_IMAGE_BYTES + 2) // 3)
_MIME_FORMAT = {"image/png": "PNG", "image/jpeg": "JPEG"}


@dataclass(frozen=True)
class ScreenshotImage:
    data: str
    mime_type: str


class BrowserCallResult(dict):
    """JSON envelope with separately typed, validated native image content."""

    __slots__ = ("images",)

    def __init__(self, envelope: dict, *, images: tuple[ScreenshotImage, ...] = ()):
        super().__init__(envelope)
        self.images = images


def _image(value: dict) -> tuple[dict, ScreenshotImage]:
    mime = value.get("mimeType")
    encoded = value.get("data")
    if (
        type(mime) is not str
        or mime not in _MIME_FORMAT
        or type(encoded) is not str
        or not encoded
        or len(encoded) > MAX_ENCODED_IMAGE_BYTES
        or set(value) - {"type", "data", "mimeType", "annotations", "_meta"}
    ):
        raise ValueError("screenshot image is invalid")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("screenshot image encoding is invalid") from exc
    if (
        not raw
        or len(raw) > MAX_IMAGE_BYTES
        or base64.b64encode(raw).decode("ascii") != encoded
    ):
        raise ValueError("screenshot image encoding is invalid")

    from PIL import Image

    try:
        with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG"]) as decoded:
            width, height = decoded.size
            if (
                decoded.format != _MIME_FORMAT[mime]
                or not 0 < width <= MAX_IMAGE_DIMENSION
                or not 0 < height <= MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
                or getattr(decoded, "n_frames", 1) != 1
            ):
                raise ValueError("screenshot image dimensions or format are invalid")
            decoded.verify()
        # JPEG verify does not decode scan data. Loading is necessary to refuse
        # truncated/corrupt images, after the pixel budget has been checked.
        with Image.open(io.BytesIO(raw), formats=["PNG", "JPEG"]) as decoded:
            decoded.load()
    except Exception as exc:
        raise ValueError("screenshot image is undecodable") from exc

    return (
        {
            "type": "image",
            "mimeType": mime,
            "width": width,
            "height": height,
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        ScreenshotImage(data=encoded, mime_type=mime),
    )


def separate_screenshot(value: Any) -> tuple[dict, tuple[ScreenshotImage, ...]]:
    """Validate one viewport screenshot and remove image data from JSON."""
    if type(value) is not dict or value.get("isError", False) is not False:
        raise ValueError("screenshot result is invalid")
    content = value.get("content")
    if type(content) is not list or not 1 <= len(content) <= 8:
        raise ValueError("screenshot content is invalid")
    data = dict(value)
    blocks = []
    images = []
    for block in content:
        if type(block) is not dict:
            raise ValueError("screenshot block is invalid")
        if block.get("type") == "image":
            if images:
                raise ValueError("screenshot contains multiple images")
            metadata, image = _image(block)
            blocks.append(metadata)
            images.append(image)
        elif block.get("type") == "text" and type(block.get("text")) is str:
            blocks.append(dict(block))
        else:
            raise ValueError("unsupported screenshot content")
    if not images:
        raise ValueError("screenshot contains no image")
    data["content"] = blocks
    return data, tuple(images)
