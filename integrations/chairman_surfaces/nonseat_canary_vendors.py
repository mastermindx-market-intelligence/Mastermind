"""Narrow secret-owning helper for the MAS-115 disposable non-seat canary.

The model-visible coordinator in :mod:`nonseat_canary` cannot read a live
credential or construct a live client.  A human operator invokes this module
directly.  This helper validates the provision and affirmative non-seat
binding census first; only then does it spawn the fixed Keychain command with
stdout wired directly into its own secret input through an anonymous OS pipe.
There is no eager external shell producer, captured stdout, or returned raw
value.  The helper then owns the credential, the single bounded HTTP client,
and the live matrix for the remainder of the process.

Refuses closed. Every path this module cannot prove against a documented
vendor surface raises :class:`~integrations.chairman_surfaces.
nonseat_canary.CanaryRefusal` rather than improvising. BUILT_NOT_PROVEN until
an operator provisions a disposable credential and profile and runs this
against them for real — no test in this repository ever calls a real vendor
endpoint.

The ONLY WebDriver operations used anywhere in this module are create a
session, navigate the selected page, enumerate/switch window handles, and
read the current URL.  There is structurally no pointer, keyboard, form,
script-evaluation, cookie, storage, download, or arbitrary-command surface.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import http.server
import importlib.util
import json
import os
import re
import secrets
import select
import signal
import stat
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from control_plane import surface_bindings as _surface_bindings
from . import nonseat_canary as _core
from . import mas115_multilogin_port_policy as _port_policy
#: Frozen official Multilogin X surfaces.  Launcher profile status/stop are
#: v1; profile start is v2; existence is proven by a bounded cloud folder
#: census rather than by launcher 404 (which is ambiguous after Agent restart).
_MLX_LAUNCHER_ORIGIN = "https://launcher.mlx.yt:45001"
_MLX_CLOUD_ORIGIN = "https://api.multilogin.com"
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_DECLARED_MEDIA_TYPE_BYTES = 256
# Keep each cloud-inventory response comfortably below the independent 64 KiB
# transport cap even when profile metadata is several KiB per row. The census
# remains complete and bounded by `_MAX_PROFILE_CENSUS`; only its page size is
# reduced.
_PROFILE_PAGE_SIZE = 10
_MAX_PROFILE_CENSUS = 1000
_MAX_STDIN_BYTES = 16 * 1024
_KEYCHAIN_READ_TIMEOUT_SECONDS = 15.0
_KEYCHAIN_WAIT_TIMEOUT_SECONDS = 2.0
_CLEANUP_PROCESS_TIMEOUT_SECONDS = 15.0
_CLEANUP_PROCESS_POLL_SECONDS = 0.1
_SECURITY_BIN = "/usr/bin/security"
_KEYCHAIN_SERVICE = "mastermind.mas115.multilogin.disposable"
_KEYCHAIN_ACCOUNT = "mastermind-mas115-canary"
_MLX_STATUS_DATA_KEYS = frozenset({
    "browser_type", "core_version", "folder_id", "in_use_by", "is_quick",
    "last_launched_at", "last_launched_by", "last_launched_on", "message",
    "name", "profile_id", "status", "timestamp", "workspace_id",
})

_USER_DATA_DIR_RE = re.compile(r"--user-data-dir=(\S+)")
_WEBDRIVER_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_WEBDRIVER_MISSING = object()
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HTTP_TOKEN_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def _canonical_multilogin_profile_id(value):
    """Return the one canonical Multilogin UUID, never a loose identifier."""
    if not isinstance(value, str) or _surface_bindings.UUID_RE.fullmatch(value) is None:
        return None
    return value.lower()

# ---------------------------------------------------------------------------
# REALM1-C1 — MAS-115 one-profile Multilogin peer create/reconcile/remove
# (Mastermind #385). See docs/CHAIRMAN_CONTROL_ROOM.md item 6/7.
# ---------------------------------------------------------------------------

_MLX_PROFILE_CREATE_PATH = "/profile/create"
_MLX_PROFILE_REMOVE_PATH = "/profile/remove"

PEER_OPERATION_KEY = "web-sol-realm1-multilogin-profile-create-owner-20260902-sol-001"
PEER_BOOTSTRAP_OPERATION_KEY = "web-sol-realm1-bootstrap-evidence-binding-repair-20260903-sol-001"
PEER_PROVISION_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_canary_peer.json"
PEER_INTENT_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_peer_create_intent.json"
PEER_GENESIS_WITNESS_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_peer_genesis_witness.json"
PEER_BOOTSTRAP_FENCE_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_peer_bootstrap_fence.json"
PEER_OWNERSHIP_RECEIPT_PATH = "~/Library/Application Support/Mastermind/control-room/mas115_nonseat_peer_release_receipt.json"
PEER_INTENT_SCHEMA = "mastermind.mas115_nonseat_peer_lifecycle_state.v5"
PEER_GENESIS_WITNESS_SCHEMA = "mastermind.mas115_nonseat_peer_genesis_witness.v1"
PEER_BOOTSTRAP_FENCE_SCHEMA = "mastermind.mas115_nonseat_peer_bootstrap_fence.v1"
PEER_RECEIPT_SCHEMA = "mastermind.mas115_nonseat_peer_lifecycle.v3"
PEER_OWNERSHIP_FACT_SCHEMA = "mastermind.mas115_peer_downstream_ownership.v1"
# Semantic source generation for the reviewed REALM1-C1 R4 lifecycle.  It is
# deliberately independent of a self-referential Git commit hash, but changes
# whenever this authority/state contract changes.
PEER_SOURCE_GENERATION = "4b4c77c81a19dafdd6c0ecbed58f14025a41eea77efb2ec070a537e52c999f49"
PF1_OPERATION_KEY = "web-sol-pf1-provider-continuation-falsifier-20260901-sol-001"
INSTALL1_OPERATION_KEY = "web-sol-install1-two-profile-disposable-proof-20260902-sol-001"
_MAX_OWNERSHIP_RECEIPT_AGE = timedelta(minutes=5)
_PEER_NAME_PREFIX = "mas115-peer-"
_PEER_BROWSER_TYPE = "mimic"
_PEER_OS_TYPE = "macos"
_PEER_REMOVE_PERMANENTLY = False  # recoverable; absence is proven against the active census

CREATED_THIS_CALL = "CREATED_THIS_CALL"
EXISTING_EXACT = "EXISTING_EXACT"
REFUSED = "REFUSED"
_CLAIM_DISPOSITIONS = frozenset({CREATED_THIS_CALL, EXISTING_EXACT, REFUSED})

PEER_PHASE_INITIALIZED = "INITIALIZED"
PEER_PHASE_CREATE_CLAIMED = "CREATE_CLAIMED"
PEER_PHASE_CREATE_AUTH_REJECTED = "CREATE_AUTH_REJECTED"
PEER_PHASE_CREATE_RESPONSE_OBSERVED = "CREATE_RESPONSE_OBSERVED"
PEER_PHASE_PROFILE_STOPPED = "PROFILE_STOPPED_PROVEN"
PEER_PHASE_PROVISION_COMMITTED = "PROVISION_COMMITTED"
PEER_PHASE_REMOVE_DISPATCHED = "REMOVE_DISPATCHED"
PEER_PHASE_ROLLBACK_VERIFIED = "ROLLBACK_VERIFIED"
_PEER_PHASES = frozenset({
    PEER_PHASE_INITIALIZED,
    PEER_PHASE_CREATE_CLAIMED,
    PEER_PHASE_CREATE_AUTH_REJECTED,
    PEER_PHASE_CREATE_RESPONSE_OBSERVED,
    PEER_PHASE_PROFILE_STOPPED,
    PEER_PHASE_PROVISION_COMMITTED,
    PEER_PHASE_REMOVE_DISPATCHED,
    PEER_PHASE_ROLLBACK_VERIFIED,
})
_PEER_STATE_KEYS = frozenset({
    "schema", "operation", "generation", "folder_digest",
    "anchor_profile_digest", "browser_type", "os_type", "peer_name",
    "state_dev", "state_ino", "genesis_witness_coordinate_digest",
    "genesis_witness_dev", "genesis_witness_ino",
    "peer_profile_digest", "peer_provision_coordinate_digest",
    "peer_provision_digest", "peer_provision_dev", "peer_provision_ino",
    "phase", "response_profile_digest", "ownership_fact_digest",
    "ownership_observed_at",
})
_PEER_GENESIS_WITNESS_PENDING = "PENDING"
_PEER_GENESIS_WITNESS_BOUND = "BOUND"
_PEER_GENESIS_WITNESS_KEYS = frozenset({
    "schema", "operation", "source_generation", "lifecycle_generation",
    "state_coordinate_digest", "peer_provision_coordinate_digest",
    "folder_digest", "anchor_profile_digest", "peer_name_digest",
    "witness_dev", "witness_ino", "state_dev", "state_ino", "phase",
})
PEER_BOOTSTRAP_PHASE_PENDING = "PENDING"
PEER_BOOTSTRAP_PHASE_COMPLETE = "COMPLETE"
_PEER_BOOTSTRAP_FENCE_KEYS = frozenset({
    "schema", "operation", "peer_operation", "source_generation",
    "anchor_coordinate_digest", "state_coordinate_digest",
    "genesis_witness_coordinate_digest", "peer_provision_coordinate_digest",
    "anchor_document_digest", "anchor_dev", "anchor_ino",
    "lifecycle_generation", "fence_dev", "fence_ino", "phase",
    "state_document_digest", "state_dev", "state_ino",
    "witness_document_digest", "witness_dev", "witness_ino",
})
_MAX_PEER_STATE_BYTES = 16 * 1024


class _PeerAuthorization:
    """Opaque in-process capability; no serialized CLI value can create one."""

    __slots__ = ()


CREATE_PEER_AUTHORIZATION = _PeerAuthorization()
ROLLBACK_PEER_AUTHORIZATION = _PeerAuthorization()


_PEER_BOOTSTRAP_EVIDENCE_SEAL = object()


class _PeerBootstrapEvidence:
    """One-use, process-bound proof retaining both exact source inodes."""

    __slots__ = (
        "_seal", "_operation", "_generation", "_mint_pid", "_anchor_path",
        "_anchor_fd", "_anchor_raw", "_anchor_sha256", "_anchor_security",
        "_bindings_path", "_bindings_fd", "_bindings_raw",
        "_bindings_sha256", "_bindings_security", "_census_digest",
        "_guard", "_consumed", "_closed",
    )

    def __init__(
        self, seal, *, operation, generation, anchor_path, anchor_fd,
        anchor_raw, anchor_security, bindings_path, bindings_fd, bindings_raw,
        bindings_security, census_digest,
    ):
        if seal is not _PEER_BOOTSTRAP_EVIDENCE_SEAL:
            raise TypeError("peer bootstrap evidence is private")
        self._seal = seal
        self._operation = operation
        self._generation = generation
        self._mint_pid = os.getpid()
        self._anchor_path = anchor_path
        self._anchor_fd = anchor_fd
        self._anchor_raw = anchor_raw
        self._anchor_sha256 = hashlib.sha256(anchor_raw).hexdigest()
        self._anchor_security = anchor_security
        self._bindings_path = bindings_path
        self._bindings_fd = bindings_fd
        self._bindings_raw = bindings_raw
        self._bindings_sha256 = hashlib.sha256(bindings_raw).hexdigest()
        self._bindings_security = bindings_security
        self._census_digest = census_digest
        self._guard = threading.Lock()
        self._consumed = False
        self._closed = False

    def __copy__(self):
        raise TypeError("peer bootstrap evidence cannot be copied")

    def __deepcopy__(self, _memo):
        raise TypeError("peer bootstrap evidence cannot be copied")

    def __reduce__(self):
        raise TypeError("peer bootstrap evidence cannot be serialized")

    def _begin_consume(self) -> bool:
        with self._guard:
            if self._consumed or self._closed:
                return False
            self._consumed = True
            return True

    def _close_held_descriptors(self) -> None:
        with self._guard:
            if self._closed:
                return
            self._closed = True
            descriptors = (self._anchor_fd, self._bindings_fd)
            self._anchor_fd = -1
            self._bindings_fd = -1
        for descriptor in descriptors:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def __del__(self):
        try:
            self._close_held_descriptors()
        except Exception:  # noqa: BLE001 — destructor must never escape
            pass

PEER_EFFECT_CODES = frozenset({
    "NONE", "CREATE_DISPATCHED", "CREATE_APPLIED", "CREATE_EFFECT_UNKNOWN",
    "PROVISION_WRITTEN", "PROFILE_STOPPED_PROVEN", "REMOVE_DISPATCHED",
    "REMOVE_APPLIED", "REMOVE_EFFECT_UNKNOWN", "ROLLBACK_VERIFIED",
})
PEER_EFFECT_DETAILS = {
    "NONE": "no peer-profile effect occurred.",
    "CREATE_DISPATCHED": "a create request for the disposable peer profile was sent to the vendor.",
    "CREATE_APPLIED": "the disposable peer profile exists but its stopped state is not yet proven.",
    "CREATE_EFFECT_UNKNOWN": "whether the disposable peer profile was created could not be determined.",
    "PROVISION_WRITTEN": "the disposable peer profile was created, proven stopped, and its provision was written.",
    "PROFILE_STOPPED_PROVEN": "the disposable peer profile was proven to exist and to be stopped.",
    "REMOVE_DISPATCHED": "a remove request for the disposable peer profile was sent to the vendor.",
    "REMOVE_APPLIED": "the disposable peer profile was moved to the vendor trash but its absence is not yet proven.",
    "REMOVE_EFFECT_UNKNOWN": "whether the disposable peer profile was removed could not be determined.",
    "ROLLBACK_VERIFIED": "the disposable peer profile is absent from the active folder census after removal.",
}
if set(PEER_EFFECT_DETAILS) != PEER_EFFECT_CODES:
    raise RuntimeError("nonseat_canary_vendors: PEER_EFFECT_DETAILS keys must exactly match PEER_EFFECT_CODES")

#: Multilogin deletion is two-stage: an ordinary remove moves the profile to the
#: Trash, where it stays restorable and may still consume a plan slot; permanent
#: deletion is a separate irreversible action taken from inside the Trash.
#: #385 authorizes ONE exact remove request -- not a second-stage purge -- so this
#: operation only ever asks for the reversible form. Flipping this constant is a
#: load-bearing authority change, not a tuning knob, and the module refuses to
#: import rather than let it happen silently.
if _PEER_REMOVE_PERMANENTLY is not False:
    # An `assert` here would be stripped by `python -O`; this boundary must hold
    # even in an optimized interpreter.
    raise RuntimeError(
        "nonseat_canary_vendors: permanent profile deletion is not authorized by #385; "
        "a DECISION_REQUEST / PERMANENT_DELETE_BOUNDARY ruling is required first"
    )

REMOVAL_DISPOSITIONS = frozenset({"NOT_APPLICABLE", "TRASHED_RESTORABLE"})
REMOVAL_DISPOSITION_DETAILS = {
    "NOT_APPLICABLE": "this operation dispatched no removal.",
    "TRASHED_RESTORABLE": (
        "the profile was removed from the active folder into the vendor trash with "
        "permanently=false; it remains restorable and may still consume a plan slot. "
        "Absence from the active census is not permanent deletion and no capacity "
        "release is claimed."
    ),
}
if set(REMOVAL_DISPOSITION_DETAILS) != REMOVAL_DISPOSITIONS:
    raise RuntimeError(
        "nonseat_canary_vendors: REMOVAL_DISPOSITION_DETAILS keys must exactly match REMOVAL_DISPOSITIONS"
    )

_PEER_PASS_EFFECTS = frozenset({"PROVISION_WRITTEN", "PROFILE_STOPPED_PROVEN", "ROLLBACK_VERIFIED"})
_PEER_HOLD_EFFECTS = frozenset({
    "CREATE_DISPATCHED", "CREATE_APPLIED", "CREATE_EFFECT_UNKNOWN",
    "REMOVE_DISPATCHED", "REMOVE_APPLIED", "REMOVE_EFFECT_UNKNOWN",
})

_PEER_RECEIPT_PREDICATE_KEYS = frozenset({
    "intent_committed", "candidates_before", "dispatched", "reconciled",
    "exact_readback", "stopped_proven", "provision_written",
    "cleanup_lease_retained", "removed_absent",
})
_PEER_BASE_PREDICATES = {
    "intent_committed": False,
    "candidates_before": 0,
    "dispatched": False,
    "reconciled": False,
    "exact_readback": False,
    "stopped_proven": False,
    "provision_written": False,
    "cleanup_lease_retained": False,
    "removed_absent": False,
}

INITIAL_PEER_CENSUS_DIAGNOSTICS = frozenset({
    "NONE",
    "TRANSPORT_FAILURE",
    "RESPONSE_BODY_LIMIT",
    "RESPONSE_DECODE_FAILURE",
    "HTTP_RATE_LIMITED",
    "HTTP_REQUEST_REJECTED",
    "HTTP_SERVICE_UNAVAILABLE",
    "HTTP_UNEXPECTED",
    "STATUS_ENVELOPE_INVALID",
    "DATA_SCHEMA_INVALID",
    "PROFILE_ITEM_INVALID",
    "PAGINATION_INVALID",
})
INITIAL_PEER_CENSUS_STATUS_CLASSES = frozenset({
    "NONE",
    "HTTP_200",
    "HTTP_3XX",
    "HTTP_AUTH",
    "HTTP_RATE_LIMITED",
    "HTTP_OTHER_4XX",
    "HTTP_5XX",
    "HTTP_OTHER",
})
INITIAL_PEER_CENSUS_MEDIA_TYPE_CLASSES = frozenset({
    "NONE", "MISSING", "JSON", "HTML", "TEXT", "OTHER",
})
INITIAL_PEER_CENSUS_DECODER_CLASSES = frozenset({
    "NONE", "UNICODE_REJECTED", "JSON_VALUE_REJECTED",
})
_INITIAL_PEER_CENSUS_DECODE_CONTEXT_KEYS = (
    "status_class", "declared_media_type_class", "decoder_class",
)
_INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE = ("NONE", "NONE", "NONE")
_INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL = object()


def _initial_peer_census_decode_context_tuple(value) -> tuple[str, str, str]:
    if value is None:
        return _INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE
    if not isinstance(value, dict) or set(value) != set(
        _INITIAL_PEER_CENSUS_DECODE_CONTEXT_KEYS
    ):
        raise ValueError("invalid initial peer census decode context")
    context = tuple(value[key] for key in _INITIAL_PEER_CENSUS_DECODE_CONTEXT_KEYS)
    if (
        not isinstance(context[0], str)
        or context[0] not in INITIAL_PEER_CENSUS_STATUS_CLASSES
        or not isinstance(context[1], str)
        or context[1] not in INITIAL_PEER_CENSUS_MEDIA_TYPE_CLASSES
        or not isinstance(context[2], str)
        or context[2] not in INITIAL_PEER_CENSUS_DECODER_CLASSES
    ):
        raise ValueError("invalid initial peer census decode context")
    return context


def _initial_peer_census_decode_context_dict(context) -> dict:
    return dict(zip(_INITIAL_PEER_CENSUS_DECODE_CONTEXT_KEYS, context))


def _initial_peer_census_status_class(status_code) -> str:
    if type(status_code) is not int:
        return "HTTP_OTHER"
    if status_code == 200:
        return "HTTP_200"
    if status_code in (401, 403):
        return "HTTP_AUTH"
    if status_code == 429:
        return "HTTP_RATE_LIMITED"
    if 300 <= status_code < 400:
        return "HTTP_3XX"
    if 400 <= status_code < 500:
        return "HTTP_OTHER_4XX"
    if 500 <= status_code < 600:
        return "HTTP_5XX"
    return "HTTP_OTHER"


def _initial_peer_census_media_type_class(headers) -> str:
    try:
        values = headers.get_list("content-type")
    except Exception:  # noqa: BLE001 — header objects are outside this receipt contract
        return "OTHER"
    if not values:
        return "MISSING"
    if len(values) != 1:
        return "OTHER"
    declared = values[0]
    if not isinstance(declared, str):
        return "OTHER"
    try:
        if len(declared.encode("utf-8")) > _MAX_DECLARED_MEDIA_TYPE_BYTES:
            return "OTHER"
    except UnicodeError:
        return "OTHER"
    # A comma is ambiguous here: it may represent combined duplicate fields.
    if "," in declared:
        return "OTHER"
    # HTTP media-type tokens are ASCII.  Validate the declared tokens before
    # normalization so Unicode case folding or non-OWS whitespace cannot turn
    # an invalid wire value into an accepted JSON declaration.
    media_type = declared.split(";", 1)[0].strip(" \t")
    if media_type.count("/") != 1:
        return "OTHER"
    major, subtype = media_type.split("/", 1)
    if (
        not major
        or not subtype
        or _HTTP_TOKEN_RE.fullmatch(major) is None
        or _HTTP_TOKEN_RE.fullmatch(subtype) is None
    ):
        return "OTHER"
    major = major.casefold()
    subtype = subtype.casefold()
    if major == "application" and (
        subtype == "json"
        or (subtype.endswith("+json") and len(subtype) > len("+json"))
    ):
        return "JSON"
    if (major, subtype) == ("text", "html"):
        return "HTML"
    if (major, subtype) == ("text", "plain"):
        return "TEXT"
    return "OTHER"


class _InitialPeerCensusDiagnosticSink:
    """Invocation-local, one-way observation capability for the first census."""

    __slots__ = ("_observation", "_seal")

    def __init__(self, seal):
        if seal is not _INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL:
            raise TypeError("initial peer census diagnostic sink is private")
        self._seal = seal
        self._observation = (
            "NONE", _INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE,
        )

    @property
    def value(self) -> str:
        return self._observation[0]

    @property
    def decode_context(self) -> dict:
        return _initial_peer_census_decode_context_dict(self._observation[1])

    def _record(self, diagnostic: str, *, decode_context=None) -> None:
        if diagnostic not in INITIAL_PEER_CENSUS_DIAGNOSTICS or diagnostic == "NONE":
            raise ValueError("invalid initial peer census diagnostic")
        if self._observation[0] != "NONE":
            return
        context = _initial_peer_census_decode_context_tuple(decode_context)
        if diagnostic == "RESPONSE_DECODE_FAILURE":
            if "NONE" in context:
                raise ValueError("decode failure requires complete decode context")
        elif context != _INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE:
            raise ValueError("decode context is only valid for decode failure")
        # One immutable observation assignment binds the first failure and its
        # optional decode context together for this invocation.
        self._observation = (diagnostic, context)


def _record_initial_peer_census_diagnostic(
    sink, diagnostic: str, *, decode_context=None,
) -> None:
    if (
        type(sink) is _InitialPeerCensusDiagnosticSink
        and sink._seal is _INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL  # noqa: SLF001
    ):
        sink._record(diagnostic, decode_context=decode_context)  # noqa: SLF001


def peer_profile_name(folder_id: str, anchor_profile_id: str) -> str:
    """Pure, deterministic, opaque peer-profile name.

    Same ``(folder_id, anchor_profile_id)`` always yields the same name; the
    caller can never supply a name directly. This is what makes read-back
    reconciliation possible without ever storing a raw vendor identity.
    """
    material = "|".join((PEER_OPERATION_KEY, folder_id, anchor_profile_id))
    return _PEER_NAME_PREFIX + _core.sha256_hex(material)[:16]


def peer_receipt(
    *, effect: str, code: str, verdict: str, digests: dict,
    removal_disposition: str = "NOT_APPLICABLE",
    initial_peer_census_diagnostic: str = "NONE",
    initial_peer_census_decode_context=None, **predicates,
) -> dict:
    """Build one closed, redacted MAS-115 peer lifecycle receipt."""

    if effect not in PEER_EFFECT_CODES:
        raise ValueError(f"unknown peer effect: {effect!r}")
    if code not in _core.RESULT_CODES:
        raise ValueError(f"unknown peer receipt code: {code!r}")
    if verdict not in ("PASS", "HOLD", "REFUSED"):
        raise ValueError(f"unknown peer receipt verdict: {verdict!r}")
    if removal_disposition not in REMOVAL_DISPOSITIONS:
        raise ValueError(f"unknown removal disposition: {removal_disposition!r}")
    if (
        not isinstance(initial_peer_census_diagnostic, str)
        or initial_peer_census_diagnostic not in INITIAL_PEER_CENSUS_DIAGNOSTICS
    ):
        raise ValueError("unknown initial peer census diagnostic")
    decode_context = _initial_peer_census_decode_context_tuple(
        initial_peer_census_decode_context,
    )
    if initial_peer_census_diagnostic == "RESPONSE_DECODE_FAILURE":
        if "NONE" in decode_context:
            raise ValueError("decode failure requires complete decode context")
    elif decode_context != _INITIAL_PEER_CENSUS_DECODE_CONTEXT_NONE:
        raise ValueError("decode context is only valid for decode failure")
    if not isinstance(digests, dict) or set(digests) != {"folder", "peer_name", "peer_profile", "anchor_profile"}:
        raise ValueError("peer receipt digests must carry exactly the fixed digest keys")
    for value in digests.values():
        if value is not None and not (isinstance(value, str) and _HEX64_RE.fullmatch(value)):
            raise ValueError("peer receipt digest values must be a sha256 hex digest or None")
    if set(predicates) != _PEER_RECEIPT_PREDICATE_KEYS:
        raise ValueError("peer receipt predicates must carry exactly the fixed predicate keys")
    for key, value in predicates.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            continue
        raise ValueError(f"peer receipt predicate {key!r} must be bool or int")
    return {
        "schema": PEER_RECEIPT_SCHEMA,
        "operation": PEER_OPERATION_KEY,
        "initial_peer_census_diagnostic": initial_peer_census_diagnostic,
        "initial_peer_census_decode_context": (
            _initial_peer_census_decode_context_dict(decode_context)
        ),
        "verdict": verdict,
        "effect": effect,
        "effect_detail": PEER_EFFECT_DETAILS[effect],
        "code": code,
        "detail": _core.DETAILS[code],
        "removal_disposition": removal_disposition,
        "removal_disposition_detail": REMOVAL_DISPOSITION_DETAILS[removal_disposition],
        "digests": dict(digests),
        "predicates": dict(predicates),
    }


# ---------------------------------------------------------------------------
# bounded HTTP transport
# ---------------------------------------------------------------------------


class _BoundedResponse:
    __slots__ = ("status_code", "payload")

    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload


class BoundedHttpClient:
    """One fail-closed transport for cloud, launcher, and loopback calls.

    No caller can supply a URL or method.  Every public method below binds a
    fixed method/origin/path; redirects and ambient proxy/TLS environment are
    disabled at client construction; response bodies are capped before JSON
    parsing.  Dynamic transport errors and response bodies never escape.
    """

    def __init__(self, *, client=None):
        self._client = client if client is not None else httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — cleanup cannot expand the error surface
            return

    def _request(
        self, method, origin, path, *, headers=None, params=None, json_body=None,
        diagnostic_sink=None,
    ):
        chunks = []
        size = 0
        status_class = "HTTP_OTHER"
        declared_media_type_class = "OTHER"
        try:
            with self._client.stream(
                method, origin + path, headers=headers, params=params, json=json_body,
            ) as response:
                status_code = response.status_code
                if diagnostic_sink is not None:
                    status_class = _initial_peer_census_status_class(status_code)
                    declared_media_type_class = (
                        _initial_peer_census_media_type_class(
                            getattr(response, "headers", None),
                        )
                    )
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > _MAX_RESPONSE_BYTES:
                        _record_initial_peer_census_diagnostic(
                            diagnostic_sink, "RESPONSE_BODY_LIMIT",
                        )
                        return None
                    chunks.append(chunk)
        except Exception:  # noqa: BLE001 — never echo a dynamic transport error
            _record_initial_peer_census_diagnostic(
                diagnostic_sink, "TRANSPORT_FAILURE",
            )
            return None
        try:
            payload = json.loads(b"".join(chunks)) if chunks else None
        except UnicodeDecodeError:
            _record_initial_peer_census_diagnostic(
                diagnostic_sink,
                "RESPONSE_DECODE_FAILURE",
                decode_context={
                    "status_class": status_class,
                    "declared_media_type_class": declared_media_type_class,
                    "decoder_class": "UNICODE_REJECTED",
                },
            )
            return None
        except ValueError:
            _record_initial_peer_census_diagnostic(
                diagnostic_sink,
                "RESPONSE_DECODE_FAILURE",
                decode_context={
                    "status_class": status_class,
                    "declared_media_type_class": declared_media_type_class,
                    "decoder_class": "JSON_VALUE_REJECTED",
                },
            )
            return None
        return _BoundedResponse(status_code, payload)

    @staticmethod
    def _bearer(credential) -> dict:
        return {"Authorization": f"Bearer {credential.expose()}"}

    def _mlx_profile_search(self, credential, folder_id: str, *, offset: int):
        return self._mlx_profile_search_request(
            credential, folder_id, offset=offset, diagnostic_sink=None,
        )

    def _mlx_profile_search_with_diagnostic(
        self, credential, folder_id: str, *, offset: int, diagnostic_sink,
    ):
        if type(diagnostic_sink) is not _InitialPeerCensusDiagnosticSink:
            raise TypeError("initial peer census diagnostic capability required")
        return self._mlx_profile_search_request(
            credential, folder_id, offset=offset, diagnostic_sink=diagnostic_sink,
        )

    def _mlx_profile_search_request(
        self, credential, folder_id: str, *, offset: int, diagnostic_sink,
    ):
        body = {
            "is_removed": False,
            "limit": _PROFILE_PAGE_SIZE,
            "offset": offset,
            "search_text": "",
            "storage_type": "all",
            "order_by": "created_at",
            "sort": "asc",
            "folder_id": folder_id,
        }
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/search",
            headers=self._bearer(credential), json_body=body,
            diagnostic_sink=diagnostic_sink,
        )

    def _mlx_profile_create(self, credential, folder_id: str, name: str):
        body = {
            "name": name,
            "browser_type": _PEER_BROWSER_TYPE,
            "os_type": _PEER_OS_TYPE,
            "folder_id": folder_id,
            "times": 1,
            "parameters": {
                "flags": {"ports_masking": "mask", "proxy_masking": "disabled"},
                "storage": {"is_local": True, "save_service_worker": True},
                "fingerprint": {},
            },
        }
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, _MLX_PROFILE_CREATE_PATH,
            headers=self._bearer(credential), json_body=body,
        )

    def _mlx_profile_remove(self, credential, profile_id: str):
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, _MLX_PROFILE_REMOVE_PATH,
            headers=self._bearer(credential),
            json_body={"ids": [profile_id], "permanently": _PEER_REMOVE_PERMANENTLY},
        )

    def _mlx_profile_status(self, credential, profile_id: str):
        path = "/api/v1/profile/status/p/" + quote(profile_id, safe="")
        return self._request("GET", _MLX_LAUNCHER_ORIGIN, path, headers=self._bearer(credential))

    def _mlx_profile_metas(self, credential, profile_id: str):
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/metas",
            headers=self._bearer(credential), json_body={"ids": [profile_id]},
        )

    def _mlx_configure_canary_port(self, credential, profile_id: str, snapshot):
        body = _port_policy.build_partial_update_body(profile_id, snapshot)
        expected = {
            "profile_id": profile_id,
            "auto_update_core": snapshot.auto_update_core,
            "parameters": {
                "flags": {"ports_masking": "mask"},
                "fingerprint": {"ports": [_port_policy.CANARY_PORT]},
            },
        }
        if body != expected:
            return None
        return self._request(
            "POST", _MLX_CLOUD_ORIGIN, "/profile/partial_update",
            headers=self._bearer(credential), json_body=body,
        )

    def _mlx_profile_start(self, credential, folder_id: str, profile_id: str):
        path = (
            "/api/v2/profile/f/" + quote(folder_id, safe="")
            + "/p/" + quote(profile_id, safe="") + "/start"
        )
        return self._request(
            "GET", _MLX_LAUNCHER_ORIGIN, path,
            headers=self._bearer(credential),
            params={"automation_type": "selenium", "headless_mode": "false"},
        )

    def _mlx_profile_stop(self, credential, profile_id: str):
        path = "/api/v1/profile/stop/p/" + quote(profile_id, safe="")
        return self._request("GET", _MLX_LAUNCHER_ORIGIN, path, headers=self._bearer(credential))

    @staticmethod
    def _webdriver_origin(port: int):
        if not isinstance(port, int) or isinstance(port, bool) or not 0 < port <= 65535:
            return None
        return f"http://127.0.0.1:{port}"

    def _webdriver_create_session(self, port: int, browser_type: str):
        origin = self._webdriver_origin(port)
        browser_name = {"mimic": "chrome", "stealthfox": "firefox"}.get(browser_type)
        if origin is None or browser_name is None:
            return None
        always_match = {
            "acceptInsecureCerts": False,
            "browserName": browser_name,
            "pageLoadStrategy": "normal",
            "unhandledPromptBehavior": "dismiss and notify",
        }
        if browser_type == "mimic":
            always_match["goog:chromeOptions"] = {}
        else:
            always_match["moz:firefoxOptions"] = {}
        return self._request(
            "POST", origin, "/session",
            json_body={"capabilities": {"alwaysMatch": always_match, "firstMatch": [{}]}},
        )

    def _webdriver_session_address(self, port: int, session_id: str):
        origin = self._webdriver_origin(port)
        if origin is None or not isinstance(session_id, str) or not _WEBDRIVER_ID_RE.fullmatch(session_id):
            return None
        return origin, "/session/" + quote(session_id, safe="")

    def _webdriver_navigate(self, port: int, session_id: str, url: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None or not isinstance(url, str):
            return None
        origin, path = address
        return self._request("POST", origin, path + "/url", json_body={"url": url})

    def _webdriver_current_url(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/url")

    def _webdriver_current_window(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/window")

    def _webdriver_window_handles(self, port: int, session_id: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None:
            return None
        origin, path = address
        return self._request("GET", origin, path + "/window/handles")

    def _webdriver_switch_window(self, port: int, session_id: str, handle: str):
        address = self._webdriver_session_address(port, session_id)
        if address is None or not isinstance(handle, str) or not _WEBDRIVER_ID_RE.fullmatch(handle):
            return None
        origin, path = address
        return self._request("POST", origin, path + "/window", json_body={"handle": handle})


# ---------------------------------------------------------------------------
# W3C WebDriver navigator — navigation and URL observation only
# ---------------------------------------------------------------------------


class WebDriverNavigator:
    """Public surface: list_pages, open_url. No other methods."""

    def __init__(self, client: BoundedHttpClient, provision: dict):
        self._client = client
        self._provision = provision
        self._sessions: dict[int, str] = {}

    @staticmethod
    def _valid_port(port) -> bool:
        return isinstance(port, int) and not isinstance(port, bool) and 0 < port <= 65535

    @staticmethod
    def _value(resp):
        if resp is None or resp.status_code != 200 or not isinstance(resp.payload, dict):
            return _WEBDRIVER_MISSING
        if set(resp.payload) != {"value"}:
            return _WEBDRIVER_MISSING
        return resp.payload.get("value")

    def _session_for(self, port: int):
        existing = self._sessions.get(port)
        if existing is not None:
            return existing
        resp = self._client._webdriver_create_session(port, self._provision.get("browser_type"))
        value = self._value(resp)
        if not isinstance(value, dict) or not {"sessionId", "capabilities"}.issubset(value):
            return None
        session_id = value.get("sessionId")
        capabilities = value.get("capabilities")
        expected = {"mimic": "chrome", "stealthfox": "firefox"}.get(
            self._provision.get("browser_type")
        )
        if (
            not isinstance(session_id, str)
            or not _WEBDRIVER_ID_RE.fullmatch(session_id)
            or not isinstance(capabilities, dict)
            or capabilities.get("browserName") != expected
        ):
            return None
        self._sessions[port] = session_id
        return session_id

    def _forget(self, port) -> None:
        if self._valid_port(port):
            self._sessions.pop(port, None)

    def list_pages(self, port) -> list:
        if not self._valid_port(port):
            return []
        session_id = self._sessions.get(port)
        if session_id is None:
            return []
        handles = self._value(
            self._client._webdriver_window_handles(port, session_id)
        )
        current = self._value(self._client._webdriver_current_window(port, session_id))
        if (
            not isinstance(handles, list)
            or not handles
            or not all(isinstance(handle, str) and _WEBDRIVER_ID_RE.fullmatch(handle) for handle in handles)
            or not isinstance(current, str)
            or current not in handles
        ):
            return []
        urls = []
        for handle in handles:
            switched = self._value(
                self._client._webdriver_switch_window(port, session_id, handle)
            )
            if switched is not None:
                return []
            current_url = self._value(
                self._client._webdriver_current_url(port, session_id)
            )
            if not isinstance(current_url, str):
                return []
            urls.append(current_url)
        restored = self._value(
            self._client._webdriver_switch_window(port, session_id, current)
        )
        return urls if restored is None else []

    def open_url(self, port, url: str) -> bool:
        if not self._valid_port(port) or not _core.allowed_url(self._provision, url):
            return False
        session_id = self._session_for(port)
        if session_id is None:
            return False
        value = self._value(
            self._client._webdriver_navigate(port, session_id, url)
        )
        return value is None


# ---------------------------------------------------------------------------
# Multilogin
# ---------------------------------------------------------------------------


def _exact_profile_create_id(response):
    """Return the one acknowledged profile id iff ``response`` is an exact
    documented create success, else ``None``.

    The two official sources disagree on the success status code (the help
    article's prose says ``200``; the Postman collection's saved example
    shows ``201``), so both are accepted as *dispatch acknowledged*. This
    never decides the effect on its own -- the read-back always does -- but
    the acknowledged id is the strongest available cross-check on the record
    the census hands back.
    """
    if response is None or response.status_code not in (200, 201):
        return None
    payload = response.payload
    if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
        return None
    status = payload.get("status")
    data = payload.get("data")
    if not isinstance(status, dict) or set(status) != {"error_code", "http_code", "message"}:
        return None
    if (
        status.get("error_code") != ""
        or status.get("http_code") != response.status_code
        or status.get("message") != "Profile successfully created"
    ):
        return None
    if not isinstance(data, dict) or set(data) != {"ids"}:
        return None
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids) != 1:
        return None
    return _canonical_multilogin_profile_id(ids[0])


def _observed_profile_create_id(response):
    """Return one safely bounded response profile id, independent of prose.

    This is identity evidence only.  A response with drifted status prose or
    extra advisory fields is still not an exact acknowledgement, but its one
    structurally usable id must constrain the subsequent census read-back.
    """
    if response is None or not 200 <= response.status_code < 300:
        return None
    payload = response.payload
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids) != 1:
        return None
    return _canonical_multilogin_profile_id(ids[0])


def _is_exact_profile_create_success(response) -> bool:
    return _exact_profile_create_id(response) is not None


def _is_exact_profile_remove_success(response) -> bool:
    return (
        response is not None
        and response.status_code == 200
        and response.payload == {
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Profile successfully removed",
            },
            "data": None,
        }
    )


def _is_exact_partial_update_success(response) -> bool:
    return (
        response is not None
        and response.status_code == 200
        and response.payload == {
            "status": {
                "error_code": "",
                "http_code": 200,
                "message": "Profile successfully updated",
            },
            "data": None,
        }
    )


def _is_explicit_partial_update_rejection(response) -> bool:
    if response is None or response.status_code in (401, 403):
        return False
    if not isinstance(response.status_code, int) or not 400 <= response.status_code <= 599:
        return False
    payload = response.payload
    if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
        return False
    status = payload.get("status")
    return (
        payload.get("data") is None
        and isinstance(status, dict)
        and set(status) == {"error_code", "http_code", "message"}
        and isinstance(status.get("error_code"), str)
        and bool(status.get("error_code"))
        and status.get("http_code") == response.status_code
        and isinstance(status.get("message"), str)
    )


class MultiloginClient:
    """Frozen Multilogin cloud/launcher contract; no prose inference."""

    def __init__(self, credential, client: BoundedHttpClient, *, browser_type: str = "mimic"):
        self._credential = credential
        self._client = client
        if browser_type not in ("mimic", "stealthfox"):
            raise _core.CanaryRefusal("PROVISION_MISSING")
        self._browser_type = browser_type
        #: profile_id we last started and have not since stopped/forgotten —
        #: profile-SCOPED ownership, not a client-wide boolean. ``None`` when
        #: we hold no profile.
        self._started_profile_id = None
        #: Exact teardown lease minted immediately before this client sends
        #: its one preflighted start request. Unlike operational owner state,
        #: it survives ambiguous responses and C5's simulated owner loss and
        #: cannot be redirected to a caller-supplied profile.
        self._cleanup_profile_ref = None
        #: Resolved id of the peer profile the most recent
        #: :meth:`create_peer_profile` proved into existence — set only from
        #: an exact read-back, never from a caller or a vendor response
        #: alone. The CLI layer reads this to write the peer provision; it
        #: is never placed in a receipt.
        self._peer_profile_id = None

    def _require_credential(self) -> None:
        if not self._credential.present:
            raise _core.CanaryRefusal("AUTH_MISSING")

    @staticmethod
    def _safe_call(call, *, diagnostic_sink=None):
        failed = False
        response = None
        try:
            response = call()
        except Exception:  # noqa: BLE001 — dynamic errors never cross the shell
            failed = True
        if failed:
            _record_initial_peer_census_diagnostic(
                diagnostic_sink, "TRANSPORT_FAILURE",
            )
            raise _core.CanaryRefusal("VENDOR_ERROR") from None
        return response

    @staticmethod
    def _valid_ref(profile_ref) -> bool:
        return (
            isinstance(profile_ref, dict)
            and isinstance(profile_ref.get("profile_id"), str)
            and bool(profile_ref.get("profile_id"))
            and isinstance(profile_ref.get("folder_id"), str)
            and bool(profile_ref.get("folder_id"))
        )

    @staticmethod
    def _successful_envelope(payload, *, profile_id=None, folder_id=None, expected_message=""):
        if not isinstance(payload, dict) or set(payload) != {"status", "data"}:
            return None
        status = payload.get("status")
        data = payload.get("data")
        if (
            not isinstance(status, dict)
            or set(status) != {"error_code", "http_code", "message"}
            or not isinstance(data, dict)
        ):
            return None
        if status.get("error_code") != "" or status.get("http_code") != 200:
            return None
        message = status.get("message")
        if not isinstance(message, str):
            return None
        # Multilogin Profile Search has changed this human-readable success
        # prose while retaining the documented success codes and exact data
        # contract.  ``None`` makes prose advisory for that one read-only
        # census surface; lifecycle and launch responses remain exact.
        if expected_message is not None and message != expected_message:
            return None
        if profile_id is not None and data.get("profile_id") != profile_id:
            return None
        if folder_id is not None and data.get("folder_id") != folder_id:
            return None
        return data

    def _profile_state(self, profile_ref: dict) -> str:
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile_id = profile_ref["profile_id"]
        folder_id = profile_ref["folder_id"]
        resp = self._safe_call(lambda: self._client._mlx_profile_status(self._credential, profile_id))
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code != 200:
            # Launcher 404 can mean its Agent restarted and lost the session
            # table; it is never evidence that the profile is closed.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        data = self._successful_envelope(
            resp.payload, profile_id=profile_id, folder_id=folder_id,
        )
        if (
            data is None
            or set(data) != _MLX_STATUS_DATA_KEYS
            or data.get("browser_type") != self._browser_type
            or not isinstance(data.get("core_version"), int)
            or isinstance(data.get("core_version"), bool)
            or data.get("core_version") <= 0
            or not isinstance(data.get("in_use_by"), str)
            or not isinstance(data.get("is_quick"), bool)
            or not all(isinstance(data.get(key), str) for key in (
                "last_launched_at", "last_launched_by", "last_launched_on",
                "message", "name", "workspace_id",
            ))
            or not isinstance(data.get("timestamp"), int)
            or isinstance(data.get("timestamp"), bool)
            or data.get("timestamp") <= 0
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        state = data.get("status")
        if state not in ("browser_running", "stopped"):
            # Includes transitional/error states and every renamed state.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if state == "stopped" and data.get("in_use_by") != "":
            # A closed lifecycle state paired with a claimed Agent owner is
            # contradictory.  Contradiction is uncertainty, not permission.
            raise _core.CanaryRefusal("VENDOR_ERROR")
        return state

    def start(self, profile_ref: dict) -> dict:
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile_id = profile_ref.get("profile_id")
        folder_id = profile_ref.get("folder_id")
        if self._started_profile_id is not None or self._cleanup_profile_ref is not None:
            raise _core.CanaryRefusal("BUSY_PROFILE")

        # Direct callers cannot bypass the actuator's preflight: exact cloud
        # identity and exact launcher-closed state are re-proven immediately
        # before the only launch request.
        profile = self._profile_inventory_item(profile_ref)
        if profile is None:
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if profile.get("browser_type") != self._browser_type:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        # The cloud census must positively say that no other vendor session
        # owns or locks this profile.  Missing or renamed ownership fields are
        # uncertainty, never permission to launch.
        if profile.get("in_use_by") != "":
            if isinstance(profile.get("in_use_by"), str) and profile.get("in_use_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if "locked_by" in profile and profile.get("locked_by") != "":
            if isinstance(profile.get("locked_by"), str) and profile.get("locked_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        state = self._profile_state(profile_ref)
        if state != "stopped":
            raise _core.CanaryRefusal("BUSY_PROFILE")

        # Once the request is sent, the effect can be ambiguous even if the
        # transport/response is lost or malformed. Retain one exact-profile
        # cleanup lease before the request; clear it only for definitive
        # no-effect auth/not-found responses.
        self._cleanup_profile_ref = dict(profile_ref)
        resp = self._safe_call(
            lambda: self._client._mlx_profile_start(self._credential, folder_id, profile_id),
        )
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            self._cleanup_profile_ref = None
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code == 404:
            self._cleanup_profile_ref = None
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        data = self._successful_envelope(
            resp.payload, expected_message="Profile started successfully",
        )
        if (
            data is None
            or set(data) != {"browser_type", "core_version", "id", "is_quick", "port"}
            or data.get("id") != profile_id
            or data.get("browser_type") != self._browser_type
            or not isinstance(data.get("core_version"), int)
            or isinstance(data.get("core_version"), bool)
            or data.get("core_version") <= 0
            or data.get("is_quick") is not False
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        raw_port = data.get("port")
        if isinstance(raw_port, str) and raw_port.isascii() and raw_port.isdigit():
            port = int(raw_port)
        elif isinstance(raw_port, int) and not isinstance(raw_port, bool):
            port = raw_port
        else:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if not 0 < port <= 65535:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = profile_id
        return {"profile_id": profile_id, "port": port}

    def _stop_cleanup_ref(self, profile_ref: dict) -> None:
        profile_id = profile_ref["profile_id"]
        resp = self._safe_call(lambda: self._client._mlx_profile_stop(self._credential, profile_id))
        if resp is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if resp.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if resp.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        payload = resp.payload
        if not isinstance(payload, dict) or set(payload) != {"status"}:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        status = payload.get("status")
        if (
            not isinstance(status, dict)
            or set(status) != {"error_code", "http_code", "message"}
            or status.get("error_code") != ""
            or status.get("http_code") != 200
            or status.get("message") != ""
        ):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        self._started_profile_id = None
        self._cleanup_profile_ref = None

    def stop(self, profile_ref: dict) -> None:
        self._require_credential()
        if (
            not self._valid_ref(profile_ref)
            or self._started_profile_id != profile_ref.get("profile_id")
            or self._cleanup_profile_ref != profile_ref
        ):
            raise _core.CanaryRefusal("UNOWNED_RUNNING_PROFILE")
        self._stop_cleanup_ref(profile_ref)

    def _cleanup_started_profile(self) -> bool:
        """Stop only the exact profile targeted by this client's start request."""
        self._require_credential()
        profile_ref = self._cleanup_profile_ref
        if profile_ref is None:
            return False
        self._stop_cleanup_ref(profile_ref)
        return True

    def forget_ownership(self) -> None:
        """Forget operational ownership only; never call the vendor.

        The private exact-profile teardown lease remains so the outer canary
        boundary can still contain C5 and early matrix failures.
        """
        self._started_profile_id = None

    def _profile_inventory_item(self, profile_ref: dict):
        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        target_id = profile_ref["profile_id"]
        folder_id = profile_ref["folder_id"]
        offset = 0
        expected_total = None
        seen_ids = set()
        found = None
        while offset < _MAX_PROFILE_CENSUS:
            resp = self._safe_call(
                lambda: self._client._mlx_profile_search(self._credential, folder_id, offset=offset),
            )
            if resp is None:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if resp.status_code in (401, 403):
                raise _core.CanaryRefusal("AUTH_EXPIRED")
            if resp.status_code != 200:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            data = self._successful_envelope(resp.payload, expected_message=None)
            if data is None or set(data) != {"profiles", "total_count"}:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            profiles = data.get("profiles")
            total = data.get("total_count")
            if not isinstance(profiles, list) or not isinstance(total, int) or isinstance(total, bool):
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if total < 0 or total > _MAX_PROFILE_CENSUS:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if expected_total is None:
                expected_total = total
            if total != expected_total or len(profiles) > _PROFILE_PAGE_SIZE:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            for item in profiles:
                if not isinstance(item, dict) or not {"id", "folder_id"}.issubset(item):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                item_id = item.get("id")
                item_folder = item.get("folder_id")
                if not isinstance(item_id, str) or not isinstance(item_folder, str):
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                if item_id in seen_ids:
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                seen_ids.add(item_id)
                if item_id == target_id:
                    if item_folder != folder_id:
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    found = dict(item)
            offset += len(profiles)
            if offset == total:
                return found
            if not profiles or offset > total:
                raise _core.CanaryRefusal("VENDOR_ERROR")
        raise _core.CanaryRefusal("VENDOR_ERROR")

    def profile_exists(self, profile_ref: dict) -> bool:
        return self._profile_inventory_item(profile_ref) is not None

    def is_running_externally(self, profile_ref: dict) -> bool:
        state = self._profile_state(profile_ref)
        if state == "stopped":
            return False
        return self._started_profile_id != profile_ref.get("profile_id")

    # -----------------------------------------------------------------
    # REALM1-C1 — one-profile peer create/reconcile/remove (Mastermind #385)
    # -----------------------------------------------------------------

    def peer_candidates(self, *, folder_id: str, peer_name: str) -> list:
        """Read-only census of every profile in ``folder_id`` named exactly
        ``peer_name``. Mirrors :meth:`_profile_inventory_item`'s pagination,
        duplicate-id, and auth/shape guards; never mutates anything."""
        return self._peer_candidates(
            folder_id=folder_id, peer_name=peer_name, diagnostic_sink=None,
        )

    def _peer_candidates(
        self, *, folder_id: str, peer_name: str, diagnostic_sink,
    ) -> list:
        self._require_credential()
        offset = 0
        expected_total = None
        seen_ids = set()
        matches = []
        while offset < _MAX_PROFILE_CENSUS:
            def _search():
                diagnostic_call = getattr(
                    self._client, "_mlx_profile_search_with_diagnostic", None,
                )
                if diagnostic_sink is not None and callable(diagnostic_call):
                    return diagnostic_call(
                        self._credential, folder_id, offset=offset,
                        diagnostic_sink=diagnostic_sink,
                    )
                return self._client._mlx_profile_search(
                    self._credential, folder_id, offset=offset,
                )

            resp = self._safe_call(
                _search, diagnostic_sink=diagnostic_sink,
            )
            if resp is None:
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "TRANSPORT_FAILURE",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if resp.status_code in (401, 403):
                raise _core.CanaryRefusal("AUTH_EXPIRED")
            if resp.status_code != 200:
                if resp.status_code == 429:
                    diagnostic = "HTTP_RATE_LIMITED"
                elif (
                    isinstance(resp.status_code, int)
                    and not isinstance(resp.status_code, bool)
                    and 400 <= resp.status_code < 500
                ):
                    diagnostic = "HTTP_REQUEST_REJECTED"
                elif (
                    isinstance(resp.status_code, int)
                    and not isinstance(resp.status_code, bool)
                    and 500 <= resp.status_code < 600
                ):
                    diagnostic = "HTTP_SERVICE_UNAVAILABLE"
                else:
                    diagnostic = "HTTP_UNEXPECTED"
                _record_initial_peer_census_diagnostic(diagnostic_sink, diagnostic)
                raise _core.CanaryRefusal("VENDOR_ERROR")
            data = self._successful_envelope(resp.payload, expected_message=None)
            if data is None:
                payload = resp.payload
                status = payload.get("status") if isinstance(payload, dict) else None
                status_valid = (
                    isinstance(payload, dict)
                    and set(payload) == {"status", "data"}
                    and isinstance(status, dict)
                    and set(status) == {"error_code", "http_code", "message"}
                    and status.get("error_code") == ""
                    and status.get("http_code") == 200
                    and isinstance(status.get("message"), str)
                )
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink,
                    "DATA_SCHEMA_INVALID" if status_valid else "STATUS_ENVELOPE_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if set(data) != {"profiles", "total_count"}:
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "DATA_SCHEMA_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            profiles = data.get("profiles")
            total = data.get("total_count")
            if not isinstance(profiles, list) or not isinstance(total, int) or isinstance(total, bool):
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "DATA_SCHEMA_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if total < 0 or total > _MAX_PROFILE_CENSUS:
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "DATA_SCHEMA_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            if expected_total is None:
                expected_total = total
            if total != expected_total or len(profiles) > _PROFILE_PAGE_SIZE:
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "PAGINATION_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
            for item in profiles:
                if not isinstance(item, dict) or not {"id", "folder_id", "name"}.issubset(item):
                    _record_initial_peer_census_diagnostic(
                        diagnostic_sink, "PROFILE_ITEM_INVALID",
                    )
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                item_id = _canonical_multilogin_profile_id(item.get("id"))
                item_folder = _canonical_multilogin_profile_id(item.get("folder_id"))
                item_name = item.get("name")
                if (
                    item_id is None
                    or item_folder is None
                    or not isinstance(item_name, str)
                ):
                    _record_initial_peer_census_diagnostic(
                        diagnostic_sink, "PROFILE_ITEM_INVALID",
                    )
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                if item_id in seen_ids:
                    _record_initial_peer_census_diagnostic(
                        diagnostic_sink, "PAGINATION_INVALID",
                    )
                    raise _core.CanaryRefusal("VENDOR_ERROR")
                seen_ids.add(item_id)
                if item_name == peer_name:
                    if item_folder != folder_id:
                        _record_initial_peer_census_diagnostic(
                            diagnostic_sink, "PROFILE_ITEM_INVALID",
                        )
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    if not isinstance(item.get("browser_type"), str) or not isinstance(item.get("os_type"), str):
                        # We cannot prove identity we cannot see.
                        _record_initial_peer_census_diagnostic(
                            diagnostic_sink, "PROFILE_ITEM_INVALID",
                        )
                        raise _core.CanaryRefusal("VENDOR_ERROR")
                    canonical = dict(item)
                    canonical["id"] = item_id
                    canonical["folder_id"] = item_folder
                    matches.append(canonical)
            offset += len(profiles)
            if offset == total:
                return matches
            if not profiles or offset > total:
                _record_initial_peer_census_diagnostic(
                    diagnostic_sink, "PAGINATION_INVALID",
                )
                raise _core.CanaryRefusal("VENDOR_ERROR")
        _record_initial_peer_census_diagnostic(
            diagnostic_sink, "PAGINATION_INVALID",
        )
        raise _core.CanaryRefusal("VENDOR_ERROR")

    @staticmethod
    def _peer_identity_matches(record, *, folder_id: str, peer_name: str, require_unowned: bool = False) -> bool:
        if not isinstance(record, dict):
            return False
        ok = (
            record.get("folder_id") == folder_id
            and record.get("browser_type") == _PEER_BROWSER_TYPE
            and record.get("os_type") == _PEER_OS_TYPE
            and record.get("name") == peer_name
        )
        if not ok:
            return False
        if require_unowned:
            if record.get("in_use_by") != "":
                return False
            if "locked_by" in record and record.get("locked_by") != "":
                return False
        return True

    @staticmethod
    def _peer_digests(folder_id: str, anchor_profile_id: str, peer_name: str, *, peer_profile_id=None) -> dict:
        return {
            "folder": _core.sha256_hex(folder_id),
            "peer_name": _core.sha256_hex(peer_name),
            "peer_profile": _core.sha256_hex(peer_profile_id) if peer_profile_id else None,
            "anchor_profile": _core.sha256_hex(anchor_profile_id),
        }

    def create_peer_profile(
        self, *, folder_id, anchor_profile_id, intent_present, commit_intent,
        observed_profile_digest=None, record_response_id=None,
        intent_reconciliation_ready=False,
    ) -> dict:
        """Create the one missing stopped disposable peer profile.

        At most ONE create dispatch, ever. The vendor response never decides
        the effect — a single read-only census read-back always does. This
        method performs NO file I/O: ``intent_present``/``commit_intent`` are
        supplied by the caller (the CLI layer in :func:`main`).
        """
        peer_name = peer_profile_name(folder_id, anchor_profile_id)
        digests = self._peer_digests(folder_id, anchor_profile_id, peer_name)
        intent_committed = bool(intent_present)
        initial_census_diagnostic = _InitialPeerCensusDiagnosticSink(
            _INITIAL_PEER_CENSUS_DIAGNOSTIC_SEAL,
        )

        def _receipt(effect, code, verdict, **overrides):
            predicates = dict(_PEER_BASE_PREDICATES)
            predicates["intent_committed"] = intent_committed
            predicates.update(overrides)
            return peer_receipt(
                effect=effect,
                code=code,
                verdict=verdict,
                digests=digests,
                initial_peer_census_diagnostic=initial_census_diagnostic.value,
                initial_peer_census_decode_context=(
                    initial_census_diagnostic.decode_context
                ),
                **predicates,
            )

        if not self._credential.present:
            return _receipt("NONE", "AUTH_MISSING", "REFUSED")

        try:
            candidates = self._peer_candidates(
                folder_id=folder_id,
                peer_name=peer_name,
                diagnostic_sink=initial_census_diagnostic,
            )
        except _core.CanaryRefusal as refusal:
            return _receipt("NONE", refusal.code, "REFUSED")

        candidates_before = len(candidates)
        dispatched = False
        reconciled = False
        acknowledged_id = None
        observed_id = None

        if candidates_before >= 1 and not intent_present:
            # A name-colliding profile we did not create is a conflict; we
            # never adopt it.
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        if intent_present and candidates_before == 1:
            if not intent_reconciliation_ready:
                # CREATE_CLAIMED may still belong to a live owner between
                # dispatch and durable response-ID recording.  A second
                # invocation cannot provision its census row until the state
                # itself carries the response identity (or a later phase).
                return _receipt(
                    "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                    candidates_before=candidates_before,
                    dispatched=False,
                    reconciled=True,
                )
            if not self._peer_identity_matches(candidates[0], folder_id=folder_id, peer_name=peer_name):
                return _receipt("NONE", "VENDOR_ERROR", "REFUSED", candidates_before=candidates_before)
            dispatched = False
            reconciled = True
        elif intent_present and candidates_before != 1:
            # A committed intent means a create may already have been
            # dispatched; zero or many candidates is uncertainty, never
            # permission to dispatch again.
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=False, reconciled=True,
            )
        elif not intent_present and candidates_before == 0:
            try:
                committed = commit_intent()
            except Exception:  # noqa: BLE001 — a raising commit is a failed commit
                committed = REFUSED
            if committed == EXISTING_EXACT:
                # A concurrent invocation won the durable claim.  This call
                # becomes reconciliation-only; it must never send a second
                # create even though its own pre-claim census saw zero rows.
                intent_committed = True
                dispatched = False
                reconciled = True
                return _receipt(
                    "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                    candidates_before=0,
                    dispatched=False,
                    reconciled=True,
                )
            elif committed != CREATED_THIS_CALL:
                return _receipt(
                    "NONE", "PROVISION_MISSING", "REFUSED", candidates_before=0, dispatched=False,
                )
            else:
                intent_committed = True
                response = None
                try:
                    response = self._client._mlx_profile_create(self._credential, folder_id, peer_name)
                except Exception:  # noqa: BLE001 — never echo a dynamic transport error
                    response = None
                if response is not None and response.status_code in (401, 403):
                    # Auth rejection precedes creation; the ONLY pre-effect
                    # exit after an acquired claim.
                    return _receipt(
                        "NONE", "AUTH_EXPIRED", "REFUSED", candidates_before=0, dispatched=False,
                    )
                observed_id = _observed_profile_create_id(response)
                if observed_id is not None and record_response_id is not None:
                    try:
                        recorded = record_response_id(observed_id)
                    except Exception:  # noqa: BLE001 — state uncertainty is effect uncertainty
                        recorded = False
                    if recorded is not True:
                        return _receipt(
                            "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                            candidates_before=0, dispatched=True, reconciled=False,
                        )
                acknowledged_id = _exact_profile_create_id(response)
                exact = acknowledged_id is not None
                dispatched = True
                reconciled = not exact
        else:  # pragma: no cover — every (intent_present, candidates_before)
            # combination is covered by the three branches above; this exists
            # only so a future mutation cannot silently fall through to a
            # dispatch with no guard.
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        # Read-back reconciliation: ALWAYS exactly one census read. The
        # create response never decides the effect by itself.
        try:
            after = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal as refusal:
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", refusal.code, "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        if len(after) != 1:
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        record = after[0]
        if not self._peer_identity_matches(
            record, folder_id=folder_id, peer_name=peer_name, require_unowned=True,
        ):
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        response_constraint = observed_id or acknowledged_id
        if (
            response_constraint is not None
            and record.get("id") != response_constraint
        ) or (
            observed_profile_digest is not None
            and _core.sha256_hex(record.get("id")) != observed_profile_digest
        ):
            # The vendor/state named one id and the folder census returned another.
            # Adopting the census row here would leave the acknowledged
            # profile untracked in the approved folder, unreachable by
            # rollback, and fatal to every later create. Contradiction is
            # uncertainty, never permission.
            return _receipt(
                "CREATE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=False,
            )

        resolved_id = record["id"]
        self._peer_profile_id = resolved_id
        digests["peer_profile"] = _core.sha256_hex(resolved_id)

        try:
            state = self._profile_state({"profile_id": resolved_id, "folder_id": folder_id})
        except _core.CanaryRefusal:
            state = None

        if state != "stopped":
            return _receipt(
                "CREATE_APPLIED", "BUSY_PROFILE", "HOLD",
                candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
                exact_readback=True, stopped_proven=False, cleanup_lease_retained=True,
            )

        return _receipt(
            "PROFILE_STOPPED_PROVEN", "OK", "HOLD",
            candidates_before=candidates_before, dispatched=dispatched, reconciled=reconciled,
            exact_readback=True, stopped_proven=True, cleanup_lease_retained=True,
        )

    def remove_peer_profile(
        self, *, folder_id, anchor_profile_id, peer_profile_id,
        remove_already_claimed=False, claim_remove=None,
    ) -> dict:
        """Remove ONLY the exact stopped, unowned, operation-created peer
        profile. At most ONE remove dispatch, ever; the vendor response
        never decides the effect on its own."""
        peer_name = peer_profile_name(folder_id, anchor_profile_id)
        digests = self._peer_digests(
            folder_id, anchor_profile_id, peer_name, peer_profile_id=peer_profile_id,
        )

        def _receipt(effect, code, verdict, **overrides):
            predicates = dict(_PEER_BASE_PREDICATES)
            predicates.update(overrides)
            # A dispatched removal is a TRASH move, never a permanent delete.
            disposition = "TRASHED_RESTORABLE" if predicates["dispatched"] else "NOT_APPLICABLE"
            return peer_receipt(
                effect=effect, code=code, verdict=verdict, digests=digests,
                removal_disposition=disposition, **predicates,
            )

        if not self._credential.present:
            return _receipt("NONE", "AUTH_MISSING", "REFUSED")

        try:
            candidates = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal as refusal:
            return _receipt("NONE", refusal.code, "REFUSED")

        candidates_before = len(candidates)
        if candidates_before == 0:
            if remove_already_claimed:
                return _receipt(
                    "ROLLBACK_VERIFIED", "OK", "PASS", candidates_before=0,
                    dispatched=False, reconciled=True, removed_absent=True,
                )
            return _receipt("NONE", "PROFILE_NOT_FOUND", "REFUSED", candidates_before=0)

        exact_target = (
            candidates_before == 1
            and candidates[0].get("id") == peer_profile_id
            and self._peer_identity_matches(
                candidates[0], folder_id=folder_id, peer_name=peer_name, require_unowned=True,
            )
        )
        if not exact_target:
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        try:
            state = self._profile_state({"profile_id": peer_profile_id, "folder_id": folder_id})
        except _core.CanaryRefusal:
            state = None
        if state != "stopped":
            return _receipt("NONE", "BUSY_PROFILE", "REFUSED", candidates_before=candidates_before)

        dispatch_owned = False
        if remove_already_claimed:
            claim = EXISTING_EXACT
        elif claim_remove is None:
            # Direct unit callers without lifecycle state are never granted a
            # durable external remove.  The coordinator supplies the claim.
            claim = REFUSED
        else:
            try:
                claim = claim_remove()
            except Exception:  # noqa: BLE001 — claim uncertainty is refusal
                claim = REFUSED
        if claim == CREATED_THIS_CALL:
            dispatch_owned = True
        elif claim != EXISTING_EXACT:
            return _receipt(
                "NONE", "PROVISION_MISSING", "REFUSED",
                candidates_before=candidates_before, dispatched=False,
            )

        response = None
        exact = False
        if dispatch_owned:
            try:
                response = self._client._mlx_profile_remove(self._credential, peer_profile_id)
            except Exception:  # noqa: BLE001 — never echo a dynamic transport error
                response = None
            if response is not None and response.status_code in (401, 403):
                # The durable remove claim remains: a retry could duplicate an
                # effect if the remote classification were ever wrong.
                return _receipt(
                    "REMOVE_EFFECT_UNKNOWN", "AUTH_EXPIRED", "HOLD",
                    candidates_before=candidates_before, dispatched=True, reconciled=False,
                )
            exact = _is_exact_profile_remove_success(response)

        try:
            after = self.peer_candidates(folder_id=folder_id, peer_name=peer_name)
        except _core.CanaryRefusal:
            return _receipt(
                "REMOVE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
                candidates_before=candidates_before, dispatched=dispatch_owned, reconciled=True,
            )

        if len(after) == 0:
            return _receipt(
                "ROLLBACK_VERIFIED", "OK", "PASS",
                candidates_before=candidates_before, dispatched=dispatch_owned,
                reconciled=not exact, removed_absent=True,
            )
        return _receipt(
            "REMOVE_EFFECT_UNKNOWN", "VENDOR_ERROR", "HOLD",
            candidates_before=candidates_before, dispatched=dispatch_owned, reconciled=True,
        )

    def port_policy_snapshot(self, profile_ref: dict):
        """Read and classify the exact stopped disposable profile policy."""

        self._require_credential()
        if not self._valid_ref(profile_ref):
            raise _core.CanaryRefusal("VENDOR_ERROR")
        profile = self._profile_inventory_item(profile_ref)
        if profile is None:
            raise _core.CanaryRefusal("PROFILE_NOT_FOUND")
        if profile.get("browser_type") != "mimic":
            raise _core.CanaryRefusal("UNSUPPORTED_PORT_STATE")
        if profile.get("in_use_by") != "":
            if isinstance(profile.get("in_use_by"), str) and profile.get("in_use_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if "locked_by" in profile and profile.get("locked_by") != "":
            if isinstance(profile.get("locked_by"), str) and profile.get("locked_by"):
                raise _core.CanaryRefusal("BUSY_PROFILE")
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if self._profile_state(profile_ref) != "stopped":
            raise _core.CanaryRefusal("BUSY_PROFILE")

        response = self._safe_call(
            lambda: self._client._mlx_profile_metas(
                self._credential, profile_ref["profile_id"],
            ),
        )
        if response is None:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        if response.status_code in (401, 403):
            raise _core.CanaryRefusal("AUTH_EXPIRED")
        if response.status_code != 200:
            raise _core.CanaryRefusal("VENDOR_ERROR")
        try:
            return _port_policy.classify_profile_metas(
                response.payload,
                profile_id=profile_ref["profile_id"],
                folder_id=profile_ref["folder_id"],
            )
        except _port_policy.PortPolicyRefusal as refusal:
            code = (
                "UNSUPPORTED_PORT_STATE"
                if refusal.code == _port_policy.UNSUPPORTED_PORT_STATE
                else "VENDOR_ERROR"
            )
            raise _core.CanaryRefusal(code) from None

    @staticmethod
    def _config_receipt(code: str, **flags) -> dict:
        return _port_policy.configuration_receipt(code, **flags)

    def _post_configuration_receipt(
        self, before, profile_ref: dict, *, response_was_ambiguous: bool,
    ) -> dict:
        try:
            after = self.port_policy_snapshot(profile_ref)
        except _core.CanaryRefusal:
            return self._config_receipt(
                "EFFECT_UNKNOWN", updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=False,
            )
        preservation_unchanged = after.preservation_digest == before.preservation_digest
        auto_update_unchanged = after.auto_update_core == before.auto_update_core
        if not preservation_unchanged or not auto_update_unchanged:
            return self._config_receipt(
                "PRESERVATION_DRIFT", updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=preservation_unchanged,
                auto_update_unchanged=auto_update_unchanged,
                exact_profile_stopped=True,
            )
        if after.state != _port_policy.EXACT_CONFIGURED:
            return self._config_receipt(
                "EFFECT_UNKNOWN" if response_was_ambiguous else "VENDOR_ERROR",
                updated=False, reconciled=response_was_ambiguous,
                preservation_unchanged=True, auto_update_unchanged=True,
                exact_profile_stopped=True,
            )
        return self._config_receipt(
            "CONFIGURED_AFTER_RECONCILIATION" if response_was_ambiguous else "CONFIGURED",
            updated=True, reconciled=response_was_ambiguous,
            preservation_unchanged=True, auto_update_unchanged=True,
            exact_profile_stopped=True,
        )

    def configure_canary_port(self, profile_ref: dict) -> dict:
        """Perform at most one exact update, followed only by read-back."""

        try:
            before = self.port_policy_snapshot(profile_ref)
        except _core.CanaryRefusal as refusal:
            code = (
                "UNSUPPORTED_PORT_STATE"
                if refusal.code == "UNSUPPORTED_PORT_STATE"
                else "AUTH_EXPIRED_NO_PROOF"
                if refusal.code == "AUTH_EXPIRED"
                else "VENDOR_ERROR"
            )
            return self._config_receipt(
                code, updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=False,
            )
        if before.state == _port_policy.EXACT_CONFIGURED:
            return self._config_receipt(
                "ALREADY_CONFIGURED", updated=False, reconciled=False,
                preservation_unchanged=True, auto_update_unchanged=True,
                exact_profile_stopped=True,
            )
        if before.state != _port_policy.DEFAULT_MASKED:
            return self._config_receipt(
                "UNSUPPORTED_PORT_STATE", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        try:
            response = self._client._mlx_configure_canary_port(
                self._credential, profile_ref["profile_id"], before,
            )
        except Exception:  # noqa: BLE001 — reconcile read-only after ambiguous write
            response = None
        if response is not None and response.status_code in (401, 403):
            return self._config_receipt(
                "AUTH_EXPIRED_NO_PROOF", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        if _is_exact_partial_update_success(response):
            return self._post_configuration_receipt(
                before, profile_ref, response_was_ambiguous=False,
            )
        if _is_explicit_partial_update_rejection(response):
            return self._config_receipt(
                "REJECTED_NO_PROOF", updated=False, reconciled=False,
                preservation_unchanged=False, auto_update_unchanged=False,
                exact_profile_stopped=True,
            )
        return self._post_configuration_receipt(
            before, profile_ref, response_was_ambiguous=True,
        )


# ---------------------------------------------------------------------------
# GoLogin
# ---------------------------------------------------------------------------


class GoLoginClient:
    """GoLogin shell. The official lifecycle is SDK-owned (the "gologin"
    package on PyPI/npm); this repository does not depend on that SDK, so
    every method refuses UNSUPPORTED_SURFACE — never an unofficial REST
    lifecycle or partial existence improvisation."""

    PINNED_GOLOGIN_SDK = "gologin"
    PINNED_GOLOGIN_SDK_VERSION = "not-installed-unpinned"

    def __init__(self, credential, client=None):
        self._credential = credential
        self._client = client

    @staticmethod
    def _sdk_available() -> bool:
        try:
            return importlib.util.find_spec(GoLoginClient.PINNED_GOLOGIN_SDK) is not None
        except (ImportError, ValueError):
            return False

    def start(self, profile_ref: dict) -> dict:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def stop(self, profile_ref: dict) -> None:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def is_running_externally(self, profile_ref: dict) -> bool:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")

    def forget_ownership(self) -> None:
        """No-op: GoLoginClient never starts/stops anything (see class
        docstring), so it has no started-profile bookkeeping to forget.
        Exists only for uniform shape with MultiloginClient."""
        return None

    def _cleanup_started_profile(self) -> bool:
        return False

    def profile_exists(self, profile_ref: dict) -> bool:
        raise _core.CanaryRefusal("UNSUPPORTED_SURFACE")


# ---------------------------------------------------------------------------
# benign loopback origin
# ---------------------------------------------------------------------------


class _CanaryRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format_str, *args) -> None:  # noqa: A002 — stdlib signature
        return

    def _origin(self) -> "LoopbackBenignOrigin":
        return self.server.canary_origin  # type: ignore[attr-defined]

    def _respond(self, status: int, body: bytes, extra_headers=None) -> None:
        self.send_response(status)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 — stdlib method name
        origin = self._origin()
        path = self.path.split("?", 1)[0]
        origin._record(path)

        if path in ("/a", "/b"):
            self._respond(200, b"ok")
            return
        if path == "/state/set":
            self._respond(200, b"ok", {"Set-Cookie": f"mas115_canary={origin.token}; Path=/"})
            return
        if path == "/state/check":
            cookie_header = self.headers.get("Cookie", "") or ""
            if f"mas115_canary={origin.token}" in cookie_header:
                origin._mark_cookie_seen()
            self._respond(200, b"ok")
            return
        if path == "/auth":
            self._respond(401, b"unauthorized", {"WWW-Authenticate": 'Basic realm="mas115-canary"'})
            return
        self._respond(404, b"not found")

    # PUT is unused by the benign origin itself. Preserve a closed response
    # if an old inert harness sends the former DevTools-shaped method.
    do_PUT = do_GET  # noqa: N815


class LoopbackBenignOrigin:
    """Stdlib ``ThreadingHTTPServer`` serving only the five canary paths."""

    def __init__(self, token: str = "mas115-loopback-token"):
        self.token = token
        self._seen_paths: set = set()
        self._cookie_seen = False
        self._lock = threading.Lock()
        self._server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", _port_policy.CANARY_PORT), _CanaryRequestHandler,
        )
        if self._server.server_address[:2] != ("127.0.0.1", _port_policy.CANARY_PORT):
            self._server.server_close()
            raise _core.CanaryRefusal("CANARY_PORT_UNAVAILABLE")
        self._server.canary_origin = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def _record(self, path: str) -> None:
        with self._lock:
            self._seen_paths.add(path)

    def _mark_cookie_seen(self) -> None:
        with self._lock:
            self._cookie_seen = True

    @property
    def base_url(self) -> str:
        return _port_policy.CANARY_ORIGIN

    def self_test(self) -> bool:
        """Prove the fixed loopback listener and clear the probe observation."""

        connection = http.client.HTTPConnection(
            "127.0.0.1", _port_policy.CANARY_PORT, timeout=2.0,
        )
        try:
            connection.request("GET", "/auth")
            response = connection.getresponse()
            body = response.read(64)
            healthy = (
                response.status == 401
                and response.getheader("WWW-Authenticate") == 'Basic realm="mas115-canary"'
                and body == b"unauthorized"
            )
        except Exception:  # noqa: BLE001 — local self-test has one closed result
            healthy = False
        finally:
            connection.close()
            with self._lock:
                self._seen_paths.discard("/auth")
        return healthy

    def saw(self, path: str) -> bool:
        with self._lock:
            return path in self._seen_paths

    def cookie_seen(self, token: str) -> bool:
        with self._lock:
            return self._cookie_seen and token == self.token

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


# ---------------------------------------------------------------------------
# live process probe
# ---------------------------------------------------------------------------


def _matches_this_profile(parts: list, vendor: str, folder_id, profile_id) -> bool:
    if vendor == "multilogin":
        return len(parts) >= 2 and parts[-2] == folder_id and parts[-1] == profile_id
    if vendor == "gologin":
        return profile_id in parts
    return False


def live_process_probe(provision: dict):
    """Build a zero-arg process probe -> ``{"this_profile": int, "other_profiles": int}``.

    Raw process-argument lines never leave this function — only the two
    integer counts are returned (ARGV-PRIVACY LAW, see
    :mod:`integrations.chairman_surfaces.chatgpt`)."""
    from integrations.chairman_surfaces import chatgpt as _chatgpt

    vendor = provision.get("vendor")
    profile_id = provision.get("profile_id")
    folder_id = provision.get("folder_id")

    def _probe() -> dict:
        try:
            lines = _chatgpt._default_process_args_reader()
        except Exception:  # noqa: BLE001 — a probe failure must never propagate
            lines = []
        if not isinstance(lines, list):
            lines = []

        this_profile = 0
        other_profiles = 0
        for line in lines:
            if not isinstance(line, str):
                continue
            match = _USER_DATA_DIR_RE.search(line)
            if not match:
                continue
            raw_path = match.group(1)
            parts = [part for part in raw_path.split("/") if part]
            if _matches_this_profile(parts, vendor, folder_id, profile_id):
                this_profile += 1
                continue
            if "/mlx/profiles/" in raw_path or "/GoLogin/profiles/" in raw_path:
                other_profiles += 1

        return {"this_profile": this_profile, "other_profiles": other_profiles}

    return _probe


def _settled_cleanup_probe(
    process_probe, *, monotonic=time.monotonic, sleep=time.sleep,
    timeout_seconds=_CLEANUP_PROCESS_TIMEOUT_SECONDS,
):
    """Wait boundedly for the exact disposable process group to disappear."""
    def _probe():
        deadline = monotonic() + timeout_seconds
        latest = process_probe()
        while (
            isinstance(latest, dict)
            and isinstance(latest.get("this_profile"), int)
            and not isinstance(latest.get("this_profile"), bool)
            and latest.get("this_profile") > 0
            and monotonic() < deadline
        ):
            sleep(_CLEANUP_PROCESS_POLL_SECONDS)
            latest = process_probe()
        return latest

    return _probe


# ---------------------------------------------------------------------------
# operator-only secret pipe + entrypoint
# ---------------------------------------------------------------------------


class _KeychainCredentialPipe:
    """One bounded anonymous pipe from fixed Keychain stdout to this helper.

    The producer is started by ``posix_spawn`` file actions, not a process
    wrapper carrying stdout: fd 1 is the pipe's integer write FD, while this
    object owns only the read FD.  Dynamic child errors and output never cross
    the helper's closed result boundary.
    """

    __slots__ = ("_fd", "_pid", "_waitpid", "_kill")

    def __init__(self, read_fd: int, pid: int, *, waitpid=os.waitpid, kill=os.kill):
        self._fd = read_fd
        self._pid = pid
        self._waitpid = waitpid
        self._kill = kill

    def read(self, limit: int):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return b""
        deadline = time.monotonic() + _KEYCHAIN_READ_TIMEOUT_SECONDS
        chunks = []
        remaining = limit
        while remaining > 0:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                return b""
            try:
                ready, _, _ = select.select([self._fd], [], [], timeout)
            except Exception:  # noqa: BLE001 — fixed absent result only
                return b""
            if not ready:
                return b""
            try:
                chunk = os.read(self._fd, min(4096, remaining))
            except OSError:
                return b""
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _wait_until(self, deadline: float) -> bool:
        while True:
            try:
                waited_pid, _status = self._waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                return True
            except Exception:  # noqa: BLE001 — cleanup remains fixed and bounded
                return False
            if waited_pid == self._pid:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)

    def close(self) -> None:
        try:
            os.close(self._fd)
        except OSError:
            pass
        if self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS):
            return
        try:
            self._kill(self._pid, signal.SIGTERM)
        except Exception:  # noqa: BLE001 — cleanup of our fixed child only
            pass
        if self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS):
            return
        try:
            self._kill(self._pid, signal.SIGKILL)
        except Exception:  # noqa: BLE001 — never expand the result surface
            pass
        self._wait_until(time.monotonic() + _KEYCHAIN_WAIT_TIMEOUT_SECONDS)


