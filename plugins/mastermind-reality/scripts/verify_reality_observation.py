"""Pure, stateless deterministic verifier for one Mastermind Reality observation.

Contract
--------
``verify_observation_file(observation_path, evidence_root, schema_path)`` reads one
closed observation record, one owner-qualified evidence root, and the packaged
observation schema, and returns one closed verification receipt.

The function is pure and stateless. It performs no write, no network access, no
subprocess, no repository or filesystem search, and it creates no database,
evidence store, browser registry, lifecycle, identity, retry, queue, browser or
control plane. The caller supplies the owner-qualified evidence root; this API
grants no authority of any kind.

A ``VALID`` verdict proves exactly one thing: the supplied record and the
supplied artifacts are mutually consistent. It does not prove newly
authenticated model consumption, a real-product success, installation,
deployment, or runtime authority.

Every failure is a closed error code with a bounded, sanitized detail. Secret
values are never echoed back.
"""

from __future__ import annotations

import datetime as _datetime
import errno
import hashlib
import json
import math
import os
import re
import stat
import struct
import zlib
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

RECEIPT_SCHEMA = "mastermind.reality_verification_receipt.v1"
OBSERVATION_SCHEMA = "mastermind.reality_observation.v1"

MAX_OBSERVATION_BYTES = 8 * 1024 * 1024
MAX_SCHEMA_BYTES = 4 * 1024 * 1024
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
MAX_PNG_IDAT_BYTES = 16 * 1024 * 1024
MAX_PNG_RASTER_BYTES = 64 * 1024 * 1024
MAX_ERROR_DETAIL = 240
READ_CHUNK = 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_ERRORS = 256
MAX_TOTAL_ARTIFACT_BYTES = 128 * 1024 * 1024

# Closed error codes. Nothing outside this tuple may be emitted.
ERROR_CODES = (
    "ARTIFACT_DIGEST_MISMATCH",
    "ARTIFACT_IDENTITY_CONFLICT",
    "ARTIFACT_IDENTITY_UNRESOLVED",
    "ARTIFACT_MISSING",
    "ARTIFACT_NOT_REGULAR_FILE",
    "ARTIFACT_REF_INVALID",
    "ARTIFACT_SIZE_MISMATCH",
    "CAPABILITY_CONSISTENCY_INVALID",
    "CLEANUP_CLAIM_INVALID",
    "CONSUMPTION_BINDING_INVALID",
    "CORRECTION_INVALID",
    "EVIDENCE_REF_UNDECLARED",
    "EVIDENCE_ROOT_INVALID",
    "EVIDENCE_STATE_INVALID",
    "EFFECT_INVALID",
    "FINDING_INVALID",
    "JSON_DUPLICATE_KEY",
    "JSON_INVALID",
    "JSON_NON_FINITE",
    "NEGATIVE_CONTROL_INVALID",
    "OBSERVATION_UNREADABLE",
    "PNG_DIMENSION_MISMATCH",
    "PNG_INVALID",
    "SCHEMA_INVALID",
    "SCHEMA_UNREADABLE",
    "SCHEMA_VIOLATION",
    "SECRET_SHAPED_VALUE",
    "SOURCE_RELATION_INVALID",
    "TARGET_INVALID",
    "TIME_ORDER_INVALID",
    "TIMESTAMP_INVALID",
)

# The closed negative-control contract. Each control must carry exactly the
# method and signal that make it discriminate its own bad state.
NEGATIVE_CONTROL_CONTRACT = {
    "wrong_target": ("OWNER_EVIDENCE", "HTTP_404"),
    "stale_capture": ("OWNER_EVIDENCE", "STALE_INPUT_DISCLOSED"),
    "different_build": ("OWNER_EVIDENCE", "SOURCE_SHA_DISTINCT"),
    "different_viewport_or_data_state": (
        "OWNER_EVIDENCE",
        "VIEWPORT_OR_DATA_STATE_DISTINCT",
    ),
    "missing_screenshot_bytes": ("CONTRACT_REFUSAL", "SCREENSHOT_BYTES_REQUIRED"),
    "broken_browser_connection": ("OWNER_EVIDENCE", "PROVIDER_DISCONNECTED"),
    "excluded_account_surface": ("CONTRACT_REFUSAL", "TARGET_CLASS_EXCLUDED"),
}

NEGATIVE_CONTROL_STATUSES = ("DETECTED", "REFUSED", "NOT_EXERCISED")

# Schema violations are reported under a closed, pointer-derived code so that a
# hostile record never fails for an unrelated generic reason.
POINTER_CODES = (
    ("revision", "CORRECTION_INVALID"),
    ("effect", "EFFECT_INVALID"),
    ("cleanup", "CLEANUP_CLAIM_INVALID"),
    ("negative_controls", "NEGATIVE_CONTROL_INVALID"),
    ("findings", "FINDING_INVALID"),
    ("source_relationship", "SOURCE_RELATION_INVALID"),
    ("journey", "JOURNEY_INVALID"),
    ("target", "TARGET_INVALID"),
    ("capture", "CAPTURE_INVALID"),
)

SAFE_REF_PATTERN = (
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?![A-Za-z][A-Za-z0-9+.-]*://)"
    r"[A-Za-z0-9][A-Za-z0-9._/-]{0,511}$"
)

_UTC_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?Z$"
)

# Secret shapes are matched without embedding any literal credential prefix.
_SECRET_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github[_]pat[_][A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])sk[-](?:proj|ant|svcacct|admin)[-][A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])sk[-][A-Za-z0-9_-]{32,}"),
    re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"(?<![A-Za-z0-9])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class _DuplicateKeyError(ValueError):
    """Raised when a JSON object repeats a key."""


class _NonFiniteError(ValueError):
    """Raised when a JSON document carries a non-finite number."""


def _strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKeyError(str(key))
        out[key] = value
    return out


def _reject_constant(name):
    raise _NonFiniteError(str(name))


def _strict_float(text):
    value = float(text)
    if not math.isfinite(value):
        raise _NonFiniteError(text)
    return value


def _strict_loads(text):
    """Strict JSON with finite numbers, unique keys and bounded traversal."""
    node = json.loads(
        text,
        object_pairs_hook=_strict_pairs,
        parse_constant=_reject_constant,
        parse_float=_strict_float,
    )
    stack = [(node, 0)]
    count = 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > MAX_JSON_DEPTH or count > MAX_JSON_NODES:
            raise ValueError("JSON structure exceeds the supported budget")
        if isinstance(value, dict):
            count += len(value)  # Keys are input nodes too.
            if count + len(stack) + len(value) > MAX_JSON_NODES:
                raise ValueError("JSON structure exceeds the supported budget")
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            if count + len(stack) + len(value) > MAX_JSON_NODES:
                raise ValueError("JSON structure exceeds the supported budget")
            stack.extend((child, depth + 1) for child in value)
    return node


def _utc_epoch_ns(text):
    """Return integer nanoseconds for a strict UTC RFC 3339 ``Z`` timestamp.

    Returns ``None`` when the value is not a real UTC calendar instant.
    """
    if not isinstance(text, str):
        return None
    match = _UTC_RE.fullmatch(text)
    if match is None:
        return None
    year, month, day, hour, minute, second = (int(g) for g in match.groups()[:6])
    fraction = match.group(7) or ""
    try:
        base = _datetime.datetime(
            year, month, day, hour, minute, second, tzinfo=_datetime.timezone.utc
        )
    except ValueError:
        return None
    nanos = int((fraction + "000000000")[:9]) if fraction else 0
    return int(base.timestamp()) * 1_000_000_000 + nanos


