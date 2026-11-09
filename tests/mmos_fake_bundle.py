"""Fake Mastermind OS .app bundle fixtures for receipt/rollback tests.

Builds hermetic ``.app`` directories with a real (binary or XML) Info.plist
and a Mach-O-ish fake executable carrying the same embedded-string shapes
observed in the real installed builds, so extraction, archive and rollback
behavior can be proven without touching /Applications or ~/Applications.
"""
from __future__ import annotations

import json
import plistlib
from pathlib import Path

# On-disk magic of a little-endarm 64-bit Mach-O header (bytes only; never executed).
MACHO_MAGIC_64_LE = b"\xcf\xfa\xed\xfe"

# 40-hex decoys observed in the REAL binaries that a naive scan would trip on:
# an embedded-python fixture hash, a std-backtrace build id (repeated), and a
# placeholder fixture revision.
_REAL_DECOYS = (
    b"python/fixture 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19 tool_search.py\x00"
    + b"rustc/library/backtrace " + b"b940084d7eb6a299eb4bfeb8e34901bc051e7ac4" * 3
    + b"\x00"
    + b"0000111122223333444455556666777788889999::::\x00"
)


def fake_executable_bytes(
    *,
    revision: str | None = None,
    identity: str | None = None,
    marker: bool = True,
    version: str = "0.1.0",
    decoys: bool = True,
    extra: bytes = b"",
) -> bytes:
    """Fake main-executable image.

    ``marker=True`` embeds the proposed ``MM_RECEIPT:{json}`` machine marker
    AND the legacy Readiness rodata blob (with *different* values, so tests
    can prove the marker wins). ``marker=False`` embeds only the legacy blob
    ``<version><rev40><identity><adjacent literal 'native'>`` exactly as the
    real 2026-11-09 builds lay it out.
    """
    parts: list[bytes] = [MACHO_MAGIC_64_LE, b"\x00" * 16, b"BUNDLE-RUNS-NEVER\x00"]
    if revision and identity and marker:
        payload = json.dumps(
            {"source_revision": revision, "build_identity": identity},
            separators=(",", ":"),
        ).encode("ascii")
        parts += [b"MM_RECEIPT:", payload, b"\x00"]
    if revision and identity:
        parts += [
            b"REQUEST_INVALIDMAIN_WINDOW_CONFIG_UNAVAILABLECONFIGURED\x00",
            version.encode("ascii") + revision.encode("ascii")
            + identity.encode("ascii") + b"native\x00",
            b"BUILT_NOT_PROVEN\x00",
        ]
    if decoys:
        parts.append(_REAL_DECOYS)
    parts.append(extra)
    return b"".join(parts)


def make_fake_app(
    parent: str | Path,
    *,
    name: str = "Mastermind OS.app",
    revision: str | None = None,
    identity: str | None = None,
    marker: bool = True,
    version: str = "0.1.0",
    build: str | None = None,
    identifier: str = "com.mastermind.os",
    executable_name: str = "mastermind-os",
    binary_plist: bool = False,
    executable_bytes: bytes | None = None,
) -> Path:
    """Create a fake installed bundle under ``parent`` and return its path."""
    bundle = Path(parent) / name
    (bundle / "Contents" / "MacOS").mkdir(parents=True)
    plist = {
        "CFBundleIdentifier": identifier,
        "CFBundleShortVersionString": version,
        "CFBundleVersion": build or version,
        "CFBundleExecutable": executable_name,
    }
    with open(bundle / "Contents" / "Info.plist", "wb") as handle:
        plistlib.dump(plist, handle, fmt=plistlib.FMT_BINARY if binary_plist else plistlib.FMT_XML)
    exe = bundle / "Contents" / "MacOS" / executable_name
    exe.write_bytes(
        executable_bytes
        if executable_bytes is not None
        else fake_executable_bytes(revision=revision, identity=identity, marker=marker, version=version)
    )
    exe.chmod(0o755)
    return bundle