def _open_keychain_credential_pipe(*, spawn=os.posix_spawn, waitpid=os.waitpid, kill=os.kill):
    """Open the fixed Keychain producer only after the caller's preflights.

    The secret producer's stdout is an anonymous integer FD, never the
    library's captured-pipe sentinel and never a returned stdout value.
    """
    read_fd, write_fd = os.pipe()
    argv = [
        _SECURITY_BIN, "find-generic-password", "-w",
        "-s", _KEYCHAIN_SERVICE, "-a", _KEYCHAIN_ACCOUNT,
    ]
    try:
        pid = spawn(
            _SECURITY_BIN,
            argv,
            {},
            file_actions=[
                (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
                (os.POSIX_SPAWN_DUP2, write_fd, 1),
                (os.POSIX_SPAWN_OPEN, 2, os.devnull, os.O_WRONLY, 0),
                (os.POSIX_SPAWN_CLOSE, read_fd),
                (os.POSIX_SPAWN_CLOSE, write_fd),
            ],
        )
    except Exception:  # noqa: BLE001 — dynamic spawn errors never escape
        try:
            os.close(read_fd)
        except OSError:
            pass
        raise _core.CanaryRefusal("AUTH_MISSING") from None
    finally:
        try:
            os.close(write_fd)
        except OSError:
            pass
    return _KeychainCredentialPipe(read_fd, pid, waitpid=waitpid, kill=kill)


def _read_direct_pipe_credential(stream) -> _core.Credential:
    """Read one bounded anonymous-pipe credential into this helper's holder.

    The raw value is never returned: the only successful return is the
    redacting :class:`Credential` object.  Callers must run every non-secret
    preflight before invoking this function.
    """
    source = getattr(stream, "buffer", stream)
    try:
        raw = source.read(_MAX_STDIN_BYTES + 1)
    except Exception:  # noqa: BLE001 — pipe failure has one fixed refusal
        return _core.Credential(None, "absent")
    if isinstance(raw, bytes):
        if len(raw) > _MAX_STDIN_BYTES:
            return _core.Credential(None, "absent")
        try:
            value = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return _core.Credential(None, "absent")
    elif isinstance(raw, str):
        if len(raw.encode("utf-8")) > _MAX_STDIN_BYTES:
            return _core.Credential(None, "absent")
        value = raw.strip()
    else:
        return _core.Credential(None, "absent")
    return _core.Credential(value, "stdin") if value else _core.Credential(None, "absent")


def _emit_refusal(out, vendor: str, code: str) -> int:
    print(json.dumps(_core._refused_payload(vendor, code), indent=2, sort_keys=True), file=out)
    return 2


def _local_disposable_preflight(
    provision: dict, *, current_environment_snapshot,
):
    """Require one exact locally stopped Multilogin profile before secrets."""

    if not _core._is_current_environment_snapshot(current_environment_snapshot):  # noqa: SLF001
        return "BINDINGS_UNAVAILABLE"
    if not isinstance(provision, dict):
        return "VENDOR_ERROR"
    profile_id = provision.get("profile_id")
    folder_id = provision.get("folder_id")
    if (
        provision.get("vendor") != "multilogin"
        or not isinstance(profile_id, str)
        or not isinstance(folder_id, str)
    ):
        return "VENDOR_ERROR"
    profile_id = profile_id.lower()
    folder_id = folder_id.lower()
    profile_matches = [
        row for row in current_environment_snapshot.rows
        if row["env_manager"] == "multilogin" and row["profile_id"] == profile_id
    ]
    if not profile_matches:
        return "PROFILE_NOT_FOUND"
    if (
        len(profile_matches) != 1
        or profile_matches[0]["folder_id"] != folder_id
    ):
        return "VENDOR_ERROR"
    return "BUSY_PROFILE" if profile_matches[0]["running"] else None


def atomic_private_json(doc: dict, path) -> None:
    """Write ``doc`` to ``path`` as private (0600) JSON, atomically.

    The single implementation (moved here from ``scripts/mas115_setup.py``
    per the REALM1-C1 spec §3.10): parent mkdir 0700, tmp file in the same
    directory, fchmod 0600, write/flush/fsync, ``os.replace``, chmod 0600,
    unlink the tmp file on any failure.
    """
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    tmp = tempfile.NamedTemporaryFile(
        dir=os.fspath(target.parent), prefix=f".{target.name}.", suffix=".tmp", delete=False,
    )
    try:
        os.fchmod(tmp.fileno(), 0o600)
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    try:
        os.replace(tmp.name, target)
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise


class _PeerStateRefusal(Exception):
    """Internal fixed-state refusal.  Its text is never emitted."""


@dataclass(frozen=True)
class _PrivateJsonSnapshot:
    path: Path
    document: dict
    raw: bytes
    sha256: str
    st_dev: int
    st_ino: int
    st_uid: int
    st_mode: int
    st_nlink: int


def _normalized_private_path(path) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = Path.cwd() / target
    return Path(os.path.abspath(os.fspath(target)))


def _open_private_parent(path, *, exclusive=False):
    """Open and lock one private, symlink-free parent directory."""
    target = _normalized_private_path(path)
    parent = target.parent
    parent_fd = None
    try:
        if os.path.realpath(parent) != os.path.abspath(parent):
            raise _PeerStateRefusal()
        before = os.stat(parent, follow_symlinks=False)
        if (
            not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) & 0o077
        ):
            raise _PeerStateRefusal()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(parent, flags)
        after = os.fstat(parent_fd)
        if (
            (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
            or not stat.S_ISDIR(after.st_mode)
            or after.st_uid != os.geteuid()
            or stat.S_IMODE(after.st_mode) & 0o077
        ):
            os.close(parent_fd)
            parent_fd = None
            raise _PeerStateRefusal()
        fcntl.flock(parent_fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        # The path may have been renamed/replaced while the advisory lock was
        # being acquired.  A descriptor for the old directory cannot confer
        # authority over the fixed path in the replacement directory.
        named_after_lock = os.stat(parent, follow_symlinks=False)
        if (
            (named_after_lock.st_dev, named_after_lock.st_ino)
            != (after.st_dev, after.st_ino)
            or not stat.S_ISDIR(named_after_lock.st_mode)
            or named_after_lock.st_uid != os.geteuid()
            or stat.S_IMODE(named_after_lock.st_mode) & 0o077
        ):
            raise _PeerStateRefusal()
        return target, parent_fd
    except (_PeerStateRefusal, OSError):
        if parent_fd is not None:
            try:
                os.close(parent_fd)
            except OSError:
                pass
        raise _PeerStateRefusal() from None


def _private_security_tuple(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IMODE(info.st_mode),
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _snapshot_created_private_fd(
    target: Path, parent_fd: int, leaf_fd: int, *, document: dict, raw: bytes,
):
    """Bind a just-created private record to its descriptor and fixed path.

    The caller holds the parent and leaf locks.  Validation is repeated after
    the directory durability barrier so a hard-link, rename, parent swap, or
    byte-identical replacement can only turn the operation into a refusal.
    """
    try:
        fcntl.flock(leaf_fd, fcntl.LOCK_EX)
        opened = os.fstat(leaf_fd)
        opened_security = _private_security_tuple(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or opened.st_size != len(raw)
            or len(raw) > _MAX_PEER_STATE_BYTES
        ):
            raise _PeerStateRefusal()
        readback = _read_private_fd(leaf_fd)
        after_read = os.fstat(leaf_fd)
        if readback != raw or _private_security_tuple(after_read) != opened_security:
            raise _PeerStateRefusal()
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if _private_security_tuple(named) != opened_security:
            raise _PeerStateRefusal()

        os.fsync(parent_fd)

        final_opened = os.fstat(leaf_fd)
        final_named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        parent_opened = os.fstat(parent_fd)
        parent_named = os.stat(target.parent, follow_symlinks=False)
        if (
            _private_security_tuple(final_opened) != opened_security
            or _private_security_tuple(final_named) != opened_security
            or (parent_named.st_dev, parent_named.st_ino)
            != (parent_opened.st_dev, parent_opened.st_ino)
            or not stat.S_ISDIR(parent_named.st_mode)
            or parent_named.st_uid != os.geteuid()
            or stat.S_IMODE(parent_named.st_mode) & 0o077
        ):
            raise _PeerStateRefusal()
        return _PrivateJsonSnapshot(
            path=target,
            document=dict(document),
            raw=readback,
            sha256=hashlib.sha256(readback).hexdigest(),
            st_dev=final_opened.st_dev,
            st_ino=final_opened.st_ino,
            st_uid=final_opened.st_uid,
            st_mode=stat.S_IMODE(final_opened.st_mode),
            st_nlink=final_opened.st_nlink,
        )
    except (OSError, _PeerStateRefusal):
        raise _PeerStateRefusal() from None


def _snapshot_from_parent(target: Path, parent_fd: int) -> _PrivateJsonSnapshot:
    name = target.name
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size > _MAX_PEER_STATE_BYTES
        ):
            raise _PeerStateRefusal()
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        leaf_fd = os.open(name, flags, dir_fd=parent_fd)
        try:
            fcntl.flock(leaf_fd, fcntl.LOCK_SH)
            opened = os.fstat(leaf_fd)
            stable_before = (
                before.st_dev, before.st_ino, before.st_uid,
                stat.S_IMODE(before.st_mode), before.st_nlink, before.st_size,
                before.st_mtime_ns, before.st_ctime_ns,
            )
            stable_opened = (
                opened.st_dev, opened.st_ino, opened.st_uid,
                stat.S_IMODE(opened.st_mode), opened.st_nlink, opened.st_size,
                opened.st_mtime_ns, opened.st_ctime_ns,
            )
            if (
                stable_opened != stable_before
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
            ):
                raise _PeerStateRefusal()
            chunks = []
            remaining = _MAX_PEER_STATE_BYTES + 1
            while remaining:
                chunk = os.read(leaf_fd, min(remaining, 4096))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > _MAX_PEER_STATE_BYTES:
                raise _PeerStateRefusal()
            after_read = os.fstat(leaf_fd)
            stable_after_read = (
                after_read.st_dev, after_read.st_ino, after_read.st_uid,
                stat.S_IMODE(after_read.st_mode), after_read.st_nlink,
                after_read.st_size, after_read.st_mtime_ns, after_read.st_ctime_ns,
            )
            if stable_after_read != stable_opened:
                raise _PeerStateRefusal()
        finally:
            os.close(leaf_fd)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        stable_named = (
            named.st_dev, named.st_ino, named.st_uid,
            stat.S_IMODE(named.st_mode), named.st_nlink, named.st_size,
            named.st_mtime_ns, named.st_ctime_ns,
        )
        if stable_named != stable_after_read:
            raise _PeerStateRefusal()
        def _closed_object(pairs):
            document = {}
            for key, value in pairs:
                if not isinstance(key, str) or key in document:
                    raise ValueError("duplicate or non-string JSON key")
                document[key] = value
            return document

        document = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_closed_object,
        )
        if not isinstance(document, dict):
            raise _PeerStateRefusal()
        return _PrivateJsonSnapshot(
            path=target,
            document=document,
            raw=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            st_dev=before.st_dev,
            st_ino=before.st_ino,
            st_uid=before.st_uid,
            st_mode=stat.S_IMODE(before.st_mode),
            st_nlink=before.st_nlink,
        )
    except (OSError, UnicodeError, ValueError, _PeerStateRefusal):
        raise _PeerStateRefusal() from None


def _read_private_json_snapshot(path) -> _PrivateJsonSnapshot:
    target, parent_fd = _open_private_parent(path)
    try:
        return _snapshot_from_parent(target, parent_fd)
    finally:
        os.close(parent_fd)


def _optional_private_json_snapshot(path):
    target = _normalized_private_path(path)
    try:
        target, parent_fd = _open_private_parent(target)
        try:
            try:
                os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            return _snapshot_from_parent(target, parent_fd)
        finally:
            os.close(parent_fd)
    except _PeerStateRefusal:
        raise


def _peer_genesis_witness_path(state_path) -> Path:
    """Return the one witness coordinate for a lifecycle coordinate.

    Production is deliberately pinned to :data:`PEER_GENESIS_WITNESS_PATH`.
    Tests use an equally deterministic sibling so the runtime surface never
    accepts a caller-selected witness path.
    """
    target = _normalized_private_path(state_path)
    if target == _normalized_private_path(PEER_INTENT_PATH):
        return _normalized_private_path(PEER_GENESIS_WITNESS_PATH)
    return target.with_name(f"{target.name}.genesis")


def _peer_genesis_witness_document(
    *, state_path, peer_provision_path, folder_id: str,
    anchor_profile_id: str, peer_name: str, generation: str,
    witness_dev=None, witness_ino=None, state_dev=None, state_ino=None,
    phase=_PEER_GENESIS_WITNESS_PENDING,
) -> dict:
    return {
        "schema": PEER_GENESIS_WITNESS_SCHEMA,
        "operation": PEER_OPERATION_KEY,
        "source_generation": PEER_SOURCE_GENERATION,
        "lifecycle_generation": generation,
        "state_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(state_path))
        ),
        "peer_provision_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(peer_provision_path))
        ),
        "folder_digest": _core.sha256_hex(folder_id),
        "anchor_profile_digest": _core.sha256_hex(anchor_profile_id),
        "peer_name_digest": _core.sha256_hex(peer_name),
        "witness_dev": witness_dev,
        "witness_ino": witness_ino,
        "state_dev": state_dev,
        "state_ino": state_ino,
        "phase": phase,
    }


