"""Fixed-project Git + GitHub PR publication seam for Mastermind workspace projects.

``FixedProjectGitPublisher`` turns a bounded workspace-project request into one
canonical source file on a deterministic proposal branch of the fixed repository
``mastermindx-market-intelligence/macro`` and opens exactly one pull request for
it.  It is SOURCE ONLY: it never installs, never calls a live provider from this
repository, and never creates a Project row.  The only side effects it may cause
are normal Git plumbing writes inside the caller's own clone (a private temporary
index, loose objects, one stable branch ref) plus a non-force push of that one
branch to the verified origin, plus one PR creation through the injected
``pr_owner`` seam.

The same class also carries the closed project-knowledge publication surface
(``publish_knowledge``/``reconcile_knowledge``): one atomic two-postimage commit
(a fixed project file plus the owning workstream record, or the fixed project
communication-preference decision record plus the owning workstream record)
built from an already compiled canonical recipe and published under an actual
private durable-phase claim.  It is the SAME publisher, the SAME binding, the
SAME Git/PR mechanics; it introduces no second store, queue, retry authority or
credential path.

Ownership boundaries
--------------------
* Every policy decision is delegated to an injected, installed-owner seam:
  ``compile_proposal``, ``authorize``, ``permission_stamp``,
  ``qualify_publisher`` and ``pr_owner``.  They are required constructor
  arguments with no defaults; a missing seam refuses before any effect.  Plain
  string labels are never accepted in their place.
* The knowledge methods use their own injected owner seams -- ``authorize_knowledge``,
  ``knowledge_permission_stamp``, ``load_original_operation`` and
  ``validate_original_claim`` -- and never fall back to the CREATE authorizer or
  stamp.  When the knowledge seams are absent the knowledge methods deny without
  any effect; the CREATE surface is unaffected.
* ``qualify_publisher`` is the real Git/gh credential *identity source*
  qualifier.  It is never derived from an Auth0 principal, and this module never
  inspects, transports or logs credential material.
* The caller never supplies a proposal, a path, a branch, a remote, an actor,
  a credential or any other option to ``publish``.  The public CREATE surface is
  exactly ``publish(request, principal)`` and ``reconcile(request, principal)``.
  The knowledge surface is exactly ``publish_knowledge(request, recipe,
  principal, *, claim)`` and ``reconcile_knowledge(lookup, principal)``.  The
  private common-Runtime Events claim is passed through untouched: this module
  never issues, retries, serializes or accepts a public claim, and the claim
  never appears in a result.
* ``compile_proposal`` owns canonical workstream-key semantics, complete
  authored metadata and request digest derivation.  The private recipe compiler
  owns YAML/source semantics.  This module re-validates the closed envelope and
  recipe shapes but never infers or repairs an owner, a key, metadata or source
  text.

Effect discipline
-----------------
* ``NOT_DISPATCHED`` -- a refusal or callback failure before the first write.
* ``EFFECT_UNKNOWN`` -- a write was attempted and its outcome is unknown; this
  is sticky and is never cleared by this module.  ``reconcile`` and
  ``reconcile_knowledge`` are the only ways to learn the actual rung afterwards.
* ``PREPARED`` -- a stable local (and/or remote) proposal branch commit exists
  but no pull request exists; it is not a Project and not a saved record.
* ``PROPOSAL_PUBLISHED`` -- the exact branch is on the verified origin and a
  real ``pr_owner`` receipt exists.
* ``PROJECT_CREATED`` -- the qualified upstream default branch was read back and contains
  exactly the authored bytes after the normal protected merge performed by someone else.
  ``SOURCE_PUBLISHED`` -- the qualified upstream default branch was read back and
  carries exactly both canonical knowledge postimages in one verified tree, or the
  owner-retained source-observed publication proof matches the original hashes.
  This module never merges.
* ``CONFLICT`` -- deterministic disagreement (differing canonical bytes, ref
  collision, non-fast-forward remote branch, foreign receipt, retained operation
  identity mismatch).

Git safety
----------
Only normal plumbing is used, through ``subprocess`` with a fixed argv list (no
shell), bounded timeouts and stdin payloads.  The caller's index, HEAD, worktree
and unrelated files are preserved: no checkout, reset, stash, merge, rebase,
force push, default-branch write or worktree file write ever happens here.  A
prepared commit is created from a private temporary index (``read-tree`` the
expected base, ``hash-object -w --stdin`` the content, ``update-index --add
--cacheinfo``, ``write-tree``, ``commit-tree`` with the expected commit as the
exact single parent) and anchored with a create-only ``git update-ref`` against
the zero object id.  The knowledge commit changes both logical postimages in ONE
private temporary index, one ``write-tree`` and one ``commit-tree``.  Push is a
plain non-force ``git push origin refs/heads/<branch>:refs/heads/<branch>``; the
default branch is never pushed.

Import and construction perform no filesystem writes, no subprocess and no
network access.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from common import workspace_discovery_correction_contract as correction

__all__ = [
    "PUBLICATION_SCHEMA",
    "PROPOSAL_SCHEMA",
    "REPOSITORY",
    "PublisherBinding",
    "FixedProjectGitPublisher",
    "PrOwnerError",
    "PrLookupMissing",
    "PrLookupAmbiguous",
    "PrLookupForeign",
    "PrOwnerRefused",
    "PrOwnerUnknownOutcome",
    "PUBLICATION_STATES",
    "PUBLICATION_REASONS",
    "KNOWLEDGE_SCHEMA",
    "KNOWLEDGE_OPERATION_SCHEMA",
    "KNOWLEDGE_RECIPE_SCHEMA",
    "KNOWLEDGE_STATES",
    "KNOWLEDGE_REASONS",
    "KNOWLEDGE_PHASES",
]


# --------------------------------------------------------------------------- #
# Closed contract constants
# --------------------------------------------------------------------------- #

PUBLICATION_SCHEMA = "mastermind.workspace_project_publication.v1"
PROPOSAL_SCHEMA = "agentos.project_proposal.v1"
DRAFT_ONLY_STATE = "DRAFT_ONLY"
REPOSITORY = "mastermindx-market-intelligence/macro"
SHORT_REPOSITORY = "macro"
PATH_PREFIX = "agentos/workstreams/"
PATH_SUFFIX = ".md"
CONTENT_MAX_BYTES = 32768
REQUEST_ID_MAX_CHARS = 128
WORK_REF_MIN_CHARS = 5
WORK_REF_MAX_CHARS = 67
BRANCH_PREFIX = "mmos/new-project-"

STATE_PROJECT_CREATED = "PROJECT_CREATED"
STATE_PROPOSAL_PUBLISHED = "PROPOSAL_PUBLISHED"
STATE_PREPARED = "PREPARED"
STATE_NOT_DISPATCHED = "NOT_DISPATCHED"
STATE_CONFLICT = "CONFLICT"
STATE_EFFECT_UNKNOWN = "EFFECT_UNKNOWN"

PUBLICATION_STATES = frozenset(
    {
        STATE_PROJECT_CREATED,
        STATE_PROPOSAL_PUBLISHED,
        STATE_PREPARED,
        STATE_NOT_DISPATCHED,
        STATE_CONFLICT,
        STATE_EFFECT_UNKNOWN,
    }
)

PUBLICATION_REASONS = frozenset(
    {
        "BINDING_INVALID",
        "WORKTREE_INVALID",
        "ORIGIN_MISMATCH",
        "DEFAULT_BRANCH_MISSING",
        "UNAUTHORIZED",
        "QUALIFIER_REFUSED",
        "PERMISSION_STAMP_INVALID",
        "SEAM_IDENTITY_CHANGED",
        "COMPILE_REFUSED",
        "PROPOSAL_INVALID",
        "REQUEST_INVALID",
        "EXPECTED_COMMIT_MISSING",
        "STALE_EXPECTED_COMMIT",
        "PATH_COLLISION_IN_BASE",
        "DEFAULT_BYTES_CONFLICT",
        "REF_COLLISION",
        "REMOTE_BRANCH_CONFLICT",
        "REMOTE_BRANCH_UNVERIFIED",
        "PUSH_REFUSED_NON_FAST_FORWARD",
        "PR_RECEIPT_INVALID",
        "PR_RECEIPT_FOREIGN",
        "PR_LOOKUP_FAILED",
        "PR_LOOKUP_UNKNOWN",
        "PR_CREATION_REFUSED",
        "PR_CREATION_UNKNOWN",
        "AUTHORIZATION_REVOKED",
        "REMOTE_BRANCH_WITHOUT_PR",
        "LOCAL_ONLY",
        "READ_ONLY_RECONCILE",
        "NO_EXISTING_PUBLICATION",
        "GIT_INVOCATION_FAILED",
        "GIT_WRITE_UNKNOWN",
    }
)

_RESULT_KEYS = frozenset(
    {
        "schema",
        "state",
        "request_sha256",
        "work_ref",
        "branch",
        "source",
        "proposal",
        "reason",
        "retryable",
    }
)
_SOURCE_KEYS = frozenset(
    {"repository", "commit", "path", "content_sha256", "request_sha256"}
)
_RECEIPT_KEYS = frozenset({"number", "url", "head_commit", "head_branch"})
_ENVELOPE_KEYS = frozenset(
    {
        "schema",
        "state",
        "request_id",
        "request_sha256",
        "expected_commit",
        "work_ref",
        "path",
        "content_utf8",
        "content_sha256",
    }
)

# --------------------------------------------------------------------------- #
# Closed project-knowledge contract constants
# --------------------------------------------------------------------------- #

KNOWLEDGE_SCHEMA = "mastermind.workspace_project_knowledge_publication.v1"
KNOWLEDGE_OPERATION_SCHEMA = "mastermind.workspace_project_knowledge_operation.v1"
KNOWLEDGE_RECIPE_SCHEMA = "mastermind.project_knowledge_recipe.v1"
KNOWLEDGE_RECIPE_STATE = "DRAFT_ONLY"
KNOWLEDGE_REQUEST_SCHEMA_FILE_ADD = "mastermind.project_file_add_request.v1"
KNOWLEDGE_REQUEST_SCHEMA_PREFERENCE = "mastermind.project_preference_set_request.v1"
KNOWLEDGE_ACTION_FILE_ADD = "add_project_file"
KNOWLEDGE_ACTION_PREFERENCE = "set_project_communication_preference"
KNOWLEDGE_RECIPE_ACTION_FILE_ADD = "project_file_add"
KNOWLEDGE_RECIPE_ACTION_PREFERENCE = "project_preference_set"
KNOWLEDGE_FILE_REQUEST_ID_PREFIX = "mmos-project-file-add-"
KNOWLEDGE_PREFERENCE_REQUEST_ID_PREFIX = "mmos-project-preference-set-"
KNOWLEDGE_BRANCH_PREFIX = "mmos/knowledge-"
KNOWLEDGE_COMMIT_SUBJECT_PREFIX = "mmos knowledge "
KNOWLEDGE_PROJECT_FILES_DIR = "agentos/project-files"
KNOWLEDGE_DECISIONS_DIR = "agentos/decisions"
KNOWLEDGE_DECISION_KEY_PREFIX = "PROJECT-COMMUNICATION-PREFERENCE-"
KNOWLEDGE_MEDIA_MD = "text/markdown"
KNOWLEDGE_MEDIA_TXT = "text/plain"
KNOWLEDGE_FILE_MAX_BYTES = 32768
KNOWLEDGE_PREFERENCE_MAX_BYTES = 2000
KNOWLEDGE_DISPLAY_NAME_MAX_CHARS = 128
KNOWLEDGE_RECIPE_OUTPUT_MAX_BYTES = 262144

STATE_SOURCE_PUBLISHED = "SOURCE_PUBLISHED"

KNOWLEDGE_PHASE_CLAIMED = "CLAIMED"
KNOWLEDGE_PHASE_STARTED = "STARTED"
KNOWLEDGE_PHASE_PROPOSAL_PUBLISHED = "PROPOSAL_PUBLISHED"
KNOWLEDGE_PHASE_SOURCE_PUBLISHED = "SOURCE_PUBLISHED"
KNOWLEDGE_PHASE_NOT_DISPATCHED = "NOT_DISPATCHED"
KNOWLEDGE_PHASE_UNKNOWN = "UNKNOWN"

KNOWLEDGE_PHASES = frozenset(
    {
        KNOWLEDGE_PHASE_CLAIMED,
        KNOWLEDGE_PHASE_STARTED,
        KNOWLEDGE_PHASE_PROPOSAL_PUBLISHED,
        KNOWLEDGE_PHASE_SOURCE_PUBLISHED,
        KNOWLEDGE_PHASE_NOT_DISPATCHED,
        KNOWLEDGE_PHASE_UNKNOWN,
    }
)

KNOWLEDGE_STATES = frozenset(
    {
        STATE_SOURCE_PUBLISHED,
        STATE_PROPOSAL_PUBLISHED,
        STATE_PREPARED,
        STATE_NOT_DISPATCHED,
        STATE_CONFLICT,
        STATE_EFFECT_UNKNOWN,
    }
)

KNOWLEDGE_REASONS = frozenset(
    {
        "BINDING_INVALID",
        "WORKTREE_INVALID",
        "ORIGIN_MISMATCH",
        "DEFAULT_BRANCH_MISSING",
        "UNAUTHORIZED",
        "QUALIFIER_REFUSED",
        "PERMISSION_STAMP_INVALID",
        "SEAM_IDENTITY_CHANGED",
        "KNOWLEDGE_SEAMS_ABSENT",
        "REQUEST_INVALID",
        "RECIPE_INVALID",
        "CLAIM_INVALID",
        "PHASE_NOT_CLAIMED",
        "OPERATION_MISSING",
        "OPERATION_INVALID",
        "OPERATION_CONFLICT",
        "OPERATION_UNKNOWN",
        "EXPECTED_COMMIT_MISSING",
        "STALE_EXPECTED_COMMIT",
        "PATH_COLLISION_IN_BASE",
        "PREIMAGE_CONFLICT",
        "DEFAULT_BYTES_CONFLICT",
        "REF_COLLISION",
        "REMOTE_BRANCH_CONFLICT",
        "REMOTE_BRANCH_UNVERIFIED",
        "PUSH_REFUSED_NON_FAST_FORWARD",
        "PR_RECEIPT_INVALID",
        "PR_RECEIPT_FOREIGN",
        "PR_LOOKUP_FAILED",
        "PR_LOOKUP_UNKNOWN",
        "PR_CREATION_REFUSED",
        "PR_CREATION_UNKNOWN",
        "AUTHORIZATION_REVOKED",
        "REMOTE_BRANCH_WITHOUT_PR",
        "LOCAL_ONLY",
        "READ_ONLY_RECONCILE",
        "NO_EXISTING_PUBLICATION",
        "GIT_INVOCATION_FAILED",
        "GIT_WRITE_UNKNOWN",
    }
)

_KNOWLEDGE_LOOKUP_KEYS = frozenset(
    {
        "action",
        "request_id",
        "work_ref",
        "source_commit",
        "base_revision",
        "request_sha256",
        "expected_preference_revision",
    }
)
_KNOWLEDGE_IDENTITY_KEYS = _KNOWLEDGE_LOOKUP_KEYS | frozenset({"principal_scope"})
_KNOWLEDGE_POSTIMAGE_KEYS = frozenset(
    {"path", "content_sha256", "expected_preimage_sha256"}
)
_KNOWLEDGE_METADATA_KEYS = frozenset(
    {
        "schema",
        "identity",
        "recipe_fingerprint_sha256",
        "permission_binding_digest",
        "phase",
        "expected_commit",
        "postimages",
        "branch",
        "publication",
        "proposal",
    }
)
_KNOWLEDGE_PUBLICATION_KEYS = frozenset({"repository", "commit", "postimages"})
_KNOWLEDGE_PUBLICATION_IMAGE_KEYS = frozenset({"path", "content_sha256"})
_KNOWLEDGE_RECIPE_KEYS = frozenset(
    {
        "schema",
        "state",
        "action",
        "work_ref",
        "request_id",
        "request_fingerprint",
        "captured_commit",
        "permission_binding_digest",
        "postimages",
    }
)
_KNOWLEDGE_RECIPE_POSTIMAGE_KEYS = frozenset(
    {"path", "content_utf8", "content_sha256", "expected_preimage_sha256"}
)
_KNOWLEDGE_RESULT_KEYS = frozenset(
    {
        "schema",
        "selection",
        "state",
        "recipe_fingerprint_sha256",
        "source",
        "proposal",
        "reason",
        "retryable",
    }
)
_KNOWLEDGE_FILE_REQUEST_KEYS = frozenset(
    {"schema", "request_id", "work_ref", "source_commit", "base_revision", "file"}
)
_KNOWLEDGE_FILE_KEYS = frozenset({"display_name", "media_type", "content_utf8"})
_KNOWLEDGE_PREFERENCE_REQUEST_KEYS = frozenset(
    {
        "schema",
        "request_id",
        "work_ref",
        "source_commit",
        "base_revision",
        "expected_preference_revision",
        "value",
    }
)

_KNOWLEDGE_FILE_REQUEST_ID_RE = re.compile(
    r"\A" + re.escape(KNOWLEDGE_FILE_REQUEST_ID_PREFIX) + r"[0-9a-f]{40}\Z"
)
_KNOWLEDGE_PREFERENCE_REQUEST_ID_RE = re.compile(
    r"\A" + re.escape(KNOWLEDGE_PREFERENCE_REQUEST_ID_PREFIX) + r"[0-9a-f]{40}\Z"
)

# Closed action descriptors.  The closed action is derived ONLY from the exact
# public request schema/key set, never from a caller-supplied action string.
_KNOWLEDGE_ACTIONS = (
    {
        "action": correction.ACTION,
        "recipe_action": correction.RECIPE_ACTION,
        "request_schema": correction.REQUEST_SCHEMA,
        "request_keys": correction.REQUEST_KEYS,
        "request_id_re": re.compile(r"\A" + re.escape(correction.REQUEST_PREFIX) + r"[0-9a-f]{40}\Z"),
        "expected_preference_revision": False,
    },
    {
        "action": KNOWLEDGE_ACTION_FILE_ADD,
        "recipe_action": KNOWLEDGE_RECIPE_ACTION_FILE_ADD,
        "request_schema": KNOWLEDGE_REQUEST_SCHEMA_FILE_ADD,
        "request_keys": _KNOWLEDGE_FILE_REQUEST_KEYS,
        "request_id_re": _KNOWLEDGE_FILE_REQUEST_ID_RE,
        "expected_preference_revision": False,
    },
    {
        "action": KNOWLEDGE_ACTION_PREFERENCE,
        "recipe_action": KNOWLEDGE_RECIPE_ACTION_PREFERENCE,
        "request_schema": KNOWLEDGE_REQUEST_SCHEMA_PREFERENCE,
        "request_keys": _KNOWLEDGE_PREFERENCE_REQUEST_KEYS,
        "request_id_re": _KNOWLEDGE_PREFERENCE_REQUEST_ID_RE,
        "expected_preference_revision": True,
    },
)

_HEX40_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_HEX64_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_COMMIT_ID_RE = _HEX40_RE
_REQUEST_ID_RE = re.compile(r"\Ammos-project-create-[0-9a-f]{40}\Z")
# Canonical workstream key: UPPER KEBAB, 2..64 characters, single dashes only.
_WORK_REF_RE = re.compile(r"\AWS:[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")

_SHA1_ZERO = "0" * 40
_SHA256_ZERO = "0" * 64

_KNOWN_PUSH_REFUSALS = (
    "non-fast-forward",
    "fetch first",
    "[rejected]",
    "contains work",
)


# --------------------------------------------------------------------------- #
# Small validators
# --------------------------------------------------------------------------- #


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_hex40(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX40_RE.match(value))


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64_RE.match(value))


def _is_commit_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_COMMIT_ID_RE.match(value))


def _valid_work_ref(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if not (WORK_REF_MIN_CHARS <= len(value) <= WORK_REF_MAX_CHARS):
        return False
    return bool(_WORK_REF_RE.match(value))


def _valid_request_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_REQUEST_ID_RE.match(value))


def _valid_branch_name(name: Any) -> bool:
    """Normal ``refs/heads`` branch component validation (no object expansion)."""
    if not isinstance(name, str) or not name or len(name) > 200:
        return False
    if name.startswith("/") or name.endswith("/"):
        return False
    if name.startswith("refs/") or "/refs/" in name:
        # A short branch name is required; the refs/ namespace is added here.
        return False
    if name.endswith(".") or name.endswith(".lock"):
        return False
    if ".." in name or "@{" in name or name.endswith("@"):
        return False
    for char in name:
        if char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F:
            return False
        if char in "~^:?*[]\\":
            return False
    for part in name.split("/"):
        if not part or part.startswith(".") or part.endswith(".lock"):
            return False
    return True


def _canonical_json(value: Any) -> str:
    """Canonical UTF-8 JSON: sorted keys, ``(',',':')``, raw non-ASCII, no NaN."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_envelope(envelope: Any) -> None:
    """Validate the closed canonical ``agentos.project_proposal.v1`` envelope.

    Raises ``_Refusal`` with reason ``PROPOSAL_INVALID``.  The trusted compiler
    owns workstream-key semantics and authored metadata; this check enforces the
    closed shape, the derived canonical path and the self-consistent digests.
    """
    invalid = _Refusal(STATE_NOT_DISPATCHED, "PROPOSAL_INVALID")
    if not isinstance(envelope, Mapping):
        raise invalid
    if frozenset(envelope.keys()) != _ENVELOPE_KEYS:
        raise invalid
    if envelope["schema"] != PROPOSAL_SCHEMA:
        raise invalid
    if envelope["state"] != DRAFT_ONLY_STATE:
        raise invalid
    if not _valid_request_id(envelope["request_id"]):
        raise invalid
    if not _is_hex64(envelope["request_sha256"]):
        raise invalid
    if not _is_commit_id(envelope["expected_commit"]):
        raise invalid
    if not _valid_work_ref(envelope["work_ref"]):
        raise invalid
    work_ref = envelope["work_ref"]
    derived_path = PATH_PREFIX + "WS-" + work_ref[3:] + PATH_SUFFIX
    if envelope["path"] != derived_path:
        # Never accept a client-chosen path: only the derived canonical one.
        raise invalid
    content = envelope["content_utf8"]
    if not isinstance(content, str):
        raise invalid
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > CONTENT_MAX_BYTES:
        raise invalid
    if not _is_hex64(envelope["content_sha256"]):
        raise invalid
    if envelope["content_sha256"] != _sha256_hex(content_bytes):
        raise invalid


