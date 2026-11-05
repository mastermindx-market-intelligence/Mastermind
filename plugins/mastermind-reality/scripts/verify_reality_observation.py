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
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,9}))?Z$"
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
    """Parse JSON strictly: duplicate keys and non-finite numbers are refused."""
    return json.loads(
        text,
        object_pairs_hook=_strict_pairs,
        parse_constant=_reject_constant,
        parse_float=_strict_float,
    )


def _utc_epoch_ns(text):
    """Return integer nanoseconds for a strict UTC RFC 3339 ``Z`` timestamp.

    Returns ``None`` when the value is not a real UTC calendar instant.
    """
    if not isinstance(text, str):
        return None
    match = _UTC_RE.match(text)
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


def _sanitize(detail):
    """Bound and flatten one error detail so it never carries a secret value."""
    text = " ".join(str(detail).split())
    if len(text) > MAX_ERROR_DETAIL:
        text = text[: MAX_ERROR_DETAIL - 3] + "..."
    return text


def _walk_strings(node, path="$"):
    """Yield ``(json_path, text)`` for every string inside a JSON document."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            for item in _walk_strings(value, "%s.%s" % (path, key)):
                yield item
    elif isinstance(node, list):
        for index, value in enumerate(node):
            for item in _walk_strings(value, "%s[%d]" % (path, index)):
                yield item


def _safe_ref(ref):
    """Return True when a reference is a safe owner-relative path fragment."""
    if not isinstance(ref, str) or not ref or "\x00" in ref:
        return False
    if ref.startswith("/") or os.path.isabs(ref):
        return False
    if "://" in ref:
        return False
    if len(ref) > 1 and ref[1] == ":":
        return False
    parts = ref.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            return False
    return True


def _resolve_ref(root_real, ref):
    """Resolve one owner-relative reference under the supplied evidence root.

    Returns ``(path, None)`` on success or ``(None, code)`` on refusal.
    Absolute paths, traversal, URL-shaped references, and symlink escapes are
    refused before any file is touched.
    """
    if not _safe_ref(ref):
        return None, "ARTIFACT_REF_INVALID"
    candidate = os.path.join(root_real, ref)
    real = os.path.realpath(candidate)
    if real != root_real and not real.startswith(root_real + os.sep):
        return None, "ARTIFACT_REF_INVALID"
    if not os.path.exists(real):
        return None, "ARTIFACT_MISSING"
    try:
        info = os.stat(real)
    except OSError:
        return None, "ARTIFACT_MISSING"
    if not stat.S_ISREG(info.st_mode):
        return None, "ARTIFACT_NOT_REGULAR_FILE"
    if info.st_size > MAX_ARTIFACT_BYTES:
        return None, "ARTIFACT_SIZE_MISMATCH"
    return real, None


def _digest_file(path):
    """Return ``(sha256_hex, size_bytes)`` for one regular file."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(READ_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _read_bounded(path, limit):
    """Read at most ``limit`` bytes from one regular file."""
    with open(path, "rb") as handle:
        return handle.read(limit + 1)