def _peer_genesis_witness_shape_exact(document) -> bool:
    if not isinstance(document, dict) or set(document) != _PEER_GENESIS_WITNESS_KEYS:
        return False
    if (
        document.get("schema") != PEER_GENESIS_WITNESS_SCHEMA
        or document.get("operation") != PEER_OPERATION_KEY
        or document.get("source_generation") != PEER_SOURCE_GENERATION
        or not isinstance(document.get("lifecycle_generation"), str)
        or not re.fullmatch(r"[0-9a-f]{32,64}", document["lifecycle_generation"])
        or document.get("phase") not in (
            _PEER_GENESIS_WITNESS_PENDING,
            _PEER_GENESIS_WITNESS_BOUND,
        )
    ):
        return False
    for key in (
        "state_coordinate_digest", "peer_provision_coordinate_digest",
        "folder_digest", "anchor_profile_digest", "peer_name_digest",
    ):
        if not isinstance(document.get(key), str) or not _HEX64_RE.fullmatch(document[key]):
            return False
    for key in ("witness_dev", "witness_ino"):
        value = document.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    for key in ("state_dev", "state_ino"):
        value = document.get(key)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value < 0
        ):
            return False
    if document["phase"] == _PEER_GENESIS_WITNESS_PENDING:
        return document["state_dev"] is None and document["state_ino"] is None
    return document["state_dev"] is not None and document["state_ino"] is not None