def _has_secret(text):
    return isinstance(text, str) and any(p.search(text) for p in _SECRET_PATTERNS)


def _sanitize(detail):
    """Redact before truncating; no partial credential survives the bound."""
    text = str(detail)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    text = " ".join(text.split())
    return text if len(text) <= MAX_ERROR_DETAIL else text[:MAX_ERROR_DETAIL - 3] + "..."


def _walk_strings(node, path="$"):
    """Iterate keys and values without exposing input keys in output paths."""
    pending = [(node, path)]
    while pending:
        value, site = pending.pop()
        if isinstance(value, str):
            yield site, value
        elif isinstance(value, dict):
            for index, (key, child) in reversed(list(enumerate(value.items()))):
                yield "%s.key[%d]" % (site, index), key
                pending.append((child, "%s.value[%d]" % (site, index)))
        elif isinstance(value, list):
            pending.extend(
                (child, "%s[%d]" % (site, index))
                for index, child in reversed(list(enumerate(value)))
            )


def _safe_ref(ref):
    return (
        isinstance(ref, str)
        and re.fullmatch(SAFE_REF_PATTERN, ref) is not None
        and all(part not in ("", ".", "..") for part in ref.split("/"))
    )


class _ReadRefusal(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode


def _version(info):
    return _identity(info) + (info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_flags():
    # Unsupported hosts fail closed; there is no follow-symlinks fallback.
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _check_links(links):
    for parent, name, expected in links:
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if _identity(current) != _identity(expected) or not stat.S_ISDIR(current.st_mode):
            raise _ReadRefusal("ARTIFACT_REF_INVALID")


def _open_directory_chain(path):
    """Walk only the explicitly supplied path, retaining directory identities."""
    fds, links = [], []
    try:
        absolute = os.path.abspath(os.fspath(path))
        if not isinstance(absolute, str) or "\x00" in absolute:
            raise _ReadRefusal("ARTIFACT_REF_INVALID")
        fds.append(os.open(os.sep, _directory_flags()))
        for name in absolute.split(os.sep):
            if not name:
                continue
            before = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise _ReadRefusal("ARTIFACT_REF_INVALID")
            child = os.open(name, _directory_flags(), dir_fd=fds[-1])
            fds.append(child)
            after = os.fstat(child)
            if _identity(before) != _identity(after):
                raise _ReadRefusal("ARTIFACT_REF_INVALID")
            links.append((fds[-2], name, after))
        _check_links(links)
        return fds, links
    except BaseException:
        for fd in reversed(fds):
            os.close(fd)
        raise


def _read_relative(root_fd, ref, limit, root_links):
    """Read once through a no-follow descriptor, then prove its identity."""
    fds, links = [], list(root_links)
    file_fd = None
    try:
        parent = root_fd
        parts = ref.split("/")
        for name in parts[:-1]:
            before = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise _ReadRefusal("ARTIFACT_REF_INVALID")
            child = os.open(name, _directory_flags(), dir_fd=parent)
            fds.append(child)
            after = os.fstat(child)
            if _identity(before) != _identity(after):
                raise _ReadRefusal("ARTIFACT_REF_INVALID")
            links.append((parent, name, after))
            parent = child
        leaf = parts[-1]
        named_before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISLNK(named_before.st_mode):
            raise _ReadRefusal("ARTIFACT_REF_INVALID")
        if not stat.S_ISREG(named_before.st_mode):
            raise _ReadRefusal("ARTIFACT_NOT_REGULAR_FILE")
        file_fd = os.open(
            leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=parent,
        )
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise _ReadRefusal("ARTIFACT_NOT_REGULAR_FILE")
        if _version(named_before) != _version(before):
            raise _ReadRefusal("ARTIFACT_REF_INVALID")
        if before.st_size > limit:
            raise _ReadRefusal("ARTIFACT_SIZE_MISMATCH")
        chunks, count = [], 0
        while True:
            chunk = os.read(file_fd, min(READ_CHUNK, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > limit:
                raise _ReadRefusal("ARTIFACT_SIZE_MISMATCH")
            chunks.append(chunk)
        after = os.fstat(file_fd)
        named_after = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        if (
            _version(before) != _version(after)
            or _version(after) != _version(named_after)
            or count != after.st_size
        ):
            raise _ReadRefusal("ARTIFACT_REF_INVALID")
        _check_links(links)
        return b"".join(chunks)
    except OSError as exc:
        code = "ARTIFACT_REF_INVALID" if exc.errno in (errno.ELOOP, errno.ENOTDIR) else "ARTIFACT_MISSING"
        raise _ReadRefusal(code) from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for fd in reversed(fds):
            os.close(fd)


def _read_regular_input(path, limit):
    """Explicit observation/schema input: bounded, regular and stable."""
    fds = []
    try:
        absolute = os.path.abspath(os.fspath(path))
        parent, leaf = os.path.split(absolute)
        fds, links = _open_directory_chain(parent)
        return _read_relative(fds[-1], leaf, limit, links)
    finally:
        for fd in reversed(fds):
            os.close(fd)


class _QualifiedArtifacts:
    """One invocation's byte cache; no persistent store or authority."""
    def __init__(self, root):
        self.fds, self.links = _open_directory_chain(root)
        self.cache = {}
        self.total = 0

    def close(self):
        for fd in reversed(self.fds):
            os.close(fd)
        self.fds = []

    def read(self, ref, limit=MAX_ARTIFACT_BYTES):
        if not _safe_ref(ref):
            raise _ReadRefusal("ARTIFACT_REF_INVALID")
        if ref in self.cache:
            result = self.cache[ref]
            if isinstance(result, _ReadRefusal):
                raise result
            if len(result) > limit:
                raise _ReadRefusal("ARTIFACT_SIZE_MISMATCH")
            return result
        try:
            data = _read_relative(
                self.fds[-1], ref,
                min(limit, MAX_TOTAL_ARTIFACT_BYTES - self.total), self.links,
            )
        except _ReadRefusal as exc:
            self.cache[ref] = exc
            raise
        self.total += len(data)
        self.cache[ref] = data
        return data


def _payload(entry):
    """Parse only already-qualified bytes, at most once for each artifact."""
    if entry is None or not entry.get("qualified"):
        return None
    if "payload" not in entry:
        try:
            if len(entry["raw"]) > MAX_OBSERVATION_BYTES:
                raise ValueError("JSON witness exceeds the supported budget")
            value = _strict_loads(entry["raw"].decode("utf-8"))
            entry["payload"] = value if isinstance(value, dict) else None
        except (UnicodeDecodeError, ValueError, RecursionError):
            entry["payload"] = None
    return entry["payload"]


def _record_shape_safe(record):
    """Admit containers before semantic helpers, even with a bad schema."""
    if not isinstance(record, dict):
        return False
    for key in (
        "revision", "persona", "target", "source_relationship", "journey",
        "capture", "negative_controls", "effect", "cleanup", "next_action",
    ):
        if not isinstance(record.get(key), dict):
            return False
    capture = record["capture"]
    shots, findings = capture.get("screenshots"), record.get("findings")
    if not isinstance(shots, list) or not isinstance(findings, list):
        return False
    descriptors = []
    for shot in shots:
        if not isinstance(shot, dict):
            return False
        if not isinstance(shot.get("viewport"), dict) or not isinstance(shot.get("consumption"), dict):
            return False
        descriptors.append(shot)
        for key in ("proof_ref", "proof_sha256", "consumer_ref"):
            if shot["consumption"].get(key) is not None and not isinstance(shot["consumption"][key], str):
                return False
    for family in ("semantic_evidence", "runtime_evidence"):
        block = capture.get(family)
        if not isinstance(block, dict) or not isinstance(block.get("artifacts"), list):
            return False
        descriptors.extend(block["artifacts"])
    for name in ("effect", "cleanup"):
        block = record[name]
        if not isinstance(block.get("evidence"), list):
            return False
        descriptors.extend(block["evidence"])
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            return False
        for key in ("artifact_ref", "sha256"):
            if descriptor.get(key) is not None and not isinstance(descriptor[key], str):
                return False
    for finding in findings:
        if not isinstance(finding, dict):
            return False
        if finding.get("finding_id") is not None and not isinstance(finding["finding_id"], str):
            return False
    for block in [*findings, *record["negative_controls"].values()]:
        if not isinstance(block, dict) or not isinstance(block.get("evidence_refs"), list):
            return False
        if not all(isinstance(ref, str) for ref in block["evidence_refs"]):
            return False
    for field in ("changed_input_refs", "affected_finding_ids"):
        value = record["revision"].get(field)
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            return False
    return True


def _schema_without_references(schema):
    if not isinstance(schema, dict):
        return False
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        return False
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        return False
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not isinstance(properties.get("schema"), dict):
        return False
    if properties["schema"].get("const") != OBSERVATION_SCHEMA:
        return False
    pending = [schema]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if {"$ref", "$dynamicRef", "$recursiveRef"} & node.keys():
                return False
            if "$schema" in node and node["$schema"] != schema["$schema"]:
                return False
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return True


def _schema_path(error):
    # Field names from untrusted JSON/schema never become receipt text.
    return "observation" + "".join(
        "[%d]" % item if isinstance(item, int) else ".field"
        for item in error.absolute_path
    )


def _png_dimensions(data):
    """Validate the bounded default-image raster and return its dimensions.

    PNG3 critical-chunk, filter and Adam7 rules apply. Ancillary payloads are
    CRC checked but not interpreted. Final-IDAT padding is not another image.
    """
    if not data.startswith(_PNG_SIGNATURE):
        return None
    position, total = len(_PNG_SIGNATURE), len(data)
    geometry = None
    palette_size = None
    idat = bytearray()
    seen_idat, after_idat, seen_iend = False, False, False
    while position < total:
        if total - position < 12:
            return None
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        position += 8
        if (
            length > MAX_ARTIFACT_BYTES
            or position + length + 4 > total
            or not all(65 <= ch <= 90 or 97 <= ch <= 122 for ch in kind)
        ):
            return None
        payload = data[position:position + length]
        position += length
        crc = struct.unpack(">I", data[position:position + 4])[0]
        position += 4
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            return None
        if geometry is None and kind != b"IHDR":
            return None
        if seen_idat and kind != b"IDAT":
            after_idat = True
        if kind == b"IHDR":
            if geometry is not None or length != 13:
                return None
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", payload)
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            if (
                not 1 <= width <= 16384 or not 1 <= height <= 16384
                or color not in depths or depth not in depths[color]
                or compression != 0 or filtering != 0 or interlace not in (0, 1)
            ):
                return None
            geometry = width, height, depth, color, interlace
        elif kind == b"PLTE":
            if (
                palette_size is not None or seen_idat or color in (0, 4)
                or not length or length % 3 or length > 768
            ):
                return None
            palette_size = length // 3
            if color == 3 and palette_size > 2 ** depth:
                return None
        elif kind == b"IDAT":
            if after_idat or (color == 3 and palette_size is None):
                return None
            seen_idat = True
            if len(idat) + length > MAX_PNG_IDAT_BYTES:
                return None
            idat.extend(payload)
        elif kind == b"IEND":
            if length != 0 or not seen_idat or position != total:
                return None
            seen_iend = True
            break
        elif not kind[0] & 32:
            return None  # An unknown critical chunk cannot be ignored.
    if geometry is None or not seen_iend or not idat:
        return None
    bits_per_pixel = _PNG_CHANNELS[color] * depth
    steps = ((0, 0, 1, 1),) if interlace == 0 else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
        (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
    )
    passes, expected = [], 0
    for x, y, dx, dy in steps:
        columns = max(0, (width - x + dx - 1) // dx)
        rows = max(0, (height - y + dy - 1) // dy)
        if not columns or not rows:
            continue  # Empty Adam7 passes have no filter bytes.
        row_bytes = (columns * bits_per_pixel + 7) // 8
        expected += rows * (row_bytes + 1)
        if expected > MAX_PNG_RASTER_BYTES:
            return None
        passes.append((columns, rows, row_bytes))
    try:
        decoder = zlib.decompressobj()
        raster = decoder.decompress(bytes(idat), expected + 1)
    except zlib.error:
        return None
    # No unbounded flush: the extra byte distinguishes an oversized raster.
    # PNG3 permits unused bytes after the zlib stream in final IDAT data.
    if not decoder.eof or decoder.unconsumed_tail or len(raster) != expected:
        return None
    offset, stride = 0, max(1, (bits_per_pixel + 7) // 8)
    for columns, rows, row_bytes in passes:
        previous = bytearray(row_bytes)
        for _ in range(rows):
            filter_type = raster[offset]
            offset += 1
            if filter_type > 4:
                return None
            row = bytearray(raster[offset:offset + row_bytes])
            offset += row_bytes
            if color != 3:
                continue  # Every reconstructed non-indexed sample is legal.
            for index in range(row_bytes):
                left = row[index - stride] if index >= stride else 0
                up = previous[index]
                corner = previous[index - stride] if index >= stride else 0
                if filter_type == 1:
                    predictor = left
                elif filter_type == 2:
                    predictor = up
                elif filter_type == 3:
                    predictor = (left + up) // 2
                elif filter_type == 4:
                    center = left + up - corner
                    distances = (abs(center - left), abs(center - up), abs(center - corner))
                    predictor = (left, up, corner)[distances.index(min(distances))]
                else:
                    predictor = 0
                row[index] = (row[index] + predictor) & 255
            mask = (1 << depth) - 1
            for index in range(columns):
                bit = index * depth
                value = (row[bit // 8] >> (8 - depth - bit % 8)) & mask
                if value >= palette_size:
                    return None
            # Unused low-order packed-sample bits are intentionally ignored.
            previous = row
    return width, height


def _collect_declarations(record):
    """Collect every declared artifact identity from one observation record.

    Returns a list of declaration dictionaries in a deterministic order.
    """
    declarations = []
    capture = record.get("capture") or {}
    screenshots = capture.get("screenshots") or []
    for index, screenshot in enumerate(screenshots):
        screenshot = screenshot or {}
        viewport = screenshot.get("viewport") or {}
        declarations.append(
            {
                "site": "capture.screenshots[%d]" % index,
                "ref": screenshot.get("artifact_ref"),
                "sha256": screenshot.get("sha256"),
                "bytes": screenshot.get("bytes"),
                "kind": "screenshot",
                "width": viewport.get("width"),
                "height": viewport.get("height"),
            }
        )
        consumption = screenshot.get("consumption") or {}
        declarations.append(
            {
                "site": "capture.screenshots[%d].consumption.proof_ref" % index,
                "ref": consumption.get("proof_ref"),
                "sha256": consumption.get("proof_sha256"),
                "bytes": None,
                "kind": "consumption_proof",
                "width": None,
                "height": None,
            }
        )
    for family in ("semantic_evidence", "runtime_evidence"):
        block = capture.get(family) or {}
        for index, artifact in enumerate(block.get("artifacts") or []):
            artifact = artifact or {}
            declarations.append(
                {
                    "site": "capture.%s.artifacts[%d]" % (family, index),
                    "ref": artifact.get("artifact_ref"),
                    "sha256": artifact.get("sha256"),
                    "bytes": None,
                    "kind": family,
                    "width": None,
                    "height": None,
                }
            )
    for block_name in ("effect", "cleanup"):
        block = record.get(block_name) or {}
        for index, artifact in enumerate(block.get("evidence") or []):
            artifact = artifact or {}
            declarations.append(
                {
                    "site": "%s.evidence[%d]" % (block_name, index),
                    "ref": artifact.get("artifact_ref"),
                    "sha256": artifact.get("sha256"),
                    "bytes": None,
                    "kind": block_name,
                    "width": None,
                    "height": None,
                }
            )
    return declarations


def _declared_identities(declarations):
    """Map one artifact reference to the set of declared digests for it."""
    identities = {}
    for declaration in declarations:
        ref = declaration["ref"]
        digest = declaration["sha256"]
        if not isinstance(ref, str):
            continue
        identities.setdefault(ref, set())
        if isinstance(digest, str):
            identities[ref].add(digest)
    return identities


def _predecessor_identities(predecessor):
    """Return the artifact identities declared by a predecessor record."""
    identities = {}
    for declaration in _collect_declarations(predecessor):
        ref = declaration["ref"]
        digest = declaration["sha256"]
        if isinstance(ref, str) and isinstance(digest, str):
            identities[ref] = digest
    return identities


def _block_identities(record, block_name):
    """Return the effect or cleanup evidence identities declared by a record."""
    identities = {}
    block = (record or {}).get(block_name) or {}
    for artifact in block.get("evidence") or []:
        artifact = artifact or {}
        ref = artifact.get("artifact_ref")
        digest = artifact.get("sha256")
        if isinstance(ref, str) and isinstance(digest, str):
            identities[ref] = digest
    return identities


def _schema_error_code(error):
    """Map one schema violation to a closed, pointer-derived error code.

    Artifact-reference safety is not decided here. It is decided by the
    resolver, so that weakening the resolver is observable in the receipt.
    """
    path = list(error.absolute_path)
    for prefix, code in POINTER_CODES:
        if path and path[0] == prefix:
            return code
    return "SCHEMA_VIOLATION"


def _check_secret_shapes(record, add):
    for path, text in _walk_strings(record):
        for pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                add(
                    "SECRET_SHAPED_VALUE",
                    path,
                    "a secret-shaped value is present in this public text field",
                )
                break


def _check_timestamps(record, add):
    checks = (
        ("recorded_at", record.get("recorded_at")),
        ("capture.started_at", (record.get("capture") or {}).get("started_at")),
        ("capture.completed_at", (record.get("capture") or {}).get("completed_at")),
    )
    checks += tuple(
        ("capture.screenshots[%d].consumption.consumed_at" % index,
         screenshot["consumption"].get("consumed_at"))
        for index, screenshot in enumerate(record["capture"]["screenshots"])
    )
    relationship = record.get("source_relationship") or {}
    checks = checks + (
        ("source_relationship.observed_at", relationship.get("observed_at")),
    )
    values = {}
    for name, value in checks:
        if value is None:
            continue
        stamp = _utc_epoch_ns(value)
        if stamp is None:
            add(
                "TIMESTAMP_INVALID",
                name,
                "value is not a real UTC calendar instant ending in Z",
            )
        else:
            values[name] = stamp
    started = values.get("capture.started_at")
    completed = values.get("capture.completed_at")
    if started is not None and completed is not None and completed < started:
        add(
            "TIME_ORDER_INVALID",
            "capture.completed_at",
            "capture completion precedes capture start",
        )


def _check_source_relationship(record, add):
    relationship = record.get("source_relationship") or {}
    relation = relationship.get("relation")
    protected = relationship.get("protected_sha")
    deployed = relationship.get("observed_deployed_sha")
    comparison = relationship.get("revision_comparison")
    for field, revision in (("protected_sha", protected), ("observed_deployed_sha", deployed)):
        if field == "observed_deployed_sha" and revision is None:
            continue
        if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship." + field,
                "source revision must be a 40-character lowercase hexadecimal Git SHA",
            )
    if relation == "MATCH":
        if not isinstance(protected, str) or not isinstance(deployed, str):
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship",
                "MATCH requires both source revisions to be observed",
            )
        elif protected != deployed:
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship",
                "MATCH requires identical source revisions",
            )
        if comparison != "EQUAL":
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship.revision_comparison",
                "MATCH requires an exact comparison receipt",
            )
    elif relation == "DIFFERENT":
        if not isinstance(protected, str) or not isinstance(deployed, str):
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship",
                "DIFFERENT requires both source revisions to be observed",
            )
        elif protected == deployed:
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship",
                "DIFFERENT requires distinct source revisions",
            )
        if comparison != "DISTINCT":
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship.revision_comparison",
                "DIFFERENT requires an exact comparison receipt",
            )
    elif relation == "UNKNOWN":
        if deployed is not None or comparison != "UNOBSERVABLE":
            add(
                "SOURCE_RELATION_INVALID",
                "source_relationship",
                "UNKNOWN requires an unobservable deployed revision",
            )


def _opaque_identity(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}", value) is not None


def _control_witness_matches(name, witness, record, references, resolved):
    """Interpret one explicitly bound negative case, never a primary success."""
    if not isinstance(witness, dict):
        return False
    effect, capture = record["effect"], record["capture"]
    observed = _utc_epoch_ns(witness.get("observed_at"))
    started = _utc_epoch_ns(capture.get("started_at"))
    completed = _utc_epoch_ns(capture.get("completed_at"))
    if (
        witness.get("control") != name
        or witness.get("operation_ref") != effect.get("operation_ref")
        or witness.get("carrier_ref") != effect.get("carrier_ref")
        or not _opaque_identity(witness.get("case_ref"))
        or observed is None or started is None or completed is None
        or not started <= observed <= completed
    ):
        return False
    target = witness.get("target_ref")
    if not isinstance(target, str) or not target or len(target) > 1000:
        return False
    if name in ("wrong_target", "different_build", "excluded_account_surface"):
        if target == record["target"].get("locator"):
            return False
    if name == "wrong_target":
        return type(witness.get("http_status")) is int and witness["http_status"] == 404
    if name == "stale_capture":
        captured = _utc_epoch_ns(witness.get("input_captured_at"))
        threshold = _utc_epoch_ns(witness.get("required_not_before"))
        return (
            captured is not None and threshold is not None
            and captured < threshold <= observed
            and witness.get("stale_disclosed") is True
            and _safe_ref(witness.get("input_ref"))
            and isinstance(witness.get("input_sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", witness["input_sha256"]) is not None
        )
    if name == "different_build":
        expected, actual = witness.get("protected_sha"), witness.get("observed_deployed_sha")
        return (
            isinstance(expected, str) and isinstance(actual, str)
            and re.fullmatch(r"[0-9a-f]{40}", expected) is not None
            and re.fullmatch(r"[0-9a-f]{40}", actual) is not None
            and expected == record["source_relationship"].get("protected_sha")
            and expected != actual
        )
    if name == "different_viewport_or_data_state":
        first, second = witness.get("first_artifact_ref"), witness.get("second_artifact_ref")
        if not isinstance(first, str) or not isinstance(second, str):
            return False
        a, b = resolved.get(first), resolved.get(second)
        return (
            first in references and second in references
            and _payload(a) is not None and _payload(b) is not None
            and a["sha256"] != b["sha256"]
            and isinstance(_payload(a).get("data_state"), str)
            and isinstance(_payload(b).get("data_state"), str)
            and _payload(a)["data_state"] != _payload(b)["data_state"]
        )
    if name == "missing_screenshot_bytes":
        attempted = witness.get("attempted_artifact_ref")
        return (
            witness.get("screenshot_bytes_present") is False
            and witness.get("refusal_code") == "SCREENSHOT_BYTES_REQUIRED"
            and _safe_ref(attempted) and attempted not in resolved
        )
    if name == "broken_browser_connection":
        return (
            witness.get("connection_state") == "DISCONNECTED"
            and _opaque_identity(witness.get("provider_ref"))
            and target == record["target"].get("locator")
        )
    if name == "excluded_account_surface":
        return (
            witness.get("surface_class") == "MANAGED_CHAIRMAN_ACCOUNT"
            and witness.get("refusal_code") == "TARGET_CLASS_EXCLUDED"
            and witness.get("access_attempted") is False
        )
    return False


def _check_negative_controls(record, declared_refs, resolved, add):
    controls = record["negative_controls"]
    for name, (method, signal) in NEGATIVE_CONTROL_CONTRACT.items():
        control = controls.get(name)
        path = "negative_controls." + name
        if not isinstance(control, dict):
            add("NEGATIVE_CONTROL_INVALID", path, "this required negative control is absent")
            continue
        if control.get("method") != method or control.get("signal") != signal:
            add("NEGATIVE_CONTROL_INVALID", path, "the control method or signal does not discriminate its bad state")
        status, references = control.get("status"), control.get("evidence_refs", [])
        if status not in NEGATIVE_CONTROL_STATUSES:
            add("NEGATIVE_CONTROL_INVALID", path, "control status is not a closed state")
        for ref in references:
            if ref not in declared_refs or not resolved.get(ref, {}).get("qualified"):
                add("NEGATIVE_CONTROL_INVALID", path, "control evidence is not an identity-qualified declared artifact")
        if status == "NOT_EXERCISED":
            continue
        wanted = "DETECTED" if method == "OWNER_EVIDENCE" else "REFUSED"
        if status != wanted:
            add("NEGATIVE_CONTROL_INVALID", path, "the recorded result does not match the control method")
        witnessed, contradiction = False, False
        for ref in references:
            payload = _payload(resolved.get(ref))
            facts = payload.get("negative_controls") if isinstance(payload, dict) else None
            if isinstance(facts, dict) and name in facts:
                matches = _control_witness_matches(name, facts[name], record, references, resolved)
                witnessed = witnessed or matches
                contradiction = contradiction or not matches
        if name == "different_viewport_or_data_state":
            dimensions = {
                resolved[ref]["dimensions"] for ref in references
                if ref in resolved and resolved[ref].get("qualified")
                and resolved[ref].get("dimensions") is not None
            }
            # These are decoded bytes from this capture, not viewport labels.
            witnessed = witnessed or len(dimensions) > 1
        if not witnessed or contradiction:
            add("NEGATIVE_CONTROL_INVALID", path, "the supplied bytes do not consistently witness this negative case")


def _check_reference_closure(record, declared_refs, add):
    findings = record.get("findings") or []
    for index, finding in enumerate(findings):
        finding = finding or {}
        for reference in finding.get("evidence_refs") or []:
            if reference not in declared_refs:
                add(
                    "EVIDENCE_REF_UNDECLARED",
                    "findings[%d].evidence_refs" % index,
                    "finding evidence does not resolve to a declared artifact",
                )


def _check_evidence_semantics(record, add):
    capture = record.get("capture") or {}
    for family in ("semantic_evidence", "runtime_evidence"):
        block = capture.get(family) or {}
        state = block.get("state")
        artifacts = block.get("artifacts") or []
        reason = block.get("reason")
        path = "capture.%s" % family
        if state == "AVAILABLE" and (not artifacts or reason is not None):
            add(
                "EVIDENCE_STATE_INVALID",
                path,
                "AVAILABLE requires retained artifacts and no limitation reason",
            )
        elif state == "PARTIAL" and (not artifacts or not reason):
            add(
                "EVIDENCE_STATE_INVALID",
                path,
                "PARTIAL requires retained artifacts and a concrete reason",
            )
        elif state == "UNAVAILABLE" and (artifacts or not reason):
            add(
                "EVIDENCE_STATE_INVALID",
                path,
                "UNAVAILABLE requires zero artifacts and a concrete reason",
            )


def _capability_problem(record, unresolved):
    """Return the first PROVEN_LIVE consistency problem, else ``None``."""
    if record.get("capability_state") != "PROVEN_LIVE":
        return None
    target = record.get("target") or {}
    journey = record.get("journey") or {}
    if target.get("surface_class") == "TEST_FIXTURE":
        return "target.surface_class is TEST_FIXTURE"
    outcome = journey.get("outcome")
    if outcome != "SUCCESS":
        return "the journey is not a recorded success"
    if target.get("observed_surface_state") != "LIVE":
        return "the observed surface is not recorded as live"
    if not target.get("architecture_ref"):
        return "target.architecture_ref is an unknown architecture binding"
    controls = record.get("negative_controls") or {}
    unexercised = sorted(
        name
        for name, control in controls.items()
        if isinstance(control, dict) and control.get("status") == "NOT_EXERCISED"
    )
    if unexercised:
        return "at least one required negative control was not exercised"
    if unresolved:
        return "the record carries an unresolved artifact identity"
    return None


def _effect_payload_matches(payload, effect):
    return isinstance(payload, dict) and all(
        payload.get(key) == effect.get(key)
        for key in ("state", "operation_ref", "carrier_ref")
    )


def _effect_problem(record, resolved):
    effect = record["effect"]
    evidence = effect.get("evidence", [])
    if not evidence:
        return "the effect has no owner-recorded evidence"
    for descriptor in evidence:
        if not _effect_payload_matches(_payload(resolved.get(descriptor.get("artifact_ref"))), effect):
            return "effect evidence does not agree with the original operation, carrier and state"
    return None


def _cleanup_problem(record, cleanup_payloads):
    """A positive profile claim needs named, typed before/after facts."""
    cleanup, effect = record["cleanup"], record["effect"]
    state, profile = cleanup.get("state"), cleanup.get("temporary_profile")
    if state == "CLEAN" and cleanup.get("temporary_processes") != "ABSENT":
        return "CLEAN requires absent temporary processes"
    if state == "CLEAN" and cleanup.get("shared_resources") != "UNCHANGED":
        return "CLEAN requires unchanged shared resources"
    if state == "CLEAN" and profile not in ("REMOVED", "NOT_CREATED"):
        return "CLEAN requires a proven removed or never-created profile"
    if profile not in ("REMOVED", "NOT_CREATED"):
        return None
    expected = cleanup.get("temporary_profile_id")
    if not _opaque_identity(expected):
        return "a positive profile claim requires the explicitly intended profile identity"
    grounded, terminal = False, False
    for payload in cleanup_payloads:
        if not isinstance(payload, dict):
            return "positive cleanup evidence must be a qualified JSON object"
        for field in ("operation_ref", "carrier_ref"):
            if field in payload and payload[field] != effect.get(field):
                return "the cleanup witness names a different original operation or carrier"
        for field in ("temporary_processes", "shared_resources", "temporary_profile"):
            if field in payload and payload[field] != cleanup.get(field):
                return "a cleanup witness contradicts the recorded disposition"
        terminal = terminal or (
            payload.get("temporary_processes") == "ABSENT"
            and payload.get("shared_resources") == "UNCHANGED"
        )
        if "temporary_profile_id" not in payload:
            continue
        if payload["temporary_profile_id"] != expected:
            return "a cleanup witness names a different intended profile"
        before = payload.get("pre_removal")
        if not isinstance(before, dict) or before.get("temporary_profile_id") != expected:
            return "the profile witness lacks a bound before-state"
        before_time = _utc_epoch_ns(before.get("observed_at"))
        if before_time is None:
            return "the profile before-state has no valid observation time"
        if profile == "REMOVED":
            after = payload.get("post_removal")
            if not isinstance(after, dict) or after.get("temporary_profile_id") != expected:
                return "the profile witness lacks a bound after-state"
            after_time = _utc_epoch_ns(after.get("observed_at"))
            if (
                before.get("present") is not True or after.get("present") is not False
                or after_time is None or after_time < before_time
            ):
                return "REMOVED requires ordered presence and absence facts for the same profile"
        else:
            decision = payload.get("creation")
            if not isinstance(decision, dict):
                return "NOT_CREATED requires an explicit owner-recorded no-create decision"
            decision_time = _utc_epoch_ns(decision.get("observed_at"))
            if (
                before.get("present") is not False
                or decision.get("temporary_profile_id") != expected
                or decision.get("created") is not False
                or not _opaque_identity(decision.get("owner_ref"))
                or decision_time is None or decision_time < before_time
            ):
                return "NOT_CREATED requires prior absence and a named owner's ordered no-create decision"
        grounded = True
    if not grounded:
        return "the intended profile has no complete owner-grounded witness"
    if state == "CLEAN" and not terminal:
        return "CLEAN requires terminal process and shared-resource facts in its evidence"
    return None


def _check_revision(record, declared_refs, reader, resolved, validator, add):
    """Validate the closed revision object and, for a correction, its proof."""
    revision = record.get("revision")
    if not isinstance(revision, dict):
        add("CORRECTION_INVALID", "revision", "the revision object is absent")
        return
    state = revision.get("state")
    if state == "ORIGINAL":
        if revision.get("predecessor_observation_id") is not None:
            add(
                "CORRECTION_INVALID",
                "revision.predecessor_observation_id",
                "an original record names no predecessor observation",
            )
        for field in ("changed_input_refs", "affected_finding_ids"):
            if revision.get(field):
                add(
                    "CORRECTION_INVALID",
                    "revision." + field,
                    "an original record names no changed input or affected finding",
                )
        for field in ("reason", "revised_conclusion"):
            if revision.get(field) is not None:
                add(
                    "CORRECTION_INVALID",
                    "revision." + field,
                    "an original record carries no correction reason or conclusion",
                )
        return
    if state != "CORRECTION":
        add("CORRECTION_INVALID", "revision.state", "the revision state is not closed")
        return

    predecessor_id = revision.get("predecessor_observation_id")
    if not isinstance(predecessor_id, str) or not predecessor_id:
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_observation_id",
            "a correction must identify its predecessor observation",
        )
        return
    if predecessor_id == record.get("observation_id"):
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_observation_id",
            "a correction may not reference its own observation",
        )
        return

    changed_refs = revision.get("changed_input_refs") or []
    if not changed_refs:
        add(
            "CORRECTION_INVALID",
            "revision.changed_input_refs",
            "a correction must name at least one changed input reference",
        )
    for reference in changed_refs:
        if reference not in declared_refs:
            add(
                "CORRECTION_INVALID",
                "revision.changed_input_refs",
                "a changed input reference does not resolve to a declared artifact",
            )

    finding_ids = [
        (finding or {}).get("finding_id") for finding in record.get("findings") or []
    ]
    affected = revision.get("affected_finding_ids") or []
    if not affected:
        add(
            "CORRECTION_INVALID",
            "revision.affected_finding_ids",
            "a correction must name at least one affected finding",
        )
    for finding_id in affected:
        if finding_id not in finding_ids:
            add(
                "CORRECTION_INVALID",
                "revision.affected_finding_ids",
                "an affected finding is not present in this observation",
            )

    if revision.get("reason") in (None, "") or revision.get("revised_conclusion") in (
        None,
        "",
    ):
        add(
            "CORRECTION_INVALID",
            "revision.reason",
            "a correction must state its reason and revised conclusion",
        )

    predecessor_ref = revision.get("predecessor_record_ref")
    predecessor_digest = revision.get("predecessor_record_sha256")
    if not isinstance(predecessor_ref, str) or not isinstance(predecessor_digest, str):
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_ref",
            "a correction must bind an owner-relative predecessor record and digest",
        )
        return
    try:
        if reader is None:
            raise _ReadRefusal("EVIDENCE_ROOT_INVALID")
        raw = reader.read(predecessor_ref, MAX_OBSERVATION_BYTES)
    except _ReadRefusal:
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the predecessor record is not a bounded, qualified file under the supplied root")
        return
    actual = hashlib.sha256(raw).hexdigest()
    if actual != predecessor_digest:
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_sha256",
            "the bound predecessor record digest does not match its bytes",
        )
        return
    try:
        predecessor = _strict_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the bound predecessor record is not a bounded strict JSON document")
        return
    if not _record_shape_safe(predecessor):
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the bound predecessor record is not a closed comparable observation")
        return
    if validator is None or next(validator.iter_errors(predecessor), None) is not None:
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the bound predecessor record violates the closed observation schema")
        return
    if predecessor.get("observation_id") != predecessor_id:
        add("CORRECTION_INVALID", "revision.predecessor_observation_id",
            "the predecessor bytes do not carry the named observation identity")
        return
    time_problems = []
    _check_timestamps(predecessor, lambda *args: time_problems.append(args))
    if time_problems:
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the predecessor has invalid or inconsistent observation times")
        return
    for field in ("started_at", "completed_at"):
        before = _utc_epoch_ns(predecessor["capture"].get(field))
        after = _utc_epoch_ns(record["capture"].get(field))
        if before is None or before != after:
            add("CORRECTION_INVALID", "capture." + field,
                "a correction preserves both original capture instants")
    predecessor_sets = _declared_identities(_collect_declarations(predecessor))
    if any(len(digests) > 1 for digests in predecessor_sets.values()):
        add("CORRECTION_INVALID", "revision.predecessor_record_ref",
            "the predecessor carries conflicting declared artifact identities")
        return
    for reference in changed_refs:
        if not resolved.get(reference, {}).get("qualified"):
            add("CORRECTION_INVALID", "revision.changed_input_refs",
                "changed evidence must resolve to the current qualified bytes")

    predecessor_identities = _predecessor_identities(predecessor)
    current_identities = _declared_identities(_collect_declarations(record))
    evidence_changed = False
    for reference in changed_refs:
        before = predecessor_identities.get(reference)
        after = current_identities.get(reference)
        if before is None or (after and before not in after):
            evidence_changed = True
            break
    predecessor_findings = {
        (finding or {}).get("finding_id"): (finding or {}).get("claim")
        for finding in predecessor.get("findings") or []
    }
    current_findings = {
        (finding or {}).get("finding_id"): (finding or {}).get("claim")
        for finding in record.get("findings") or []
    }
    finding_changed = False
    for finding_id in affected:
        if predecessor_findings.get(finding_id) != current_findings.get(finding_id):
            finding_changed = True
            break
    capability_changed = predecessor.get("capability_state") != record.get(
        "capability_state"
    )
    if not (evidence_changed or finding_changed or capability_changed):
        add(
            "CORRECTION_INVALID",
            "revision.revised_conclusion",
            "a correction must change evidence, a finding, or the stated capability",
        )

    predecessor_effect = predecessor["effect"]
    current_effect = record["effect"]
    if any(predecessor_effect.get(key) != current_effect.get(key)
           for key in ("operation_ref", "carrier_ref")):
        add("CORRECTION_INVALID", "effect",
            "a correction preserves the original effect operation and carrier")
    if predecessor_effect.get("state") != current_effect.get("state"):
        before_effect = _block_identities(predecessor, "effect")
        after_effect = _block_identities(record, "effect")
        evidence_changed = any(
            reference in changed_refs
            and digest is not None
            and digest != before_effect.get(reference)
            and digest not in before_effect.values()
            and resolved.get(reference, {}).get("sha256") == digest
            and _effect_payload_matches(_payload(resolved.get(reference)), current_effect)
            for reference, digest in after_effect.items()
        )
        if not evidence_changed:
            add("CORRECTION_INVALID", "effect.state",
                "an effect change needs new qualified supporting evidence named among the changed inputs")


