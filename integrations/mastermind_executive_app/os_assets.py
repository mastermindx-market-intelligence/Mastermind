"""Closed asset layouts for the sealed legacy and Noir OS releases.

This contract admits names and MIME types only. The installed launcher remains
the owner of file custody, byte limits, content hashes and immutable loading.
"""
from __future__ import annotations

import re

_BASE = (
    (r"assets/index-[A-Za-z0-9_-]+\.css", "text/css; charset=utf-8"),
    (r"assets/index-[A-Za-z0-9_-]+\.js", "text/javascript; charset=utf-8"),
)
_NOIR = (
    (r"assets/atelier-office-[A-Za-z0-9_-]+\.jpg", "image/jpeg"),
    (r"assets/Manrope-Variable-[A-Za-z0-9_-]+\.ttf", "font/ttf"),
    (r"assets/Inter-Variable-[A-Za-z0-9_-]+\.woff2", "font/woff2"),
)
_LICENSES = (
    "licenses/fonts/Inter-OFL.txt",
    "licenses/fonts/Manrope-OFL.txt",
    "licenses/fonts/Manrope-FONTLOG.txt",
)


def os_asset_mimes(names) -> dict[str, str]:
    """Exactly the old three-file layout or all nine Noir assets/licenses."""
    names = tuple(names)
    if (any(type(name) is not str for name in names)
            or len(names) not in (3, 9) or len(set(names)) != len(names)):
        raise ValueError("fixed OS asset set required")
    expected = {"index.html": "text/html; charset=utf-8"}
    for pattern, mime in _BASE + (_NOIR if len(names) == 9 else ()):
        matches = [name for name in names if re.fullmatch(pattern, name)]
        if len(matches) != 1:
            raise ValueError("fixed OS asset set required")
        expected[matches[0]] = mime
    if len(names) == 9:
        expected.update({name: "text/plain; charset=utf-8" for name in _LICENSES})
    if set(names) != set(expected):
        raise ValueError("fixed OS asset set required")
    return expected