def _peer_genesis_witness_snapshot(path):
    try:
        snapshot = _read_private_json_snapshot(path)
    except _PeerStateRefusal:
        return None
    return snapshot if (
        _peer_genesis_witness_shape_exact(snapshot.document)
        and snapshot.document["witness_dev"] == snapshot.st_dev
        and snapshot.document["witness_ino"] == snapshot.st_ino
    ) else None


def _peer_genesis_witness_matches_authority(
    snapshot, *, state_path, peer_provision_path, folder_id: str,
    anchor_profile_id: str, peer_name: str, generation: str,
) -> bool:
    if snapshot is None or not _peer_genesis_witness_shape_exact(snapshot.document):
        return False
    expected = _peer_genesis_witness_document(
        state_path=state_path,
        peer_provision_path=peer_provision_path,
        folder_id=folder_id,
        anchor_profile_id=anchor_profile_id,
        peer_name=peer_name,
        generation=generation,
        witness_dev=snapshot.st_dev,
        witness_ino=snapshot.st_ino,
        state_dev=snapshot.document.get("state_dev"),
        state_ino=snapshot.document.get("state_ino"),
        phase=snapshot.document.get("phase"),
    )
    return snapshot.document == expected


def _peer_state_shape_exact(document: dict) -> bool:
    if not isinstance(document, dict) or set(document) != _PEER_STATE_KEYS:
        return False
    nullable_digests = (
        "peer_profile_digest", "response_profile_digest", "peer_provision_digest",
        "ownership_fact_digest",
    )
    if (
        document.get("schema") != PEER_INTENT_SCHEMA
        or document.get("operation") != PEER_OPERATION_KEY
        or not isinstance(document.get("generation"), str)
        or not re.fullmatch(r"[0-9a-f]{32,64}", document["generation"])
        or not isinstance(document.get("peer_name"), str)
        or not document["peer_name"].startswith(_PEER_NAME_PREFIX)
        or document.get("browser_type") != _PEER_BROWSER_TYPE
        or document.get("os_type") != _PEER_OS_TYPE
        or document.get("phase") not in _PEER_PHASES
        or document.get("ownership_observed_at") is not None
        and not isinstance(document.get("ownership_observed_at"), str)
    ):
        return False
    for key in (
        "folder_digest", "anchor_profile_digest",
        "peer_provision_coordinate_digest", "genesis_witness_coordinate_digest",
    ):
        if not isinstance(document.get(key), str) or not _HEX64_RE.fullmatch(document[key]):
            return False
    for key in nullable_digests:
        value = document.get(key)
        if value is not None and (not isinstance(value, str) or not _HEX64_RE.fullmatch(value)):
            return False
    for key in (
        "state_dev", "state_ino", "genesis_witness_dev", "genesis_witness_ino",
    ):
        value = document.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    for key in ("peer_provision_dev", "peer_provision_ino"):
        value = document.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            return False
    phase = document["phase"]
    if phase in (
        PEER_PHASE_INITIALIZED,
        PEER_PHASE_CREATE_CLAIMED,
        PEER_PHASE_CREATE_AUTH_REJECTED,
        PEER_PHASE_CREATE_RESPONSE_OBSERVED,
    ):
        if document["peer_profile_digest"] is not None:
            return False
    if phase in (
        PEER_PHASE_INITIALIZED,
        PEER_PHASE_CREATE_CLAIMED,
        PEER_PHASE_CREATE_AUTH_REJECTED,
    ) and (
        document["response_profile_digest"] is not None
    ):
        return False
    if (
        phase == PEER_PHASE_CREATE_RESPONSE_OBSERVED
        and document["response_profile_digest"] is None
    ):
        return False
    if phase in (
        PEER_PHASE_PROFILE_STOPPED, PEER_PHASE_PROVISION_COMMITTED,
        PEER_PHASE_REMOVE_DISPATCHED, PEER_PHASE_ROLLBACK_VERIFIED,
    ) and document["peer_profile_digest"] is None:
        return False
    if phase in (
        PEER_PHASE_INITIALIZED,
        PEER_PHASE_CREATE_CLAIMED, PEER_PHASE_CREATE_AUTH_REJECTED,
        PEER_PHASE_CREATE_RESPONSE_OBSERVED,
        PEER_PHASE_PROFILE_STOPPED,
    ) and any(document[key] is not None for key in (
        "peer_provision_digest", "peer_provision_dev", "peer_provision_ino",
    )):
        return False
    if phase in (
        PEER_PHASE_PROVISION_COMMITTED, PEER_PHASE_REMOVE_DISPATCHED,
        PEER_PHASE_ROLLBACK_VERIFIED,
    ) and any(document[key] is None for key in (
        "peer_provision_digest", "peer_provision_dev", "peer_provision_ino",
    )):
        return False
    if phase not in (PEER_PHASE_REMOVE_DISPATCHED, PEER_PHASE_ROLLBACK_VERIFIED):
        if document["ownership_fact_digest"] is not None or document["ownership_observed_at"] is not None:
            return False
    elif document["ownership_fact_digest"] is None or document["ownership_observed_at"] is None:
        return False
    if (
        document["response_profile_digest"] is not None
        and document["peer_profile_digest"] is not None
        and document["response_profile_digest"] != document["peer_profile_digest"]
    ):
        return False
    return True


