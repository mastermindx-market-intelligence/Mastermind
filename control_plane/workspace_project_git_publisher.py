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

Ownership boundaries
--------------------
* Every policy decision is delegated to an injected, installed-owner seam:
  ``compile_proposal``, ``authorize``, ``permission_stamp``,
  ``qualify_publisher`` and ``pr_owner``.  They are required constructor
  arguments with no defaults; a missing seam refuses before any effect.  Plain
  string labels are never accepted in their place.
* ``qualify_publisher`` is the real Git/gh credential *identity source*
  qualifier.  It is never derived from an Auth0 principal, and this module never
  inspects, transports or logs credential material.
* The caller never supplies a proposal, a path, a branch, a remote, an actor,
  a credential or any other option to ``publish``.  The public surface is
  exactly ``publish(request, principal)`` and ``reconcile(request, principal)``.
* ``compile_proposal`` owns canonical workstream-key semantics, complete
  authored metadata and request digest derivation.  This module re-validates the
  closed envelope shape but never infers or repairs an owner, a key or metadata.

Effect discipline
-----------------
* ``NOT_DISPATCHED`` -- a refusal or callback failure before the first write.
* ``EFFECT_UNKNOWN`` -- a write was attempted and its outcome is unknown; this
  is sticky and is never cleared by this module.  ``reconcile`` is the only way
  to learn the actual rung afterwards.
* ``PREPARED`` -- a stable local (and/or remote) proposal branch commit exists
  but no pull request exists; it is not a Project.
* ``PROPOSAL_PUBLISHED`` -- the exact branch is on the verified origin and a
  real ``pr_owner`` receipt exists.
* ``PROJECT_CREATED`` -- the qualified upstream default branch was read back and contains
  exactly the authored bytes after the normal protected merge performed by
  someone else.  This module never merges.
* ``CONFLICT`` -- deterministic disagreement (differing canonical bytes, ref
  collision, non-fast-forward remote branch, foreign receipt).

Git safety
----------
Only normal plumbing is used, through ``subprocess`` with a fixed argv list (no
shell), bounded timeouts and stdin payloads.  The caller's index, HEAD, worktree
and unrelated files are preserved: no checkout, reset, stash, merge, rebase,
force push, default-branch write or worktree file write ever happens here.  The
prepared commit is created from a private temporary index (``read-tree`` the
expected base, ``hash-object -w --stdin`` the content, ``update-index --add
--cacheinfo``, ``write-tree``, ``commit-tree`` with the expected commit as the
exact single parent) and anchored with a create-only ``git update-ref`` against
the zero object id.  Push is a plain non-force ``git push origin
refs/heads/<branch>:refs/heads/<branch>``; the default branch is never pushed.

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
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

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
        }
        if current != self._seam_identities:
            raise _Refusal(STATE_NOT_DISPATCHED, "SEAM_IDENTITY_CHANGED")

    def _authorize_and_stamp(self, principal: Any) -> str:
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
        becomes EFFECT_UNKNOWN instead of a false clear.
        """
        try:
            self._require_seams()
            current = self._authorize_and_stamp(principal)
            self._require_qualifier()
            if current != stamp or self._principal_scope(principal) != op.scope:
                raise _Refusal(STATE_NOT_DISPATCHED, "AUTHORIZATION_REVOKED")
            if self._origin_url(op) != self._binding.expected_origin:
                raise _Refusal(STATE_NOT_DISPATCHED, "ORIGIN_MISMATCH")
            if self._remote_branch_commit(op, self._binding.default_branch) != op.expected_commit:
                raise _Refusal(STATE_NOT_DISPATCHED, "STALE_EXPECTED_COMMIT")
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
        if index_file is not None:
            env["GIT_INDEX_FILE"] = index_file
        try:
            completed = subprocess.run(
                argv,
                cwd=self._binding.worktree,
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                timeout=self._command_timeout,
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
        if self._authorize_and_stamp(op.principal) != op.stamp or self._principal_scope(op.principal) != op.scope:
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