def _callable_identity(token: Any) -> str:
    """Stable identity fingerprint for an injected seam (never a label)."""
    bound = getattr(token, "__func__", None)
    base = bound if bound is not None else token
    module = getattr(base, "__module__", None) or type(base).__module__
    qualname = (
        getattr(token, "__qualname__", None)
        or getattr(base, "__qualname__", None)
        or getattr(base, "__name__", None)
        or type(base).__name__
    )
    return "%s.%s@%x" % (module, qualname, id(token))


def _require_callable(token: Any, seam_name: str) -> Callable[..., Any]:
    if isinstance(token, (str, bytes, bytearray)) or not callable(token):
        raise TypeError(
            "%s seam must be an injected callable; plain string labels are not grants"
            % seam_name
        )
    return token


# --------------------------------------------------------------------------- #
# Closed project-knowledge validators (public request, lookup, recipe, retained
# operation metadata).  YAML/source semantics stay with the private recipe
# compiler; these checks enforce the closed shapes and exact identity binding.
# --------------------------------------------------------------------------- #


def _knowledge_action_record(value: Any) -> Optional[dict]:
    for record in _KNOWLEDGE_ACTIONS:
        if value == record["action"]:
            return record
    return None


def _knowledge_request_record(request: Any) -> Optional[dict]:
    """Derive the closed action record from the exact public request shape."""
    if not isinstance(request, Mapping):
        return None
    for record in _KNOWLEDGE_ACTIONS:
        if (
            request.get("schema") == record["request_schema"]
            and frozenset(request.keys()) == record["request_keys"]
        ):
            return record
    return None


def _valid_knowledge_request_id(value: Any, record: dict) -> bool:
    if not isinstance(value, str):
        return False
    return bool(record["request_id_re"].match(value))


def _knowledge_file_extension(display_name: Any) -> str:
    """Bounded display-name check; returns the canonical ``md``/``txt`` extension.

    Mirrors the public media rules of the recipe compiler: bounded, printable,
    no path separators, exactly one dotted extension of ``md`` or ``txt``.
    """
    invalid = _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not isinstance(display_name, str) or isinstance(display_name, bool):
        raise invalid
    if not display_name or len(display_name) > KNOWLEDGE_DISPLAY_NAME_MAX_CHARS:
        raise invalid
    for char in display_name:
        point = ord(char)
        if point < 0x20 or 0x7F <= point <= 0x9F:
            raise invalid
    if "/" in display_name or "\\" in display_name:
        raise invalid
    if "." not in display_name:
        raise invalid
    stem, _, ext = display_name.rpartition(".")
    ext = ext.lower()
    if not stem or ext not in ("md", "txt"):
        raise invalid
    return ext


def _knowledge_media_type(media_type: Any, ext: str) -> None:
    expected = KNOWLEDGE_MEDIA_MD if ext == "md" else KNOWLEDGE_MEDIA_TXT
    if not isinstance(media_type, str) or media_type != expected:
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")


def _knowledge_bounded_text(value: Any, max_bytes: int) -> bytes:
    """Bounded non-empty UTF-8 text; rejects stray control characters."""
    invalid = _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not isinstance(value, str) or isinstance(value, bool):
        raise invalid
    try:
        raw = value.encode("utf-8")
    except UnicodeEncodeError:
        raise invalid from None
    if not raw or len(raw) > max_bytes:
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    for char in value:
        point = ord(char)
        if point in (0x09, 0x0A, 0x0D):
            continue
        if point < 0x20 or 0x7F <= point <= 0x9F:
            raise invalid
    return raw


def _knowledge_request_lookup(request: Any) -> dict:
    """Validate the closed public request; return the body-free 7-field lookup.

    The public ``request_sha256`` is derived here from the canonical public
    request.  It is distinct from the private recipe fingerprint and from the
    scoped action permission stamp.
    """
    if type(request) is dict and request.get("schema") == correction.REQUEST_SCHEMA:
        try:
            return correction.request_lookup(request)
        except ValueError:
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID") from None
    record = _knowledge_request_record(request)
    if record is None:
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not _valid_knowledge_request_id(request["request_id"], record):
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not _valid_work_ref(request["work_ref"]):
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not _is_commit_id(request["source_commit"]):
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if not _is_hex64(request["base_revision"]):
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if record["expected_preference_revision"]:
        revision = request["expected_preference_revision"]
        if revision is not None and not _is_hex64(revision):
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        _knowledge_bounded_text(request["value"], KNOWLEDGE_PREFERENCE_MAX_BYTES)
        if not request["value"].strip():
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    else:
        file_request = request["file"]
        if not isinstance(file_request, Mapping):
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        if frozenset(file_request.keys()) != _KNOWLEDGE_FILE_KEYS:
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        ext = _knowledge_file_extension(file_request["display_name"])
        _knowledge_media_type(file_request["media_type"], ext)
        _knowledge_bounded_text(file_request["content_utf8"], KNOWLEDGE_FILE_MAX_BYTES)
    try:
        request_sha256 = _sha256_hex(_canonical_json(request).encode("utf-8"))
    except (TypeError, ValueError):
        raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID") from None
    return {
        "action": record["action"],
        "request_id": request["request_id"],
        "work_ref": request["work_ref"],
        "source_commit": request["source_commit"],
        "base_revision": request["base_revision"],
        "request_sha256": request_sha256,
        "expected_preference_revision": (
            request.get("expected_preference_revision")
            if record["expected_preference_revision"]
            else None
        ),
    }