def _peer_authority_document(
    *, folder_id: str, anchor_profile_id: str, peer_name: str,
    peer_provision_path, generation: str, state_dev=None, state_ino=None,
    genesis_witness_path=None, genesis_witness_dev=None,
    genesis_witness_ino=None,
    phase=PEER_PHASE_INITIALIZED,
) -> dict:
    genesis_witness_path = genesis_witness_path or PEER_GENESIS_WITNESS_PATH
    return {
        "schema": PEER_INTENT_SCHEMA,
        "operation": PEER_OPERATION_KEY,
        "generation": generation,
        "folder_digest": _core.sha256_hex(folder_id),
        "anchor_profile_digest": _core.sha256_hex(anchor_profile_id),
        "browser_type": _PEER_BROWSER_TYPE,
        "os_type": _PEER_OS_TYPE,
        "peer_name": peer_name,
        "state_dev": state_dev,
        "state_ino": state_ino,
        "genesis_witness_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(genesis_witness_path))
        ),
        "genesis_witness_dev": genesis_witness_dev,
        "genesis_witness_ino": genesis_witness_ino,
        "peer_profile_digest": None,
        "peer_provision_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(peer_provision_path))
        ),
        "peer_provision_digest": None,
        "peer_provision_dev": None,
        "peer_provision_ino": None,
        "phase": phase,
        "response_profile_digest": None,
        "ownership_fact_digest": None,
        "ownership_observed_at": None,
    }


def _state_matches_authority(
    snapshot, *, folder_id: str, anchor_profile_id: str, peer_name: str,
    peer_provision_path, generation=None,
) -> bool:
    if snapshot is None or not _peer_state_shape_exact(snapshot.document):
        return False
    document = snapshot.document
    expected = _peer_authority_document(
        folder_id=folder_id,
        anchor_profile_id=anchor_profile_id,
        peer_name=peer_name,
        peer_provision_path=peer_provision_path,
        generation=generation or PEER_SOURCE_GENERATION,
        genesis_witness_path=_peer_genesis_witness_path(snapshot.path),
        genesis_witness_dev=document.get("genesis_witness_dev"),
        genesis_witness_ino=document.get("genesis_witness_ino"),
    )
    static_keys = (
        "schema", "operation", "generation", "folder_digest",
        "anchor_profile_digest", "browser_type", "os_type", "peer_name",
        "genesis_witness_coordinate_digest", "genesis_witness_dev",
        "genesis_witness_ino",
        "peer_provision_coordinate_digest",
    )
    return (
        all(document[key] == expected[key] for key in static_keys)
        and document["state_dev"] == snapshot.st_dev
        and document["state_ino"] == snapshot.st_ino
    )


def _canonical_private_bytes(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _create_self_bound_private_record(
    target: Path, parent_fd: int, document: dict, *, dev_key: str,
    ino_key: str, validator,
):
    """O_EXCL-create one private record whose bytes bind its own inode."""
    leaf_fd = None
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        leaf_fd = os.open(target.name, flags, 0o600, dir_fd=parent_fd)
        os.fchmod(leaf_fd, 0o600)
        opened = os.fstat(leaf_fd)
        candidate = dict(document)
        candidate[dev_key] = opened.st_dev
        candidate[ino_key] = opened.st_ino
        if not validator(candidate):
            raise _PeerStateRefusal()
        raw = _canonical_private_bytes(candidate)
        _write_private_fd(leaf_fd, raw)
        return _snapshot_created_private_fd(
            target,
            parent_fd,
            leaf_fd,
            document=candidate,
            raw=raw,
        )
    except (FileExistsError, OSError, _PeerStateRefusal):
        return None
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)


def _rewrite_private_record_in_parent(
    target: Path, parent_fd: int, *, expected, next_document: dict, validator,
):
    """CAS-rewrite an exact private inode while its parent lock is held."""
    if not isinstance(expected, _PrivateJsonSnapshot) or not validator(next_document):
        return None
    leaf_fd = None
    try:
        current = _snapshot_from_parent(target, parent_fd)
        if not _same_snapshot(current, expected):
            return None
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        leaf_fd = os.open(target.name, flags, dir_fd=parent_fd)
        fcntl.flock(leaf_fd, fcntl.LOCK_EX)
        opened = os.fstat(leaf_fd)
        if (
            (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or _read_private_fd(leaf_fd) != expected.raw
        ):
            return None
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            return None
        next_raw = _canonical_private_bytes(next_document)
        _write_private_fd(leaf_fd, next_raw)
        return _snapshot_created_private_fd(
            target,
            parent_fd,
            leaf_fd,
            document=next_document,
            raw=next_raw,
        )
    except (_PeerStateRefusal, OSError):
        return None
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)


def _initialize_peer_lifecycle_state_in_parent(
    target: Path, parent_fd: int, *, folder_id: str,
    anchor_profile_id: str, peer_name: str, peer_provision_path=None,
    generation=None, snapshot_sink=None,
) -> str:
    """Create/reconcile genesis while the caller holds its parent lock."""
    target = _normalized_private_path(target)
    peer_provision_path = peer_provision_path or PEER_PROVISION_PATH
    generation = generation or PEER_SOURCE_GENERATION
    witness_path = _peer_genesis_witness_path(target)
    try:
        provision_target = _normalized_private_path(peer_provision_path)
        witness_target = _normalized_private_path(witness_path)
        if (
            provision_target.parent != target.parent
            or witness_target.parent != target.parent
            or witness_target == target
            or witness_target == provision_target
        ):
            return REFUSED
        try:
            os.stat(provision_target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            # A create/re-arm can never coexist with any provision entry.
            return REFUSED

        def _named_snapshot_or_none(named_target):
            try:
                os.stat(named_target.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            return _snapshot_from_parent(named_target, parent_fd)

        state = _named_snapshot_or_none(target)
        witness = _named_snapshot_or_none(witness_target)

        created_state = False
        if witness is None:
            # A lifecycle without its older genesis witness is always foreign.
            if state is not None:
                return REFUSED
            pending = _peer_genesis_witness_document(
                state_path=target,
                peer_provision_path=provision_target,
                folder_id=folder_id,
                anchor_profile_id=anchor_profile_id,
                peer_name=peer_name,
                generation=generation,
            )
            witness = _create_self_bound_private_record(
                witness_target,
                parent_fd,
                pending,
                dev_key="witness_dev",
                ino_key="witness_ino",
                validator=_peer_genesis_witness_shape_exact,
            )
            if witness is None:
                return REFUSED

        if not _peer_genesis_witness_matches_authority(
            witness,
            state_path=target,
            peer_provision_path=provision_target,
            folder_id=folder_id,
            anchor_profile_id=anchor_profile_id,
            peer_name=peer_name,
            generation=generation,
        ):
            return REFUSED

        if state is None:
            # Only a never-bound PENDING witness can recover a crash between
            # witness creation and lifecycle creation.
            if witness.document.get("phase") != _PEER_GENESIS_WITNESS_PENDING:
                return REFUSED
            candidate = _peer_authority_document(
                folder_id=folder_id,
                anchor_profile_id=anchor_profile_id,
                peer_name=peer_name,
                peer_provision_path=provision_target,
                generation=generation,
                genesis_witness_path=witness_target,
                genesis_witness_dev=witness.st_dev,
                genesis_witness_ino=witness.st_ino,
            )
            state = _create_self_bound_private_record(
                target,
                parent_fd,
                candidate,
                dev_key="state_dev",
                ino_key="state_ino",
                validator=_peer_state_shape_exact,
            )
            if state is None:
                return REFUSED
            created_state = True
        elif (
            not _state_matches_authority(
                state,
                folder_id=folder_id,
                anchor_profile_id=anchor_profile_id,
                peer_name=peer_name,
                peer_provision_path=provision_target,
                generation=generation,
            )
            or state.document.get("phase") != PEER_PHASE_INITIALIZED
            or state.document.get("genesis_witness_dev") != witness.st_dev
            or state.document.get("genesis_witness_ino") != witness.st_ino
        ):
            return REFUSED

        if witness.document.get("phase") == _PEER_GENESIS_WITNESS_PENDING:
            bound = dict(witness.document)
            bound["state_dev"] = state.st_dev
            bound["state_ino"] = state.st_ino
            bound["phase"] = _PEER_GENESIS_WITNESS_BOUND
            witness = _rewrite_private_record_in_parent(
                witness_target,
                parent_fd,
                expected=witness,
                next_document=bound,
                validator=_peer_genesis_witness_shape_exact,
            )
            if witness is None:
                return REFUSED

        if (
            witness.document.get("phase") != _PEER_GENESIS_WITNESS_BOUND
            or witness.document.get("state_dev") != state.st_dev
            or witness.document.get("state_ino") != state.st_ino
            or state.document.get("genesis_witness_dev") != witness.st_dev
            or state.document.get("genesis_witness_ino") != witness.st_ino
        ):
            return REFUSED
        if isinstance(snapshot_sink, list):
            snapshot_sink.append(state)
        return CREATED_THIS_CALL if created_state else EXISTING_EXACT
    except (_PeerStateRefusal, OSError):
        return REFUSED


def initialize_peer_lifecycle_state(
    path, *, folder_id: str, anchor_profile_id: str, peer_name: str,
    peer_provision_path=None, generation=None, snapshot_sink=None,
) -> str:
    """Create the inert lifecycle genesis before create can be authorized.

    This is a setup operation, not a create-operation fallback.  The runtime
    create/rollback entrypoints never call it.  Once any exact lifecycle inode
    exists it may only be accepted while still INITIALIZED; a missing inode is
    therefore not reinterpreted as virgin state after a dispatch.
    """
    try:
        target, parent_fd = _open_private_parent(path, exclusive=True)
    except _PeerStateRefusal:
        return REFUSED
    try:
        return _initialize_peer_lifecycle_state_in_parent(
            target,
            parent_fd,
            folder_id=folder_id,
            anchor_profile_id=anchor_profile_id,
            peer_name=peer_name,
            peer_provision_path=peer_provision_path,
            generation=generation,
            snapshot_sink=snapshot_sink,
        )
    finally:
        os.close(parent_fd)


def _peer_bootstrap_fence_path(state_path) -> Path:
    """Return the one bootstrap fence coordinate for a lifecycle coordinate."""
    target = _normalized_private_path(state_path)
    if target == _normalized_private_path(PEER_INTENT_PATH):
        return _normalized_private_path(PEER_BOOTSTRAP_FENCE_PATH)
    return target.with_name(f"{target.name}.bootstrap")


def _peer_bootstrap_fence_document(
    *, anchor_path, state_path, witness_path, peer_provision_path,
    anchor: _PrivateJsonSnapshot, fence_dev=None, fence_ino=None,
    phase=PEER_BOOTSTRAP_PHASE_PENDING, state=None, witness=None,
) -> dict:
    return {
        "schema": PEER_BOOTSTRAP_FENCE_SCHEMA,
        "operation": PEER_BOOTSTRAP_OPERATION_KEY,
        "peer_operation": PEER_OPERATION_KEY,
        "source_generation": PEER_SOURCE_GENERATION,
        "anchor_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(anchor_path))
        ),
        "state_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(state_path))
        ),
        "genesis_witness_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(witness_path))
        ),
        "peer_provision_coordinate_digest": _core.sha256_hex(
            os.fspath(_normalized_private_path(peer_provision_path))
        ),
        "anchor_document_digest": anchor.sha256,
        "anchor_dev": anchor.st_dev,
        "anchor_ino": anchor.st_ino,
        "lifecycle_generation": PEER_SOURCE_GENERATION,
        "fence_dev": fence_dev,
        "fence_ino": fence_ino,
        "phase": phase,
        "state_document_digest": None if state is None else state.sha256,
        "state_dev": None if state is None else state.st_dev,
        "state_ino": None if state is None else state.st_ino,
        "witness_document_digest": None if witness is None else witness.sha256,
        "witness_dev": None if witness is None else witness.st_dev,
        "witness_ino": None if witness is None else witness.st_ino,
    }


def _peer_bootstrap_fence_shape_exact(document) -> bool:
    if not isinstance(document, dict) or set(document) != _PEER_BOOTSTRAP_FENCE_KEYS:
        return False
    if (
        document.get("schema") != PEER_BOOTSTRAP_FENCE_SCHEMA
        or document.get("operation") != PEER_BOOTSTRAP_OPERATION_KEY
        or document.get("peer_operation") != PEER_OPERATION_KEY
        or document.get("source_generation") != PEER_SOURCE_GENERATION
        or document.get("lifecycle_generation") != PEER_SOURCE_GENERATION
        or document.get("phase") not in (
            PEER_BOOTSTRAP_PHASE_PENDING, PEER_BOOTSTRAP_PHASE_COMPLETE,
        )
    ):
        return False
    for key in (
        "anchor_coordinate_digest", "state_coordinate_digest",
        "genesis_witness_coordinate_digest", "peer_provision_coordinate_digest",
        "anchor_document_digest",
    ):
        if not isinstance(document.get(key), str) or _HEX64_RE.fullmatch(document[key]) is None:
            return False
    for key in ("anchor_dev", "anchor_ino", "fence_dev", "fence_ino"):
        value = document.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    completion_keys = (
        "state_document_digest", "state_dev", "state_ino",
        "witness_document_digest", "witness_dev", "witness_ino",
    )
    if document["phase"] == PEER_BOOTSTRAP_PHASE_PENDING:
        return all(document[key] is None for key in completion_keys)
    for key in ("state_document_digest", "witness_document_digest"):
        if not isinstance(document.get(key), str) or _HEX64_RE.fullmatch(document[key]) is None:
            return False
    for key in ("state_dev", "state_ino", "witness_dev", "witness_ino"):
        value = document.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return False
    return True


def _peer_bootstrap_fence_snapshot(path):
    """Read one exact self-bound fence without interpreting absence as virgin."""
    try:
        snapshot = _read_private_json_snapshot(path)
    except _PeerStateRefusal:
        return None
    return snapshot if (
        _peer_bootstrap_fence_shape_exact(snapshot.document)
        and snapshot.document["fence_dev"] == snapshot.st_dev
        and snapshot.document["fence_ino"] == snapshot.st_ino
    ) else None


def _peer_bootstrap_fence_matches(
    fence, *, anchor_path, state_path, witness_path, peer_provision_path,
    anchor, state=None, witness=None,
) -> bool:
    if fence is None or not _peer_bootstrap_fence_shape_exact(fence.document):
        return False
    expected = _peer_bootstrap_fence_document(
        anchor_path=anchor_path,
        state_path=state_path,
        witness_path=witness_path,
        peer_provision_path=peer_provision_path,
        anchor=anchor,
        fence_dev=fence.st_dev,
        fence_ino=fence.st_ino,
        phase=fence.document["phase"],
        state=state,
        witness=witness,
    )
    return fence.document == expected


def _peer_bootstrap_anchor_shape_exact(document) -> bool:
    """Accept only the canonical existing v3 Multilogin Mimic anchor."""
    return (
        _peer_provision_shape_exact(document)
        and document.get("profile_id")
        == _canonical_multilogin_profile_id(document.get("profile_id"))
        and document.get("folder_id")
        == _canonical_multilogin_profile_id(document.get("folder_id"))
    )


def _read_bounded_private_fd(leaf_fd: int, *, max_bytes: int) -> bytes:
    os.lseek(leaf_fd, 0, os.SEEK_SET)
    chunks = []
    remaining = max_bytes + 1
    while remaining:
        chunk = os.read(leaf_fd, min(remaining, 4096))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > max_bytes:
        raise _PeerStateRefusal()
    return raw


def _closed_json_object(raw: bytes) -> dict:
    def _closed_object(pairs):
        document = {}
        for key, value in pairs:
            if not isinstance(key, str) or key in document:
                raise ValueError("duplicate or non-string JSON key")
            document[key] = value
        return document

    document = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_closed_object,
    )
    if not isinstance(document, dict):
        raise _PeerStateRefusal()
    return document


def _open_held_private_json(target: Path, parent_fd: int, *, max_bytes: int):
    """Open, parse and retain one exact private file through a no-follow fd."""
    leaf_fd = None
    try:
        before = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or before.st_size > max_bytes
        ):
            raise _PeerStateRefusal()
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        leaf_fd = os.open(target.name, flags, dir_fd=parent_fd)
        fcntl.flock(leaf_fd, fcntl.LOCK_SH)
        opened = os.fstat(leaf_fd)
        security = _private_security_tuple(opened)
        if security != _private_security_tuple(before):
            raise _PeerStateRefusal()
        raw = _read_bounded_private_fd(leaf_fd, max_bytes=max_bytes)
        document = _closed_json_object(raw)
        after_read = os.fstat(leaf_fd)
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _private_security_tuple(after_read) != security
            or _private_security_tuple(named) != security
        ):
            raise _PeerStateRefusal()
        return leaf_fd, raw, document, security
    except (OSError, UnicodeError, ValueError, _PeerStateRefusal):
        if leaf_fd is not None:
            try:
                os.close(leaf_fd)
            except OSError:
                pass
        raise _PeerStateRefusal() from None


