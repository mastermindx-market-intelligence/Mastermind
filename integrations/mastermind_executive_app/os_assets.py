"""Closed asset layouts for the sealed legacy, Noir and rich-client OS releases.

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


_RICH_CLIENT = (
    (r"assets/SourceMarkdown-[A-Za-z0-9_-]+\.js", "text/javascript; charset=utf-8"),
    (r"assets/SourceMarkdown-[A-Za-z0-9_-]+\.css", "text/css; charset=utf-8"),
)
_CLIENT_LICENSES = (
    "third-party/deepseek-client-dependency-NOTICES.txt",
    "third-party/deepseek-harness-LICENSE.txt",
)

# Single closed topology source for both packaging and later staged publication.
# Each profile contains index.html plus its required asset patterns/notices.
OS_ASSET_PROFILE_FILE_COUNTS = (
    1 + len(_BASE),
    1 + len(_BASE) + len(_NOIR) + len(_LICENSES),
    1 + len(_BASE) + len(_NOIR) + len(_LICENSES) + len(_RICH_CLIENT) + len(_CLIENT_LICENSES),
)


def os_asset_mimes(names) -> dict[str, str]:
    """Exactly legacy3, Noir9, or Noir plus both rich chunks/notices13.

    There is no wildcard asset directory, arbitrary chunk name, optional partial
    profile or caller-supplied MIME. File custody and bytes stay with the launcher.
    """
    names = tuple(names)
    if (any(type(name) is not str for name in names)
            or len(names) not in OS_ASSET_PROFILE_FILE_COUNTS or len(set(names)) != len(names)):
        raise ValueError("fixed OS asset set required")
    expected = {"index.html": "text/html; charset=utf-8"}
    patterns = _BASE + (_NOIR if len(names) in (9, 13) else ()) + (_RICH_CLIENT if len(names) == 13 else ())
    for pattern, mime in patterns:
        matches = [name for name in names if re.fullmatch(pattern, name)]
        if len(matches) != 1:
            raise ValueError("fixed OS asset set required")
        expected[matches[0]] = mime
    if len(names) in (9, 13):
        expected.update({name: "text/plain; charset=utf-8" for name in _LICENSES})
    if len(names) == 13:
        expected.update({name: "text/plain; charset=utf-8" for name in _CLIENT_LICENSES})
    if set(names) != set(expected):
        raise ValueError("fixed OS asset set required")
    return expected