def _consumption_problem(record, resolved):
    """Return the list of consumption binding failures for one record."""
    failures = []
    capture = record.get("capture") or {}
    for index, screenshot in enumerate(capture.get("screenshots") or []):
        screenshot = screenshot or {}
        consumption = screenshot.get("consumption") or {}
        path = "capture.screenshots[%d].consumption" % index
        proof_ref = consumption.get("proof_ref")
        proof_digest = consumption.get("proof_sha256")
        if not isinstance(proof_ref, str) or not isinstance(proof_digest, str):
            failures.append((path, "the consumption proof reference or digest is absent"))
            continue
        entry = resolved.get(proof_ref)
        proof = _payload(entry)
        if proof is None:
            failures.append((path, "the consumption proof is not an identity-qualified strict JSON object"))
            continue
        if proof.get("consumer_ref") != consumption.get("consumer_ref"):
            failures.append(
                (path, "the consumption proof names a different intended consumer")
            )
        consumed = proof.get("consumed_artifacts")
        if not isinstance(consumed, list):
            failures.append((path, "the consumption proof lists no consumed artifacts"))
            continue
        matched = False
        for entry in consumed:
            if not isinstance(entry, dict):
                continue
            if (
                entry.get("artifact_ref") == screenshot.get("artifact_ref")
                and entry.get("sha256") == screenshot.get("sha256")
            ):
                matched = True
                break
        if not matched:
            failures.append(
                (path, "the consumption proof does not bind the exact screenshot identity")
            )
    return failures