def _canonical_reduced_local_census(census):
    """Return the one canonical strict snapshot or refuse the whole census."""

    snapshot = _core._seal_current_environment_snapshot(census)  # noqa: SLF001
    if snapshot is None:
        raise _PeerStateRefusal()
    return snapshot


def _validate_peer_bootstrap_evidence_documents(
    anchor_document, bindings_document, census, *, now,
) -> str:
    if (
        not _peer_bootstrap_anchor_shape_exact(anchor_document)
        or _surface_bindings.validate_bindings_document(bindings_document)
    ):
        raise _PeerStateRefusal()
    snapshot = _canonical_reduced_local_census(census)
    if _local_disposable_preflight(
        anchor_document, current_environment_snapshot=snapshot,
    ) is not None:
        raise _PeerStateRefusal()
    if _core._current_chairman_profile_census(  # noqa: SLF001
        bindings_document,
        now=now,
        candidate_profile_id=anchor_document["profile_id"],
        candidate_vendor=anchor_document["vendor"],
        candidate_folder_id=anchor_document["folder_id"],
        current_environment_snapshot=snapshot,
    ) != "clear":
        raise _PeerStateRefusal()
    return snapshot.digest


def _mint_peer_bootstrap_evidence(
    *, operation, anchor_path, bindings_path, census_loader, now,
):
    """Mint one exact post-confirmation proof while retaining both source fds."""
    anchor_fd = None
    bindings_fd = None
    parent_fd = None
    try:
        if operation != PEER_BOOTSTRAP_OPERATION_KEY or not callable(census_loader):
            raise _PeerStateRefusal()
        anchor_target = _normalized_private_path(anchor_path)
        bindings_target = _normalized_private_path(bindings_path)
        if (
            anchor_target == bindings_target
            or anchor_target.parent != bindings_target.parent
        ):
            raise _PeerStateRefusal()
        anchor_target, parent_fd = _open_private_parent(anchor_target)
        anchor_fd, anchor_raw, anchor_document, anchor_security = (
            _open_held_private_json(
                anchor_target, parent_fd, max_bytes=_MAX_PEER_STATE_BYTES,
            )
        )
        bindings_fd, bindings_raw, bindings_document, bindings_security = (
            _open_held_private_json(
                bindings_target,
                parent_fd,
                max_bytes=_surface_bindings._MAX_BYTES,  # noqa: SLF001
            )
        )
        census_digest = _validate_peer_bootstrap_evidence_documents(
            anchor_document,
            bindings_document,
            census_loader(),
            now=now,
        )
        evidence = _PeerBootstrapEvidence(
            _PEER_BOOTSTRAP_EVIDENCE_SEAL,
            operation=operation,
            generation=PEER_SOURCE_GENERATION,
            anchor_path=anchor_target,
            anchor_fd=anchor_fd,
            anchor_raw=anchor_raw,
            anchor_security=anchor_security,
            bindings_path=bindings_target,
            bindings_fd=bindings_fd,
            bindings_raw=bindings_raw,
            bindings_security=bindings_security,
            census_digest=census_digest,
        )
        anchor_fd = None
        bindings_fd = None
        return evidence
    except Exception:  # noqa: BLE001 — every failed proof is a closed refusal
        return None
    finally:
        for descriptor in (bindings_fd, anchor_fd, parent_fd):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass


def _held_bootstrap_snapshot(
    evidence, *, anchor_target, bindings_target, parent_fd, census_loader, now,
):
    """Revalidate held bytes, named paths and fresh census in one lock epoch."""
    if (
        not isinstance(evidence, _PeerBootstrapEvidence)
        or evidence._seal is not _PEER_BOOTSTRAP_EVIDENCE_SEAL
        or evidence._operation != PEER_BOOTSTRAP_OPERATION_KEY
        or evidence._generation != PEER_SOURCE_GENERATION
        or evidence._mint_pid != os.getpid()
        or evidence._anchor_path != anchor_target
        or evidence._bindings_path != bindings_target
    ):
        raise _PeerStateRefusal()

    documents = []
    for target, descriptor, expected_raw, expected_sha256, expected_security, limit in (
        (
            anchor_target,
            evidence._anchor_fd,
            evidence._anchor_raw,
            evidence._anchor_sha256,
            evidence._anchor_security,
            _MAX_PEER_STATE_BYTES,
        ),
        (
            bindings_target,
            evidence._bindings_fd,
            evidence._bindings_raw,
            evidence._bindings_sha256,
            evidence._bindings_security,
            _surface_bindings._MAX_BYTES,  # noqa: SLF001
        ),
    ):
        opened = os.fstat(descriptor)
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _private_security_tuple(opened) != expected_security
            or _private_security_tuple(named) != expected_security
        ):
            raise _PeerStateRefusal()
        raw = _read_bounded_private_fd(descriptor, max_bytes=limit)
        after_read = os.fstat(descriptor)
        if (
            raw != expected_raw
            or hashlib.sha256(raw).hexdigest() != expected_sha256
            or _private_security_tuple(after_read) != expected_security
        ):
            raise _PeerStateRefusal()
        documents.append(_closed_json_object(raw))

    anchor_document, bindings_document = documents
    census_digest = _validate_peer_bootstrap_evidence_documents(
        anchor_document,
        bindings_document,
        census_loader(),
        now=now,
    )
    if census_digest != evidence._census_digest:
        raise _PeerStateRefusal()
    security = evidence._anchor_security
    return _PrivateJsonSnapshot(
        path=anchor_target,
        document=anchor_document,
        raw=evidence._anchor_raw,
        sha256=evidence._anchor_sha256,
        st_dev=security[0],
        st_ino=security[1],
        st_uid=security[2],
        st_mode=security[3],
        st_nlink=security[4],
    )


def _peer_bootstrap_complete_matches(
    fence, *, anchor_path, state_path, witness_path, peer_provision_path,
    anchor, state, witness,
) -> bool:
    if (
        state is None
        or witness is None
        or fence.document.get("phase") != PEER_BOOTSTRAP_PHASE_COMPLETE
        or not _peer_bootstrap_fence_matches(
            fence,
            anchor_path=anchor_path,
            state_path=state_path,
            witness_path=witness_path,
            peer_provision_path=peer_provision_path,
            anchor=anchor,
            state=state,
            witness=witness,
        )
        or state.document.get("phase") != PEER_PHASE_INITIALIZED
        or not _state_matches_authority(
            state,
            folder_id=anchor.document["folder_id"],
            anchor_profile_id=anchor.document["profile_id"],
            peer_name=peer_profile_name(
                anchor.document["folder_id"], anchor.document["profile_id"],
            ),
            peer_provision_path=peer_provision_path,
            generation=PEER_SOURCE_GENERATION,
        )
        or witness.document.get("phase") != _PEER_GENESIS_WITNESS_BOUND
        or not _peer_genesis_witness_matches_authority(
            witness,
            state_path=state_path,
            peer_provision_path=peer_provision_path,
            folder_id=anchor.document["folder_id"],
            anchor_profile_id=anchor.document["profile_id"],
            peer_name=peer_profile_name(
                anchor.document["folder_id"], anchor.document["profile_id"],
            ),
            generation=PEER_SOURCE_GENERATION,
        )
    ):
        return False
    return (
        state.document.get("genesis_witness_dev") == witness.st_dev
        and state.document.get("genesis_witness_ino") == witness.st_ino
        and witness.document.get("state_dev") == state.st_dev
        and witness.document.get("state_ino") == state.st_ino
    )


def _bootstrap_peer_lifecycle_for_existing_anchor(
    *, authorization, anchor_path, bindings_path, census_loader, now,
    state_path, peer_provision_path, bootstrap_fence_path,
) -> str:
    """Bootstrap the one historical v3 anchor under a monotonic fence.

    This seam performs private local file I/O only.  It never reads a secret,
    constructs an HTTP client, invokes a vendor API, or creates a profile.
    PENDING can recover only its exact crash prefix; COMPLETE is read-only and
    refuses any missing, replaced, linked, malformed, or mismatched record.
    """
    evidence = (
        authorization
        if isinstance(authorization, _PeerBootstrapEvidence)
        else None
    )
    if evidence is None:
        return REFUSED
    parent_fd = None
    try:
        anchor_target = _normalized_private_path(anchor_path)
        bindings_target = _normalized_private_path(bindings_path)
        state_target = _normalized_private_path(state_path)
        witness_target = _peer_genesis_witness_path(state_target)
        provision_target = _normalized_private_path(peer_provision_path)
        fence_target = _normalized_private_path(bootstrap_fence_path)
        coordinates = (
            anchor_target, bindings_target, state_target, witness_target,
            provision_target, fence_target,
        )
        if (
            len(set(coordinates)) != len(coordinates)
            or len({target.parent for target in coordinates}) != 1
        ):
            return REFUSED
        anchor_target, parent_fd = _open_private_parent(
            anchor_target, exclusive=True,
        )
        if not evidence._begin_consume():
            return REFUSED
        anchor = _held_bootstrap_snapshot(
            evidence,
            anchor_target=anchor_target,
            bindings_target=bindings_target,
            parent_fd=parent_fd,
            census_loader=census_loader,
            now=now,
        )

        def _named_snapshot_or_none(target):
            try:
                os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return None
            return _snapshot_from_parent(target, parent_fd)

        state = _named_snapshot_or_none(state_target)
        witness = _named_snapshot_or_none(witness_target)
        provision = _named_snapshot_or_none(provision_target)
        fence = _named_snapshot_or_none(fence_target)
        if (
            not _peer_bootstrap_anchor_shape_exact(anchor.document)
            or provision is not None
        ):
            return REFUSED

        if fence is not None:
            if (
                not _peer_bootstrap_fence_shape_exact(fence.document)
                or fence.document.get("fence_dev") != fence.st_dev
                or fence.document.get("fence_ino") != fence.st_ino
            ):
                return REFUSED
            if fence.document.get("phase") == PEER_BOOTSTRAP_PHASE_COMPLETE:
                return EXISTING_EXACT if _peer_bootstrap_complete_matches(
                    fence,
                    anchor_path=anchor_target,
                    state_path=state_target,
                    witness_path=witness_target,
                    peer_provision_path=provision_target,
                    anchor=anchor,
                    state=state,
                    witness=witness,
                ) else REFUSED
            if not _peer_bootstrap_fence_matches(
                fence,
                anchor_path=anchor_target,
                state_path=state_target,
                witness_path=witness_target,
                peer_provision_path=provision_target,
                anchor=anchor,
            ):
                return REFUSED
            created_fence = False
        else:
            if state is not None or witness is not None:
                return REFUSED
            pending = _peer_bootstrap_fence_document(
                anchor_path=anchor_target,
                state_path=state_target,
                witness_path=witness_target,
                peer_provision_path=provision_target,
                anchor=anchor,
            )
            fence = _create_self_bound_private_record(
                fence_target,
                parent_fd,
                pending,
                dev_key="fence_dev",
                ino_key="fence_ino",
                validator=_peer_bootstrap_fence_shape_exact,
            )
            if fence is None:
                return REFUSED
            created_fence = True

        outcome = _initialize_peer_lifecycle_state_in_parent(
            state_target,
            parent_fd,
            folder_id=anchor.document["folder_id"],
            anchor_profile_id=anchor.document["profile_id"],
            peer_name=peer_profile_name(
                anchor.document["folder_id"], anchor.document["profile_id"],
            ),
            peer_provision_path=provision_target,
            generation=PEER_SOURCE_GENERATION,
        )
        if outcome not in (CREATED_THIS_CALL, EXISTING_EXACT):
            return REFUSED
        current_anchor = _named_snapshot_or_none(anchor_target)
        state = _named_snapshot_or_none(state_target)
        witness = _named_snapshot_or_none(witness_target)
        if (
            current_anchor is None
            or not _same_snapshot(current_anchor, anchor)
            or state is None
            or witness is None
        ):
            return REFUSED
        complete = _peer_bootstrap_fence_document(
            anchor_path=anchor_target,
            state_path=state_target,
            witness_path=witness_target,
            peer_provision_path=provision_target,
            anchor=anchor,
            fence_dev=fence.st_dev,
            fence_ino=fence.st_ino,
            phase=PEER_BOOTSTRAP_PHASE_COMPLETE,
            state=state,
            witness=witness,
        )
        completed = _rewrite_private_record_in_parent(
            fence_target,
            parent_fd,
            expected=fence,
            next_document=complete,
            validator=_peer_bootstrap_fence_shape_exact,
        )
        if completed is None:
            # A crash seam may have committed the bytes but lost the return.
            # Never claim that ambiguous call; the next invocation reconciles.
            return REFUSED
        if not _peer_bootstrap_complete_matches(
            completed,
            anchor_path=anchor_target,
            state_path=state_target,
            witness_path=witness_target,
            peer_provision_path=provision_target,
            anchor=anchor,
            state=state,
            witness=witness,
        ):
            return REFUSED
        return CREATED_THIS_CALL if created_fence else EXISTING_EXACT
    except Exception:  # noqa: BLE001 — no local proof failure may escape
        return REFUSED
    finally:
        evidence._close_held_descriptors()
        if parent_fd is not None:
            try:
                os.close(parent_fd)
            except OSError:
                pass


def _coordinator_local_census():
    from . import chatgpt

    return chatgpt._strict_list_local_environments()  # noqa: SLF001


def mint_coordinator_peer_bootstrap_evidence():
    """Mint the fixed-coordinate proof after the operator's exact phrase."""
    return _mint_peer_bootstrap_evidence(
        operation=PEER_BOOTSTRAP_OPERATION_KEY,
        anchor_path=_core.DEFAULT_PROVISION_PATH,
        bindings_path=_surface_bindings.DEFAULT_PATH,
        census_loader=_coordinator_local_census,
        now=datetime.now(timezone.utc),
    )


def run_coordinator_peer_bootstrap(*, authorization) -> str:
    """Consume one proof in the fixed-coordinate local bootstrap seam."""
    return _bootstrap_peer_lifecycle_for_existing_anchor(
        authorization=authorization,
        anchor_path=_core.DEFAULT_PROVISION_PATH,
        bindings_path=_surface_bindings.DEFAULT_PATH,
        census_loader=_coordinator_local_census,
        now=datetime.now(timezone.utc),
        state_path=PEER_INTENT_PATH,
        peer_provision_path=PEER_PROVISION_PATH,
        bootstrap_fence_path=_peer_bootstrap_fence_path(PEER_INTENT_PATH),
    )


def _commit_peer_intent(
    path, *, folder_id: str, anchor_profile_id: str, peer_name: str,
    peer_provision_path=None, generation=None, snapshot_sink=None,
) -> str:
    """CAS the pre-provisioned genesis inode into the one create claim."""
    peer_provision_path = peer_provision_path or PEER_PROVISION_PATH
    generation = generation or PEER_SOURCE_GENERATION
    try:
        existing, provision = _preflight_peer_paths(
            operation="create-peer-profile",
            state_path=path,
            provision_path=peer_provision_path,
            generation=generation,
        )
    except _PeerStateRefusal:
        return REFUSED
    if provision is not None:
        return REFUSED
    if not _state_matches_authority(
        existing,
        folder_id=folder_id,
        anchor_profile_id=anchor_profile_id,
        peer_name=peer_name,
        peer_provision_path=peer_provision_path,
        generation=generation,
    ):
        return REFUSED
    phase = existing.document.get("phase")
    existing_create_phases = frozenset({
        PEER_PHASE_CREATE_CLAIMED,
        PEER_PHASE_CREATE_RESPONSE_OBSERVED,
        PEER_PHASE_PROFILE_STOPPED,
        PEER_PHASE_PROVISION_COMMITTED,
    })

    def _reconcile_existing(snapshot):
        """Return only one exact, currently valid create lifecycle."""
        if (
            snapshot is None
            or snapshot.document.get("phase") not in existing_create_phases
            or not _state_matches_authority(
                snapshot,
                folder_id=folder_id,
                anchor_profile_id=anchor_profile_id,
                peer_name=peer_name,
                peer_provision_path=peer_provision_path,
                generation=generation,
            )
        ):
            return REFUSED
        try:
            current, _provision = _preflight_peer_paths(
                operation="create-peer-profile",
                state_path=path,
                provision_path=peer_provision_path,
                generation=generation,
            )
        except _PeerStateRefusal:
            return REFUSED
        if not _same_snapshot(current, snapshot):
            return REFUSED
        if isinstance(snapshot_sink, list):
            snapshot_sink.append(current)
        return EXISTING_EXACT

    if phase in existing_create_phases:
        return _reconcile_existing(existing)
    if phase not in (PEER_PHASE_INITIALIZED, PEER_PHASE_CREATE_AUTH_REJECTED):
        return REFUSED

    try:
        if _optional_private_json_snapshot(peer_provision_path) is not None:
            return REFUSED
    except _PeerStateRefusal:
        return REFUSED

    claimed = _transition_peer_intent(
        path, expected=existing, phase=PEER_PHASE_CREATE_CLAIMED,
    )
    try:
        current, current_provision = _preflight_peer_paths(
            operation="create-peer-profile",
            state_path=path,
            provision_path=peer_provision_path,
            generation=generation,
        )
    except _PeerStateRefusal:
        current = None
        current_provision = object()
    if (
        claimed is not None
        and current is not None
        and _same_snapshot(current, claimed)
        and current_provision is None
    ):
        if isinstance(snapshot_sink, list):
            snapshot_sink.append(current)
        return CREATED_THIS_CALL
    if current_provision is None and current is not None:
        reconciled = _reconcile_existing(current)
        if reconciled == EXISTING_EXACT:
            return reconciled
    return REFUSED


def _peer_intent_snapshot(path):
    try:
        snapshot = _read_private_json_snapshot(path)
    except _PeerStateRefusal:
        return None
    return snapshot if (
        _peer_state_shape_exact(snapshot.document)
        and snapshot.document["state_dev"] == snapshot.st_dev
        and snapshot.document["state_ino"] == snapshot.st_ino
    ) else None


def _peer_provision_snapshot(path):
    try:
        return _read_private_json_snapshot(path)
    except _PeerStateRefusal:
        return None


def _peer_intent_present(
    path, *, peer_name: str, folder_id=None, anchor_profile_id=None,
    peer_provision_path=None,
) -> bool:
    snapshot = _peer_intent_snapshot(path)
    if snapshot is None or snapshot.document.get("peer_name") != peer_name:
        return False
    if folder_id is None or anchor_profile_id is None:
        return True
    return _state_matches_authority(
        snapshot,
        folder_id=folder_id,
        anchor_profile_id=anchor_profile_id,
        peer_name=peer_name,
        peer_provision_path=peer_provision_path or PEER_PROVISION_PATH,
    )


def _same_snapshot(current, expected) -> bool:
    return (
        isinstance(expected, _PrivateJsonSnapshot)
        and current.st_dev == expected.st_dev
        and current.st_ino == expected.st_ino
        and current.raw == expected.raw
        and current.sha256 == expected.sha256
    )


def _read_private_fd(leaf_fd: int) -> bytes:
    os.lseek(leaf_fd, 0, os.SEEK_SET)
    chunks = []
    remaining = _MAX_PEER_STATE_BYTES + 1
    while remaining:
        chunk = os.read(leaf_fd, min(remaining, 4096))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    if len(raw) > _MAX_PEER_STATE_BYTES:
        raise _PeerStateRefusal()
    return raw


def _write_private_fd(leaf_fd: int, raw: bytes) -> None:
    if len(raw) > _MAX_PEER_STATE_BYTES:
        raise _PeerStateRefusal()
    os.lseek(leaf_fd, 0, os.SEEK_SET)
    os.ftruncate(leaf_fd, 0)
    view = memoryview(raw)
    while view:
        written = os.write(leaf_fd, view)
        if written <= 0:
            raise OSError()
        view = view[written:]
    os.fsync(leaf_fd)


def _rewrite_private_json_cas(path, *, expected, next_document):
    """Rewrite only the already-open exact inode captured by ``expected``.

    A path replacement after validation can make this transition fail, but it
    cannot make us overwrite the replacement: all bytes are written through
    the no-follow descriptor for the expected inode.  A crash-torn write is a
    closed malformed state and therefore cannot authorize a later dispatch.
    """
    if not _peer_state_shape_exact(next_document):
        return None
    try:
        target, parent_fd = _open_private_parent(path, exclusive=True)
    except _PeerStateRefusal:
        return None
    leaf_fd = None
    try:
        current = _snapshot_from_parent(target, parent_fd)
        if not _same_snapshot(current, expected):
            return None
        flags = os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        leaf_fd = os.open(target.name, flags, dir_fd=parent_fd)
        fcntl.flock(leaf_fd, fcntl.LOCK_EX)
        opened = os.fstat(leaf_fd)
        if (
            (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
            or _read_private_fd(leaf_fd) != expected.raw
        ):
            return None
        named = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            return None

        next_raw = _canonical_private_bytes(next_document)
        try:
            _write_private_fd(leaf_fd, next_raw)
        except (OSError, _PeerStateRefusal):
            # A normal write failure is rolled back through the same exact
            # descriptor.  A process crash instead leaves a malformed record,
            # which every preflight refuses without external effect.
            try:
                _write_private_fd(leaf_fd, expected.raw)
            except (OSError, _PeerStateRefusal):
                pass
            return None

        return _snapshot_created_private_fd(
            target,
            parent_fd,
            leaf_fd,
            document=next_document,
            raw=next_raw,
        )
    except (_PeerStateRefusal, OSError):
        return None
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)
        os.close(parent_fd)


def _transition_peer_intent(
    path, *, expected, phase: str, peer_profile_id=None,
    response_profile_id=None, peer_provision_snapshot=None,
    ownership_fact=None,
):
    if not isinstance(expected, _PrivateJsonSnapshot) or phase not in _PEER_PHASES:
        return None
    document = dict(expected.document)
    current_phase = document.get("phase")
    allowed_next = {
        PEER_PHASE_INITIALIZED: {PEER_PHASE_CREATE_CLAIMED},
        PEER_PHASE_CREATE_CLAIMED: {
            PEER_PHASE_CREATE_AUTH_REJECTED,
            PEER_PHASE_CREATE_RESPONSE_OBSERVED,
            PEER_PHASE_PROFILE_STOPPED,
        },
        PEER_PHASE_CREATE_AUTH_REJECTED: {PEER_PHASE_CREATE_CLAIMED},
        PEER_PHASE_CREATE_RESPONSE_OBSERVED: {PEER_PHASE_PROFILE_STOPPED},
        PEER_PHASE_PROFILE_STOPPED: {PEER_PHASE_PROVISION_COMMITTED},
        PEER_PHASE_PROVISION_COMMITTED: {PEER_PHASE_REMOVE_DISPATCHED},
        PEER_PHASE_REMOVE_DISPATCHED: {PEER_PHASE_ROLLBACK_VERIFIED},
        PEER_PHASE_ROLLBACK_VERIFIED: set(),
    }
    if current_phase not in allowed_next:
        return None
    if phase != current_phase and phase not in allowed_next[current_phase]:
        return None
    if response_profile_id is not None:
        digest = _core.sha256_hex(response_profile_id)
        if document["response_profile_digest"] not in (None, digest):
            return None
        document["response_profile_digest"] = digest
    if peer_profile_id is not None:
        digest = _core.sha256_hex(peer_profile_id)
        if document["peer_profile_digest"] not in (None, digest):
            return None
        document["peer_profile_digest"] = digest
    if peer_provision_snapshot is not None:
        if not isinstance(peer_provision_snapshot, _PrivateJsonSnapshot):
            return None
        document["peer_provision_digest"] = peer_provision_snapshot.sha256
        document["peer_provision_dev"] = peer_provision_snapshot.st_dev
        document["peer_provision_ino"] = peer_provision_snapshot.st_ino
    if ownership_fact is not None:
        document["ownership_fact_digest"] = hashlib.sha256(
            _canonical_private_bytes(ownership_fact)
        ).hexdigest()
        document["ownership_observed_at"] = ownership_fact.get("observed_at")
    document["phase"] = phase
    if document == expected.document:
        current = _peer_intent_snapshot(path)
        return current if current is not None and _same_snapshot(current, expected) else None
    if phase == current_phase:
        return None
    return _rewrite_private_json_cas(path, expected=expected, next_document=document)