def _validate_knowledge_lookup(lookup: Any) -> dict:
    """Validate the closed body-free 7-field lookup shape."""
    invalid = _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
    if type(lookup) is dict and lookup.get("action") == correction.ACTION:
        try:
            return correction.validate_lookup(lookup)
        except ValueError:
            raise invalid from None
    if not isinstance(lookup, Mapping):
        raise invalid
    if frozenset(lookup.keys()) != _KNOWLEDGE_LOOKUP_KEYS:
        raise invalid
    record = _knowledge_action_record(lookup["action"])
    if record is None:
        raise invalid
    if not _valid_knowledge_request_id(lookup["request_id"], record):
        raise invalid
    if not _valid_work_ref(lookup["work_ref"]):
        raise invalid
    if not _is_commit_id(lookup["source_commit"]):
        raise invalid
    if not _is_hex64(lookup["base_revision"]):
        raise invalid
    if not _is_hex64(lookup["request_sha256"]):
        raise invalid
    revision = lookup["expected_preference_revision"]
    if revision is not None and not _is_hex64(revision):
        raise invalid
    if not record["expected_preference_revision"] and revision is not None:
        # A file-add lookup never carries a preference revision.
        raise invalid
    return dict(lookup)


def _validate_knowledge_recipe(recipe: Any, lookup: dict) -> dict:
    """Validate the closed private recipe shape against the actual lookup.

    The recipe is private canonical compiler output, never public request
    input.  Identity/target binding to the lookup is enforced here; path and
    content binding to the actual principal scope is enforced separately once
    the actual scope is known.
    """
    invalid = _Refusal(STATE_NOT_DISPATCHED, "RECIPE_INVALID")
    if not isinstance(recipe, Mapping):
        raise invalid
    if frozenset(recipe.keys()) != _KNOWLEDGE_RECIPE_KEYS:
        raise invalid
    if recipe["schema"] != KNOWLEDGE_RECIPE_SCHEMA:
        raise invalid
    if recipe["state"] != KNOWLEDGE_RECIPE_STATE:
        raise invalid
    record = _knowledge_action_record(lookup["action"])
    if recipe["action"] != record["recipe_action"]:
        raise invalid
    if recipe["work_ref"] != lookup["work_ref"]:
        raise invalid
    if recipe["request_id"] != lookup["request_id"]:
        raise invalid
    if not _is_hex64(recipe["request_fingerprint"]):
        raise invalid
    if recipe["captured_commit"] != lookup["source_commit"]:
        raise invalid
    if not _is_hex64(recipe["permission_binding_digest"]):
        raise invalid
    postimages = recipe["postimages"]
    count = 3 if lookup["action"] == correction.ACTION else 2
    if not isinstance(postimages, list) or len(postimages) != count:
        raise invalid
    total = 0
    paths = []
    for image in postimages:
        if not isinstance(image, Mapping):
            raise invalid
        if frozenset(image.keys()) != _KNOWLEDGE_RECIPE_POSTIMAGE_KEYS:
            raise invalid
        path = image["path"]
        if not isinstance(path, str) or not path or not _valid_repo_path(path):
            raise invalid
        content = image["content_utf8"]
        if not isinstance(content, str) or isinstance(content, bool):
            raise invalid
        try:
            raw = content.encode("utf-8")
        except UnicodeEncodeError:
            raise invalid from None
        if not _is_hex64(image["content_sha256"]):
            raise invalid
        if image["content_sha256"] != _sha256_hex(raw):
            raise invalid
        preimage = image["expected_preimage_sha256"]
        if preimage is not None and not _is_hex64(preimage):
            raise invalid
        total += len(raw)
        paths.append(path)
    if total > KNOWLEDGE_RECIPE_OUTPUT_MAX_BYTES:
        raise invalid
    if len(set(paths)) != count:
        raise invalid
    changed = _knowledge_changed_paths(postimages)
    if not changed:
        # A recipe that changes neither logical postimage is not a publication.
        raise invalid
    return recipe


def _valid_repo_path(path: str) -> bool:
    """Bounded in-repository path check: absolute, dot-dot and lock free."""
    if not isinstance(path, str) or not path or len(path) > 4096:
        return False
    if path.startswith("/") or path.endswith("/"):
        return False
    if "\x00" in path:
        return False
    for part in path.split("/"):
        if not part or part == "." or part == ".." or part.endswith(".lock"):
            return False
    return True


def _knowledge_changed_paths(postimages: Any) -> "list[str]":
    """Logical changed paths: postimages whose new SHA differs from the preimage.

    A preference edit may leave the workstream record unchanged, so the changed
    set may be a single path; at least one path must always change.
    """
    changed = []
    for image in postimages:
        preimage = image["expected_preimage_sha256"]
        if preimage is None or preimage != image["content_sha256"]:
            changed.append(image["path"])
    return changed


def _knowledge_expected_paths(lookup: dict, request: Any, file_id: str) -> "list[str]":
    """The only writable paths for this original, derived from actual identity."""
    record = _knowledge_action_record(lookup["action"])
    key = lookup["work_ref"][len("WS:"):]
    workstream_path = PATH_PREFIX + "WS-" + key + PATH_SUFFIX
    if record["action"] == correction.ACTION:
        return ["agentos/discoveries/DSC-" + lookup["discovery_ref"][4:] + ".md",
                "agentos/discoveries/DSC-PROJECT-CORRECTION-" + file_id[:40].upper() + ".md", workstream_path]
    if record["action"] == KNOWLEDGE_ACTION_FILE_ADD:
        file_request = request["file"]
        ext = _knowledge_file_extension(file_request["display_name"])
        media_path = "%s/WS-%s/%s.%s" % (
            KNOWLEDGE_PROJECT_FILES_DIR,
            key,
            file_id,
            ext,
        )
        return [media_path, workstream_path]
    decision_path = "%s/DEC-%s%s%s" % (
        KNOWLEDGE_DECISIONS_DIR,
        KNOWLEDGE_DECISION_KEY_PREFIX,
        key,
        PATH_SUFFIX,
    )
    return [decision_path, workstream_path]


def _knowledge_postimage_digests(postimages: Any) -> "list[tuple]":
    """Comparable (path, content sha, expected preimage) triples."""
    return [
        (image["path"], image["content_sha256"], image["expected_preimage_sha256"])
        for image in postimages
    ]