def _receipt(verdict, observation_id, observation_sha256, artifact_count, checks, errors):
    ordered_errors = sorted(
        errors, key=lambda item: (item["code"], item["path"], item["detail"])
    )
    return {
        "schema": RECEIPT_SCHEMA,
        "verdict": verdict,
        "observation_id": observation_id,
        "observation_sha256": observation_sha256,
        "artifact_count": artifact_count,
        "checks": checks,
        "errors": ordered_errors,
    }


def verify_observation_file(observation_path, evidence_root, schema_path):
    """Return the closed consistency receipt for exactly the supplied inputs."""
    errors, error_keys = [], set()
    names = (
        "JSON_STRICT_PARSE", "SCHEMA_CLOSED_SHAPE", "UTC_TIMESTAMP_CALENDAR",
        "TIME_ORDERING", "SOURCE_RELATION_CONSISTENCY", "SECRET_SHAPE_SCAN",
        "NEGATIVE_CONTROL_MEANING", "CAPABILITY_CONSISTENCY", "CLEANUP_ATTESTATION",
        "REVISION_SEMANTICS", "ARTIFACT_RESOLUTION", "ARTIFACT_IDENTITY_UNIQUENESS",
        "ARTIFACT_BYTES_AND_DIGEST", "PNG_STRUCTURE_AND_DIMENSIONS",
        "CONSUMPTION_BINDING", "REFERENCE_CLOSURE", "EVIDENCE_FAMILY_SEMANTICS",
        "EFFECT_BINDING",
    )
    checks = dict.fromkeys(names, "NOT_APPLICABLE")
    observation_id, observation_sha256, artifact_count = None, None, 0

    def add(code, path, detail):
        if code not in ERROR_CODES:
            code = "SCHEMA_VIOLATION"
        key = (code, _sanitize(path), _sanitize(detail))
        if key in error_keys or len(errors) >= MAX_ERRORS:
            return
        if len(errors) == MAX_ERRORS - 1:
            key = ("SCHEMA_VIOLATION", "observation", "the bounded error budget is exhausted")
        error_keys.add(key)
        errors.append(dict(zip(("code", "path", "detail"), key)))

    def mark(name, ok):
        checks[name] = "PASS" if ok else "FAIL"

    def finish():
        return _receipt(
            "INVALID" if errors else "VALID", observation_id,
            observation_sha256, artifact_count,
            [{"name": name, "status": status} for name, status in sorted(checks.items())],
            errors,
        )

    raw, schema_raw = None, None
    for supplied, limit, label in (
        (observation_path, MAX_OBSERVATION_BYTES, "observation"),
        (schema_path, MAX_SCHEMA_BYTES, "schema"),
    ):
        try:
            data = _read_regular_input(supplied, limit)
        except (_ReadRefusal, OSError, TypeError, ValueError, AttributeError):
            add(
                "OBSERVATION_UNREADABLE" if label == "observation" else "SCHEMA_UNREADABLE",
                label + "_path", "the input is not a complete bounded stable regular file",
            )
            continue
        if label == "observation":
            raw = data
            observation_sha256 = hashlib.sha256(data).hexdigest()
        else:
            schema_raw = data

    record = None
    try:
        if raw is None:
            raise ValueError("no complete observation input")
        record = _strict_loads(raw.decode("utf-8"))
        mark("JSON_STRICT_PARSE", True)
    except _DuplicateKeyError:
        add("JSON_DUPLICATE_KEY", "observation", "the record repeats an object key")
    except _NonFiniteError:
        add("JSON_NON_FINITE", "observation", "the record carries a non-finite number")
    except (UnicodeDecodeError, ValueError, RecursionError):
        add("JSON_INVALID", "observation", "the record is not bounded strict UTF-8 JSON")
    if checks["JSON_STRICT_PARSE"] != "PASS":
        mark("JSON_STRICT_PARSE", False)
        mark("SCHEMA_CLOSED_SHAPE", False)
        return finish()
    _check_secret_shapes(record, add)
    mark("SECRET_SHAPE_SCAN", not any(e["code"] == "SECRET_SHAPED_VALUE" for e in errors))
    if not isinstance(record, dict):
        add("SCHEMA_VIOLATION", "observation", "the observation must be a closed object")
        mark("SCHEMA_CLOSED_SHAPE", False)
        return finish()
    proposed_id = record.get("observation_id")
    if (
        isinstance(proposed_id, str)
        and re.fullmatch(r"[A-Z0-9][A-Z0-9._:-]{2,127}", proposed_id) is not None
        and not _has_secret(proposed_id)
    ):
        observation_id = proposed_id

    validator, schema_errors = None, 0
    try:
        if schema_raw is None:
            raise ValueError("no complete schema input")
        schema = _strict_loads(schema_raw.decode("utf-8"))
        if not _schema_without_references(schema):
            raise ValueError("only the closed, reference-free packaged dialect is supported")
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for error in validator.iter_errors(record):
            schema_errors += 1
            add(_schema_error_code(error), _schema_path(error),
                "the record violates the closed observation schema")
            if schema_errors >= MAX_ERRORS:
                break
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError, SchemaError):
        add("SCHEMA_INVALID", "schema_path", "the supplied schema is not a supported closed offline schema")
        validator = None
    mark("SCHEMA_CLOSED_SHAPE", validator is not None and schema_errors == 0)
    if not _record_shape_safe(record):
        add("SCHEMA_VIOLATION", "observation", "unsafe nested containers are refused before semantic traversal")
        mark("SCHEMA_CLOSED_SHAPE", False)
        return finish()
    if validator is None:
        return finish()

    declarations = _collect_declarations(record)
    identities = _declared_identities(declarations)
    declared_refs = set(identities)
    artifact_count = len(declared_refs)
    identity_conflict = False
    for ref, digests in identities.items():
        if len(digests) > 1:
            identity_conflict = True
            site = next(d["site"] for d in declarations if d["ref"] == ref)
            add("ARTIFACT_IDENTITY_CONFLICT", site, "one reference has conflicting declared identities")
    mark("ARTIFACT_IDENTITY_UNIQUENESS", not identity_conflict)
    unresolved = any(d["sha256"] is None for d in declarations)

    reader = None
    try:
        try:
            reader = _QualifiedArtifacts(evidence_root)
        except (_ReadRefusal, OSError, TypeError, ValueError, AttributeError):
            add("EVIDENCE_ROOT_INVALID", "evidence_root", "the supplied owner root is not a qualified directory")
        resolved = {}
        resolution_ok = bytes_ok = png_ok = True
        for declaration in declarations:
            ref, site, expected = declaration["ref"], declaration["site"], declaration["sha256"]
            if expected is None:
                bytes_ok = False
                add("ARTIFACT_IDENTITY_UNRESOLVED", site, "this artifact identity is explicitly unresolved")
            if not isinstance(ref, str):
                resolution_ok = bytes_ok = False
                add("ARTIFACT_REF_INVALID", site, "the artifact reference is not a string")
                continue
            try:
                if reader is None:
                    raise _ReadRefusal("ARTIFACT_MISSING")
                data = reader.read(ref, MAX_ARTIFACT_BYTES)
            except _ReadRefusal as exc:
                resolution_ok = bytes_ok = False
                if declaration["kind"] == "screenshot":
                    png_ok = False
                add(exc.code, site, "the artifact is not a bounded stable regular file under the owner root")
                continue
            if ref not in resolved:
                digest = hashlib.sha256(data).hexdigest()
                related = [d for d in declarations if d["ref"] == ref]
                qualified = all(
                    d["sha256"] == digest
                    and (d["bytes"] is None or (type(d["bytes"]) is int and d["bytes"] == len(data)))
                    for d in related
                )
                resolved[ref] = {
                    "raw": data, "sha256": digest, "size": len(data),
                    "qualified": qualified,
                }
            entry = resolved[ref]
            if expected is not None and expected != entry["sha256"]:
                bytes_ok = False
                add("ARTIFACT_DIGEST_MISMATCH", site, "the declared identity does not match the qualified bytes")
            if declaration["bytes"] is not None and declaration["bytes"] != entry["size"]:
                bytes_ok = False
                add("ARTIFACT_SIZE_MISMATCH", site, "the declared size does not match the qualified bytes")
            if declaration["kind"] == "screenshot":
                if "dimensions" not in entry:
                    entry["dimensions"] = _png_dimensions(entry["raw"])
                dimensions = entry["dimensions"]
                if dimensions is None:
                    png_ok = False
                    add("PNG_INVALID", site, "the bytes do not contain a valid supported PNG default-image raster")
                elif dimensions != (declaration["width"], declaration["height"]):
                    png_ok = False
                    add("PNG_DIMENSION_MISMATCH", site, "the declared viewport differs from decoded geometry")
        mark("ARTIFACT_RESOLUTION", resolution_ok)
        mark("ARTIFACT_BYTES_AND_DIGEST", bytes_ok)
        mark("PNG_STRUCTURE_AND_DIMENSIONS", png_ok)

        _check_timestamps(record, add)
        mark("UTC_TIMESTAMP_CALENDAR", not any(e["code"] == "TIMESTAMP_INVALID" for e in errors))
        mark("TIME_ORDERING", not any(e["code"] == "TIME_ORDER_INVALID" for e in errors))
        _check_source_relationship(record, add)
        mark("SOURCE_RELATION_CONSISTENCY", not any(e["code"] == "SOURCE_RELATION_INVALID" for e in errors))
        _check_negative_controls(record, declared_refs, resolved, add)
        mark("NEGATIVE_CONTROL_MEANING", not any(e["code"] == "NEGATIVE_CONTROL_INVALID" for e in errors))
        _check_reference_closure(record, declared_refs, add)
        mark("REFERENCE_CLOSURE", not any(e["code"] == "EVIDENCE_REF_UNDECLARED" for e in errors))
        _check_evidence_semantics(record, add)
        mark("EVIDENCE_FAMILY_SEMANTICS", not any(e["code"] == "EVIDENCE_STATE_INVALID" for e in errors))
        consumption_failures = _consumption_problem(record, resolved)
        for path, detail in consumption_failures:
            add("CONSUMPTION_BINDING_INVALID", path, detail)
        mark("CONSUMPTION_BINDING", not consumption_failures)
        problem = _effect_problem(record, resolved)
        if problem:
            add("EFFECT_INVALID", "effect", problem)
        mark("EFFECT_BINDING", problem is None)
        cleanup_payloads = [_payload(resolved.get(d.get("artifact_ref"))) for d in record["cleanup"]["evidence"]]
        problem = _cleanup_problem(record, cleanup_payloads)
        if problem:
            add("CLEANUP_CLAIM_INVALID", "cleanup", problem)
        mark("CLEANUP_ATTESTATION", problem is None)
        problem = _capability_problem(record, unresolved)
        if (
            problem is None and record.get("capability_state") == "PROVEN_LIVE"
            and checks["NEGATIVE_CONTROL_MEANING"] != "PASS"
        ):
            problem = "a required negative control is not grounded in the qualified evidence"
        if problem:
            add("CAPABILITY_CONSISTENCY_INVALID", "capability_state", problem)
        mark("CAPABILITY_CONSISTENCY", problem is None)
        _check_revision(record, declared_refs, reader, resolved, validator, add)
        mark("REVISION_SEMANTICS", not any(e["code"] == "CORRECTION_INVALID" for e in errors))
        return finish()
    finally:
        if reader is not None:
            reader.close()


__all__ = ["verify_observation_file", "RECEIPT_SCHEMA", "ERROR_CODES"]