def _claim_peer_remove(
    path, *, expected, peer_profile_id: str, provision_snapshot,
    ownership_fact=None, now=None,
) -> str:
    if not isinstance(expected, _PrivateJsonSnapshot):
        return REFUSED
    document = expected.document
    peer_digest = _core.sha256_hex(peer_profile_id)
    if document.get("peer_profile_digest") != peer_digest:
        return REFUSED
    try:
        current_state, current_provision = _preflight_peer_paths(
            operation="rollback-peer-profile",
            state_path=path,
            provision_path=provision_snapshot.path,
            generation=document.get("generation"),
        )
    except _PeerStateRefusal:
        return REFUSED
    if not _same_optional_snapshot(current_provision, provision_snapshot):
        return REFUSED
    if not _validate_peer_ownership_fact(
        ownership_fact,
        generation=document.get("generation"),
        peer_profile_id=peer_profile_id,
        provision_snapshot=provision_snapshot,
        now=now or datetime.now(timezone.utc),
    ):
        return REFUSED
    if not _same_optional_snapshot(current_state, expected):
        expected_after = dict(expected.document)
        expected_after["phase"] = PEER_PHASE_REMOVE_DISPATCHED
        expected_after["ownership_fact_digest"] = hashlib.sha256(
            _canonical_private_bytes(ownership_fact)
        ).hexdigest()
        expected_after["ownership_observed_at"] = ownership_fact["observed_at"]
        current_document = dict(current_state.document)
        if current_document.get("phase") == PEER_PHASE_ROLLBACK_VERIFIED:
            current_document["phase"] = PEER_PHASE_REMOVE_DISPATCHED
        return EXISTING_EXACT if current_document == expected_after else REFUSED
    if document.get("phase") in (PEER_PHASE_REMOVE_DISPATCHED, PEER_PHASE_ROLLBACK_VERIFIED):
        return EXISTING_EXACT
    if document.get("phase") != PEER_PHASE_PROVISION_COMMITTED:
        return REFUSED
    transitioned = _transition_peer_intent(
        path,
        expected=expected,
        phase=PEER_PHASE_REMOVE_DISPATCHED,
        ownership_fact=ownership_fact,
    )
    if transitioned is not None:
        try:
            current, current_provision = _preflight_peer_paths(
                operation="rollback-peer-profile",
                state_path=path,
                provision_path=provision_snapshot.path,
                generation=document.get("generation"),
            )
        except _PeerStateRefusal:
            current = None
            current_provision = None
        if (
            current is not None
            and _same_snapshot(current, transitioned)
            and _same_optional_snapshot(current_provision, provision_snapshot)
        ):
            return CREATED_THIS_CALL
        # The durable REMOVE_DISPATCHED fence is intentionally retained, but
        # a raced provision coordinate cannot authorize an external remove.
        return REFUSED

    # A concurrent exact claimant may have won the CAS after this invocation
    # captured ``expected``.  Re-read once and accept only the byte-for-byte
    # state that this exact transition would have produced; every foreign or
    # partial replacement remains a refusal.
    current = _peer_intent_snapshot(path)
    expected_after = dict(expected.document)
    expected_after["phase"] = PEER_PHASE_REMOVE_DISPATCHED
    expected_after["ownership_fact_digest"] = hashlib.sha256(
        _canonical_private_bytes(ownership_fact)
    ).hexdigest()
    expected_after["ownership_observed_at"] = ownership_fact["observed_at"]
    if (
        current is not None
        and (current.st_dev, current.st_ino) == (expected.st_dev, expected.st_ino)
    ):
        current_document = dict(current.document)
        if current_document.get("phase") == PEER_PHASE_ROLLBACK_VERIFIED:
            current_document["phase"] = PEER_PHASE_REMOVE_DISPATCHED
        if current_document == expected_after:
            return EXISTING_EXACT
    return REFUSED


def _peer_provision_shape_exact(document) -> bool:
    return (
        isinstance(document, dict)
        and set(document) == {
            "schema", "vendor", "profile_id", "folder_id", "browser_type",
            "origin_policy", "disposable_ack",
        }
        and document.get("schema") == _core.PROVISION_SCHEMA
        and document.get("vendor") == "multilogin"
        and document.get("browser_type") == _PEER_BROWSER_TYPE
        and document.get("origin_policy") == _port_policy.ORIGIN_POLICY
        and document.get("disposable_ack") == _core.REQUIRED_ACK
        and isinstance(document.get("profile_id"), str)
        and isinstance(document.get("folder_id"), str)
    )


def _preflight_peer_paths(
    *, operation, state_path, provision_path, generation=PEER_SOURCE_GENERATION,
):
    """Validate the cross-bound genesis and both peer coordinates first."""
    if operation not in ("create-peer-profile", "rollback-peer-profile"):
        raise _PeerStateRefusal()
    witness_path = _peer_genesis_witness_path(state_path)
    witness = _optional_private_json_snapshot(witness_path)
    state = _optional_private_json_snapshot(state_path)
    provision = _optional_private_json_snapshot(provision_path)
    if state is None or witness is None:
        # Setup owns the one inert INITIALIZED inode.  Runtime create never
        # interprets absence as virgin state, because absence after a dispatch
        # is indistinguishable from first use and would reopen the one-shot.
        raise _PeerStateRefusal()
    if (
        not _peer_genesis_witness_shape_exact(witness.document)
        or witness.document["witness_dev"] != witness.st_dev
        or witness.document["witness_ino"] != witness.st_ino
        or witness.document.get("phase") != _PEER_GENESIS_WITNESS_BOUND
        or witness.document.get("source_generation") != PEER_SOURCE_GENERATION
        or witness.document.get("lifecycle_generation") != generation
        or witness.document.get("state_coordinate_digest")
        != _core.sha256_hex(os.fspath(_normalized_private_path(state_path)))
        or witness.document.get("peer_provision_coordinate_digest")
        != _core.sha256_hex(os.fspath(_normalized_private_path(provision_path)))
    ):
        raise _PeerStateRefusal()
    if state is not None and not _peer_state_shape_exact(state.document):
        raise _PeerStateRefusal()
    if state is not None and (
        state.document["state_dev"] != state.st_dev
        or state.document["state_ino"] != state.st_ino
    ):
        # The lifecycle document is self-bound to the one inode created by
        # the operation.  Byte-identical replacement is still foreign state
        # and must refuse in the first, pre-anchor/pre-secret path census.
        raise _PeerStateRefusal()
    if state is not None and (
        state.document.get("generation") != generation
        or state.document.get("peer_provision_coordinate_digest")
        != _core.sha256_hex(os.fspath(_normalized_private_path(provision_path)))
        or state.document.get("genesis_witness_coordinate_digest")
        != _core.sha256_hex(os.fspath(_normalized_private_path(witness_path)))
        or state.document.get("genesis_witness_dev") != witness.st_dev
        or state.document.get("genesis_witness_ino") != witness.st_ino
        or witness.document.get("state_dev") != state.st_dev
        or witness.document.get("state_ino") != state.st_ino
        or witness.document.get("folder_digest") != state.document.get("folder_digest")
        or witness.document.get("anchor_profile_digest")
        != state.document.get("anchor_profile_digest")
        or witness.document.get("peer_name_digest")
        != _core.sha256_hex(state.document.get("peer_name"))
    ):
        raise _PeerStateRefusal()
    if provision is not None and not _peer_provision_shape_exact(provision.document):
        raise _PeerStateRefusal()
    phase = state.document.get("phase")
    if state is not None:
        if phase in (
            PEER_PHASE_INITIALIZED,
            PEER_PHASE_CREATE_CLAIMED,
            PEER_PHASE_CREATE_AUTH_REJECTED,
            PEER_PHASE_CREATE_RESPONSE_OBSERVED,
            PEER_PHASE_PROFILE_STOPPED,
        ) and provision is not None:
            raise _PeerStateRefusal()
        if phase in (
            PEER_PHASE_PROVISION_COMMITTED,
            PEER_PHASE_REMOVE_DISPATCHED,
            PEER_PHASE_ROLLBACK_VERIFIED,
        ) and provision is None:
            raise _PeerStateRefusal()
        if provision is not None:
            if (
                state.document.get("peer_profile_digest")
                != _core.sha256_hex(provision.document["profile_id"])
                or state.document.get("folder_digest")
                != _core.sha256_hex(provision.document["folder_id"])
            ):
                raise _PeerStateRefusal()
            if phase in (
                PEER_PHASE_PROVISION_COMMITTED,
                PEER_PHASE_REMOVE_DISPATCHED,
                PEER_PHASE_ROLLBACK_VERIFIED,
            ) and (
                state.document.get("peer_provision_digest") != provision.sha256
                or state.document.get("peer_provision_dev") != provision.st_dev
                or state.document.get("peer_provision_ino") != provision.st_ino
            ):
                raise _PeerStateRefusal()
    if operation == "rollback-peer-profile":
        if state is None or provision is None:
            raise _PeerStateRefusal()
        if state.document.get("phase") not in (
            PEER_PHASE_PROVISION_COMMITTED,
            PEER_PHASE_REMOVE_DISPATCHED,
            PEER_PHASE_ROLLBACK_VERIFIED,
        ):
            raise _PeerStateRefusal()
    elif state.document.get("phase") in (
        PEER_PHASE_REMOVE_DISPATCHED, PEER_PHASE_ROLLBACK_VERIFIED,
    ):
        raise _PeerStateRefusal()
    return state, provision


def coordinator_peer_paths_safe(operation: str) -> bool:
    """Pure first-step fixed-path gate for the interactive coordinator."""
    try:
        _preflight_peer_paths(
            operation=operation,
            state_path=PEER_INTENT_PATH,
            provision_path=PEER_PROVISION_PATH,
        )
    except _PeerStateRefusal:
        return False
    return True


def _same_optional_snapshot(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return _same_snapshot(left, right)


def _parse_utc_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _validate_peer_ownership_fact(
    fact, *, generation: str, peer_profile_id: str, provision_snapshot, now,
) -> bool:
    """Validate one fixed-path producer-expiring PF-1/INSTALL1 release receipt.

    The source wave is reader-only.  A separate #359 host operation owns the
    writer; caller prose, flags, dictionaries and vendor lock fields never
    substitute for this receipt.
    """
    keys = {
        "schema", "peer_operation", "source_generation", "lifecycle_generation",
        "peer_profile_digest", "peer_provision_digest", "peer_provision_dev",
        "peer_provision_ino", "pf1_operation", "pf1_active",
        "install1_operation", "install1_active", "observed_at", "valid_until",
        "release_nonce_digest",
    }
    if (
        not isinstance(fact, dict)
        or set(fact) != keys
        or not isinstance(provision_snapshot, _PrivateJsonSnapshot)
    ):
        return False
    if (
        fact.get("schema") != PEER_OWNERSHIP_FACT_SCHEMA
        or fact.get("peer_operation") != PEER_OPERATION_KEY
        or fact.get("source_generation") != PEER_SOURCE_GENERATION
        or fact.get("lifecycle_generation") != generation
        or fact.get("peer_profile_digest") != _core.sha256_hex(peer_profile_id)
        or fact.get("peer_provision_digest") != provision_snapshot.sha256
        or fact.get("peer_provision_dev") != provision_snapshot.st_dev
        or fact.get("peer_provision_ino") != provision_snapshot.st_ino
        or fact.get("pf1_operation") != PF1_OPERATION_KEY
        or fact.get("pf1_active") is not False
        or fact.get("install1_operation") != INSTALL1_OPERATION_KEY
        or fact.get("install1_active") is not False
        or not isinstance(fact.get("release_nonce_digest"), str)
        or not _HEX64_RE.fullmatch(fact["release_nonce_digest"])
    ):
        return False
    observed = _parse_utc_timestamp(fact.get("observed_at"))
    valid_until = _parse_utc_timestamp(fact.get("valid_until"))
    if observed is None or valid_until is None or not isinstance(now, datetime):
        return False
    current = now.astimezone(timezone.utc)
    return (
        observed <= current <= valid_until
        and observed <= valid_until
        and valid_until - observed <= _MAX_OWNERSHIP_RECEIPT_AGE
    )


def _load_peer_ownership_receipt(loader=None):
    try:
        if loader is None:
            return _read_private_json_snapshot(PEER_OWNERSHIP_RECEIPT_PATH).document
        document = loader()
        return document if isinstance(document, dict) else None
    except (_PeerStateRefusal, OSError, ValueError, TypeError):
        return None


def coordinator_peer_rollback_receipt_ready(*, now=None, loader=None) -> bool:
    """Pure production-reader gate; this source wave exposes no receipt writer."""
    try:
        state, provision = _preflight_peer_paths(
            operation="rollback-peer-profile",
            state_path=PEER_INTENT_PATH,
            provision_path=PEER_PROVISION_PATH,
        )
    except _PeerStateRefusal:
        return False
    document = _load_peer_ownership_receipt(loader)
    return _validate_peer_ownership_fact(
        document,
        generation=state.document["generation"],
        peer_profile_id=provision.document["profile_id"],
        provision_snapshot=provision,
        now=now or datetime.now(timezone.utc),
    )


def _exclusive_private_json(path, document):
    try:
        target, parent_fd = _open_private_parent(path, exclusive=True)
    except _PeerStateRefusal:
        return REFUSED, None
    leaf_fd = None
    try:
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            leaf_fd = os.open(target.name, flags, 0o600, dir_fd=parent_fd)
        except FileExistsError:
            existing = _snapshot_from_parent(target, parent_fd)
            if existing.document == document:
                return EXISTING_EXACT, existing
            return REFUSED, None
        os.fchmod(leaf_fd, 0o600)
        raw = _canonical_private_bytes(document)
        view = memoryview(raw)
        while view:
            written = os.write(leaf_fd, view)
            if written <= 0:
                raise OSError()
            view = view[written:]
        os.fsync(leaf_fd)
        snapshot = _snapshot_created_private_fd(
            target,
            parent_fd,
            leaf_fd,
            document=document,
            raw=raw,
        )
        return CREATED_THIS_CALL, snapshot
    except (_PeerStateRefusal, OSError):
        return REFUSED, None
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)
        os.close(parent_fd)


def _write_peer_provision(
    path, *, profile_id: str, folder_id: str, bindings_loader, now,
    current_environment_snapshot, snapshot_sink=None,
):
    """Exclusive-write or exact-reconcile the private peer provision."""
    profile_id = _canonical_multilogin_profile_id(profile_id)
    folder_id = _canonical_multilogin_profile_id(folder_id)
    if profile_id is None or folder_id is None:
        return False, None
    doc = {
        "schema": _core.PROVISION_SCHEMA,
        "vendor": "multilogin",
        "profile_id": profile_id,
        "folder_id": folder_id,
        "browser_type": _PEER_BROWSER_TYPE,
        "origin_policy": _port_policy.ORIGIN_POLICY,
        "disposable_ack": _core.REQUIRED_ACK,
    }
    outcome, snapshot = _exclusive_private_json(path, doc)
    if outcome != CREATED_THIS_CALL:
        # A provision that was not created by this exact invocation is never
        # adopted here, even when its bytes are identical.  A normal completed
        # rerun is reconciled through the PROVISION_COMMITTED lifecycle state;
        # a crash between provision creation and that state transition stays a
        # fail-closed HOLD rather than acquiring a foreign inode by path.
        return False, None
    current = _peer_provision_snapshot(path)
    if (
        snapshot is None
        or snapshot.document != doc
        or current is None
        or not _same_snapshot(current, snapshot)
    ):
        return False, None
    loaded, _code = _core._validate_provision_document(
        snapshot.document,
        bindings_loader=bindings_loader,
        now=now,
        current_environment_snapshot=current_environment_snapshot,
    )
    current = _peer_provision_snapshot(path)
    if current is None or not _same_snapshot(current, snapshot):
        return False, None
    if loaded is not None and isinstance(snapshot_sink, list):
        snapshot_sink.append(snapshot)
    return (loaded is not None), loaded


def _create_peer_profile_cli(
    client: "MultiloginClient", provision: dict, *,
    peer_intent_path, peer_provision_path, bindings_loader, now,
    current_environment_snapshot, initial_state=None,
) -> dict:
    """CLI-layer wrapper: owns the intent/provision file I/O that
    :meth:`MultiloginClient.create_peer_profile` deliberately does not."""
    folder_id = provision["folder_id"]
    anchor_profile_id = provision["profile_id"]
    peer_name = peer_profile_name(folder_id, anchor_profile_id)
    state = {"snapshot": initial_state or _peer_intent_snapshot(peer_intent_path)}
    intent_present = (
        state["snapshot"] is not None
        and state["snapshot"].document.get("phase")
        not in (PEER_PHASE_INITIALIZED, PEER_PHASE_CREATE_AUTH_REJECTED)
    )
    committed_here = {"value": False}

    def _commit():
        claim_snapshots = []
        outcome = _commit_peer_intent(
            peer_intent_path, folder_id=folder_id, anchor_profile_id=anchor_profile_id,
            peer_name=peer_name, peer_provision_path=peer_provision_path,
            snapshot_sink=claim_snapshots,
        )
        if outcome == CREATED_THIS_CALL:
            current = _peer_intent_snapshot(peer_intent_path)
            if (
                len(claim_snapshots) != 1
                or current is None
                or not _same_snapshot(current, claim_snapshots[0])
            ):
                return REFUSED
            state["snapshot"] = current
        elif outcome == EXISTING_EXACT:
            # The losing invocation returns a reconciliation HOLD immediately.
            # Retain the exact snapshot observed by the claim helper rather
            # than converting a subsequent lawful phase advance into a false
            # effect=NONE refusal.
            if len(claim_snapshots) != 1:
                return REFUSED
            state["snapshot"] = claim_snapshots[0]
        committed_here["value"] = outcome == CREATED_THIS_CALL
        return outcome

    def _record_response_id(profile_id):
        current = state["snapshot"] or _peer_intent_snapshot(peer_intent_path)
        if current is None:
            return False
        transitioned = _transition_peer_intent(
            peer_intent_path,
            expected=current,
            phase=PEER_PHASE_CREATE_RESPONSE_OBSERVED,
            response_profile_id=profile_id,
        )
        if transitioned is None:
            return False
        state["snapshot"] = transitioned
        return True

    observed_digest = None
    if state["snapshot"] is not None:
        if not _state_matches_authority(
            state["snapshot"],
            folder_id=folder_id,
            anchor_profile_id=anchor_profile_id,
            peer_name=peer_name,
            peer_provision_path=peer_provision_path,
        ):
            return peer_receipt(
                effect="NONE", code="PROVISION_MISSING", verdict="REFUSED",
                digests=client._peer_digests(folder_id, anchor_profile_id, peer_name),
                **_PEER_BASE_PREDICATES,
            )
        observed_digest = state["snapshot"].document["response_profile_digest"]

    receipt = client.create_peer_profile(
        folder_id=folder_id, anchor_profile_id=anchor_profile_id,
        intent_present=intent_present, commit_intent=_commit,
        observed_profile_digest=observed_digest,
        record_response_id=_record_response_id,
        intent_reconciliation_ready=(
            state["snapshot"] is not None
            and state["snapshot"].document.get("phase")
            not in (PEER_PHASE_CREATE_CLAIMED, PEER_PHASE_CREATE_AUTH_REJECTED)
        ),
    )
    if (
        not committed_here["value"]
        and receipt["effect"] == "NONE"
    ):
        # The client's first vendor census is an externally observable pause.
        # Another exact invocation can advance the one lifecycle inode from
        # INITIALIZED into an effect-bearing create phase during that pause.
        # The input snapshot may already be effect-bearing, or another exact
        # invocation may advance it during the census.  A NONE receipt (busy
        # row, transport/auth failure, malformed census, or identity conflict
        # alike) is not truthful while that durable claim exists.  Re-read the
        # complete cross-bound authority before returning.  Never adopt the
        # concurrent profile or dispatch here: this invocation becomes a
        # conservative reconciliation HOLD for the existing operation.  The
        # only excluded case is a claim created by this invocation; its exact
        # pre-effect AUTH_EXPIRED transition is handled immediately below.
        initial = state["snapshot"]
        try:
            fresh_state, _fresh_provision = _preflight_peer_paths(
                operation="create-peer-profile",
                state_path=peer_intent_path,
                provision_path=peer_provision_path,
                generation=(
                    initial.document["generation"]
                    if initial is not None else PEER_SOURCE_GENERATION
                ),
            )
        except _PeerStateRefusal:
            fresh_state = None
        effect_bearing_phases = {
            PEER_PHASE_CREATE_CLAIMED,
            PEER_PHASE_CREATE_RESPONSE_OBSERVED,
            PEER_PHASE_PROFILE_STOPPED,
            PEER_PHASE_PROVISION_COMMITTED,
        }
        if (
            initial is not None
            and fresh_state is not None
            and (fresh_state.st_dev, fresh_state.st_ino)
            == (initial.st_dev, initial.st_ino)
            and fresh_state.document.get("phase") in effect_bearing_phases
        ):
            state["snapshot"] = fresh_state
            predicates = dict(receipt["predicates"])
            predicates.update({
                "intent_committed": True,
                "dispatched": False,
                "reconciled": True,
                "cleanup_lease_retained": True,
            })
            return peer_receipt(
                effect="CREATE_EFFECT_UNKNOWN",
                code="VENDOR_ERROR",
                verdict="HOLD",
                digests=receipt["digests"],
                initial_peer_census_diagnostic=receipt[
                    "initial_peer_census_diagnostic"
                ],
                initial_peer_census_decode_context=receipt[
                    "initial_peer_census_decode_context"
                ],
                **predicates,
            )
    if (
        committed_here["value"]
        and receipt["effect"] == "NONE"
        and receipt["code"] == "AUTH_EXPIRED"
    ):
        # #385-9 classifies an explicit 401/403 as preceding any possible
        # creation.  Preserve that proof as an exact-inode state transition
        # instead of unlinking a path that a same-UID process could race.
        # The next invocation must win a CAS re-arm before it may dispatch.
        rejected_state = _transition_peer_intent(
            peer_intent_path,
            expected=state["snapshot"],
            phase=PEER_PHASE_CREATE_AUTH_REJECTED,
        ) if state["snapshot"] is not None else None
        if rejected_state is None:
            predicates = dict(receipt["predicates"])
            predicates["cleanup_lease_retained"] = True
            return peer_receipt(
                effect="CREATE_EFFECT_UNKNOWN", code="VENDOR_ERROR", verdict="HOLD",
                digests=receipt["digests"], **predicates,
            )
        state["snapshot"] = rejected_state
    if receipt["effect"] != "PROFILE_STOPPED_PROVEN":
        # A create whose read-back could not prove the profile stopped is NOT
        # a provisionable profile. Writing profile_B here would publish a
        # binding for a profile that may be running or owned, and would let a
        # HOLD masquerade as PASS. The exact cleanup lease stays retained.
        return receipt

    peer_profile_id = client._peer_profile_id  # noqa: SLF001 — CLI/client are one unit here
    current = state["snapshot"] or _peer_intent_snapshot(peer_intent_path)
    if (
        current is not None
        and current.document.get("phase") == PEER_PHASE_PROVISION_COMMITTED
    ):
        # A completed create is an immutable, read-only reconciliation.  The
        # client has just proved the one canonical peer still exists, remains
        # stopped/unowned, and matches any persisted response-id constraint.
        # Do not attempt a backwards lifecycle transition or rewrite either
        # artifact on a normal rerun.
        provision_snapshot = _peer_provision_snapshot(peer_provision_path)
        loaded = None
        if provision_snapshot is not None:
            loaded, _code = _core._validate_provision_document(
                provision_snapshot.document,
                bindings_loader=bindings_loader,
                now=now,
                current_environment_snapshot=current_environment_snapshot,
            )
        try:
            fresh_state, fresh_provision = _preflight_peer_paths(
                operation="create-peer-profile",
                state_path=peer_intent_path,
                provision_path=peer_provision_path,
                generation=current.document.get("generation"),
            )
        except _PeerStateRefusal:
            fresh_state = None
            fresh_provision = None
        if (
            fresh_state is not None
            and _same_snapshot(fresh_state, current)
            and provision_snapshot is not None
            and fresh_provision is not None
            and _same_snapshot(fresh_provision, provision_snapshot)
            and loaded is not None
            and loaded.get("profile_id") == peer_profile_id
            and loaded.get("folder_id") == folder_id
            and current.document.get("peer_profile_digest")
            == _core.sha256_hex(peer_profile_id)
            and current.document.get("peer_provision_digest")
            == provision_snapshot.sha256
            and current.document.get("peer_provision_dev")
            == provision_snapshot.st_dev
            and current.document.get("peer_provision_ino")
            == provision_snapshot.st_ino
        ):
            predicates = dict(receipt["predicates"])
            predicates["provision_written"] = True
            predicates["cleanup_lease_retained"] = False
            return peer_receipt(
                effect="PROVISION_WRITTEN",
                code="OK",
                verdict="PASS",
                digests=receipt["digests"],
                **predicates,
            )
        predicates = dict(receipt["predicates"])
        predicates["cleanup_lease_retained"] = True
        return peer_receipt(
            effect="CREATE_EFFECT_UNKNOWN",
            code="PROVISION_MISSING",
            verdict="HOLD",
            digests=receipt["digests"],
            **predicates,
        )
    stopped_state = _transition_peer_intent(
        peer_intent_path,
        expected=current,
        phase=PEER_PHASE_PROFILE_STOPPED,
        peer_profile_id=peer_profile_id,
    ) if current is not None else None
    if stopped_state is None:
        predicates = dict(receipt["predicates"])
        predicates["cleanup_lease_retained"] = True
        return peer_receipt(
            effect="CREATE_EFFECT_UNKNOWN", code="VENDOR_ERROR", verdict="HOLD",
            digests=receipt["digests"], **predicates,
        )
    state["snapshot"] = stopped_state
    provision_snapshots = []
    written, _loaded = _write_peer_provision(
        peer_provision_path, profile_id=peer_profile_id, folder_id=folder_id,
        bindings_loader=bindings_loader, now=now,
        current_environment_snapshot=current_environment_snapshot,
        snapshot_sink=provision_snapshots,
    )
    predicates = dict(receipt["predicates"])
    if written:
        provision_snapshot = provision_snapshots[0] if len(provision_snapshots) == 1 else None
        current_provision = _peer_provision_snapshot(peer_provision_path)
        if (
            provision_snapshot is None
            or current_provision is None
            or not _same_snapshot(current_provision, provision_snapshot)
        ):
            predicates["provision_written"] = True
            predicates["cleanup_lease_retained"] = True
            return peer_receipt(
                effect="PROVISION_WRITTEN", code="VENDOR_ERROR", verdict="HOLD",
                digests=receipt["digests"], **predicates,
            )
        committed_state = _transition_peer_intent(
            peer_intent_path,
            expected=state["snapshot"],
            phase=PEER_PHASE_PROVISION_COMMITTED,
            peer_profile_id=peer_profile_id,
            peer_provision_snapshot=provision_snapshot,
        ) if provision_snapshot is not None else None
        if committed_state is None:
            predicates["provision_written"] = True
            predicates["cleanup_lease_retained"] = True
            return peer_receipt(
                effect="PROVISION_WRITTEN", code="VENDOR_ERROR", verdict="HOLD",
                digests=receipt["digests"], **predicates,
            )
        try:
            final_state, final_provision = _preflight_peer_paths(
                operation="create-peer-profile",
                state_path=peer_intent_path,
                provision_path=peer_provision_path,
                generation=committed_state.document.get("generation"),
            )
        except _PeerStateRefusal:
            final_state = None
            final_provision = None
        if (
            final_state is None
            or final_provision is None
            or not _same_snapshot(final_state, committed_state)
            or not _same_snapshot(final_provision, provision_snapshot)
        ):
            predicates["provision_written"] = True
            predicates["cleanup_lease_retained"] = True
            return peer_receipt(
                effect="CREATE_EFFECT_UNKNOWN", code="VENDOR_ERROR", verdict="HOLD",
                digests=receipt["digests"], **predicates,
            )
        predicates["provision_written"] = True
        predicates["cleanup_lease_retained"] = False
        return peer_receipt(
            effect="PROVISION_WRITTEN", code="OK", verdict="PASS",
            digests=receipt["digests"], **predicates,
        )
    predicates["provision_written"] = False
    predicates["cleanup_lease_retained"] = True
    return peer_receipt(
        effect=receipt["effect"], code="PROVISION_MISSING", verdict="HOLD",
        digests=receipt["digests"], **predicates,
    )


