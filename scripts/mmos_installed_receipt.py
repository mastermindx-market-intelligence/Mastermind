#!/usr/bin/env python3
"""Read-only installed-bundle receipt observer for the Mastermind OS desktop app.

Emits a ``mastermind.installed_receipt/v1`` JSON document for an installed
.app bundle (default ``/Applications/Mastermind OS.app``; on hosts where the
app lives elsewhere, pass ``--bundle`` explicitly). The receipt records:

* bundle path + existence,
* Info.plist identity (CFBundleIdentifier / ShortVersionString / Version),
* main executable path, sha256, size, mtime,
* the embedded ``MM_SOURCE_REVISION`` / ``MM_BUILD_IDENTITY`` values with an
  honest provenance label — ``embedded_marker`` (the proposed ``MM_RECEIPT:``
  binary marker, see integrations/mmos/INSTALL_RECEIPTS_AND_ROLLBACK.md),
  ``heuristic_scan`` (version-anchored rodata adjacency, calibrated against
  the two real installed builds) or ``unknown``. Unknown is unknown; a value
  is never fabricated,
* codesign display status (unknown when the tool is unavailable),
* whether a running process was launched from this exact bundle (ps + path
  match; ``unknown`` when only ambiguous evidence exists),
* observed_at, host, and a ``receipt_digest`` over the content-identity
  fields (paths/mtimes/codesign/running state are excluded so the same bytes
  archive and reinstall under the same digest).

This script is strictly an observer: it never writes, moves, launches or
kills anything. Exit codes: 0 = receipt emitted (possibly with honest
unknowns), 2 = malformed arguments.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "mastermind.installed_receipt/v1"
DEFAULT_BUNDLE = "/Applications/Mastermind OS.app"

# --- provenance vocabulary -------------------------------------------------
PROV_MARKER = "embedded_marker"
PROV_HEURISTIC = "heuristic_scan"
PROV_UNKNOWN = "unknown"

# src-tauri/build.rs `required()` allows exactly [A-Za-z0-9._:-] (len <= 160)
# for MM_BUILD_IDENTITY, and exactly 40 hex chars for MM_SOURCE_REVISION.
_IDENTITY_BYTES = frozenset(
    b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
)
IDENTITY_MAX_LEN = 160

# Future machine marker: MM_RECEIPT:{"source_revision":"<40hex>","build_identity":"<id>"}
_MARKER_RE = re.compile(rb"MM_RECEIPT:(\{[^{}]{1,1024}\})")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")

# Adjacent rodata literals observed directly after the build identity inside
# the Readiness value blob of both real installed builds (2026-11-09). The
# linker concatenates string literals without separators, so the identity
# capture can run into the next literal; these documented seams are trimmed.
_SEAM_SUFFIXES = ("native", "BUILT_NOT_PROVEN", "CONFIGURED", "UNCONFIGURED")


def utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds")


def _unknown() -> dict:
    return {"value": None, "provenance": PROV_UNKNOWN}


# ---------------------------------------------------------------------------
# Info.plist / executable location
# ---------------------------------------------------------------------------

def read_info_plist(bundle: Path) -> dict | None:
    """Return selected Info.plist keys, or None when absent/unreadable."""
    import plistlib

    path = bundle / "Contents" / "Info.plist"
    try:
        with open(path, "rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    if not isinstance(plist, dict):
        return None
    keys = (
        "CFBundleIdentifier",
        "CFBundleShortVersionString",
        "CFBundleVersion",
        "CFBundleExecutable",
    )
    return {key: plist.get(key) for key in keys}


def main_executable(bundle: Path, info_plist: dict | None) -> Path | None:
    """Locate the bundle main executable without launching anything."""
    macos_dir = bundle / "Contents" / "MacOS"
    name = (info_plist or {}).get("CFBundleExecutable")
    if isinstance(name, str) and name:
        candidate = macos_dir / name
        if candidate.exists():
            return candidate
    if macos_dir.is_dir():
        entries = sorted(p for p in macos_dir.iterdir() if p.is_file())
        if len(entries) == 1:
            return entries[0]
    return None


def file_facts(path: Path) -> dict:
    """sha256/size/mtime for a file; honest nulls when unreadable."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
    except OSError:
        return {"path": str(path), "sha256": None, "size_bytes": None, "mtime": None}
    mtime = _dt.datetime.fromtimestamp(stat.st_mtime, _dt.timezone.utc).isoformat()
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size_bytes": stat.st_size,
        "mtime": mtime,
    }


# ---------------------------------------------------------------------------
# Embedded revision / identity extraction
# ---------------------------------------------------------------------------