def _validate_knowledge_operation_metadata(
    metadata: Any, lookup: dict, scope: str
) -> dict:
    """Validate the exact retained operation metadata from the private reader.

    The retained metadata comes from the actual private common-Runtime Events
    reader, never from a public caller claim or an unsigned receipt.  Identity,
    principal scope and every target/digest are compared in full; changed work
    or a changed payload under the same original id is a conflict, never a new
    operation.
    """
    invalid = _Refusal(STATE_CONFLICT, "OPERATION_INVALID")
    if not isinstance(metadata, Mapping):
        raise invalid
    if frozenset(metadata.keys()) != _KNOWLEDGE_METADATA_KEYS:
        raise invalid
    if metadata["schema"] != KNOWLEDGE_OPERATION_SCHEMA:
        raise invalid
    identity = metadata["identity"]
    if not isinstance(identity, Mapping):
        raise invalid
    if frozenset(identity.keys()) != frozenset(lookup) | {"principal_scope"}:
        raise invalid
    if dict(identity) != {**dict(lookup), "principal_scope": scope}:
        # Well-formed retained metadata that disagrees with the actual original
        # identity (changed work, payload, commit, scope or action) is a
        # deterministic conflict, never a new operation.
        raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")
    if not _is_hex64(metadata["recipe_fingerprint_sha256"]):
        raise invalid
    if not _is_hex64(metadata["permission_binding_digest"]):
        raise invalid
    if metadata["phase"] not in KNOWLEDGE_PHASES:
        raise invalid
    if metadata["expected_commit"] != lookup["source_commit"]:
        raise invalid
    if not _is_commit_id(metadata["expected_commit"]):
        raise invalid
    postimages = metadata["postimages"]
    count = 3 if lookup["action"] == correction.ACTION else 2
    if not isinstance(postimages, list) or len(postimages) != count:
        raise invalid
    for image in postimages:
        if not isinstance(image, Mapping):
            raise invalid
        if frozenset(image.keys()) != _KNOWLEDGE_POSTIMAGE_KEYS:
            raise invalid
        if not isinstance(image["path"], str) or not _valid_repo_path(image["path"]):
            raise invalid
        if not _is_hex64(image["content_sha256"]):
            raise invalid
        preimage = image["expected_preimage_sha256"]
        if preimage is not None and not _is_hex64(preimage):
            raise invalid
    if len(set(image["path"] for image in postimages)) != count:
        raise invalid
    if lookup["action"] == correction.ACTION:
        if {image["path"]: image["expected_preimage_sha256"] for image in postimages} != correction.expected_preimages(lookup, scope):
            raise invalid
    branch = metadata["branch"]
    if branch is not None and not _valid_branch_name(branch):
        raise invalid
    publication = metadata["publication"]
    if publication is not None:
        if not isinstance(publication, Mapping):
            raise invalid
        if frozenset(publication.keys()) != _KNOWLEDGE_PUBLICATION_KEYS:
            raise invalid
        if publication["repository"] != REPOSITORY:
            raise invalid
        if not _is_commit_id(publication["commit"]):
            raise invalid
        images = publication["postimages"]
        if not isinstance(images, list) or len(images) != count:
            raise invalid
        for image in images:
            if not isinstance(image, Mapping):
                raise invalid
            if frozenset(image.keys()) != _KNOWLEDGE_PUBLICATION_IMAGE_KEYS:
                raise invalid
            if not isinstance(image["path"], str) or not _valid_repo_path(image["path"]):
                raise invalid
            if not _is_hex64(image["content_sha256"]):
                raise invalid
    proposal = metadata["proposal"]
    if proposal is not None:
        if not isinstance(proposal, Mapping):
            raise invalid
        if frozenset(proposal.keys()) != _RECEIPT_KEYS:
            raise invalid
        number = proposal["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise invalid
        if not isinstance(proposal["url"], str) or not proposal["url"]:
            raise invalid
        if not _is_hex40(proposal["head_commit"]):
            raise invalid
        if not isinstance(proposal["head_branch"], str):
            raise invalid
    return metadata


def _knowledge_publication_proof(metadata: Mapping[str, Any]) -> Optional[dict]:
    """The owner-retained source-observed publication proof, when it matches.

    Returns the retained publication mapping only when it binds the original
    canonical postimage hashes; anything else is not SOURCE_PUBLISHED proof.
    """
    publication = metadata.get("publication")
    if not isinstance(publication, Mapping):
        return None
    if metadata.get("phase") != KNOWLEDGE_PHASE_SOURCE_PUBLISHED:
        return None
    images = publication.get("postimages")
    count = 3 if metadata.get("identity", {}).get("action") == correction.ACTION else 2
    if not isinstance(images, list) or len(images) != count:
        return None
    observed = [(image["path"], image["content_sha256"]) for image in images]
    retained = [
        (image["path"], image["content_sha256"])
        for image in metadata.get("postimages", [])
    ]
    if sorted(observed) != sorted(retained):
        return None
    return {
        "repository": publication["repository"],
        "commit": publication["commit"],
        "postimages": [
            {"path": image["path"], "content_sha256": image["content_sha256"]}
            for image in images
        ],
    }


# --------------------------------------------------------------------------- #
# Control-flow signals (never expose raw exception text in public results)
# --------------------------------------------------------------------------- #


class _Refusal(Exception):
    """A closed, deterministic refusal."""

    def __init__(self, state: str, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason


class _Unknown(Exception):
    """A write was attempted and its outcome is unknown."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --------------------------------------------------------------------------- #
# Pull-request owner seam contract
# --------------------------------------------------------------------------- #


class PrOwnerError(Exception):
    """Base class for typed pull-request seam outcomes."""


class PrLookupMissing(PrOwnerError):
    """No matching pull request exists (a definitive negative read)."""


class PrLookupAmbiguous(PrOwnerError):
    """The pull-request lookup could not resolve to exactly one PR."""


class PrLookupForeign(PrOwnerError):
    """A matching PR exists but belongs to a different payload/branch."""


class PrOwnerRefused(PrOwnerError):
    """A closed refusal: the PR was definitely not created."""


class PrOwnerUnknownOutcome(PrOwnerError):
    """A PR write was attempted and its outcome is unknown."""


# --------------------------------------------------------------------------- #
# Server-owned immutable binding
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PublisherBinding:
    """Immutable, server-owned publisher binding.

    Constructed and held by the operator, never by a caller of ``publish``.
    ``repository`` is fixed; ``worktree`` must be an absolute, non-symlink path
    to an existing isolated Git clone; ``expected_origin`` must be the exact
    verified Git remote URL; ``default_branch`` is a fixed qualified branch
    name; ``publisher_identity`` is the server's receipt/digest for this
    publisher and is never exposed in a public result.
    """

    worktree: str
    expected_origin: str
    default_branch: str
    publisher_identity: str
    repository: str = REPOSITORY

    def __post_init__(self) -> None:
        if self.repository != REPOSITORY:
            raise ValueError("binding repository is fixed to %s" % REPOSITORY)
        worktree = self.worktree
        if not isinstance(worktree, str) or not worktree:
            raise ValueError("worktree must be a non-empty absolute path")
        if not os.path.isabs(worktree):
            raise ValueError("worktree must be an absolute path")
        if os.path.islink(worktree):
            raise ValueError("symlinked worktree is not accepted")
        if not isinstance(self.expected_origin, str) or not self.expected_origin:
            raise ValueError("expected_origin must be a non-empty remote URL string")
        if not _valid_branch_name(self.default_branch):
            raise ValueError("default_branch must be a qualified branch name")
        if not isinstance(self.publisher_identity, str) or not self.publisher_identity:
            raise ValueError("publisher_identity receipt/digest is required")

    @property
    def short_repository(self) -> str:
        return self.repository.rsplit("/", 1)[-1]

    @property
    def fingerprint(self) -> str:
        payload = "\x1f".join(
            (
                self.worktree,
                self.expected_origin,
                self.default_branch,
                self.publisher_identity,
                self.repository,
            )
        )
        return _sha256_hex(payload.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Per-operation bookkeeping
# --------------------------------------------------------------------------- #


class _Operation:
    """Tracks one publish/reconcile operation's context and effect horizon."""

    def __init__(self, binding: PublisherBinding) -> None:
        self.binding_fingerprint = binding.fingerprint
        self.request_sha256: Optional[str] = None
        self.work_ref: Optional[str] = None
        self.branch: Optional[str] = None
        self.zero_id = _SHA1_ZERO
        self.effects_started = False
        # Knowledge operations carry the closed body-free selection, the actual
        # nonpublic claim and the retained metadata for guard re-checks.
        self.mode = "create"
        self.lookup: Optional[dict] = None
        self.claim: Any = None
        self.metadata: Optional[Mapping[str, Any]] = None
        self.recipe_fingerprint: Optional[str] = None

    def context(
        self, request_sha256: str, work_ref: str, branch: str
    ) -> None:
        self.request_sha256 = request_sha256
        self.work_ref = work_ref
        self.branch = branch

    def mark_effect(self) -> None:
        self.effects_started = True


# --------------------------------------------------------------------------- #
# The publisher
# --------------------------------------------------------------------------- #


class FixedProjectGitPublisher:
    """Publish exactly one canonical workspace-project file and one PR.

    All policy seams are injected by the installed owner; nothing here invents a
    credential, a GitHub call, a ledger, a queue, a scheduler or an authority.
    """

    def __init__(
        self,
        binding: PublisherBinding,
        compile_proposal: Callable[[Any], Mapping[str, Any]],
        authorize: Callable[[Any], bool],
        permission_stamp: Callable[[Any], str],
        qualify_publisher: Callable[[PublisherBinding], bool],
        pr_owner: Any,
        *,
        git_binary: str = "git",
        command_timeout: float = 30.0,
        principal_scope: Callable[[Any], str],
        authorize_knowledge: Optional[Callable[[Any, str, str], bool]] = None,
        knowledge_permission_stamp: Optional[Callable[[Any, str, str], str]] = None,
        load_original_operation: Optional[Callable[[Any, Mapping[str, Any]], Any]] = None,
        validate_original_claim: Optional[Callable[[Any, Mapping[str, Any], Any, Mapping[str, Any]], bool]] = None,
        authorize_plan_adoption: Optional[Callable[..., bool]] = None,
        plan_adoption_permission_stamp: Optional[Callable[..., str]] = None,
        load_plan_adoption_operation: Optional[Callable[..., Any]] = None,
        validate_plan_adoption_claim: Optional[Callable[..., bool]] = None,
        authorize_plan_proposal: Optional[Callable[..., bool]] = None,
        plan_proposal_permission_stamp: Optional[Callable[..., str]] = None,
        load_plan_proposal_operation: Optional[Callable[..., Any]] = None,
        validate_plan_proposal_claim: Optional[Callable[..., bool]] = None,
        canonical_data_macro_root: Optional[str] = None,
        canonical_data_code_commit: Optional[str] = None,
        authorize_workspace_read: Optional[Callable[..., bool]] = None,
        workspace_read_permission_stamp: Optional[Callable[..., str]] = None,
        authorize_latest_project_data: Optional[Callable[..., bool]] = None,
        latest_project_data_permission_stamp: Optional[Callable[..., str]] = None,
        canonical_data_publication: Optional[Callable[..., Any]] = None,
        canonical_data_events: Any = None,
    ) -> None:
        if not isinstance(binding, PublisherBinding):
            raise TypeError("PublisherBinding instance is required")
        self._binding = binding
        self._principal_scope = _require_callable(principal_scope, "principal_scope")
        self._compile_proposal = _require_callable(compile_proposal, "compile_proposal")
        self._authorize = _require_callable(authorize, "authorize")
        self._permission_stamp = _require_callable(permission_stamp, "permission_stamp")
        self._qualify_publisher = _require_callable(qualify_publisher, "qualify_publisher")
        if isinstance(pr_owner, (str, bytes, bytearray, Mapping)):
            raise TypeError(
                "pr_owner must be an injected service composition seam with find/create"
            )
        find = getattr(pr_owner, "find", None)
        create = getattr(pr_owner, "create", None)
        _require_callable(find, "pr_owner.find")
        _require_callable(create, "pr_owner.create")
        self._pr_find = find
        self._pr_create = create
        # Optional private knowledge seams.  They are captured with their own
        # identities and are never replaced by the CREATE authorizer/stamp.
        self._authorize_knowledge = None
        self._knowledge_permission_stamp = None
        self._load_original_operation = None
        self._validate_original_claim = None
        knowledge_seams = {
            "authorize_knowledge": authorize_knowledge,
            "knowledge_permission_stamp": knowledge_permission_stamp,
            "load_original_operation": load_original_operation,
            "validate_original_claim": validate_original_claim,
        }
        for name, seam in knowledge_seams.items():
            if seam is not None:
                _require_callable(seam, name)
        self._authorize_knowledge = knowledge_seams["authorize_knowledge"]
        self._knowledge_permission_stamp = knowledge_seams["knowledge_permission_stamp"]
        self._load_original_operation = knowledge_seams["load_original_operation"]
        self._validate_original_claim = knowledge_seams["validate_original_claim"]
        self._knowledge_ready = all(seam is not None for seam in knowledge_seams.values())
        from control_plane.project_plan_adoption_git import PlanAdoptionGitMode
        self._plan_adoption = PlanAdoptionGitMode(self,
            authorize=authorize_plan_adoption, stamp=plan_adoption_permission_stamp,
            load=load_plan_adoption_operation, claim=validate_plan_adoption_claim)
        from control_plane.project_plan_proposal_git import PlanProposalGitMode
        self._plan_proposal = PlanProposalGitMode(self, authorize=authorize_plan_proposal,
            stamp=plan_proposal_permission_stamp, load=load_plan_proposal_operation, claim=validate_plan_proposal_claim)
        from control_plane.project_canonical_data import CanonicalProjectDataMode
        self._canonical_data = CanonicalProjectDataMode(self, pinned_macro_root=canonical_data_macro_root,
            code_commit=canonical_data_code_commit, authorize_read=authorize_workspace_read,
            read_stamp=workspace_read_permission_stamp, authorize_data=authorize_latest_project_data,
            data_stamp=latest_project_data_permission_stamp, publication=canonical_data_publication, events=canonical_data_events)
        if not isinstance(git_binary, str) or not git_binary:
            raise TypeError("git_binary must be a non-empty string")
        self._git_binary = git_binary
        if not isinstance(command_timeout, (int, float)) or command_timeout <= 0:
            raise ValueError("command_timeout must be a positive number of seconds")
        self._command_timeout = float(command_timeout)
        # Captured seam identities, re-checked before every write.
        self._seam_identities = {
            "principal_scope": _callable_identity(self._principal_scope),
            "compile_proposal": _callable_identity(self._compile_proposal),
            "authorize": _callable_identity(self._authorize),
            "permission_stamp": _callable_identity(self._permission_stamp),
            "qualify_publisher": _callable_identity(self._qualify_publisher),
            "pr_find": _callable_identity(self._pr_find),
            "pr_create": _callable_identity(self._pr_create),
            "binding": binding.fingerprint,
            "authorize_knowledge": (
                None
                if self._authorize_knowledge is None
                else _callable_identity(self._authorize_knowledge)
            ),
            "knowledge_permission_stamp": (
                None
                if self._knowledge_permission_stamp is None
                else _callable_identity(self._knowledge_permission_stamp)
            ),
            "load_original_operation": (
                None
                if self._load_original_operation is None
                else _callable_identity(self._load_original_operation)
            ),
            "validate_original_claim": (
                None
                if self._validate_original_claim is None
                else _callable_identity(self._validate_original_claim)
            ),
        }
        # No I/O of any kind happens in the constructor.

    # -- public surface ---------------------------------------------------- #

    def publish(self, request: Any, principal: Any) -> Mapping[str, Any]:
        """Publish the request.  No path/branch/remote/actor/credential options."""
        return self._operate(request, principal, allow_effects=True)

    def reconcile(self, request: Any, principal: Any) -> Mapping[str, Any]:
        """READ-ONLY reconciliation: query existing branch/PR/default source.

        Never launches a retry, never pushes, never creates a PR, never builds
        an object.  Returns the same closed result schema with the honest rung.
        """
        return self._operate(request, principal, allow_effects=False)

    def observe_canonical_project_data(self, principal, *, work_ref=None, deadline=None):
        return self._canonical_data.observe(principal, work_ref=work_ref,
            **({"deadline": deadline} if deadline is not None else {}))

    def publish_plan_proposal(self, request, recipe, principal, *, claim):
        return self._plan_proposal.operate(request, recipe, principal, phase="PUBLICATION", claim=claim)

    def reconcile_plan_proposal(self, lookup, principal):
        return self._plan_proposal.operate(lookup, None, principal, phase="PUBLICATION", claim=None, reconcile=True)

    def publish_plan_adoption(self, request, recipe, principal, *, phase, claim):
        """Distinct ADOPT action over this same fixed Git/PR transport."""
        return self._plan_adoption.operate(request, recipe, principal, phase=phase, claim=claim)

    def reconcile_plan_adoption(self, original_lookup, principal, *, phase):
        """Observe the original committed phase only; no compile, claim or write."""
        return self._plan_adoption.operate(original_lookup, None, principal,
                                           phase=phase, claim=None, reconcile=True)

    def publish_knowledge(
        self,
        request: Any,
        recipe: Any,
        principal: Any,
        *,
        claim: Any,
    ) -> Mapping[str, Any]:
        """Publish one atomic knowledge postimage pair under an actual claim.

        ``recipe`` is private canonical compiler output.  ``claim`` is the
        actual private common-Runtime durable-phase-CAS permit supplied by the
        integrating engine; it is passed through to the claim validator and is
        never issued, retried, serialized or published here.
        """
        op = _Operation(self._binding)
        op.mode = "knowledge"
        try:
            return self._run_knowledge(
                request, recipe, principal, claim, op, allow_effects=True
            )
        except (ValueError, TypeError):
            # Internal schema drift must never be laundered into a result.
            raise
        except _Refusal as refusal:
            return self._knowledge_result(
                (
                    STATE_EFFECT_UNKNOWN
                    if op.effects_started and refusal.state == STATE_NOT_DISPATCHED
                    else refusal.state
                ),
                op=op,
                source=None,
                proposal=None,
                reason=refusal.reason,
            )
        except _Unknown as unknown:
            return self._knowledge_result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason=unknown.reason,
            )
        except PrOwnerError:
            if op.effects_started:
                return self._knowledge_result(
                    STATE_EFFECT_UNKNOWN,
                    op=op,
                    source=None,
                    proposal=None,
                    reason="PR_CREATION_UNKNOWN",
                )
            return self._knowledge_result(
                STATE_NOT_DISPATCHED,
                op=op,
                source=None,
                proposal=None,
                reason="PR_LOOKUP_FAILED",
            )
        except Exception:
            if op.effects_started:
                return self._knowledge_result(
                    STATE_EFFECT_UNKNOWN,
                    op=op,
                    source=None,
                    proposal=None,
                    reason="GIT_WRITE_UNKNOWN",
                )
            return self._knowledge_result(
                STATE_NOT_DISPATCHED,
                op=op,
                source=None,
                proposal=None,
                reason="GIT_INVOCATION_FAILED",
            )

    def reconcile_knowledge(
        self, lookup: Any, principal: Any
    ) -> Mapping[str, Any]:
        """READ-ONLY knowledge reconciliation from the body-free selection.

        Uses only the retained original metadata/selection, the current actual
        action grant/principal/qualifier, and Git/PR observation.  It never
        recompiles, never reads current source content, never rebuilds an
        object, never pushes, never creates a PR and never claims again.
        """
        op = _Operation(self._binding)
        op.mode = "knowledge"
        try:
            return self._reconcile_knowledge_run(lookup, principal, op)
        except (ValueError, TypeError):
            raise
        except _Refusal as refusal:
            return self._knowledge_result(
                refusal.state,
                op=op,
                source=None,
                proposal=None,
                reason=refusal.reason,
            )
        except _Unknown as unknown:
            return self._knowledge_result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason=unknown.reason,
            )
        except PrOwnerError:
            return self._knowledge_result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason="PR_LOOKUP_UNKNOWN",
            )
        except Exception:
            return self._knowledge_result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason="GIT_INVOCATION_FAILED",
            )

    # -- internal driver --------------------------------------------------- #

    def _operate(
        self, request: Any, principal: Any, *, allow_effects: bool
    ) -> Mapping[str, Any]:
        op = _Operation(self._binding)
        try:
            return self._run(request, principal, allow_effects, op)
        except (ValueError, TypeError):
            # Internal schema drift must never be laundered into a result.
            raise
        except _Refusal as refusal:
            return self._result(
                STATE_EFFECT_UNKNOWN if op.effects_started and refusal.state == STATE_NOT_DISPATCHED else refusal.state,
                op=op,
                source=None,
                proposal=None,
                reason=refusal.reason,
            )
        except _Unknown as unknown:
            return self._result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason=unknown.reason,
            )
        except PrOwnerError:
            # A typed seam error that escaped mapping is treated fail-closed.
            if op.effects_started:
                return self._result(
                    STATE_EFFECT_UNKNOWN,
                    op=op,
                    source=None,
                    proposal=None,
                    reason="PR_CREATION_UNKNOWN",
                )
            return self._result(
                STATE_NOT_DISPATCHED,
                op=op,
                source=None,
                proposal=None,
                reason="PR_LOOKUP_FAILED",
            )
        except Exception:
            # Bounded mapping only: no exception text, traceback or payload ever
            # reaches a public result.
            if op.effects_started:
                return self._result(
                    STATE_EFFECT_UNKNOWN,
                    op=op,
                    source=None,
                    proposal=None,
                    reason="GIT_WRITE_UNKNOWN",
                )
            return self._result(
                STATE_NOT_DISPATCHED,
                op=op,
                source=None,
                proposal=None,
                reason="GIT_INVOCATION_FAILED",
            )

    def _run(
        self,
        request: Any,
        principal: Any,
        allow_effects: bool,
        op: _Operation,
    ) -> Mapping[str, Any]:
        if request is None or principal is None:
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        self._require_seams()
        stamp = self._authorize_and_stamp(principal)
        self._require_qualifier()

        envelope = self._compile(request)
        _validate_envelope(envelope)
        request_sha256 = envelope["request_sha256"]
        work_ref = envelope["work_ref"]
        path = envelope["path"]
        scope = self._principal_scope(principal)
        if not _is_hex64(scope):
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        identity = json.dumps({"principal_scope": scope, "request_id": envelope["request_id"], "work_ref": work_ref}, sort_keys=True, separators=(",", ":")).encode()
        branch = BRANCH_PREFIX + _sha256_hex(identity)
        op.context(request_sha256, work_ref, branch)
        content_bytes = envelope["content_utf8"].encode("utf-8")
        expected_commit = envelope["expected_commit"]
        op.principal, op.stamp, op.scope, op.expected_commit = principal, stamp, scope, expected_commit

        object_format = self._check_worktree(op)
        if object_format != "sha1":
            raise _Refusal(STATE_NOT_DISPATCHED, "WORKTREE_INVALID")
        op.zero_id = _SHA1_ZERO

        # Fresh upstream default readback decides the publication rungs first.
        default_commit = self._resolve_default_commit(op)
        default_blob = self._read_blob_at(op, default_commit, path)
        if default_blob is not None:
            if (
                _sha256_hex(default_blob) == envelope["content_sha256"]
                and default_blob == content_bytes
            ):
                return self._project_created(op, default_commit, envelope)
            raise _Refusal(STATE_CONFLICT, "DEFAULT_BYTES_CONFLICT")
        if not allow_effects:
            return self._reconcile_only(op, envelope, content_bytes, default_commit)
        # Existing operation evidence is a reconciliation boundary, never a
        # reason to repeat push/PR creation after refusal or uncertain outcome.
        existing = self._local_branch_commit(op, branch) or self._remote_branch_commit(op, branch)
        existing_pr = self._lookup_pull_request(op, branch, request_sha256, existing)
        if existing is not None or existing_pr is not None:
            return self._reconcile_only(op, envelope, content_bytes, default_commit)
        if default_commit != expected_commit:
            raise _Refusal(STATE_NOT_DISPATCHED, "STALE_EXPECTED_COMMIT")
        self._require_path_absent_in_base(op, expected_commit, path)

        prepared_commit = self._build_commit(op, envelope, content_bytes)
        commit_id = self._claim_local_branch(
            op, principal, stamp, prepared_commit, envelope, content_bytes
        )

        remote_commit = self._remote_branch_commit(op, branch)
        if remote_commit is None:
            remote_commit = self._push_branch(
                op, principal, stamp, branch, commit_id, envelope, content_bytes
            )
        else:
            remote_commit = self._verify_remote_branch(
                op, branch, remote_commit, envelope, content_bytes, commit_id
            )

        receipt = self._ensure_pull_request(
            op, principal, stamp, branch, envelope, commit_id
        )

        # Final read-only default check: only an exact canonical readback may
        # upgrade the claim to PROJECT_CREATED.
        default_commit = self._resolve_default_commit(op)
        default_blob = self._read_blob_at(op, default_commit, path)
        if (
            default_blob is not None
            and default_blob == content_bytes
            and _sha256_hex(default_blob) == envelope["content_sha256"]
        ):
            return self._project_created(op, default_commit, envelope, proposal=receipt)
        return self._result(
            STATE_PROPOSAL_PUBLISHED,
            op=op,
            source=None,
            proposal=receipt,
            reason=None,
        )

    # -- knowledge driver -------------------------------------------------- #

    def _run_knowledge(
        self,
        request: Any,
        recipe: Any,
        principal: Any,
        claim: Any,
        op: _Operation,
        *,
        allow_effects: bool,
    ) -> Mapping[str, Any]:
        if request is None or recipe is None or principal is None or claim is None:
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        self._require_knowledge_seams()
        self._require_seams()
        lookup = _knowledge_request_lookup(request)
        _validate_knowledge_recipe(recipe, lookup)
        op.lookup = lookup
        op.recipe_fingerprint = recipe["request_fingerprint"]
        scope = self._principal_scope(principal)
        if not _is_hex64(scope):
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        if self._authorize_knowledge(principal, lookup["action"], lookup["work_ref"]) is not True:
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        stamp = self._knowledge_permission_stamp(principal, lookup["action"], lookup["work_ref"])
        if not _is_hex64(stamp):
            raise _Refusal(STATE_NOT_DISPATCHED, "PERMISSION_STAMP_INVALID")
        self._require_qualifier()

        metadata = self._load_knowledge_operation(principal, lookup)
        if metadata is None:
            # A missing original operation is never a reason to dispatch.
            raise _Refusal(STATE_NOT_DISPATCHED, "OPERATION_MISSING")
        _validate_knowledge_operation_metadata(metadata, lookup, scope)
        if metadata["recipe_fingerprint_sha256"] != recipe["request_fingerprint"]:
            raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")
        if metadata["permission_binding_digest"] != recipe["permission_binding_digest"]:
            raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")
        if metadata["permission_binding_digest"] != stamp:
            raise _Refusal(STATE_NOT_DISPATCHED, "AUTHORIZATION_REVOKED")
        if sorted(_knowledge_postimage_digests(metadata["postimages"])) != sorted(
            _knowledge_postimage_digests(recipe["postimages"])
        ):
            raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")

        # Only the fixed derived paths are writable, derived from the actual
        # current principal scope -- never from a caller-supplied path.
        file_id = _sha256_hex(
            _canonical_json(
                {
                    "principal_scope": scope,
                    "request_id": lookup["request_id"],
                    "work_ref": lookup["work_ref"],
                }
            ).encode("utf-8")
        )
        expected_paths = _knowledge_expected_paths(lookup, request, file_id)
        if sorted(image["path"] for image in recipe["postimages"]) != sorted(expected_paths):
            raise _Refusal(STATE_NOT_DISPATCHED, "RECIPE_INVALID")
        record = _knowledge_action_record(lookup["action"])
        if record["action"] == KNOWLEDGE_ACTION_FILE_ADD:
            media_path = expected_paths[0]
            media_postimage = next(
                image for image in recipe["postimages"] if image["path"] == media_path
            )
            request_bytes = request["file"]["content_utf8"].encode("utf-8")
            if media_postimage["content_utf8"].encode("utf-8") != request_bytes:
                # The media postimage must be the actual public request content.
                raise _Refusal(STATE_NOT_DISPATCHED, "RECIPE_INVALID")

        branch = KNOWLEDGE_BRANCH_PREFIX + _sha256_hex(
            _canonical_json(
                {
                    "principal_scope": scope,
                    "action": lookup["action"],
                    "request_id": lookup["request_id"],
                }
            ).encode("utf-8")
        )
        if metadata["branch"] is not None and metadata["branch"] != branch:
            raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")
        op.context(lookup["request_sha256"], lookup["work_ref"], branch)
        op.principal, op.stamp, op.scope, op.expected_commit = (
            principal,
            stamp,
            scope,
            metadata["expected_commit"],
        )
        op.claim = claim
        op.metadata = metadata

        object_format = self._check_worktree(op)
        if object_format != "sha1":
            raise _Refusal(STATE_NOT_DISPATCHED, "WORKTREE_INVALID")
        op.zero_id = _SHA1_ZERO

        # Retained owner-observed publication proof is terminal and survives
        # any later default change.
        proof = _knowledge_publication_proof(metadata)
        if proof is not None:
            return self._knowledge_source_published(
                op, proof["commit"], proof, require_default_match=False
            )

        default_commit = self._resolve_default_commit(op)
        if self._default_carries_postimages(op, default_commit, metadata):
            return self._knowledge_source_published(
                op, default_commit, self._knowledge_publication(metadata, default_commit), require_default_match=True
            )
        if default_commit != metadata["expected_commit"]:
            raise _Refusal(STATE_NOT_DISPATCHED, "STALE_EXPECTED_COMMIT")
        self._verify_knowledge_preimages_at_base(
            op, metadata["expected_commit"], recipe["postimages"]
        )
        if not allow_effects or metadata["phase"] != KNOWLEDGE_PHASE_CLAIMED:
            # Only the durable CLAIMED phase can begin effects; anything else is
            # read-only reconciliation of the actual rung.
            return self._reconcile_only_knowledge(op, metadata, default_commit)
        if self._validate_original_claim(principal, lookup, claim, metadata) is not True:
            raise _Refusal(STATE_NOT_DISPATCHED, "CLAIM_INVALID")
        # Existing operation evidence is a reconciliation boundary, never a
        # reason to repeat push/PR creation after refusal or uncertain outcome.
        existing = self._local_branch_commit(op, branch) or self._remote_branch_commit(op, branch)
        existing_pr = self._lookup_pull_request(op, branch, lookup["request_sha256"], existing)
        if existing is not None or existing_pr is not None:
            return self._reconcile_only_knowledge(op, metadata, default_commit)

        prepared_commit = self._build_knowledge_commit(op, recipe, lookup)
        commit_id = self._claim_local_branch_knowledge(op, principal, stamp, prepared_commit, recipe, lookup)

        remote_commit = self._remote_branch_commit(op, branch)
        if remote_commit is None:
            remote_commit = self._push_knowledge_branch(
                op, principal, stamp, branch, commit_id, recipe, lookup
            )
        else:
            remote_commit = self._verify_knowledge_remote_branch(
                op, branch, remote_commit, recipe, lookup, commit_id
            )

        receipt = self._ensure_pull_request_knowledge(
            op, principal, stamp, branch, lookup, commit_id
        )

        # Final read-only default check: only an exact canonical two-postimage
        # readback in one verified tree may upgrade to SOURCE_PUBLISHED.
        default_commit = self._resolve_default_commit(op)
        if self._default_carries_postimages(op, default_commit, metadata):
            return self._knowledge_source_published(
                op,
                default_commit,
                self._knowledge_publication(metadata, default_commit),
                require_default_match=True,
                proposal=receipt,
            )
        return self._knowledge_result(
            STATE_PROPOSAL_PUBLISHED,
            op=op,
            source=None,
            proposal=receipt,
            reason=None,
        )

    def _reconcile_knowledge_run(
        self, lookup: Any, principal: Any, op: _Operation
    ) -> Mapping[str, Any]:
        if lookup is None or principal is None:
            raise _Refusal(STATE_NOT_DISPATCHED, "REQUEST_INVALID")
        self._require_knowledge_seams()
        self._require_seams()
        lookup = _validate_knowledge_lookup(lookup)
        op.lookup = lookup
        scope = self._principal_scope(principal)
        if not _is_hex64(scope):
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        if self._authorize_knowledge(principal, lookup["action"], lookup["work_ref"]) is not True:
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        op.stamp = self._knowledge_permission_stamp(principal, lookup["action"], lookup["work_ref"])
        if not _is_hex64(op.stamp):
            raise _Refusal(STATE_NOT_DISPATCHED, "PERMISSION_STAMP_INVALID")
        self._require_qualifier()

        metadata = self._load_knowledge_operation(principal, lookup)
        if metadata is None:
            # Missing retained metadata after a possible effect stays unknown;
            # it is never proof of no effect and never retry authority.
            raise _Unknown("NO_EXISTING_PUBLICATION")
        _validate_knowledge_operation_metadata(metadata, lookup, scope)
        op.recipe_fingerprint = metadata["recipe_fingerprint_sha256"]
        branch = KNOWLEDGE_BRANCH_PREFIX + _sha256_hex(
            _canonical_json(
                {
                    "principal_scope": scope,
                    "action": lookup["action"],
                    "request_id": lookup["request_id"],
                }
            ).encode("utf-8")
        )
        if metadata["branch"] is not None and metadata["branch"] != branch:
            raise _Refusal(STATE_CONFLICT, "OPERATION_CONFLICT")
        op.context(lookup["request_sha256"], lookup["work_ref"], branch)
        op.principal, op.scope = principal, scope
        op.expected_commit = metadata["expected_commit"]
        op.metadata = metadata
        op.claim = None

        object_format = self._check_worktree(op)
        if object_format != "sha1":
            raise _Refusal(STATE_NOT_DISPATCHED, "WORKTREE_INVALID")
        op.zero_id = _SHA1_ZERO

        default_commit = self._resolve_default_commit(op)
        return self._reconcile_only_knowledge(op, metadata, default_commit)

    # -- seams ------------------------------------------------------------- #

    def _require_seams(self) -> None:
        current = {
            "principal_scope": _callable_identity(self._principal_scope),
            "compile_proposal": _callable_identity(self._compile_proposal),
            "authorize": _callable_identity(self._authorize),
            "permission_stamp": _callable_identity(self._permission_stamp),
            "qualify_publisher": _callable_identity(self._qualify_publisher),
            "pr_find": _callable_identity(self._pr_find),
            "pr_create": _callable_identity(self._pr_create),
            "binding": self._binding.fingerprint,
            "authorize_knowledge": (
                None
                if self._authorize_knowledge is None
                else _callable_identity(self._authorize_knowledge)
            ),
            "knowledge_permission_stamp": (
                None
                if self._knowledge_permission_stamp is None
                else _callable_identity(self._knowledge_permission_stamp)
            ),
            "load_original_operation": (
                None
                if self._load_original_operation is None
                else _callable_identity(self._load_original_operation)
            ),
            "validate_original_claim": (
                None
                if self._validate_original_claim is None
                else _callable_identity(self._validate_original_claim)
            ),
        }
        if current != self._seam_identities:
            raise _Refusal(STATE_NOT_DISPATCHED, "SEAM_IDENTITY_CHANGED")

    def _require_knowledge_seams(self) -> None:
        """Knowledge methods deny when the private knowledge seams are absent.

        There is no fallback to the CREATE authorizer or stamp: without the
        actual action/work authorizer, stamp, retained-operation reader and
        claim validator the knowledge surface performs nothing.
        """
        if not self._knowledge_ready:
            raise _Refusal(STATE_NOT_DISPATCHED, "KNOWLEDGE_SEAMS_ABSENT")

    def _authorize_and_stamp(self, principal: Any, op: Optional[_Operation] = None) -> str:
        if op is not None and op.mode == "canonical_data":
            return self._canonical_data.permission(principal, op)
        if op is not None and op.mode == "plan_proposal":
            return self._plan_proposal.permission(principal, op)
        if op is not None and op.mode == "plan_adoption":
            return self._plan_adoption.permission(principal, op)
        if op is not None and op.mode == "knowledge":
            if self._authorize_knowledge(
                principal, op.lookup["action"], op.lookup["work_ref"]
            ) is not True:
                raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
            stamp = self._knowledge_permission_stamp(principal, op.lookup["action"], op.lookup["work_ref"])
            if not _is_hex64(stamp):
                raise _Refusal(STATE_NOT_DISPATCHED, "PERMISSION_STAMP_INVALID")
            return stamp
        if self._authorize(principal) is not True:
            raise _Refusal(STATE_NOT_DISPATCHED, "UNAUTHORIZED")
        stamp = self._permission_stamp(principal)
        if not _is_hex64(stamp):
            raise _Refusal(STATE_NOT_DISPATCHED, "PERMISSION_STAMP_INVALID")
        return stamp

    def _require_qualifier(self) -> None:
        if self._qualify_publisher(self._binding) is not True:
            raise _Refusal(STATE_NOT_DISPATCHED, "QUALIFIER_REFUSED")

    def _prewrite_guard(self, op: _Operation, principal: Any, stamp: str) -> None:
        """Recheck authorization, stamp, qualifier, identities and origin.

        Called immediately before every Git/PR write.  After any write has been
        attempted a guard failure can no longer produce a clean refusal, so it
        becomes EFFECT_UNKNOWN instead of a false clear.  Knowledge operations
        additionally recheck the retained original operation and the actual
        nonpublic durable-phase claim.
        """
        try:
            self._require_seams()
            current = self._authorize_and_stamp(principal, op)
            self._require_qualifier()
            if current != stamp or self._principal_scope(principal) != op.scope:
                raise _Refusal(STATE_NOT_DISPATCHED, "AUTHORIZATION_REVOKED")
            if self._origin_url(op) != self._binding.expected_origin:
                raise _Refusal(STATE_NOT_DISPATCHED, "ORIGIN_MISMATCH")
            if self._remote_branch_commit(op, self._binding.default_branch) != op.expected_commit:
                raise _Refusal(STATE_NOT_DISPATCHED, "STALE_EXPECTED_COMMIT")
            if op.mode == "plan_proposal":
                self._plan_proposal.prewrite(op)
            if op.mode == "plan_adoption":
                self._plan_adoption.prewrite(op)
            if op.mode == "knowledge":
                fresh = self._load_knowledge_operation(principal, op.lookup)
                if fresh is None:
                    raise _Refusal(STATE_NOT_DISPATCHED, "OPERATION_MISSING")
                _validate_knowledge_operation_metadata(fresh, op.lookup, op.scope)
                if fresh != op.metadata or fresh["phase"] != KNOWLEDGE_PHASE_CLAIMED:
                    raise _Refusal(STATE_NOT_DISPATCHED, "PHASE_NOT_CLAIMED")
                if fresh["permission_binding_digest"] != stamp:
                    raise _Refusal(STATE_NOT_DISPATCHED, "AUTHORIZATION_REVOKED")
                if self._validate_original_claim(
                    principal, op.lookup, op.claim, fresh
                ) is not True:
                    raise _Refusal(STATE_NOT_DISPATCHED, "CLAIM_INVALID")
        except _Refusal:
            if op.effects_started:
                raise _Unknown("AUTHORIZATION_REVOKED") from None
            raise
        except _Unknown:
            raise
        except Exception:
            if op.effects_started:
                raise _Unknown("GIT_WRITE_UNKNOWN") from None
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED") from None

    def _compile(self, request: Any) -> Mapping[str, Any]:
        try:
            return self._compile_proposal(request)
        except Exception:
            raise _Refusal(STATE_NOT_DISPATCHED, "COMPILE_REFUSED") from None

    def _load_knowledge_operation(
        self, principal: Any, lookup: Mapping[str, Any]
    ) -> Any:
        """Read the retained original operation through the private seam."""
        try:
            return self._load_original_operation(principal, lookup)
        except _Refusal:
            raise
        except _Unknown:
            raise
        except Exception:
            raise _Unknown("OPERATION_UNKNOWN") from None

    # -- git primitives ---------------------------------------------------- #

    def _git(
        self,
        args: "list[str]",
        op: _Operation,
        *,
        stdin_bytes: Optional[bytes] = None,
        index_file: Optional[str] = None,
        bounded: bool = False,
    ) -> "subprocess.CompletedProcess":
        """Run one normal git command with a fixed argv (no shell)."""
        argv = [self._git_binary, "--no-replace-objects"] + list(args)
        env = dict(os.environ)
        for key in tuple(env):
            if key in {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_NAMESPACE", "GIT_SHALLOW_FILE", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"} or key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")):
                env.pop(key, None)
        env["GIT_NO_REPLACE_OBJECTS"] = "1"
        if op.mode == "canonical_data":
            env["GIT_NO_LAZY_FETCH"] = "1"
        if index_file is not None:
            env["GIT_INDEX_FILE"] = index_file
        timeout = self._command_timeout
        if hasattr(op, "read_deadline"):
            remaining = op.read_deadline - time.monotonic()
            if remaining <= 0:
                raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
            timeout = min(timeout, remaining)
        try:
            completed = subprocess.run(
                argv,
                cwd=self._binding.worktree,
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            if bounded:
                raise _Unknown("GIT_WRITE_UNKNOWN") from None
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED") from None
        except OSError:
            if bounded:
                raise _Unknown("GIT_WRITE_UNKNOWN") from None
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED") from None
        return completed

    def _origin_url(self, op: _Operation) -> str:
        observed = []
        for args in (["remote", "get-url", "--all", "origin"], ["remote", "get-url", "--push", "--all", "origin"]):
            completed = self._git(args, op)
            values = completed.stdout.decode("utf-8", "surrogateescape").splitlines()
            if completed.returncode != 0 or values != [self._binding.expected_origin]:
                raise _Refusal(STATE_NOT_DISPATCHED, "ORIGIN_MISMATCH")
            observed.append(values[0])
        return observed[0]

    def _check_worktree(self, op: _Operation) -> str:
        """Verify the worktree is a real Git worktree with the expected origin."""
        binding = self._binding
        if os.path.islink(binding.worktree) or not os.path.isdir(binding.worktree):
            raise _Refusal(STATE_NOT_DISPATCHED, "WORKTREE_INVALID")
        inside = self._git(["rev-parse", "--is-inside-work-tree"], op)
        if inside.returncode != 0 or inside.stdout.strip() != b"true":
            raise _Refusal(STATE_NOT_DISPATCHED, "WORKTREE_INVALID")
        if self._origin_url(op) != binding.expected_origin:
            raise _Refusal(STATE_NOT_DISPATCHED, "ORIGIN_MISMATCH")
        completed = self._git(["rev-parse", "--show-object-format"], op)
        if completed.returncode != 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
        return completed.stdout.decode("utf-8", "surrogateescape").strip() or "sha1"

    def _read_guard(self, op: _Operation) -> None:
        self._require_seams()
        if self._authorize_and_stamp(op.principal, op) != op.stamp or self._principal_scope(op.principal) != op.scope:
            raise _Refusal(STATE_NOT_DISPATCHED, "AUTHORIZATION_REVOKED")
        self._require_qualifier()
        self._origin_url(op)

    def _resolve_default_commit(self, op: _Operation) -> str:
        # Local main/origin tracking refs are not upstream publication evidence.
        self._read_guard(op)
        commit = self._remote_branch_commit(op, self._binding.default_branch)
        if commit is None:
            raise _Refusal(STATE_NOT_DISPATCHED, "DEFAULT_BRANCH_MISSING")
        fetched = self._git(["fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", commit], op)
        if fetched.returncode != 0:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        self._read_guard(op)
        if self._remote_branch_commit(op, self._binding.default_branch) != commit:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        return commit

    def _read_blob_at(self, op: _Operation, commit: str, path: str) -> Optional[bytes]:
        listed = self._git(["ls-tree", "-z", commit, "--", path], op)
        if listed.returncode != 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
        if not listed.stdout:
            return None
        metadata, actual_path = listed.stdout.rstrip(b"\0").split(b"\t", 1)
        if actual_path != path.encode() or not metadata.startswith(b"100644 blob "):
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        completed = self._git(["cat-file", "blob", metadata.split()[2].decode("ascii")], op)
        if completed.returncode != 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
        return completed.stdout

    def _require_path_absent_in_base(
        self, op: _Operation, expected_commit: str, path: str
    ) -> None:
        completed = self._git(
            ["cat-file", "-e", "%s:%s" % (expected_commit, path)], op
        )
        if completed.returncode == 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "PATH_COLLISION_IN_BASE")
        completed = self._git(["cat-file", "-e", expected_commit + "^{commit}"], op)
        if completed.returncode != 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "EXPECTED_COMMIT_MISSING")

    def _build_commit(
        self, op: _Operation, envelope: Mapping[str, Any], content_bytes: bytes
    ) -> str:
        """Create the prepared commit without touching caller index/HEAD/worktree."""
        expected_commit = envelope["expected_commit"]
        path = envelope["path"]
        message = "mmos new-project " + envelope["request_sha256"]
        index_fd, index_file = tempfile.mkstemp(prefix="mmos-index-", suffix=".idx")
        os.close(index_fd)
        try:
            read_tree = self._git(
                ["read-tree", expected_commit], op, index_file=index_file
            )
            if read_tree.returncode != 0:
                raise _Refusal(STATE_NOT_DISPATCHED, "EXPECTED_COMMIT_MISSING")
            # From here on this operation writes objects: its outcome horizon
            # becomes unknown-capable.
            self._prewrite_guard(op, op.principal, op.stamp)
            op.mark_effect()
            hash_object = self._git(
                ["hash-object", "-w", "--stdin"],
                op,
                stdin_bytes=content_bytes,
                bounded=True,
            )
            if hash_object.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
            blob_id = hash_object.stdout.decode("utf-8", "surrogateescape").strip()
            if not re.match(r"\A[0-9a-f]{40,64}\Z", blob_id):
                raise _Unknown("GIT_WRITE_UNKNOWN")
            self._prewrite_guard(op, op.principal, op.stamp)
            update_index = self._git(
                [
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    "100644,%s,%s" % (blob_id, path),
                ],
                op,
                index_file=index_file,
            )
            if update_index.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
            self._prewrite_guard(op, op.principal, op.stamp)
            write_tree = self._git(["write-tree"], op, index_file=index_file)
            if write_tree.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
            tree_id = write_tree.stdout.decode("utf-8", "surrogateescape").strip()
            if not re.match(r"\A[0-9a-f]{40,64}\Z", tree_id):
                raise _Unknown("GIT_WRITE_UNKNOWN")
            self._prewrite_guard(op, op.principal, op.stamp)
            commit_tree = self._git(
                [
                    "commit-tree",
                    tree_id,
                    "-p",
                    expected_commit,
                    "-m",
                    message,
                ],
                op,
                bounded=True,
            )
            if commit_tree.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
        finally:
            try:
                os.unlink(index_file)
            except OSError:
                pass
        commit_id = commit_tree.stdout.decode("utf-8", "surrogateescape").strip()
        if not _is_commit_id(commit_id):
            raise _Unknown("GIT_WRITE_UNKNOWN")
        self._prewrite_guard(op, op.principal, op.stamp)
        self._verify_commit_payload(op, commit_id, envelope, content_bytes)
        return commit_id

    def _verify_commit_payload(
        self,
        op: _Operation,
        commit_id: str,
        envelope: Mapping[str, Any],
        content_bytes: bytes,
    ) -> None:
        """Exact one-parent/one-file/content verification before any claim."""
        subject = self._git(["show", "-s", "--format=%s", commit_id], op)
        if subject.returncode != 0 or subject.stdout.decode().strip() != "mmos new-project " + envelope["request_sha256"]:
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        parents = self._git(["rev-list", "--parents", "-n", "1", commit_id], op)
        if parents.returncode != 0:
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        fields = parents.stdout.decode("utf-8", "surrogateescape").split()
        if len(fields) != 2 or fields[1] != envelope["expected_commit"]:
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        delta = self._git(
            ["diff-tree", "-r", "--no-commit-id", "--name-only", commit_id], op
        )
        if delta.returncode != 0:
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        changed = [
            line
            for line in delta.stdout.decode("utf-8", "surrogateescape").splitlines()
            if line
        ]
        if changed != [envelope["path"]]:
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")
        blob_bytes = self._read_blob_at(op, commit_id, envelope["path"])
        if (
            blob_bytes is None
            or blob_bytes != content_bytes
            or _sha256_hex(blob_bytes) != envelope["content_sha256"]
        ):
            raise _Refusal(STATE_CONFLICT, "REF_COLLISION")

    def _local_branch_commit(self, op: _Operation, branch: str) -> Optional[str]:
        ref = "refs/heads/" + branch
        completed = self._git(["rev-parse", "--verify", "--quiet", ref], op)
        if completed.returncode != 0:
            return None
        commit = completed.stdout.decode("utf-8", "surrogateescape").strip()
        return commit if _is_commit_id(commit) else None

    def _claim_local_branch(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        prepared_commit: str,
        envelope: Mapping[str, Any],
        content_bytes: bytes,
    ) -> str:
        branch = op.branch
        existing = self._local_branch_commit(op, branch)
        if existing is not None:
            # Reconcile the existing stable branch; never overwrite it.
            self._verify_commit_payload(op, existing, envelope, content_bytes)
            return existing
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        ref = "refs/heads/" + branch
        completed = self._git(
            ["update-ref", ref, prepared_commit, op.zero_id], op, bounded=True
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "surrogateescape")
            if "already exists" in stderr or "update_ref failed" in stderr:
                # Lost a race: fall back to reconciling whatever landed.
                raced = self._local_branch_commit(op, branch)
                if raced is not None:
                    self._verify_commit_payload(op, raced, envelope, content_bytes)
                    return raced
            raise _Unknown("GIT_WRITE_UNKNOWN")
        self._prewrite_guard(op, principal, stamp)
        return prepared_commit

    def _remote_branch_commit(self, op: _Operation, branch: str) -> Optional[str]:
        completed = self._git(["ls-remote", "origin", "refs/heads/" + branch], op)
        if completed.returncode != 0:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        lines = [
            line
            for line in completed.stdout.decode("utf-8", "surrogateescape").splitlines()
            if line.strip()
        ]
        if not lines:
            return None
        if len(lines) != 1:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        fields = lines[0].split()
        if len(fields) != 2 or not _is_commit_id(fields[0]) or fields[1] != "refs/heads/" + branch:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        return fields[0]

    def _push_branch(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        branch: str,
        commit_id: str,
        envelope: Mapping[str, Any],
        content_bytes: bytes,
    ) -> str:
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        refspec = "refs/heads/%s:refs/heads/%s" % (branch, branch)
        completed = self._git(["push", "origin", refspec], op, bounded=True)
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "surrogateescape").lower()
            if any(marker in stderr for marker in _KNOWN_PUSH_REFUSALS):
                # Normal non-fast-forward guard: someone else created the exact
                # branch.  Verify their payload instead of overwriting it.
                raced = self._remote_branch_commit(op, branch)
                if raced is None:
                    raise _Refusal(STATE_CONFLICT, "PUSH_REFUSED_NON_FAST_FORWARD")
                return self._verify_remote_branch(
                    op, branch, raced, envelope, content_bytes, commit_id
                )
            raise _Unknown("GIT_WRITE_UNKNOWN")
        pushed = self._remote_branch_commit(op, branch)
        if pushed is None:
            raise _Unknown("GIT_WRITE_UNKNOWN")
        return self._verify_remote_branch(
            op, branch, pushed, envelope, content_bytes, commit_id
        )

    def _verify_remote_branch(
        self,
        op: _Operation,
        branch: str,
        remote_commit: str,
        envelope: Mapping[str, Any],
        content_bytes: bytes,
        local_commit: str,
    ) -> str:
        if remote_commit != local_commit:
            # Objects may not exist locally yet: fetch the branch into the local
            # object store (no ref, index, HEAD or worktree change) to verify.
            fetch = self._git(["fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", remote_commit], op)
            if fetch.returncode != 0:
                raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        try:
            self._verify_commit_payload(op, remote_commit, envelope, content_bytes)
        except _Refusal:
            raise _Refusal(STATE_CONFLICT, "REMOTE_BRANCH_CONFLICT") from None
        # A different commit id carrying the exact same parent/tree/path/content
        # payload is the same logical proposal; adopt the remote commit.
        return remote_commit

    # -- pull-request seam ------------------------------------------------- #

    def _validate_receipt(
        self, receipt: Any, branch: str, commit_id: Optional[str]
    ) -> Mapping[str, Any]:
        if not isinstance(receipt, Mapping) or frozenset(receipt.keys()) != _RECEIPT_KEYS:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_INVALID")
        number = receipt["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_INVALID")
        expected_url = "https://github.com/%s/pull/%d" % (
            self._binding.repository,
            number,
        )
        if receipt["url"] != expected_url:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_INVALID")
        if receipt["head_branch"] != branch:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_FOREIGN")
        if not _is_hex40(receipt["head_commit"]):
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_INVALID")
        if commit_id is not None and receipt["head_commit"] != commit_id[:40]:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_FOREIGN")
        return {
            "number": number,
            "url": receipt["url"],
            "head_commit": receipt["head_commit"],
            "head_branch": receipt["head_branch"],
        }

    def _lookup_pull_request(
        self, op: _Operation, branch: str, request_sha256: str, commit_id: Optional[str]
    ) -> Optional[Mapping[str, Any]]:
        try:
            receipt = self._pr_find(self._binding, branch, request_sha256)
        except PrLookupMissing:
            return None
        except (PrLookupAmbiguous, PrOwnerUnknownOutcome):
            raise _Unknown("PR_LOOKUP_UNKNOWN") from None
        except PrLookupForeign:
            raise _Refusal(STATE_CONFLICT, "PR_RECEIPT_FOREIGN") from None
        except _Refusal:
            raise
        except _Unknown:
            raise
        except Exception:
            if op.effects_started:
                raise _Unknown("PR_LOOKUP_UNKNOWN") from None
            raise _Refusal(STATE_NOT_DISPATCHED, "PR_LOOKUP_FAILED") from None
        if receipt is None:
            return None
        return self._validate_receipt(receipt, branch, commit_id)

    def _ensure_pull_request(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        branch: str,
        envelope: Mapping[str, Any],
        commit_id: str,
    ) -> Mapping[str, Any]:
        request_sha256 = envelope["request_sha256"]
        receipt = self._lookup_pull_request(op, branch, request_sha256, commit_id)
        if receipt is not None:
            return receipt
        expected_head = commit_id[:40]
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        try:
            created = self._pr_create(
                self._binding, branch, envelope["expected_commit"], request_sha256
            )
        except PrOwnerRefused:
            raise _Refusal(STATE_PREPARED, "PR_CREATION_REFUSED") from None
        except (PrOwnerUnknownOutcome, PrLookupAmbiguous):
            raise _Unknown("PR_CREATION_UNKNOWN") from None
        except _Refusal:
            raise
        except _Unknown:
            raise
        except Exception:
            # Outcome of a PR write attempt is unknown; never false-clear.
            raise _Unknown("PR_CREATION_UNKNOWN") from None
        self._prewrite_guard(op, principal, stamp)
        return self._validate_receipt(created, branch, expected_head)

    # -- read-only reconciliation ----------------------------------------- #

    def _reconcile_only(
        self,
        op: _Operation,
        envelope: Mapping[str, Any],
        content_bytes: bytes,
        default_commit: str,
    ) -> Mapping[str, Any]:
        self._read_guard(op)
        branch = op.branch
        request_sha256 = envelope["request_sha256"]
        local_commit = self._local_branch_commit(op, branch)
        if local_commit is not None:
            try:
                self._verify_commit_payload(op, local_commit, envelope, content_bytes)
            except _Refusal:
                raise _Refusal(STATE_CONFLICT, "REF_COLLISION") from None
        remote_commit = self._remote_branch_commit(op, branch)
        if remote_commit is not None:
            if remote_commit != local_commit:
                fetch = self._git(["fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "origin", remote_commit], op)
                if fetch.returncode != 0:
                    raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
            try:
                self._verify_commit_payload(
                    op, remote_commit, envelope, content_bytes
                )
            except _Refusal:
                raise _Refusal(STATE_CONFLICT, "REMOTE_BRANCH_CONFLICT") from None
        receipt = self._lookup_pull_request(op, branch, request_sha256, remote_commit or local_commit)
        self._read_guard(op)
        if self._remote_branch_commit(op, branch) != remote_commit:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        if receipt is not None and remote_commit is None:
            # A receipt without a verifiable remote branch cannot be claimed.
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        if receipt is not None:
            return self._result(
                STATE_PROPOSAL_PUBLISHED,
                op=op,
                source=None,
                proposal=receipt,
                reason=None,
            )
        if local_commit is not None or remote_commit is not None:
            reason = (
                "REMOTE_BRANCH_WITHOUT_PR" if remote_commit is not None else "LOCAL_ONLY"
            )
            return self._result(
                STATE_PREPARED, op=op, source=None, proposal=None, reason=reason
            )
        if default_commit == envelope["expected_commit"]:
            return self._result(
                STATE_EFFECT_UNKNOWN,
                op=op,
                source=None,
                proposal=None,
                reason="NO_EXISTING_PUBLICATION",
            )
        return self._result(
            STATE_EFFECT_UNKNOWN,
            op=op,
            source=None,
            proposal=None,
            reason="STALE_EXPECTED_COMMIT",
        )

    # -- results ----------------------------------------------------------- #

    def _project_created(
        self,
        op: _Operation,
        default_commit: str,
        envelope: Mapping[str, Any],
        proposal: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        self._read_guard(op)
        if self._remote_branch_commit(op, self._binding.default_branch) != default_commit:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        source = {
            "repository": self._binding.short_repository,
            "commit": default_commit,
            "path": envelope["path"],
            "content_sha256": envelope["content_sha256"],
            "request_sha256": envelope["request_sha256"],
        }
        if frozenset(source.keys()) != _SOURCE_KEYS:
            raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
        return self._result(
            STATE_PROJECT_CREATED,
            op=op,
            source=source,
            proposal=proposal,
            reason=None,
        )

    def _result(
        self,
        state: str,
        *,
        op: _Operation,
        source: Optional[Mapping[str, Any]],
        proposal: Optional[Mapping[str, Any]],
        reason: Optional[str],
    ) -> Mapping[str, Any]:
        if state in {STATE_PROJECT_CREATED, STATE_PROPOSAL_PUBLISHED}:
            self._read_guard(op)
        if state not in PUBLICATION_STATES:
            raise ValueError("unmapped publication state")
        if reason is not None and reason not in PUBLICATION_REASONS:
            raise ValueError("unmapped publication reason")
        if proposal is not None:
            proposal = dict(proposal)
            if frozenset(proposal.keys()) != _RECEIPT_KEYS:
                raise ValueError("receipt does not match the closed receipt schema")
        result = {
            "schema": PUBLICATION_SCHEMA,
            "state": state,
            "request_sha256": op.request_sha256,
            "work_ref": op.work_ref,
            "branch": op.branch,
            "source": dict(source) if source is not None else None,
            "proposal": proposal,
            "reason": reason,
            "retryable": False,
        }
        if frozenset(result.keys()) != _RESULT_KEYS:
            raise ValueError("publication result schema drift")
        return result

    # -- knowledge git primitives ------------------------------------------ #

    def _knowledge_commit_subject(
        self, lookup: Mapping[str, Any], fingerprint: str
    ) -> str:
        """Commit subject binding the original public SHA, private fingerprint
        and identity/target of the original operation."""
        if lookup.get("action") == "ADOPT_PLAN":
            return "mmos plan-adopt " + lookup["phase"] + " " + lookup["request_sha256"] + " " + fingerprint + " " + lookup["request_id"] + " " + lookup["work_ref"]
        return (
            KNOWLEDGE_COMMIT_SUBJECT_PREFIX
            + lookup["request_sha256"]
            + " "
            + fingerprint
            + " "
            + lookup["request_id"]
            + " "
            + lookup["work_ref"]
        )

    def _verify_knowledge_commit_payload(
        self,
        op: _Operation,
        commit_id: str,
        postimages: Any,
        lookup: Mapping[str, Any],
        fingerprint: str,
        expected_commit: str,
        contents: Optional["list[bytes]"] = None,
    ) -> None:
        """Exact single-parent/payload verification of a knowledge commit.

        The changed path set must be exactly the postimages whose preimage SHA
        differs from the new SHA -- a preference edit may legitimately change
        only the decision record -- and at least one path must change.
        """
        conflict = _Refusal(STATE_CONFLICT, "REF_COLLISION")
        subject = self._git(["show", "-s", "--format=%s", commit_id], op)
        expected_subject = self._knowledge_commit_subject(lookup, fingerprint)
        if subject.returncode != 0 or subject.stdout.decode().strip() != expected_subject:
            raise conflict
        parents = self._git(["rev-list", "--parents", "-n", "1", commit_id], op)
        if parents.returncode != 0:
            raise conflict
        fields = parents.stdout.decode("utf-8", "surrogateescape").split()
        if len(fields) != 2 or fields[1] != expected_commit:
            raise conflict
        delta = self._git(
            ["diff-tree", "-r", "--no-commit-id", "--name-only", commit_id], op
        )
        if delta.returncode != 0:
            raise conflict
        changed = [
            line
            for line in delta.stdout.decode("utf-8", "surrogateescape").splitlines()
            if line
        ]
        expected_changed = _knowledge_changed_paths(postimages)
        if (
            not changed
            or len(changed) != len(set(changed))
            or sorted(changed) != sorted(expected_changed)
        ):
            raise conflict
        for position, image in enumerate(postimages):
            blob_bytes = self._read_blob_at(op, commit_id, image["path"])
            if (
                blob_bytes is None
                or _sha256_hex(blob_bytes) != image["content_sha256"]
            ):
                raise conflict
            if contents is not None and blob_bytes != contents[position]:
                raise conflict

    def _verify_knowledge_preimages_at_base(
        self,
        op: _Operation,
        expected_commit: str,
        postimages: Any,
    ) -> None:
        """Both old preimages must match bytes/SHA -- or be absent as expected.

        Read failures are distinguished from a genuinely absent canonical path.
        Any mismatch refuses before any publication object is written.
        """
        completed = self._git(["cat-file", "-e", expected_commit + "^{commit}"], op)
        if completed.returncode != 0:
            raise _Refusal(STATE_NOT_DISPATCHED, "EXPECTED_COMMIT_MISSING")
        for image in postimages:
            preimage = image["expected_preimage_sha256"]
            if preimage is None:
                listed = self._git(
                    ["ls-tree", "-z", expected_commit, "--", image["path"]], op
                )
                if listed.returncode != 0:
                    raise _Refusal(STATE_NOT_DISPATCHED, "GIT_INVOCATION_FAILED")
                if listed.stdout:
                    raise _Refusal(STATE_NOT_DISPATCHED, "PATH_COLLISION_IN_BASE")
                continue
            blob_bytes = self._read_blob_at(op, expected_commit, image["path"])
            if blob_bytes is None or _sha256_hex(blob_bytes) != preimage:
                raise _Refusal(STATE_CONFLICT, "PREIMAGE_CONFLICT")

    def _build_knowledge_commit(
        self,
        op: _Operation,
        recipe: Mapping[str, Any],
        lookup: Mapping[str, Any],
    ) -> str:
        """One private temporary index/write-tree/commit-tree changes both
        logical postimages atomically, without touching caller state."""
        expected_commit = lookup["source_commit"]
        postimages = recipe["postimages"]
        fingerprint = recipe["request_fingerprint"]
        message = self._knowledge_commit_subject(lookup, fingerprint)
        contents = [image["content_utf8"].encode("utf-8") for image in postimages]
        index_fd, index_file = tempfile.mkstemp(
            prefix="mmos-knowledge-index-", suffix=".idx"
        )
        os.close(index_fd)
        try:
            read_tree = self._git(
                ["read-tree", expected_commit], op, index_file=index_file
            )
            if read_tree.returncode != 0:
                raise _Refusal(STATE_NOT_DISPATCHED, "EXPECTED_COMMIT_MISSING")
            # From here on this operation writes objects: its outcome horizon
            # becomes unknown-capable.
            self._prewrite_guard(op, op.principal, op.stamp)
            op.mark_effect()
            for position, image in enumerate(postimages):
                hash_object = self._git(
                    ["hash-object", "-w", "--stdin"],
                    op,
                    stdin_bytes=contents[position],
                    bounded=True,
                )
                if hash_object.returncode != 0:
                    raise _Unknown("GIT_WRITE_UNKNOWN")
                blob_id = hash_object.stdout.decode("utf-8", "surrogateescape").strip()
                if not re.match(r"\A[0-9a-f]{40,64}\Z", blob_id):
                    raise _Unknown("GIT_WRITE_UNKNOWN")
                self._prewrite_guard(op, op.principal, op.stamp)
                update_index = self._git(
                    [
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        "100644,%s,%s" % (blob_id, image["path"]),
                    ],
                    op,
                    index_file=index_file,
                )
                if update_index.returncode != 0:
                    raise _Unknown("GIT_WRITE_UNKNOWN")
                self._prewrite_guard(op, op.principal, op.stamp)
            write_tree = self._git(["write-tree"], op, index_file=index_file)
            if write_tree.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
            tree_id = write_tree.stdout.decode("utf-8", "surrogateescape").strip()
            if not re.match(r"\A[0-9a-f]{40,64}\Z", tree_id):
                raise _Unknown("GIT_WRITE_UNKNOWN")
            self._prewrite_guard(op, op.principal, op.stamp)
            commit_tree = self._git(
                [
                    "commit-tree",
                    tree_id,
                    "-p",
                    expected_commit,
                    "-m",
                    message,
                ],
                op,
                bounded=True,
            )
            if commit_tree.returncode != 0:
                raise _Unknown("GIT_WRITE_UNKNOWN")
        finally:
            try:
                os.unlink(index_file)
            except OSError:
                pass
        commit_id = commit_tree.stdout.decode("utf-8", "surrogateescape").strip()
        if not _is_commit_id(commit_id):
            raise _Unknown("GIT_WRITE_UNKNOWN")
        self._prewrite_guard(op, op.principal, op.stamp)
        self._verify_knowledge_commit_payload(
            op,
            commit_id,
            postimages,
            lookup,
            fingerprint,
            expected_commit,
            contents,
        )
        return commit_id

    def _claim_local_branch_knowledge(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        prepared_commit: str,
        recipe: Mapping[str, Any],
        lookup: Mapping[str, Any],
    ) -> str:
        branch = op.branch
        postimages = recipe["postimages"]
        fingerprint = recipe["request_fingerprint"]
        expected_commit = lookup["source_commit"]
        contents = [image["content_utf8"].encode("utf-8") for image in postimages]
        existing = self._local_branch_commit(op, branch)
        if existing is not None:
            # Reconcile the existing stable branch; never overwrite it.
            self._verify_knowledge_commit_payload(
                op, existing, postimages, lookup, fingerprint, expected_commit, contents
            )
            return existing
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        ref = "refs/heads/" + branch
        completed = self._git(
            ["update-ref", ref, prepared_commit, op.zero_id], op, bounded=True
        )
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "surrogateescape")
            if "already exists" in stderr or "update_ref failed" in stderr:
                # Lost a race: fall back to reconciling whatever landed.
                raced = self._local_branch_commit(op, branch)
                if raced is not None:
                    self._verify_knowledge_commit_payload(
                        op, raced, postimages, lookup, fingerprint, expected_commit, contents
                    )
                    return raced
            raise _Unknown("GIT_WRITE_UNKNOWN")
        self._prewrite_guard(op, principal, stamp)
        return prepared_commit

    def _push_knowledge_branch(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        branch: str,
        commit_id: str,
        recipe: Mapping[str, Any],
        lookup: Mapping[str, Any],
    ) -> str:
        postimages = recipe["postimages"]
        fingerprint = recipe["request_fingerprint"]
        expected_commit = lookup["source_commit"]
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        refspec = "refs/heads/%s:refs/heads/%s" % (branch, branch)
        completed = self._git(["push", "origin", refspec], op, bounded=True)
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", "surrogateescape").lower()
            if any(marker in stderr for marker in _KNOWN_PUSH_REFUSALS):
                raced = self._remote_branch_commit(op, branch)
                if raced is None:
                    raise _Refusal(STATE_CONFLICT, "PUSH_REFUSED_NON_FAST_FORWARD")
                return self._verify_knowledge_remote_branch(
                    op, branch, raced, recipe, lookup, commit_id
                )
            raise _Unknown("GIT_WRITE_UNKNOWN")
        pushed = self._remote_branch_commit(op, branch)
        if pushed is None:
            raise _Unknown("GIT_WRITE_UNKNOWN")
        return self._verify_knowledge_remote_branch(
            op, branch, pushed, recipe, lookup, commit_id
        )

    def _verify_knowledge_remote_branch(
        self,
        op: _Operation,
        branch: str,
        remote_commit: str,
        recipe: Mapping[str, Any],
        lookup: Mapping[str, Any],
        local_commit: str,
    ) -> str:
        postimages = recipe["postimages"]
        fingerprint = recipe["request_fingerprint"]
        expected_commit = lookup["source_commit"]
        contents = [image["content_utf8"].encode("utf-8") for image in postimages]
        if remote_commit != local_commit:
            fetch = self._git(
                [
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--no-write-fetch-head",
                    "origin",
                    remote_commit,
                ],
                op,
            )
            if fetch.returncode != 0:
                raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        try:
            self._verify_knowledge_commit_payload(
                op, remote_commit, postimages, lookup, fingerprint, expected_commit, contents
            )
        except _Refusal:
            raise _Refusal(STATE_CONFLICT, "REMOTE_BRANCH_CONFLICT") from None
        return remote_commit

    def _ensure_pull_request_knowledge(
        self,
        op: _Operation,
        principal: Any,
        stamp: str,
        branch: str,
        lookup: Mapping[str, Any],
        commit_id: str,
    ) -> Mapping[str, Any]:
        request_sha256 = lookup["request_sha256"]
        receipt = self._lookup_pull_request(op, branch, request_sha256, commit_id)
        if receipt is not None:
            return receipt
        expected_head = commit_id[:40]
        self._prewrite_guard(op, principal, stamp)
        op.mark_effect()
        try:
            created = self._pr_create(
                self._binding, branch, lookup["source_commit"], request_sha256
            )
        except PrOwnerRefused:
            raise _Refusal(STATE_PREPARED, "PR_CREATION_REFUSED") from None
        except (PrOwnerUnknownOutcome, PrLookupAmbiguous):
            raise _Unknown("PR_CREATION_UNKNOWN") from None
        except _Refusal:
            raise
        except _Unknown:
            raise
        except Exception:
            raise _Unknown("PR_CREATION_UNKNOWN") from None
        self._prewrite_guard(op, principal, stamp)
        return self._validate_receipt(created, branch, expected_head)

    # -- knowledge read-only observation ----------------------------------- #

    def _default_carries_postimages(
        self,
        op: _Operation,
        commit: str,
        metadata: Mapping[str, Any],
    ) -> bool:
        """True only when one verified tree carries both canonical postimages.

        Read failures are refusals, never read as absence or conflict; after an
        attempted write the operation driver maps them to EFFECT_UNKNOWN.
        """
        for image in metadata["postimages"]:
            blob_bytes = self._read_blob_at(op, commit, image["path"])
            if blob_bytes is None or _sha256_hex(blob_bytes) != image["content_sha256"]:
                return False
        return True

    def _knowledge_publication(
        self, metadata: Mapping[str, Any], commit: str
    ) -> dict:
        return {
            "repository": REPOSITORY,
            "commit": commit,
            "postimages": [
                {"path": image["path"], "content_sha256": image["content_sha256"]}
                for image in metadata["postimages"]
            ],
        }

    def _knowledge_source_published(
        self,
        op: _Operation,
        commit: str,
        publication: Mapping[str, Any],
        *,
        require_default_match: bool,
        proposal: Optional[Mapping[str, Any]] = None,
    ) -> Mapping[str, Any]:
        self._read_guard(op)
        if (
            require_default_match
            and self._remote_branch_commit(op, self._binding.default_branch) != commit
        ):
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        source = {
            "repository": publication["repository"],
            "commit": publication["commit"],
            "postimages": [
                dict(image) for image in publication["postimages"]
            ],
        }
        return self._knowledge_result(
            STATE_SOURCE_PUBLISHED,
            op=op,
            source=source,
            proposal=proposal,
            reason=None,
        )

    def _reconcile_only_knowledge(
        self,
        op: _Operation,
        metadata: Mapping[str, Any],
        default_commit: str,
    ) -> Mapping[str, Any]:
        """READ-ONLY knowledge reconciliation of the actual rung.

        Never rebuilds an object, never pushes, never creates a PR and never
        claims again; it observes retained metadata plus Git/PR evidence only.
        """
        self._read_guard(op)
        branch = op.branch
        lookup = op.lookup
        postimages = metadata["postimages"]
        fingerprint = metadata["recipe_fingerprint_sha256"]
        expected_commit = metadata["expected_commit"]
        local_commit = self._local_branch_commit(op, branch)
        if local_commit is not None:
            try:
                self._verify_knowledge_commit_payload(
                    op, local_commit, postimages, lookup, fingerprint, expected_commit
                )
            except _Refusal:
                raise _Refusal(STATE_CONFLICT, "REF_COLLISION") from None
        remote_commit = self._remote_branch_commit(op, branch)
        if remote_commit is not None:
            if remote_commit != local_commit:
                fetch = self._git(
                    [
                        "fetch",
                        "--quiet",
                        "--no-tags",
                        "--no-write-fetch-head",
                        "origin",
                        remote_commit,
                    ],
                    op,
                )
                if fetch.returncode != 0:
                    raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
            try:
                self._verify_knowledge_commit_payload(
                    op, remote_commit, postimages, lookup, fingerprint, expected_commit
                )
            except _Refusal:
                raise _Refusal(STATE_CONFLICT, "REMOTE_BRANCH_CONFLICT") from None
        receipt = self._lookup_pull_request(
            op, branch, lookup["request_sha256"], remote_commit or local_commit
        )
        self._read_guard(op)
        if self._remote_branch_commit(op, branch) != remote_commit:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        if receipt is not None and remote_commit is None:
            raise _Unknown("REMOTE_BRANCH_UNVERIFIED")
        # Owner-retained source-observed proof survives any later default edit.
        proof = _knowledge_publication_proof(metadata)
        if proof is not None:
            return self._knowledge_source_published(
                op, proof["commit"], proof, require_default_match=False
            )
        # A fresh upstream default readback is the qualified saved rung; a PR
        # receipt alone is never treated as the record being saved.
        if self._default_carries_postimages(op, default_commit, metadata):
            return self._knowledge_source_published(
                op,
                default_commit,
                self._knowledge_publication(metadata, default_commit),
                require_default_match=True,
            )
        if receipt is not None:
            return self._knowledge_result(
                STATE_PROPOSAL_PUBLISHED,
                op=op,
                source=None,
                proposal=receipt,
                reason=None,
            )
        if local_commit is not None or remote_commit is not None:
            reason = (
                "REMOTE_BRANCH_WITHOUT_PR" if remote_commit is not None else "LOCAL_ONLY"
            )
            return self._knowledge_result(
                STATE_PREPARED, op=op, source=None, proposal=None, reason=reason
            )
        if (
            metadata["phase"] == KNOWLEDGE_PHASE_NOT_DISPATCHED
            and default_commit == expected_commit
        ):
            # Actual owner-retained no-effect proof is a terminal state.
            return self._knowledge_result(
                STATE_NOT_DISPATCHED, op=op, source=None, proposal=None, reason=None
            )
        if default_commit == expected_commit:
            raise _Unknown("NO_EXISTING_PUBLICATION")
        # No retained proof and the current upstream bytes differ: the rung
        # stays unknown.  It is never a failure, never proof of no effect and
        # never retry authority.
        raise _Unknown("STALE_EXPECTED_COMMIT")

    # -- knowledge results ------------------------------------------------- #

    def _knowledge_result(
        self,
        state: str,
        *,
        op: _Operation,
        source: Optional[Mapping[str, Any]],
        proposal: Optional[Mapping[str, Any]],
        reason: Optional[str],
    ) -> Mapping[str, Any]:
        if state in {STATE_SOURCE_PUBLISHED, STATE_PROPOSAL_PUBLISHED}:
            self._read_guard(op)
        if state not in KNOWLEDGE_STATES:
            raise ValueError("unmapped knowledge publication state")
        if reason is not None and reason not in KNOWLEDGE_REASONS:
            raise ValueError("unmapped knowledge publication reason")
        if proposal is not None:
            proposal = dict(proposal)
            if frozenset(proposal.keys()) != _RECEIPT_KEYS:
                raise ValueError("receipt does not match the closed receipt schema")
        if source is not None:
            source = dict(source)
            if frozenset(source.keys()) != _KNOWLEDGE_PUBLICATION_KEYS:
                raise ValueError("publication does not match the closed schema")
            images = source["postimages"]
            count = 3 if op.lookup is not None and op.lookup.get("action") == correction.ACTION else 2
            if not isinstance(images, list) or len(images) != count:
                raise ValueError("publication postimages do not match the original action")
            source["postimages"] = [dict(image) for image in images]
            for image in source["postimages"]:
                if frozenset(image.keys()) != _KNOWLEDGE_PUBLICATION_IMAGE_KEYS:
                    raise ValueError("publication postimage schema drift")
        selection = dict(op.lookup) if op.lookup is not None else None
        result = {
            "schema": KNOWLEDGE_SCHEMA,
            "selection": selection,
            "state": state,
            "recipe_fingerprint_sha256": op.recipe_fingerprint,
            "source": source,
            "proposal": proposal,
            "reason": reason,
            "retryable": False,
        }
        if frozenset(result.keys()) != _KNOWLEDGE_RESULT_KEYS:
            raise ValueError("knowledge publication result schema drift")
        return result