def _main(
    argv=None, *, stdout=None, bindings_loader=None, credential_stream_factory=None,
    client_factory=BoundedHttpClient, origin_factory=LoopbackBenignOrigin,
    environment_loader=None, now=None, peer_provision_path=None, peer_intent_path=None,
    create_authorization=None, rollback_authorization=None,
    ownership_receipt_loader=None, clock=None,
) -> int:
    """Run the operator-only helper.

    ``credential_stream_factory`` is a hermetic test seam.  The CLI/live path
    cannot set it and always uses the fixed post-preflight Keychain pipe.
    No repository test calls a real credential store or vendor endpoint.

    ``peer_provision_path``/``peer_intent_path`` are hermetic test seams for
    the same reason.  #385 requires a FIXED private peer destination, so the
    argument parser deliberately exposes no flag for either: the live CLI can
    only ever use :data:`PEER_PROVISION_PATH` and :data:`PEER_INTENT_PATH`.
    """
    parser = argparse.ArgumentParser(prog="nonseat_canary_vendors")
    parser.add_argument(
        "operation", nargs="?", default="run",
        choices=("run", "configure-canary-port", "create-peer-profile", "rollback-peer-profile"),
    )
    parser.add_argument("--vendor", required=True, choices=("gologin", "multilogin"))
    parser.add_argument("--provision-path", required=True)
    args = parser.parse_args(argv)
    peer_ops = ("create-peer-profile", "rollback-peer-profile")
    out = stdout if stdout is not None else sys.stdout

    # GoLogin stays completely unsupported until a pinned SDK contract is
    # separately accepted.  Refuse before provision I/O, Keychain, HTTP, browser,
    # origin, or process inspection.
    if args.vendor != "multilogin":
        return _emit_refusal(out, args.vendor, "UNSUPPORTED_SURFACE")

    if clock is not None:
        reference_time = clock()
        current_time = clock
    elif now is not None:
        reference_time = now
        current_time = lambda: now
    else:
        reference_time = datetime.now(timezone.utc)
        current_time = lambda: datetime.now(timezone.utc)
    peer_provision_path = peer_provision_path or PEER_PROVISION_PATH
    peer_intent_path = peer_intent_path or PEER_INTENT_PATH
    peer_state_snapshot = None
    peer_provision_snapshot = None
    ownership_fact = None
    if args.operation in peer_ops:
        expected_authorization = (
            CREATE_PEER_AUTHORIZATION
            if args.operation == "create-peer-profile"
            else ROLLBACK_PEER_AUTHORIZATION
        )
        actual_authorization = (
            create_authorization
            if args.operation == "create-peer-profile"
            else rollback_authorization
        )
        other_authorization = (
            rollback_authorization
            if args.operation == "create-peer-profile"
            else create_authorization
        )
        if actual_authorization is not expected_authorization or other_authorization is not None:
            return _emit_refusal(out, args.vendor, "DISALLOWED_TARGET")
        try:
            peer_state_snapshot, peer_provision_snapshot = _preflight_peer_paths(
                operation=args.operation,
                state_path=peer_intent_path,
                provision_path=peer_provision_path,
            )
        except _PeerStateRefusal:
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")
        if args.operation == "rollback-peer-profile":
            peer_profile_id = peer_provision_snapshot.document["profile_id"]
            state_document = peer_state_snapshot.document
            ownership_fact = _load_peer_ownership_receipt(ownership_receipt_loader)
            if not _validate_peer_ownership_fact(
                ownership_fact,
                generation=state_document["generation"],
                peer_profile_id=peer_profile_id,
                provision_snapshot=peer_provision_snapshot,
                now=reference_time,
            ):
                # The accepted PF-1/INSTALL1 owner resolver is not yet wired
                # into these five paths.  The live default therefore refuses
                # before anchor, bindings, environment, Keychain, or vendor.
                return _emit_refusal(out, args.vendor, "BINDINGS_UNAVAILABLE")

    census_loader = environment_loader or _coordinator_local_census
    try:
        current_environment_snapshot = _core._seal_current_environment_snapshot(  # noqa: SLF001
            census_loader(),
        )
    except Exception:  # noqa: BLE001 — current local proof is all-or-nothing
        current_environment_snapshot = None
    if current_environment_snapshot is None:
        return _emit_refusal(out, args.vendor, "BINDINGS_UNAVAILABLE")

    provision, code = _core.load_provision(
        args.provision_path,
        bindings_loader=bindings_loader,
        now=reference_time,
        current_environment_snapshot=current_environment_snapshot,
    )
    if provision is None:
        return _emit_refusal(out, args.vendor, code)
    if provision.get("vendor") != args.vendor:
        return _emit_refusal(out, args.vendor, "PROVISION_MISSING")
    if provision.get("browser_type") != "mimic":
        return _emit_refusal(out, args.vendor, "UNSUPPORTED_PORT_STATE")
    local_code = _local_disposable_preflight(
        provision, current_environment_snapshot=current_environment_snapshot,
    )
    if local_code is not None:
        return _emit_refusal(out, args.vendor, local_code)

    peer_provision = None
    if args.operation in peer_ops:
        try:
            current_state, current_peer_provision = _preflight_peer_paths(
                operation=args.operation,
                state_path=peer_intent_path,
                provision_path=peer_provision_path,
            )
        except _PeerStateRefusal:
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")
        if not (
            _same_optional_snapshot(current_state, peer_state_snapshot)
            and _same_optional_snapshot(current_peer_provision, peer_provision_snapshot)
        ):
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")
    if args.operation in peer_ops and peer_state_snapshot is not None:
        peer_name = peer_profile_name(provision["folder_id"], provision["profile_id"])
        if not _state_matches_authority(
            peer_state_snapshot,
            folder_id=provision["folder_id"],
            anchor_profile_id=provision["profile_id"],
            peer_name=peer_name,
            peer_provision_path=peer_provision_path,
        ):
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")
    if args.operation == "rollback-peer-profile":
        peer_provision, peer_code = _core._validate_provision_document(
            peer_provision_snapshot.document,
            bindings_loader=bindings_loader,
            now=reference_time,
            current_environment_snapshot=current_environment_snapshot,
        )
        if peer_provision is None:
            return _emit_refusal(out, args.vendor, peer_code or "PROVISION_MISSING")
        if (
            peer_provision.get("folder_id") != provision.get("folder_id")
            or peer_state_snapshot.document.get("peer_profile_digest")
            != _core.sha256_hex(peer_provision["profile_id"])
        ):
            return _emit_refusal(out, args.vendor, "PROVISION_MISSING")

    origin = None
    if args.operation not in peer_ops:
        # Bind and self-test the one fixed loopback origin before any secret
        # or vendor transport exists. There is no fallback port. The peer
        # create/rollback operations never launch a browser, so the fixed
        # port origin is irrelevant to them and is skipped entirely.
        token = "mas115-live-" + secrets.token_hex(16)
        try:
            origin = origin_factory(token=token)
            if origin.base_url != _port_policy.CANARY_ORIGIN or origin.self_test() is not True:
                raise _core.CanaryRefusal("CANARY_PORT_UNAVAILABLE")
        except Exception:  # noqa: BLE001 — bind/self-test failures have one static refusal
            if origin is not None:
                try:
                    origin.close()
                except Exception:  # noqa: BLE001 — closed result cannot expand
                    pass
            return _emit_refusal(out, args.vendor, "CANARY_PORT_UNAVAILABLE")

    # This is intentionally after every provision, collision, bind, and local
    # self-test preflight. Production has no external-stdin path: that would
    # let an eager ``security | helper`` producer run too early.
    credential_stream = None
    try:
        factory = credential_stream_factory or _open_keychain_credential_pipe
        credential_stream = factory()
        credential = _read_direct_pipe_credential(credential_stream)
    except _core.CanaryRefusal as refusal:
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, refusal.code)
    except Exception:  # noqa: BLE001 — fixed absence result only
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")
    finally:
        if credential_stream is not None:
            try:
                credential_stream.close()
            except Exception:  # noqa: BLE001 — fixed cleanup boundary
                pass
    if not credential.present:
        if origin is not None:
            origin.close()
        return _emit_refusal(out, args.vendor, "AUTH_MISSING")

    client = None
    try:
        client = client_factory()
        live_provision = dict(provision)
        live_provision["benign_origin"] = _port_policy.CANARY_ORIGIN
        vendor_client = MultiloginClient(
            credential, client, browser_type=live_provision["browser_type"],
        )
        profile_ref = {
            "profile_id": provision["profile_id"],
            "folder_id": provision["folder_id"],
        }
        if args.operation == "create-peer-profile":
            receipt = _create_peer_profile_cli(
                vendor_client, provision,
                peer_intent_path=peer_intent_path, peer_provision_path=peer_provision_path,
                bindings_loader=bindings_loader, now=reference_time,
                current_environment_snapshot=current_environment_snapshot,
                initial_state=peer_state_snapshot,
            )
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        if args.operation == "rollback-peer-profile":
            state_holder = {"snapshot": peer_state_snapshot}

            def _claim_remove_once():
                # The first fixed-path receipt was a pre-credential gate only.
                # Re-read the producer's current fact with a fresh clock at the
                # last possible moment before acquiring the one-shot remove
                # fence; expiry or replacement is a refusal, never a cached
                # authorization.
                current_ownership_fact = _load_peer_ownership_receipt(
                    ownership_receipt_loader
                )
                outcome = _claim_peer_remove(
                    peer_intent_path,
                    expected=state_holder["snapshot"],
                    peer_profile_id=peer_provision["profile_id"],
                    provision_snapshot=peer_provision_snapshot,
                    ownership_fact=current_ownership_fact,
                    now=current_time(),
                )
                if outcome in (CREATED_THIS_CALL, EXISTING_EXACT):
                    state_holder["snapshot"] = _peer_intent_snapshot(peer_intent_path)
                return outcome

            remove_already_claimed = peer_state_snapshot.document["phase"] in (
                PEER_PHASE_REMOVE_DISPATCHED,
                PEER_PHASE_ROLLBACK_VERIFIED,
            )
            receipt = vendor_client.remove_peer_profile(
                folder_id=provision["folder_id"], anchor_profile_id=provision["profile_id"],
                peer_profile_id=peer_provision["profile_id"],
                remove_already_claimed=remove_already_claimed,
                claim_remove=_claim_remove_once,
            )
            if receipt.get("effect") == "NONE":
                # The first remote census can overlap a different exact
                # invocation acquiring the durable remove fence (and possibly
                # dispatching) on the same lifecycle inode.  An already-bound
                # REMOVE_DISPATCHED/ROLLBACK_VERIFIED re-entry is equally
                # effect-bearing.  Neither a stale pre-census phase nor a
                # failed reconciliation census can justify a no-effect result.
                initial_remove_state = peer_state_snapshot
                try:
                    fresh_remove_state, fresh_remove_provision = _preflight_peer_paths(
                        operation="rollback-peer-profile",
                        state_path=peer_intent_path,
                        provision_path=peer_provision_path,
                        generation=initial_remove_state.document["generation"],
                    )
                except _PeerStateRefusal:
                    fresh_remove_state = None
                    fresh_remove_provision = None
                if (
                    fresh_remove_state is not None
                    and fresh_remove_provision is not None
                    and (fresh_remove_state.st_dev, fresh_remove_state.st_ino)
                    == (initial_remove_state.st_dev, initial_remove_state.st_ino)
                    and fresh_remove_state.document.get("phase") in (
                        PEER_PHASE_REMOVE_DISPATCHED,
                        PEER_PHASE_ROLLBACK_VERIFIED,
                    )
                    and _same_snapshot(fresh_remove_provision, peer_provision_snapshot)
                ):
                    state_holder["snapshot"] = fresh_remove_state
                    predicates = dict(receipt["predicates"])
                    predicates.update({
                        "intent_committed": True,
                        "dispatched": False,
                        "reconciled": True,
                        "cleanup_lease_retained": True,
                    })
                    receipt = peer_receipt(
                        effect="REMOVE_EFFECT_UNKNOWN",
                        code="VENDOR_ERROR",
                        verdict="HOLD",
                        digests=receipt["digests"],
                        removal_disposition=receipt["removal_disposition"],
                        **predicates,
                    )
            if receipt.get("effect") == "ROLLBACK_VERIFIED":
                current_state = state_holder["snapshot"] or _peer_intent_snapshot(peer_intent_path)
                transitioned = _transition_peer_intent(
                    peer_intent_path,
                    expected=current_state,
                    phase=PEER_PHASE_ROLLBACK_VERIFIED,
                    peer_profile_id=peer_provision["profile_id"],
                ) if current_state is not None else None
                try:
                    final_state, final_provision = _preflight_peer_paths(
                        operation="rollback-peer-profile",
                        state_path=peer_intent_path,
                        provision_path=peer_provision_path,
                        generation=(
                            transitioned.document.get("generation")
                            if transitioned is not None else PEER_SOURCE_GENERATION
                        ),
                    )
                except _PeerStateRefusal:
                    final_state = None
                    final_provision = None
                if (
                    transitioned is None
                    or final_state is None
                    or final_provision is None
                    or not _same_snapshot(final_state, transitioned)
                    or not _same_snapshot(final_provision, peer_provision_snapshot)
                ):
                    predicates = dict(receipt["predicates"])
                    receipt = peer_receipt(
                        effect="REMOVE_EFFECT_UNKNOWN", code="VENDOR_ERROR", verdict="HOLD",
                        digests=receipt["digests"],
                        removal_disposition=receipt["removal_disposition"],
                        **predicates,
                    )
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        if args.operation == "configure-canary-port":
            receipt = vendor_client.configure_canary_port(profile_ref)
            print(json.dumps(receipt, indent=2, sort_keys=True), file=out)
            if receipt.get("verdict") == "PASS":
                return 0
            return 3 if receipt.get("verdict") == "HOLD" else 2

        before_policy = vendor_client.port_policy_snapshot(profile_ref)
        if before_policy.state != _port_policy.EXACT_CONFIGURED:
            raise _core.CanaryRefusal("UNSUPPORTED_PORT_STATE")
        navigator = WebDriverNavigator(client, live_provision)

        def _clock() -> str:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        process_probe = live_process_probe(live_provision)
        receipts = _core.run_matrix(
            vendor_client=vendor_client,
            navigator=navigator,
            provision=live_provision,
            credential=credential,
            process_probe=process_probe,
            origin_probe=origin,
            clock=_clock,
            canary_token=token,
            cleanup_probe=_settled_cleanup_probe(process_probe),
        )
        postflight_ok = False
        try:
            after_policy = vendor_client.port_policy_snapshot(profile_ref)
            postflight_ok = (
                after_policy.state == _port_policy.EXACT_CONFIGURED
                and after_policy.auto_update_core == before_policy.auto_update_core
                and after_policy.preservation_digest == before_policy.preservation_digest
            )
        except _core.CanaryRefusal:
            postflight_ok = False
        if not postflight_ok:
            c10 = next(
                (row for row in receipts.get("rows", []) if row.get("row") == "C10"),
                None,
            )
            if c10 is None:
                raise _core.CanaryRefusal("VENDOR_ERROR")
            c10.update({
                "code": "UNSUPPORTED_PORT_STATE",
                "detail": _core.DETAILS["UNSUPPORTED_PORT_STATE"],
                "ok": False,
            })
            receipts["verdict"] = "FAIL"
    except _core.CanaryRefusal as refusal:
        return _emit_refusal(out, args.vendor, refusal.code)
    except Exception:  # noqa: BLE001 — never echo a dynamic error or payload
        return _emit_refusal(out, args.vendor, "VENDOR_ERROR")
    finally:
        if origin is not None:
            try:
                origin.close()
            except Exception:  # noqa: BLE001 — fixed cleanup boundary
                pass
        if client is not None:
            client.close()

    print(json.dumps(receipts, indent=2, sort_keys=True), file=out)
    return 0 if receipts.get("verdict") == "PASS" else 1


def main(
    argv=None, *, stdout=None, bindings_loader=None, credential_stream_factory=None,
    client_factory=BoundedHttpClient, origin_factory=LoopbackBenignOrigin,
    now=None, peer_provision_path=None, peer_intent_path=None,
    create_authorization=None, rollback_authorization=None,
    ownership_receipt_loader=None, clock=None,
) -> int:
    """Live CLI entry with the current-census owner fixed inside this module."""

    return _main(
        argv,
        stdout=stdout,
        bindings_loader=bindings_loader,
        credential_stream_factory=credential_stream_factory,
        client_factory=client_factory,
        origin_factory=origin_factory,
        environment_loader=_coordinator_local_census,
        now=now,
        peer_provision_path=peer_provision_path,
        peer_intent_path=peer_intent_path,
        create_authorization=create_authorization,
        rollback_authorization=rollback_authorization,
        ownership_receipt_loader=ownership_receipt_loader,
        clock=clock,
    )


def _run_coordinator_peer_create(argv=None, **kwargs) -> int:
    """Hermetic coordinator seam; only tests may replace trusted dependencies."""

    return _main(
        ["create-peer-profile", *(list(argv) if argv is not None else [])],
        create_authorization=CREATE_PEER_AUTHORIZATION,
        **kwargs,
    )


def _run_coordinator_peer_rollback(argv=None, **kwargs) -> int:
    """Hermetic rollback seam; tests still must supply an exact ownership fact."""

    return _main(
        ["rollback-peer-profile", *(list(argv) if argv is not None else [])],
        rollback_authorization=ROLLBACK_PEER_AUTHORIZATION,
        **kwargs,
    )


def run_coordinator_peer_create(argv=None) -> int:
    """Trusted live create entry with no caller-supplied census seam."""

    return _main(
        ["create-peer-profile", *(list(argv) if argv is not None else [])],
        create_authorization=CREATE_PEER_AUTHORIZATION,
        environment_loader=_coordinator_local_census,
    )


def run_coordinator_peer_rollback(argv=None) -> int:
    """Trusted live rollback entry with no caller-supplied census seam."""

    return _main(
        ["rollback-peer-profile", *(list(argv) if argv is not None else [])],
        rollback_authorization=ROLLBACK_PEER_AUTHORIZATION,
        environment_loader=_coordinator_local_census,
    )


if __name__ == "__main__":
    raise SystemExit(main())