def _valid_identity(value: object) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= IDENTITY_MAX_LEN
        and all(byte in _IDENTITY_BYTES for byte in value.encode("ascii", "strict"))
    )


def _extract_marker(data: bytes) -> dict | None:
    """Parse a machine MM_RECEIPT marker; None when absent or malformed."""
    match = _MARKER_RE.search(data)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1).decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    revision = payload.get("source_revision")
    identity = payload.get("build_identity")
    if isinstance(revision, str) and _HEX40_RE.match(revision) and _valid_identity(identity):
        return {
            "source_revision": {"value": revision, "provenance": PROV_MARKER},
            "build_identity": {"value": identity, "provenance": PROV_MARKER},
        }
    return None


def _identity_run(data: bytes, start: int) -> str | None:
    """Maximal [A-Za-z0-9._:-] run at ``start`` (linker-concatenated rodata)."""
    end = start
    limit = start + 512
    while end < len(data) and end < limit and data[end] in _IDENTITY_BYTES:
        end += 1
    if end == start:
        return None
    try:
        return data[start:end].decode("ascii", "strict")
    except UnicodeDecodeError:
        return None


def _trim_seam(run: str) -> tuple[str, str | None]:
    """Trim one documented adjacent-literal seam; return (value, seam_or_None)."""
    for seam in _SEAM_SUFFIXES:
        if run.endswith(seam) and len(run) > len(seam):
            trimmed = run[: -len(seam)]
            if trimmed and all(byte in _IDENTITY_BYTES for byte in trimmed.encode()):
                return trimmed, seam
    return run, None


def _extract_heuristic(data: bytes, bundle_version: str | None) -> dict:
    """Version-anchored scan calibrated on the real installed builds.

    In both real binaries the Readiness value blob lays out as
    ``<CFBundleShortVersionString><40-hex revision><identity>`` with no
    separators (bare 40-hex scanning cannot even see the revision: the
    preceding version ends in the hex digit '0'). A bare-unique-40-hex guess
    would additionally collide with std-backtrace build ids and embedded
    python fixture hashes, so this heuristic *requires* the bundle's own
    version string immediately before the hex token and exactly one distinct
    (revision, identity-run) pair. Anything else is unknown.
    """
    result = {"source_revision": _unknown(), "build_identity": _unknown()}
    if not bundle_version:
        return result
    pattern = re.compile(re.escape(bundle_version.encode()) + rb"([0-9a-f]{40})")
    pairs: set[tuple[str, str | None]] = set()
    for match in pattern.finditer(data):
        revision = match.group(1).decode("ascii", "strict")
        run = _identity_run(data, match.end())
        pairs.add((revision, run))
    if len(pairs) != 1:
        return result
    revision, run = next(iter(pairs))
    result["source_revision"] = {"value": revision, "provenance": PROV_HEURISTIC}
    if run is None:
        return result
    identity, seam = _trim_seam(run)
    if not _valid_identity(identity):
        return result
    field = {"value": identity, "provenance": PROV_HEURISTIC}
    if seam is not None:
        field["detail"] = (
            f"heuristic scan trimmed adjacent rodata literal {seam!r} "
            "from the raw identity capture"
        )
    result["build_identity"] = field
    return result


def extract_embedded(data: bytes, bundle_version: str | None) -> dict:
    """Marker first, calibrated heuristic second, honest unknown otherwise."""
    marker = _extract_marker(data)
    if marker is not None:
        return marker
    return _extract_heuristic(data, bundle_version)


# ---------------------------------------------------------------------------
# codesign / running-process observation (injectable seams for tests)
# ---------------------------------------------------------------------------

def codesign_display(bundle: Path) -> dict:
    """Parse `codesign -dv`; unknown when unavailable."""
    try:
        proc = subprocess.run(
            ["codesign", "-dv", str(bundle)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unknown", "identifier": None, "team_identifier": None,
                "signature": None, "detail": "codesign unavailable or timed out"}
    output = (proc.stderr or "") + (proc.stdout or "")
    if proc.returncode != 0:
        first = output.strip().splitlines()[0] if output.strip() else ""
        if "not signed" in output:
            return {"status": "unsigned", "identifier": None, "team_identifier": None,
                    "signature": None, "detail": first or "codesign reports unsigned"}
        return {"status": "unknown", "identifier": None, "team_identifier": None,
                "signature": None, "detail": first or f"codesign exit {proc.returncode}"}
    fields: dict[str, str | None] = {}
    for line in output.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())
    signature = fields.get("Signature")
    status = "signed" if signature else "signed"
    team = fields.get("TeamIdentifier")
    return {
        "status": status,
        "identifier": fields.get("Identifier"),
        "team_identifier": None if team in (None, "not set") else team,
        "signature": signature,
    }


