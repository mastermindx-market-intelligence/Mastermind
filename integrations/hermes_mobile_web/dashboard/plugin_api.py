"""Static install metadata mounted by Hermes under its existing plugin/auth gates.

This module reads no credentials, sessions, profiles or files, starts no processes,
and exposes no mutation. Browser chat stays in the upstream Desktop renderer.
"""
from __future__ import annotations

from functools import lru_cache
import re
import struct
import zlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

router = APIRouter()
PLUGIN = "mastermind-mobile"
SCHEMA = "mastermind.mobile-metadata.v1"
HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
STAFF = (
    ("meta-ceo-uncensored", "Meta-CEO"),
    ("secretary", "Secretary"),
    ("chief-of-staff", "Chief of Staff"),
)


def _base(request: Request) -> str:
    # Reuse the same proxy-prefix owner as Hermes's page, cookies and callbacks.
    from hermes_cli.dashboard_auth.prefix import prefix_from_request

    prefix = prefix_from_request(request)
    if prefix and not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", prefix):
        raise HTTPException(400, "Unsupported application prefix")
    return prefix


def manifest(base: str = "") -> dict:
    if base and not re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", base):
        raise ValueError("Invalid application prefix")
    root = base + "/"
    assets = f"{base}/api/plugins/{PLUGIN}"
    return {
        "id": root + "?app=mastermind-mobile",
        "name": "Mastermind",
        "short_name": "Mastermind",
        "description": "Your Mastermind team, through the native Hermes workspace.",
        "lang": "en",
        "start_url": root + "?mastermind-agent=meta-ceo-uncensored#/mastermind",
        "scope": root,
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui"],
        "prefer_related_applications": False,
        "icons": [
            {"src": f"{assets}/icon-{size}.png", "sizes": f"{size}x{size}",
             "type": "image/png", "purpose": "any maskable"}
            for size in (192, 512)
        ],
        # These select a route in the launcher, not an assumed runtime identity.
        # A missing or ambiguous profile remains visible; it never falls back.
        "shortcuts": [
            {"name": title, "short_name": title,
             "description": f"Open {title} conversations",
             "url": root + f"?mastermind-agent={profile}#/mastermind"}
            for profile, title in STAFF
        ],
    }


@router.get("/metadata")
def metadata(request: Request):
    base = _base(request)
    return JSONResponse({"schema": SCHEMA,
                         "manifest": f"{base}/api/plugins/{PLUGIN}/manifest.webmanifest",
                         "icon": f"{base}/api/plugins/{PLUGIN}/icon-192.png"}, headers=HEADERS)


@router.get("/manifest.webmanifest")
def web_manifest(request: Request):
    return JSONResponse(manifest(_base(request)), media_type="application/manifest+json", headers=HEADERS)


# An original monochrome M, well inside the maskable safe area. No donor branding.
_MARK = ("1000001", "1100011", "1010101", "1001001", "1000001", "1000001", "1000001")


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


@lru_cache(maxsize=2)
def icon_png(size: int) -> bytes:
    if size not in (192, 512):
        raise ValueError("Unsupported icon size")
    # Opaque neutral tile; the mark occupies 54% of its width, fitting a circular mask.
    margin = size * 23 // 100
    span = size - 2 * margin
    rows = []
    for y in range(size):
        pixels = bytearray()
        for x in range(size):
            inside = margin <= x < size - margin and margin <= y < size - margin
            mark = inside and _MARK[min(6, (y - margin) * 7 // span)][min(6, (x - margin) * 7 // span)] == "1"
            pixels.extend((245, 245, 245) if mark else (28, 28, 30))
        rows.append(b"\0" + pixels)
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(b"".join(rows))) + _chunk(b"IEND", b"")


@router.get("/icon-{size}.png")
def icon(size: int):
    if size not in (192, 512):
        raise HTTPException(404, "Icon not found")
    return Response(icon_png(size), media_type="image/png", headers=HEADERS)