def _png_dimensions(data):
    """Return ``(width, height)`` for a structurally valid PNG, else ``None``.

    The signature, chunk framing, chunk CRC, IHDR geometry, IDAT decompression
    and IEND terminator are all checked. Reads and decompression are bounded.
    """
    if len(data) < len(_PNG_SIGNATURE) or data[: len(_PNG_SIGNATURE)] != _PNG_SIGNATURE:
        return None
    position = len(_PNG_SIGNATURE)
    width = height = bit_depth = color_type = interlace = None
    seen_ihdr = False
    seen_iend = False
    idat = bytearray()
    total = len(data)
    while position + 8 <= total:
        (length,) = struct.unpack(">I", data[position : position + 4])
        chunk_type = data[position + 4 : position + 8]
        position += 8
        if length > MAX_PNG_IDAT_BYTES:
            return None
        if position + length + 4 > total:
            return None
        payload = data[position : position + length]
        position += length
        (crc,) = struct.unpack(">I", data[position : position + 4])
        position += 4
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != crc:
            return None
        if chunk_type == b"IHDR":
            if seen_ihdr or length != 13:
                return None
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", payload)
            if compression != 0 or filter_method != 0:
                return None
            if interlace not in (0, 1):
                return None
            if color_type not in _PNG_CHANNELS or bit_depth not in (1, 2, 4, 8, 16):
                return None
            if width <= 0 or height <= 0:
                return None
            seen_ihdr = True
        elif chunk_type == b"IDAT":
            if not seen_ihdr:
                return None
            idat += payload
            if len(idat) > MAX_PNG_IDAT_BYTES:
                return None
        elif chunk_type == b"IEND":
            seen_iend = True
            break
    if not seen_ihdr or not seen_iend or not idat:
        return None
    channels = _PNG_CHANNELS[color_type]
    expected = height * (1 + (width * channels * bit_depth + 7) // 8)
    if interlace == 0 and expected > MAX_PNG_RASTER_BYTES:
        return None
    bound = min(expected, MAX_PNG_RASTER_BYTES) if interlace == 0 else MAX_PNG_RASTER_BYTES
    try:
        decompressor = zlib.decompressobj()
        raster = decompressor.decompress(bytes(idat), bound + 1)
        if decompressor.unconsumed_tail:
            return None
        raster += decompressor.flush()
    except zlib.error:
        return None
    if not decompressor.eof:
        return None
    if len(raster) > bound:
        return None
    if interlace == 0 and len(raster) != expected:
        return None
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


def _check_negative_controls(record, declared_refs, add):
    controls = record.get("negative_controls") or {}
    for name, expected in NEGATIVE_CONTROL_CONTRACT.items():
        control = controls.get(name)
        path = "negative_controls.%s" % name
        if not isinstance(control, dict):
            add(
                "NEGATIVE_CONTROL_INVALID",
                path,
                "this required negative control is absent",
            )
            continue
        method, signal = expected
        if control.get("method") != method:
            add(
                "NEGATIVE_CONTROL_INVALID",
                path + ".method",
                "control method does not discriminate its own bad state",
            )
        if control.get("signal") != signal:
            add(
                "NEGATIVE_CONTROL_INVALID",
                path + ".signal",
                "control signal does not discriminate its own bad state",
            )
        status = control.get("status")
        if status not in NEGATIVE_CONTROL_STATUSES:
            add(
                "NEGATIVE_CONTROL_INVALID",
                path + ".status",
                "control status is not a closed state",
            )
        for reference in control.get("evidence_refs") or []:
            if reference not in declared_refs:
                add(
                    "NEGATIVE_CONTROL_INVALID",
                    path + ".evidence_refs",
                    "control evidence does not resolve to a declared artifact",
                )


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
    "EFFECT_INVALID",
                path,
                "AVAILABLE requires retained artifacts and no limitation reason",
            )
        elif state == "PARTIAL" and (not artifacts or not reason):
            add(
                "EVIDENCE_STATE_INVALID",
    "EFFECT_INVALID",
                path,
                "PARTIAL requires retained artifacts and a concrete reason",
            )
        elif state == "UNAVAILABLE" and (artifacts or not reason):
            add(
                "EVIDENCE_STATE_INVALID",
    "EFFECT_INVALID",
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
        return "journey.outcome is %s" % (outcome,)
    if target.get("observed_surface_state") != "LIVE":
        return "target.observed_surface_state is %s" % (
            target.get("observed_surface_state"),
        )
    if not target.get("architecture_ref"):
        return "target.architecture_ref is an unknown architecture binding"
    controls = record.get("negative_controls") or {}
    unexercised = sorted(
        name
        for name, control in controls.items()
        if isinstance(control, dict) and control.get("status") == "NOT_EXERCISED"
    )
    if unexercised:
        return "negative controls were not exercised: %s" % (", ".join(unexercised),)
    if unresolved:
        return "the record carries an unresolved artifact identity"
    return None


def _cleanup_problem(record, cleanup_payloads):
    """Return the first cleanup claim problem, else ``None``."""
    cleanup = record.get("cleanup") or {}
    state = cleanup.get("state")
    profile = cleanup.get("temporary_profile")
    if state == "CLEAN" and cleanup.get("temporary_processes") != "ABSENT":
        return "CLEAN requires absent temporary processes"
    if state == "CLEAN" and cleanup.get("shared_resources") != "UNCHANGED":
        return "CLEAN requires unchanged shared resources"
    if profile == "REMOVED":
        grounded = False
        for payload in cleanup_payloads:
            if not isinstance(payload, dict):
                continue
            identity = payload.get("temporary_profile_id")
            if not isinstance(identity, str) or not identity:
                continue
            if isinstance(payload.get("pre_removal"), dict) and isinstance(
                payload.get("post_removal"), dict
            ):
                grounded = True
                break
        if not grounded:
            return (
                "REMOVED requires an owner-grounded profile identity with "
                "pre-removal and post-removal evidence"
            )
    elif profile == "NOT_CREATED":
        grounded = False
        for payload in cleanup_payloads:
            if not isinstance(payload, dict):
                continue
            identity = payload.get("temporary_profile_id")
            if not isinstance(identity, str) or not identity:
                continue
            if isinstance(payload.get("pre_removal"), dict):
                grounded = True
                break
        if not grounded:
            return (
                "NOT_CREATED requires an owner-grounded profile identity with "
                "pre-creation evidence"
            )
    return None


def _check_revision(record, declared_refs, root_real, add):
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
    path, code = _resolve_ref(root_real, predecessor_ref)
    if code is not None:
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_ref",
            "the bound predecessor record does not resolve under the supplied root",
        )
        return
    raw = _read_bounded(path, MAX_OBSERVATION_BYTES)
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
    except (UnicodeDecodeError, ValueError):
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_ref",
            "the bound predecessor record is not a strict JSON document",
        )
        return
    if not isinstance(predecessor, dict):
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_ref",
            "the bound predecessor record is not a closed observation object",
        )
        return
    if predecessor.get("observation_id") != predecessor_id:
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_observation_id",
            "the bound predecessor record does not carry the named observation identity",
        )
        return
    if not isinstance(predecessor.get("capture"), dict) or not isinstance(
        predecessor.get("findings"), list
    ):
        add(
            "CORRECTION_INVALID",
            "revision.predecessor_record_ref",
            "the bound predecessor record does not carry a comparable shape",
        )
        return

    predecessor_capture = predecessor.get("capture") or {}
    if predecessor_capture.get("started_at") != (
        record.get("capture") or {}
    ).get("started_at"):
        add(
            "CORRECTION_INVALID",
            "capture.started_at",
            "a correction may not upgrade the capture epoch of its predecessor",
        )

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

    predecessor_effect = predecessor.get("effect") or {}
    current_effect = record.get("effect") or {}
    if predecessor_effect.get("state") != current_effect.get("state"):
        before_effect = _block_identities(predecessor, "effect")
        after_effect = _block_identities(record, "effect")
        effect_changed = any(
            before_effect.get(reference) != after_effect.get(reference)
            for reference in set(before_effect) | set(after_effect)
        )
        if not effect_changed:
            add(
                "CORRECTION_INVALID",
                "effect.state",
                "a correction may not upgrade effect authority without changed evidence",
            )


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
        resolved_path = resolved.get(proof_ref)
        if resolved_path is None:
            failures.append(
                (path, "the consumption proof does not resolve to a declared artifact")
            )
            continue
        raw = _read_bounded(resolved_path, MAX_OBSERVATION_BYTES)
        try:
            proof = _strict_loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            failures.append((path, "the consumption proof is not a strict JSON document"))
            continue
        if not isinstance(proof, dict):
            failures.append((path, "the consumption proof is not a closed JSON object"))
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
    """Verify one closed Reality observation against supplied evidence.

    Parameters
    ----------
    observation_path:
        Path to one ``mastermind.reality_observation.v1`` record.
    evidence_root:
        Owner-qualified directory that contains the declared artifacts. The
        caller supplies it; this API grants no authority over it.
    schema_path:
        Path to the packaged observation schema.

    Returns
    -------
    dict
        A closed receipt with exactly the keys ``schema``, ``verdict``,
        ``observation_id``, ``observation_sha256``, ``artifact_count``,
        ``checks`` and ``errors``.
    """
    errors = []
    checks = {}

    def add(code, path, detail):
        if code not in ERROR_CODES:
            code = "SCHEMA_VIOLATION"
        errors.append(
            {"code": code, "path": _sanitize(path), "detail": _sanitize(detail)}
        )

    def mark(name, ok, applicable=True):
        if not applicable:
            checks[name] = "NOT_APPLICABLE"
        else:
            checks[name] = "PASS" if ok else "FAIL"

    observation_path = Path(observation_path)
    evidence_root = Path(evidence_root)
    schema_path = Path(schema_path)

    # --- input availability -------------------------------------------------
    try:
        raw = observation_path.read_bytes()
    except OSError:
        add(
            "OBSERVATION_UNREADABLE",
            "observation_path",
            "the observation record could not be read",
        )
        raw = b""
    if len(raw) > MAX_OBSERVATION_BYTES:
        add(
            "OBSERVATION_UNREADABLE",
            "observation_path",
            "the observation record exceeds the supported size",
        )
        raw = raw[:MAX_OBSERVATION_BYTES]
    observation_sha256 = hashlib.sha256(raw).hexdigest()

    try:
        schema_raw = schema_path.read_bytes()
    except OSError:
        add("SCHEMA_UNREADABLE", "schema_path", "the schema could not be read")
        schema_raw = b""
    if len(schema_raw) > MAX_SCHEMA_BYTES:
        add("SCHEMA_UNREADABLE", "schema_path", "the schema exceeds the supported size")
        schema_raw = b""

    root_real = ""
    if not evidence_root.is_dir():
        add(
            "EVIDENCE_ROOT_INVALID",
            "evidence_root",
            "the supplied evidence root is not a directory",
        )
    else:
        root_real = os.path.realpath(str(evidence_root))

    # --- strict parsing -----------------------------------------------------
    record = None
    parse_ok = False
    if raw:
        try:
            record = _strict_loads(raw.decode("utf-8"))
            parse_ok = True
        except UnicodeDecodeError:
            add("JSON_INVALID", "observation", "the record is not valid UTF-8")
        except _DuplicateKeyError:
            add(
                "JSON_DUPLICATE_KEY",
                "observation",
                "the record repeats an object key",
            )
        except _NonFiniteError:
            add(
                "JSON_NON_FINITE",
                "observation",
                "the record carries a non-finite number",
            )
        except ValueError:
            add("JSON_INVALID", "observation", "the record is not valid JSON")
    else:
        add("JSON_INVALID", "observation", "the record carries no bytes")
    mark("JSON_STRICT_PARSE", parse_ok)
    if not parse_ok or not isinstance(record, dict):
        mark("SCHEMA_CLOSED_SHAPE", False)
        mark("UTC_TIMESTAMP_CALENDAR", False)
        mark("TIME_ORDERING", False)
        mark("SOURCE_RELATION_CONSISTENCY", False)
        mark("SECRET_SHAPE_SCAN", False)
        mark("NEGATIVE_CONTROL_MEANING", False)
        mark("CAPABILITY_CONSISTENCY", False)
        mark("CLEANUP_ATTESTATION", False)
        mark("REVISION_SEMANTICS", False)
        mark("ARTIFACT_RESOLUTION", False)
        mark("ARTIFACT_IDENTITY_UNIQUENESS", False)
        mark("ARTIFACT_BYTES_AND_DIGEST", False)
        mark("PNG_STRUCTURE_AND_DIMENSIONS", False)
        mark("CONSUMPTION_BINDING", False)
        mark("REFERENCE_CLOSURE", False)
        mark("EVIDENCE_FAMILY_SEMANTICS", False)
        return _receipt(
            "INVALID",
            None,
            observation_sha256,
            0,
            [{"name": name, "status": status} for name, status in sorted(checks.items())],
            errors,
        )

    observation_id = record.get("observation_id")
    if not isinstance(observation_id, str):
        observation_id = None

    # --- closed schema ------------------------------------------------------
    schema_ok = False
    validator = None
    if schema_raw:
        try:
            schema = _strict_loads(schema_raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            schema = None
        if isinstance(schema, dict):
            try:
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                schema_ok = True
            except SchemaError:
                add("SCHEMA_INVALID", "schema_path", "the schema is not a valid schema")
    if validator is None:
        add("SCHEMA_UNREADABLE", "schema_path", "no usable observation schema")
        schema_ok = False
    schema_error_count = 0
    if validator is not None:
        for error in sorted(
            validator.iter_errors(record), key=lambda item: list(item.absolute_path)
        ):
            schema_error_count += 1
            path = ".".join(str(part) for part in error.absolute_path)
            add(
                _schema_error_code(error),
                path or "observation",
                "the record violates the closed observation schema",
            )
    mark("SCHEMA_CLOSED_SHAPE", schema_error_count == 0)

    # --- declared artifacts -------------------------------------------------
    declarations = _collect_declarations(record)
    identities = _declared_identities(declarations)
    declared_refs = set(identities)
    artifact_count = len(declared_refs)

    identity_conflict = False
    for ref, digests in identities.items():
        if len(digests) > 1:
            identity_conflict = True
            add(
                "ARTIFACT_IDENTITY_CONFLICT",
                ref,
                "one artifact reference carries more than one declared identity",
            )
    mark("ARTIFACT_IDENTITY_UNIQUENESS", not identity_conflict)

    unresolved = False
    for declaration in declarations:
        if declaration["sha256"] is None:
            unresolved = True

    # --- artifact resolution ------------------------------------------------
    resolved = {}
    resolution_ok = True
    bytes_ok = True
    png_ok = True
    cleanup_payloads = []
    for declaration in declarations:
        ref = declaration["ref"]
        site = declaration["site"]
        if not isinstance(ref, str):
            resolution_ok = False
            add("ARTIFACT_REF_INVALID", site, "the artifact reference is not a string")
            continue
        if root_real == "":
            resolution_ok = False
            add(
                "ARTIFACT_MISSING",
                site,
                "the artifact cannot be resolved without a usable evidence root",
            )
            continue
        path, code = _resolve_ref(root_real, ref)
        declared_digest = declaration["sha256"]
        if declared_digest is None:
            unresolved = True
            add(
                "ARTIFACT_IDENTITY_UNRESOLVED",
                site,
                "this artifact identity is unresolved; no digest is asserted",
            )
        if code is not None:
            resolution_ok = False
            add(code, site, "the declared artifact does not resolve to a regular file")
            continue
        resolved.setdefault(ref, path)
        actual_digest, actual_size = _digest_file(path)
        if declared_digest is None:
            pass
        elif actual_digest != declared_digest:
            bytes_ok = False
            add(
                "ARTIFACT_DIGEST_MISMATCH",
                site,
                "the declared digest does not match the artifact bytes",
            )
        declared_size = declaration["bytes"]
        if isinstance(declared_size, int) and not isinstance(declared_size, bool):
            if declared_size != actual_size:
                bytes_ok = False
                add(
                    "ARTIFACT_SIZE_MISMATCH",
                    site,
                    "the declared byte count does not match the artifact bytes",
                )
        if declaration["kind"] == "screenshot":
            data = _read_bounded(path, MAX_ARTIFACT_BYTES)
            dimensions = _png_dimensions(data)
            if dimensions is None:
                png_ok = False
                add(
                    "PNG_INVALID",
                    site,
                    "the artifact is not a structurally valid PNG image",
                )
            else:
                width, height = dimensions
                if (
                    declaration["width"] != width
                    or declaration["height"] != height
                ):
                    png_ok = False
                    add(
                        "PNG_DIMENSION_MISMATCH",
                        site,
                        "the declared viewport does not match the PNG geometry",
                    )
        if declaration["kind"] == "cleanup":
            raw_cleanup = _read_bounded(path, MAX_ARTIFACT_BYTES)
            try:
                cleanup_payloads.append(_strict_loads(raw_cleanup.decode("utf-8")))
            except (UnicodeDecodeError, ValueError):
                cleanup_payloads.append(None)
    mark("ARTIFACT_RESOLUTION", resolution_ok)
    mark("ARTIFACT_BYTES_AND_DIGEST", bytes_ok)
    mark("PNG_STRUCTURE_AND_DIMENSIONS", png_ok)

    # --- secret shapes ------------------------------------------------------
    secret_before = len(errors)
    _check_secret_shapes(record, add)
    mark("SECRET_SHAPE_SCAN", len(errors) == secret_before)

    # --- time ---------------------------------------------------------------
    _check_timestamps(record, add)
    mark("UTC_TIMESTAMP_CALENDAR", not any(e["code"] == "TIMESTAMP_INVALID" for e in errors))
    mark("TIME_ORDERING", not any(e["code"] == "TIME_ORDER_INVALID" for e in errors))

    # --- source relationship ------------------------------------------------
    _check_source_relationship(record, add)
    mark(
        "SOURCE_RELATION_CONSISTENCY",
        not any(e["code"] == "SOURCE_RELATION_INVALID" for e in errors),
    )

    # --- negative controls --------------------------------------------------
    _check_negative_controls(record, declared_refs, add)
    mark(
        "NEGATIVE_CONTROL_MEANING",
        not any(e["code"] == "NEGATIVE_CONTROL_INVALID" for e in errors),
    )

    # --- reference closure --------------------------------------------------
    _check_reference_closure(record, declared_refs, add)
    mark(
        "REFERENCE_CLOSURE",
        not any(e["code"] == "EVIDENCE_REF_UNDECLARED" for e in errors),
    )

    # --- evidence family semantics -----------------------------------------
    _check_evidence_semantics(record, add)
    mark(
        "EVIDENCE_FAMILY_SEMANTICS",
        not any(e["code"] == "EVIDENCE_STATE_INVALID" for e in errors),
    )

    # --- consumption binding ------------------------------------------------
    consumption_failures = _consumption_problem(record, resolved)
    for path, detail in consumption_failures:
        add("CONSUMPTION_BINDING_INVALID", path, detail)
    mark("CONSUMPTION_BINDING", not consumption_failures)

    # --- cleanup ------------------------------------------------------------
    cleanup_problem = _cleanup_problem(record, cleanup_payloads)
    if cleanup_problem:
        add("CLEANUP_CLAIM_INVALID", "cleanup", cleanup_problem)
    mark("CLEANUP_ATTESTATION", cleanup_problem is None)

    # --- capability consistency --------------------------------------------
    capability_problem = _capability_problem(record, unresolved)
    if capability_problem:
        add("CAPABILITY_CONSISTENCY_INVALID", "capability_state", capability_problem)
    mark("CAPABILITY_CONSISTENCY", capability_problem is None)

    # --- revision semantics -------------------------------------------------
    if root_real == "":
        if (record.get("revision") or {}).get("state") == "CORRECTION":
            add(
                "CORRECTION_INVALID",
                "revision",
                "a correction cannot be proven without a usable evidence root",
            )
    else:
        _check_revision(record, declared_refs, root_real, add)
    mark(
        "REVISION_SEMANTICS",
        not any(e["code"] == "CORRECTION_INVALID" for e in errors),
    )

    verdict = "VALID" if not errors else "INVALID"
    return _receipt(
        verdict,
        observation_id,
        observation_sha256,
        artifact_count,
        [{"name": name, "status": status} for name, status in sorted(checks.items())],
        errors,
    )


__all__ = ["verify_observation_file", "RECEIPT_SCHEMA", "ERROR_CODES"]