def ps_snapshot() -> list[tuple[int, str]] | None:
    """Return [(pid, comm)] from ps, or None when the observation fails."""
    try:
        proc = subprocess.run(
            ["ps", "ax", "-o", "pid=,comm="],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    rows: list[tuple[int, str]] = []
    for line in (proc.stdout or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def running_app(executable: Path | None) -> dict:
    """Is a live process running from this exact bundle? true/false/unknown."""
    if executable is None:
        return {"from_this_bundle": None, "pids": [], "detail": "no executable observed"}
    rows = ps_snapshot()
    if rows is None:
        return {"from_this_bundle": None, "pids": [], "detail": "ps observation unavailable"}
    target = os.path.realpath(executable)
    base = os.path.basename(executable)
    exact: list[int] = []
    ambiguous: list[int] = []
    for pid, comm in rows:
        try:
            resolved = os.path.realpath(comm)
        except (OSError, ValueError):
            resolved = comm
        if resolved == target or comm == str(executable):
            exact.append(pid)
        elif os.path.basename(comm) == base:
            ambiguous.append(pid)
    if exact:
        return {"from_this_bundle": True, "pids": sorted(exact),
                "detail": "ps comm matches this bundle's executable path"}
    if ambiguous:
        return {"from_this_bundle": None, "pids": sorted(ambiguous),
                "detail": "process(es) share only the executable name; path unknown"}
    return {"from_this_bundle": False, "pids": [], "detail": "no matching process observed"}


# ---------------------------------------------------------------------------
# Receipt assembly
# ---------------------------------------------------------------------------

def _digest_payload(receipt: dict) -> dict:
    return {
        "schema": receipt["schema"],
        "info_plist": receipt["info_plist"],
        "executable": {
            "sha256": receipt["executable"]["sha256"],
            "size_bytes": receipt["executable"]["size_bytes"],
        },
        "source_revision": receipt["source_revision"],
        "build_identity": {
            "value": receipt["build_identity"]["value"],
            "provenance": receipt["build_identity"]["provenance"],
        },
    }


def receipt_digest(receipt: dict) -> str:
    canonical = json.dumps(_digest_payload(receipt), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def observe_bundle(
    bundle_path: str | os.PathLike,
    *,
    observed_at: str | None = None,
    host: str | None = None,
) -> dict:
    """Assemble the full receipt for one bundle. Purely read-only."""
    bundle = Path(bundle_path).expanduser()
    info = read_info_plist(bundle) if bundle.is_dir() else None
    executable = main_executable(bundle, info) if bundle.is_dir() else None
    exec_facts = file_facts(executable) if executable is not None else {
        "path": None, "sha256": None, "size_bytes": None, "mtime": None,
    }
    embedded = {"source_revision": _unknown(), "build_identity": _unknown()}
    if executable is not None and exec_facts["sha256"] is not None:
        try:
            data = executable.read_bytes()
        except OSError:
            data = b""
        version = (info or {}).get("CFBundleShortVersionString")
        embedded = extract_embedded(data, version if isinstance(version, str) else None)
    receipt = {
        "schema": SCHEMA,
        "bundle_path": str(bundle),
        "bundle_exists": bundle.is_dir(),
        "info_plist": info,
        "executable": exec_facts,
        "source_revision": embedded["source_revision"],
        "build_identity": embedded["build_identity"],
        "codesign": codesign_display(bundle) if bundle.is_dir() else {
            "status": "unknown", "identifier": None, "team_identifier": None,
            "signature": None, "detail": "bundle not present",
        },
        "running_app": running_app(executable if bundle.is_dir() else None),
        "observed_at": observed_at or utc_now_iso(),
        "host": host or platform.node(),
    }
    receipt["receipt_digest"] = receipt_digest(receipt)
    return receipt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mmos_installed_receipt.py",
        description="Read-only installed-bundle receipt observer "
                    f"({SCHEMA}). Never writes, launches or kills anything.",
    )
    parser.add_argument(
        "--bundle",
        default=DEFAULT_BUNDLE,
        help=f"installed .app bundle to observe (default: {DEFAULT_BUNDLE})",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="emit single-line JSON instead of pretty-printed JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.bundle or not args.bundle.strip():
        print("mmos_installed_receipt.py: --bundle must be a non-empty path", file=sys.stderr)
        return 2
    try:
        receipt = observe_bundle(args.bundle)
    except OSError as error:
        print(f"mmos_installed_receipt.py: observation failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=None if args.compact else 2, sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
