"""Bounded, inert CURRENT Git source observation (additive, source-only capability).

One strict bounded CURRENT request/response pair observes a fixed set of exact
source paths inside ONE custody triple — declared worktree, declared git_dir
and declared common_dir, all independently qualified by the native invocation
owner — at ONE validated SHA-1 commit, and returns an exact bounded response
proving the read.  Scope and boundaries:

* CURRENT only.  A ``historical`` request field, when present, is opaque echo
  data with no ancestry, permission, admission or recovery meaning.  Nothing
  here recovers, accepts or replays a historical run, worker, lease, packet or
  result, and no allowlist for an old run is created or consulted.
* Admission is principal integration.  Nothing is read and nothing is
  published without a typed ``NativeInvocation`` minted at the incumbent
  native CLI/owner boundary.  A caller-supplied mapping, digest, flag or
  boolean never counts as admission.  Missing or refused authorization
  performs zero reads.
* Trusted-process boundary (stated plainly): the invocation object and its
  owner live in the same interpreter, so an in-process attacker could call the
  private mint path.  The boundary is the owning native CLI process: untrusted
  request JSON can never construct a scope, because minting consults the
  owner, and the owner re-checks the exact request bytes it read itself, the
  invoking OS uid, the original observer correlation, the registry host and
  the declared custody.  This is process isolation, not a cryptographic
  credential, and no response or receipt claims authentication from a type
  seal or a mutable label.
* Ordinary repositories AND real linked worktrees are supported without ever
  following an arbitrary ``.git`` pointer.  The request declares git_dir and
  common_dir explicitly; the reader proves worktree/.git against the declared
  git_dir (directory identity or exact ``gitdir:`` pointer bytes), proves
  ``commondir`` against the declared common_dir, proves the git_dir backlink
  against the exact expected ``<worktree>/.git``, and re-reads every pointer
  after the reads.  Objects are read only from the declared common object
  store; alternate and promisor (partial-clone) stores are refused, which is
  what makes lazy fetch impossible rather than merely disabled.
* One additive, mutually exclusive request variant resolves the custody
  graph instead of declaring it: the request omits git_dir and common_dir
  and carries ``custody = {"mode": "worktree_pointer_graph",
  "boundary": <absolute non-root path>}``.  The boundary is a scoped
  resource selector the existing native owner consumes -- never an
  authority, credential or authentication.  Resolution is finite: the
  exact selected worktree/.git is classified with the same no-follow
  Reader discipline, an ordinary directory resolves to
  ``git_dir = common_dir = <worktree>/.git``, a regular gitfile must
  resolve inside the boundary to the standard linked shape
  ``<common>/worktrees/<one component>`` whose ``commondir`` stays inside
  the boundary and whose ``gitdir`` backlink is exactly
  ``<worktree>/.git``; relocated separate git dirs are refused.  No scan,
  no guessed path, no upward walk, no shell or Git discovery and no
  environment census ever runs.  The pointer leaf and directory
  identities and bytes are held and re-verified across the whole capture,
  so replacement by identical bytes or a changed-then-reverted pointer
  fails.  The response carries the resolved paths plus a bounded proof
  (exact pointer bytes, graph shape, identity snapshot) sealed under the
  same request digest; delivery-side validation re-derives the path
  relationship, boundary and backlink from that proof alone before
  acceptance or publication.
* Git reads are raw object reads only: commit, tree and blob.  Every object
  is verified by its own SHA-1 over the Git ``<type> <len>\\0`` header plus
  bytes, and the requested path is proven by tree membership against the
  requested commit.  Loose objects are read directly; packed objects only
  through a constrained ``git cat-file --batch`` with a fixed argv, a minimal
  constructed environment, a process deadline, bounded stdout,
  ``--no-replace-objects`` and ``--no-optional-locks``.  No shell, no hooks,
  no filters, no network, no index/worktree/config/object writes, no host or
  environment census, and no execution of observed source.
* The remote half of the composition is the generated reader: a fixed
  standalone program composed only from this module's reviewed source, shipped
  by the incumbent strict-SSH transport and executed for the exact qualified
  request.  It performs the actual bounded object reads; it is not a response
  validator that skips them.
* The composition is native CLI -> existing host registry -> strict SSH
  bounded transport -> generated reader -> validated receiver-bound exclusive
  receipt.  The destination reservation, bounded response validation and
  atomic publication reuse the incumbent primitives; an interrupted or
  duplicate destination fails closed.  The public source command is
  UNINSTALLED and NOT LIVE: no owner grant is installed by this source, and
  qualified immutable-generation installation and current scoped OS/tool
  permission remain separate external prerequisites. Provider allowed_modes
  remain unchanged; no new source-read grant registry is invented.
* The response is exact and bounded and carries a receipt binding
  receiver/request/admission.  It claims no historical execution, no worker
  acceptance, no controller completion, no lease clearance and no retry.
"""
from __future__ import annotations

import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import zlib
from inspect import getsource

SCHEMA_REQUEST = "mastermind.fabric_current_source_request.v1"
SCHEMA_OBSERVATION = "mastermind.fabric_current_source_observation.v1"
SCHEMA_INVOCATION = "mastermind.fabric_current_source_invocation.v1"
SCHEMA_SUMMARY = "mastermind.fabric_current_source_receipt_summary.v1"
SCHEMA_RECEIPT = "mastermind.fabric_current_source_receipt.v1"
# The single additive custody variant: resolved worktree pointer graph inside
# a declared boundary, instead of an explicit git_dir/common_dir triple.
CUSTODY_MODE = "worktree_pointer_graph"

MAX_REQUEST = 65536
MAX_RESPONSE = 1500000
MAX_SOURCES = 8
MAX_FILE_BYTES = 1048576
MAX_BYTES_TOTAL = 4194304
MAX_COMMIT_BYTES = 65536
MAX_TREE_BYTES = 1048576
MAX_POINTER_BYTES = 4096
MAX_DEADLINE_S = 60.0
DEFAULT_DEADLINE_S = 10.0
MAX_PATH_DEPTH = 20
MAX_RESPONSE_FILES = MAX_SOURCES

IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
HOST = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
# Relative source components may begin with an underscore (e.g. "__tests__");
# leading dots and every other punctuation stay refused.  Declared custody
# roots keep their own rule in CUSTODY_COMPONENT below.
COMPONENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]{0,127}\Z")
# Declared custody roots legitimately contain Git's leading-dot components
# (".git"); traversal stays impossible because "." and ".." are refused
# outright and every component is opened without following links.
CUSTODY_COMPONENT = re.compile(r"[A-Za-z0-9.+~-][A-Za-z0-9_.+~-]{0,127}\Z")
GIT_CANDIDATES = ("/usr/bin/git", "/bin/git")
GIT_ARGV_PREFIX = ("--no-replace-objects", "--no-optional-locks")

LIMIT_KEYS = ("max_file_bytes", "max_bytes_total", "deadline_ms")
LIMIT_CAPS = {"max_file_bytes": MAX_FILE_BYTES, "max_bytes_total": MAX_BYTES_TOTAL,
              "deadline_ms": int(MAX_DEADLINE_S * 1000)}
DEFAULT_LIMITS = {"max_file_bytes": MAX_FILE_BYTES, "max_bytes_total": MAX_BYTES_TOTAL,
                  "deadline_ms": int(DEFAULT_DEADLINE_S * 1000)}

NO_CLAIMS = (
    "no_historical_execution_replayed",
    "no_worker_acceptance_claimed",
    "no_controller_completion_claimed",
    "no_lease_clearance_or_cleanup_performed",
    "no_retry_or_release_decision_made",
    "no_allowlist_for_old_runs_created",
)


class CurrentSourceError(ValueError):
    """Refusal with a precise machine-readable reason."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason if not detail else "%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


class NativeRefused(CurrentSourceError):
    """Owner-boundary refusal: admission, activation or publication."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def strict_json(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CurrentSourceError("duplicate_key")
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _x: (_ for _ in ()).throw(
                              CurrentSourceError("nonfinite_json")))
    except CurrentSourceError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise CurrentSourceError("json_invalid", str(exc))


def digest_of(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def identity(info: os.stat_result):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, info.st_mode, info.st_uid, info.st_nlink)


def _is_str(value, pattern) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def validate_absolute_custody(path: str):
    """Declared custody root: absolute, bounded, component-checked.  The
    caller still proves every component by opening it without following
    links; this is the closed-world shape check only."""
    if type(path) is not str or not path.startswith("/") or len(path) > 270:
        raise CurrentSourceError("custody_path_invalid")
    parts = [p for p in path.split("/") if p != ""]
    if not 1 <= len(parts) <= MAX_PATH_DEPTH:
        raise CurrentSourceError("custody_path_invalid")
    for part in parts:
        if not CUSTODY_COMPONENT.fullmatch(part) or part in (".", ".."):
            raise CurrentSourceError("custody_path_invalid")
    return parts


def validate_relative_path(path: str) -> str:
    if type(path) is not str or path.startswith("/") or len(path) > 512:
        raise CurrentSourceError("path_invalid")
    parts = path.split("/")
    if not 1 <= len(parts) <= MAX_PATH_DEPTH:
        raise CurrentSourceError("path_invalid")
    for part in parts:
        if not COMPONENT.fullmatch(part) or part in (".", ".."):
            raise CurrentSourceError("path_invalid")
    return path


def _validate_source_entries(entries):
    if type(entries) is not list:
        raise CurrentSourceError("entries_invalid")
    if len(entries) > MAX_SOURCES:
        raise CurrentSourceError("entry_count_limit")
    seen = set()
    for entry in entries:
        if type(entry) is not dict or not {"path"} <= set(entry) <= {"path", "blob", "size"}:
            raise CurrentSourceError("entry_unknown_field")
        if "blob" in entry and not _is_str(entry["blob"], SHA1):
            raise CurrentSourceError("blob_digest_invalid")
        validate_relative_path(entry["path"])
        size = entry.get("size", 0)
        if type(size) is not int or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES:
            raise CurrentSourceError("declared_size_invalid")
        if entry["path"] in seen:
            raise CurrentSourceError("duplicate_path")
        seen.add(entry["path"])
    return seen


def validate_custody_variant(custody):
    """Closed-world custody variant: exactly ``mode`` and ``boundary``, the
    fixed resolution mode, and an absolute non-root boundary.  The boundary is
    a scoped resource selector consumed by the existing native owner; it is
    never an authority, credential or authentication.  Returns the boundary
    components."""
    if (type(custody) is not dict or set(custody) != {"mode", "boundary"}
            or custody["mode"] != CUSTODY_MODE):
        raise CurrentSourceError("custody_variant_invalid")
    return validate_absolute_custody(custody["boundary"])


def require_boundary_contains(boundary_parts, inner_parts):
    """Strict lexical containment at a component boundary: the inner path lies
    below the boundary -- never equal to it and never the root."""
    if (len(inner_parts) <= len(boundary_parts)
            or inner_parts[:len(boundary_parts)] != boundary_parts):
        raise CurrentSourceError("custody_boundary_invalid")


def validate_request(request) -> str:
    """Closed-world request validation; bind every field, including references.

    Exactly one custody shape is accepted: the explicit git_dir/common_dir
    triple, or the custody variant that omits both and carries the whole
    custody dict.  Partial, mixed and unknown variants are refused before any
    read.  ``digest_of`` binds the entire custody dict into the request
    digest."""
    if type(request) is not dict:
        raise CurrentSourceError("request_invalid")
    allowed = {"schema", "run_id", "root", "observer", "receiver", "host",
               "worktree", "git_dir", "common_dir", "custody", "commit",
               "sources", "limits", "historical"}
    keys = set(request)
    if "custody" in keys:
        if keys & {"git_dir", "common_dir"}:
            raise CurrentSourceError("custody_variant_invalid")
        required = allowed - {"historical", "git_dir", "common_dir"}
    else:
        required = allowed - {"historical", "custody"}
    if not keys <= allowed or not keys >= required:
        raise CurrentSourceError("request_unknown_field",
                                 ",".join(sorted(keys ^ (allowed & keys))))
    if request.get("schema") != SCHEMA_REQUEST:
        raise CurrentSourceError("schema_mismatch")
    for key in ("run_id", "root", "observer", "receiver"):
        if not _is_str(request[key], IDENTITY):
            raise CurrentSourceError("identity_invalid", key)
    if request["observer"] == request["receiver"]:
        raise CurrentSourceError("observer_receiver_collision")
    if not _is_str(request["host"], HOST):
        raise CurrentSourceError("host_invalid")
    if not _is_str(request["commit"], SHA1):
        raise CurrentSourceError("commit_digest_invalid")
    validate_absolute_custody(request["worktree"])
    if "custody" in request:
        require_boundary_contains(validate_custody_variant(request["custody"]),
                                  validate_absolute_custody(request["worktree"]))
    else:
        validate_absolute_custody(request["git_dir"])
        validate_absolute_custody(request["common_dir"])
    source_paths = _validate_source_entries(request["sources"])
    limits = request["limits"]
    if type(limits) is not dict or set(limits) != set(LIMIT_KEYS):
        raise CurrentSourceError("limits_invalid")
    for key in LIMIT_KEYS:
        value = limits[key]
        cap = LIMIT_CAPS[key]
        if type(value) is not int or isinstance(value, bool) or not 1 <= value <= cap:
            raise CurrentSourceError("limits_invalid", key)
    if "historical" in request:
        historical = request["historical"]
        if type(historical) is not str or len(historical) > 256 or not historical.isprintable():
            raise CurrentSourceError("historical_opaque_invalid")
    return digest_of(request)


def _freeze_custody(custody):
    """Frozen admitted-custody state: the exact ``(mode, boundary)`` pair of
    the resolution variant, or ``None`` for the explicit triple.  The
    caller's mutable request dict is never retained, so no later mutation of
    that dict can retarget a minted view, scope or binding."""
    if custody is None:
        return None
    if type(custody) is dict and set(custody) == {"mode", "boundary"}:
        return (custody["mode"], custody["boundary"])
    raise CurrentSourceError("custody_variant_invalid")


class NativeInvocationView:
    """Immutable typed admission input handed to the native owner.

    The whole custody dict of the resolution variant is bound here instead of
    preknown resolved paths: the scope declares the boundary and mode, and the
    resolved paths are proven later from the bounded response proof.  Only the
    frozen ``(mode, boundary)`` pair of that dict is retained; ``custody``
    hands back a fresh defensive copy, so mutating the original request
    mapping -- or the returned mapping -- never changes ``binding()``, an
    already-minted scope or any admitted binding."""

    __slots__ = ("schema", "request_sha256", "run_id", "root", "host", "worktree", "git_dir",
                 "common_dir", "_custody", "commit", "source_paths", "observer", "receiver",
                 "limits_digest")

    def __init__(self, request_sha256: str, host: str, worktree: str, git_dir: str,
                 common_dir: str, commit: str, source_paths, observer: str,
                 receiver: str, limits_digest: str, run_id: str, root: str,
                 custody=None):
        object.__setattr__(self, "schema", SCHEMA_REQUEST)
        object.__setattr__(self, "request_sha256", request_sha256)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "worktree", worktree)
        object.__setattr__(self, "git_dir", git_dir)
        object.__setattr__(self, "common_dir", common_dir)
        object.__setattr__(self, "_custody", _freeze_custody(custody))
        object.__setattr__(self, "commit", commit)
        object.__setattr__(self, "source_paths", tuple(source_paths))
        object.__setattr__(self, "observer", observer)
        object.__setattr__(self, "receiver", receiver)
        object.__setattr__(self, "limits_digest", limits_digest)

    def __setattr__(self, name, value):
        raise CurrentSourceError("admission_view_immutable")

    @property
    def custody(self):
        """Defensive copy of the frozen custody variant, or ``None``."""
        return (None if self._custody is None
                else {"mode": self._custody[0], "boundary": self._custody[1]})

    @classmethod
    def of(cls, request, request_sha256: str) -> "NativeInvocationView":
        return cls(request_sha256, request["host"], request["worktree"],
                   request.get("git_dir"), request.get("common_dir"),
                   request["commit"],
                   [e["path"] for e in request["sources"]], request["observer"],
                   request["receiver"], digest_of(request["limits"]), request["run_id"],
                   request["root"], request.get("custody"))

    def binding(self) -> str:
        return digest_of({"schema": self.schema, "request_sha256": self.request_sha256,
                          "host": self.host, "worktree": self.worktree,
                          "git_dir": self.git_dir, "common_dir": self.common_dir,
                          "custody": self.custody,
                          "commit": self.commit, "source_paths": list(self.source_paths),
                          "observer": self.observer, "receiver": self.receiver,
                          "limits_digest": self.limits_digest})


class NativeInvocationOwner:
    """Interface implemented by the trusted native CLI/owner integration.

    The default implementation refuses everything.  There is no CLI flag,
    environment variable, file or request field inside this module that can
    satisfy it: only an owner object supplied by the incumbent native process
    may, and it must re-derive every admission fact itself.
    """

    def admit_invocation(self, view: NativeInvocationView, invoking_uid: int) -> bool:
        raise NativeRefused("native_invocation_refused_by_owner")

    def registered(self, invocation: "NativeInvocation") -> None:
        return None

    def invocation_active(self, invocation: "NativeInvocation") -> bool:
        """Fail-closed: an owner that keeps no records holds no invocation."""
        return False

    def authorize_publication(self, invocation: "NativeInvocation") -> bool:
        raise NativeRefused("native_publication_refused_by_owner")

    def transport_alias(self, view: NativeInvocationView):
        """Registry ssh_alias for this qualified view, or None to refuse."""
        return None


class NativeInvocation:
    """Typed immutable qualified invocation minted only at the owner boundary.

    Untrusted JSON cannot construct one: ``mint`` consults the owner, and the
    owner re-checks the exact request digest it read itself, the invoking OS
    uid, the original observer correlation, the registry host and the declared
    custody.  The scope is revocable through its owner; a revoked scope never
    authorizes a later read or publication.

    The declared custody is frozen at mint as the ``(mode, boundary)`` pair
    taken from the view's own frozen state; ``custody`` is a fresh defensive
    copy, so a caller mutating the original request dict -- or the returned
    mapping -- after mint never changes ``scope_digest`` or retargets the
    admitted scope.
    """

    __slots__ = ("schema", "scope_digest", "request_sha256", "run_id", "root", "host", "worktree",
                 "git_dir", "common_dir", "_custody", "commit", "source_paths", "observer",
                 "receiver", "invoking_uid", "issued_by", "_owner")

    def __setattr__(self, name, value):
        raise CurrentSourceError("invocation_immutable")

    @property
    def custody(self):
        """Defensive copy of the frozen custody variant, or ``None``."""
        return (None if self._custody is None
                else {"mode": self._custody[0], "boundary": self._custody[1]})

    @classmethod
    def mint(cls, view: NativeInvocationView, owner: NativeInvocationOwner,
             invoking_uid: int, nonce: str | None = None) -> "NativeInvocation":
        if type(view) is not NativeInvocationView:
            raise NativeRefused("native_view_invalid")
        if not isinstance(owner, NativeInvocationOwner) or type(owner) is dict:
            raise NativeRefused("native_owner_invalid")
        if type(invoking_uid) is not int or isinstance(invoking_uid, bool) or invoking_uid <= 0:
            raise NativeRefused("native_invoking_uid_invalid")
        if not owner.admit_invocation(view, invoking_uid):
            raise NativeRefused("native_invocation_refused_by_owner")
        if nonce is None:
            nonce = os.urandom(8).hex()
        if type(nonce) is not str or not 1 <= len(nonce) <= 128:
            raise NativeRefused("native_nonce_invalid")
        scope = object.__new__(cls)
        object.__setattr__(scope, "schema", SCHEMA_INVOCATION)
        object.__setattr__(scope, "request_sha256", view.request_sha256)
        object.__setattr__(scope, "run_id", view.run_id)
        object.__setattr__(scope, "root", view.root)
        object.__setattr__(scope, "host", view.host)
        object.__setattr__(scope, "worktree", view.worktree)
        object.__setattr__(scope, "git_dir", view.git_dir)
        object.__setattr__(scope, "common_dir", view.common_dir)
        # The view's own frozen pair is shared, never the caller's dict.
        object.__setattr__(scope, "_custody", view._custody)
        object.__setattr__(scope, "commit", view.commit)
        object.__setattr__(scope, "source_paths", view.source_paths)
        object.__setattr__(scope, "observer", view.observer)
        object.__setattr__(scope, "receiver", view.receiver)
        object.__setattr__(scope, "invoking_uid", invoking_uid)
        # A plain class-name label for the response's admission echo only; it
        # is a record of which owner boundary minted the scope and carries no
        # authentication meaning.
        object.__setattr__(scope, "issued_by", type(owner).__name__)
        object.__setattr__(scope, "_owner", owner)
        object.__setattr__(scope, "scope_digest", digest_of(
            {"schema": SCHEMA_INVOCATION, "request_sha256": view.request_sha256,
             "host": view.host, "worktree": view.worktree, "git_dir": view.git_dir,
             "common_dir": view.common_dir, "custody": view.custody,
             "commit": view.commit,
             "source_paths": list(view.source_paths), "observer": view.observer,
             "receiver": view.receiver, "invoking_uid": invoking_uid,
             "issued_by": scope.issued_by, "nonce": nonce}))
        owner.registered(scope)
        return scope

    def binds_request(self, request) -> bool:
        try:
            return (self.root == request["root"] and self.run_id == request["run_id"]
                    and self.host == request["host"] and self.worktree == request["worktree"]
                    and self.git_dir == request.get("git_dir")
                    and self.common_dir == request.get("common_dir")
                    and self.custody == request.get("custody")
                    and self.commit == request["commit"]
                    and self.observer == request["observer"]
                    and self.source_paths == tuple(e["path"] for e in request["sources"])
                    and self.receiver == request["receiver"])
        except (KeyError, TypeError):
            return False

    def binds_observation(self, response) -> bool:
        try:
            if self.custody is not None:
                # The scope binds the declared boundary and mode, not preknown
                # resolved paths; the response's resolved paths and proof are
                # independently re-derived here before any publication.
                return (self.request_sha256 == response["request_sha256"]
                        and self.root == response["root"]
                        and self.run_id == response["run_id"]
                        and self.host == response["host"]
                        and response.get("custody") == self.custody
                        and self.worktree == response["worktree"]
                        and self.commit == response["commit"]
                        and self.observer == response["observer"]
                        and self.source_paths == tuple(i["path"] for i in response["files"])
                        and self.receiver == response["receiver"]
                        and _resolution_binds(response))
            return (self.request_sha256 == response["request_sha256"]
                    and self.root == response["root"] and self.run_id == response["run_id"]
                    and self.host == response["host"]
                    and self.worktree == response["worktree"]
                    and self.git_dir == response["git_dir"]
                    and self.common_dir == response["common_dir"]
                    and self.commit == response["commit"]
                    and self.observer == response["observer"]
                    and self.source_paths == tuple(i["path"] for i in response["files"])
                    and self.receiver == response["receiver"])
        except (KeyError, TypeError):
            return False

    def confirm_active(self) -> bool:
        owner = self._owner
        if not isinstance(owner, NativeInvocationOwner):
            return False
        return bool(owner.invocation_active(self))

    def revoke(self) -> None:
        object.__setattr__(self, "_owner", None)


class Reader:
    """Pure inert reader with injectable open/spawn seams (default: real OS).

    The directory walk reuses the DirectoryChain source principle: every
    component is opened ``O_NOFOLLOW`` relative to the previous file
    descriptor, checked for type, owner (current uid or root) and mode
    (no group/world write), and every identity is re-verified after the read
    both through the descriptor and through a fresh no-follow stat.
    """

    def __init__(self, opener=None, spawn=None):
        self._opener = opener if opener is not None else self._default_open
        self._spawn = spawn if spawn is not None else subprocess.Popen

    @staticmethod
    def _default_open(path, flags, dir_fd=None):
        return os.open(path, flags, dir_fd=dir_fd)

    # -- chain walking ----------------------------------------------------
    def _check_dir(self, index, info):
        if not stat.S_ISDIR(info.st_mode):
            raise CurrentSourceError("chain_not_directory")
        if info.st_uid not in (0, os.getuid()):
            raise CurrentSourceError("chain_foreign_owner")
        if (info.st_mode & 0o022) and not (info.st_mode & stat.S_ISVTX and info.st_uid == 0):
            # Classic safe-directory rule: group/world write is refused, except
            # for a root-owned sticky directory such as /tmp, whose entries stay
            # protected by the per-component ownership and leaf checks below.
            raise CurrentSourceError("chain_group_or_world_writable")

    def _check_leaf(self, info):
        if not stat.S_ISREG(info.st_mode):
            raise CurrentSourceError("leaf_not_regular")
        if info.st_uid not in (0, os.getuid()):
            raise CurrentSourceError("leaf_foreign_owner")
        if info.st_mode & 0o022:
            raise CurrentSourceError("leaf_group_or_world_writable")
        if info.st_nlink != 1:
            raise CurrentSourceError("leaf_hardlinked")

    def walk_chain(self, parts):
        """Open ``/p1/.../pN`` returning (fds, edges).  Caller closes fds."""
        fds = [self._opener("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)]
        edges = []
        try:
            for index, part in enumerate(parts):
                fd = self._opener(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=fds[-1])
                fds.append(fd)
                info = os.fstat(fd)
                edges.append((part, info))
                self._check_dir(index, info)
        except CurrentSourceError:
            for fd in reversed(fds):
                os.close(fd)
            raise
        except OSError as exc:
            for fd in reversed(fds):
                os.close(fd)
            raise CurrentSourceError("filesystem_refused", str(exc))
        except BaseException:
            for fd in reversed(fds):
                os.close(fd)
            raise
        return fds, edges

    def _reverify_chain(self, fds, edges):
        for index, (part, info) in enumerate(edges):
            if identity(info) != identity(os.fstat(fds[index + 1])):
                raise CurrentSourceError("changed_during_read")
            if identity(info) != identity(os.stat(part, dir_fd=fds[index],
                                                follow_symlinks=False)):
                raise CurrentSourceError("changed_during_read")

    def read_leaf(self, fds, name, cap: int) -> bytes:
        """Read a regular leaf under the last directory fd of ``fds``."""
        fd = self._opener(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                          dir_fd=fds[-1])
        try:
            before = os.fstat(fd)
            self._check_leaf(before)
            if before.st_size > cap:
                raise CurrentSourceError("size_limit")
            chunks = []
            budget = min(cap, MAX_FILE_BYTES) + 1
            while budget > 0:
                chunk = os.read(fd, min(budget, 65536))
                if not chunk:
                    break
                chunks.append(chunk)
                budget -= len(chunk)
            raw = b"".join(chunks)
            if identity(before) != identity(os.fstat(fd)):
                raise CurrentSourceError("changed_during_read")
            if identity(before) != identity(os.stat(name, dir_fd=fds[-1],
                                                    follow_symlinks=False)):
                raise CurrentSourceError("changed_during_read")
            if len(raw) != before.st_size:
                raise CurrentSourceError("changed_during_read")
            return raw
        except CurrentSourceError:
            raise
        except OSError as exc:
            raise CurrentSourceError("filesystem_refused", str(exc))
        finally:
            os.close(fd)

    def read_git_relative(self, git_parts, relative, cap: int) -> bytes:
        """Read ``<gitdir>/<relative>`` with the full chain discipline."""
        fds, edges = self.walk_chain(git_parts + relative[:-1])
        try:
            self._reverify_chain(fds, edges)
            return self.read_leaf(fds, relative[-1], cap)
        finally:
            for fd in reversed(fds):
                os.close(fd)


def read_pointer(reader: Reader, dir_parts, name: str):
    """Read a small regular pointer file directly under a qualified chain.
    Returns None when absent; refuses any non-regular entry."""
    fds, _edges = reader.walk_chain(dir_parts)
    try:
        try:
            info = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CurrentSourceError("custody_invalid", str(exc)) from exc
        if not stat.S_ISREG(info.st_mode):
            raise CurrentSourceError("custody_pointer_invalid", name)
        return reader.read_leaf(fds, name, MAX_POINTER_BYTES)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _pointer_text(raw: bytes) -> str:
    try:
        return raw.decode("ascii").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise CurrentSourceError("git_pointer_invalid") from exc


def _resolve_pointer(text: str, base_parts) -> str:
    """Exact target of a Git pointer file: absolute as written, or Git's own
    relative convention resolved lexically against the directory holding the
    pointer.  Purely lexical: no link is followed and no target is adopted
    beyond what the declaration itself states."""
    if text.startswith("/"):
        parts = [p for p in text.split("/") if p]
    else:
        parts = list(base_parts)
        for component in text.split("/"):
            if component in ("", "."):
                continue
            if component == "..":
                if not parts:
                    raise CurrentSourceError("git_pointer_invalid")
                parts.pop()
                continue
            parts.append(component)
    if not parts or len(parts) > MAX_PATH_DEPTH:
        raise CurrentSourceError("git_pointer_invalid")
    for part in parts:
        if not CUSTODY_COMPONENT.fullmatch(part) or part in (".", ".."):
            raise CurrentSourceError("git_pointer_invalid")
    return "/" + "/".join(parts)


def _gitfile_target(raw: bytes) -> str:
    """Exact ``gitdir: <path>`` gitfile payload: fixed prefix, one line."""
    if not raw.startswith(b"gitdir: "):
        raise CurrentSourceError("git_pointer_invalid")
    text = _pointer_text(raw[len(b"gitdir: "):])
    if "\n" in text or "\r" in text or not text:
        raise CurrentSourceError("git_pointer_invalid")
    return text


def _pointer_lines(raw: bytes, what: str) -> str:
    """Single-line pointer payload (``commondir``/``gitdir``): multiline or
    empty content is malformed, never lexically resolved."""
    text = _pointer_text(raw)
    if "\n" in text or "\r" in text or not text:
        raise CurrentSourceError("git_pointer_invalid", what)
    return text


def _classify_git_link(reader: Reader, wt_parts, gd_parts=None):
    """Classify worktree/.git without following it: a real directory (ordinary
    repository) or an exact regular ``gitdir:`` pointer (linked worktree or
    relocated gitdir).  Anything else is refused.  With ``gd_parts`` the
    pointer target must equal that declared git_dir; resolution mode passes
    None and derives the target itself."""
    fds, _edges = reader.walk_chain(wt_parts)
    try:
        try:
            info = os.stat(".git", dir_fd=fds[-1], follow_symlinks=False)
        except FileNotFoundError as exc:
            raise CurrentSourceError("custody_invalid", ".git missing") from exc
        except OSError as exc:
            raise CurrentSourceError("custody_invalid", str(exc)) from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)
    if stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode)
                                          or stat.S_ISREG(info.st_mode)):
        raise CurrentSourceError("unsupported_git_link")
    if stat.S_ISDIR(info.st_mode):
        return ("dir", (info.st_dev, info.st_ino), None)
    fds, _edges = reader.walk_chain(wt_parts)
    try:
        raw = reader.read_leaf(fds, ".git", MAX_POINTER_BYTES)
    finally:
        for fd in reversed(fds):
            os.close(fd)
    if gd_parts is not None and _resolve_pointer(
            _gitfile_target(raw), wt_parts) != "/" + "/".join(gd_parts):
        raise CurrentSourceError("git_pointer_mismatch")
    return ("file", None, raw)


def _chain_terminal_identity(reader: Reader, parts):
    fds, _edges = reader.walk_chain(parts)
    try:
        info = os.fstat(fds[-1])
        return (info.st_dev, info.st_ino)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def check_object_store(reader: Reader, repo_parts):
    """Require a plain object store: no alternates, no promisor partial clone."""
    fds, edges = reader.walk_chain(repo_parts + ["objects"])
    info_fd = None
    try:
        reader._reverify_chain(fds, edges)
        try:
            info_fd = reader._opener("info", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=fds[-1])
        except OSError as exc:
            if exc.errno != errno.ENOENT:
                raise CurrentSourceError("custody_invalid", str(exc))
        if info_fd is not None:
            for marker in ("alternates", "promisor"):
                try:
                    marker_fd = reader._opener(marker, os.O_RDONLY | os.O_NOFOLLOW,
                                               dir_fd=info_fd)
                except OSError as exc:
                    if exc.errno != errno.ENOENT:
                        raise CurrentSourceError("custody_invalid", str(exc))
                    continue
                os.close(marker_fd)
                raise CurrentSourceError("unsafe_object_store", marker)
    finally:
        if info_fd is not None:
            os.close(info_fd)
        for fd in reversed(fds):
            os.close(fd)


def pointer_state(reader: Reader, wt_parts, gd_parts) -> dict:
    """Exact pointer snapshot: worktree/.git classification plus the git_dir
    ``commondir`` and ``gitdir`` backlink bytes."""
    return {"git": _classify_git_link(reader, wt_parts, gd_parts),
            "commondir": read_pointer(reader, gd_parts, "commondir"),
            "gitdir": read_pointer(reader, gd_parts, "gitdir")}


def inspect_custody(reader: Reader, request) -> dict:
    """Validate the three declared custody chains and their exact pointer
    graph.  Declared git_dir and common_dir are qualified independently by
    the native invocation owner; this reader never infers or adopts an
    arbitrary pointer target.  Object stores are read only from the declared
    common_dir (and re-checked on a separate per-worktree git_dir)."""
    wt = validate_absolute_custody(request["worktree"])
    gd = validate_absolute_custody(request["git_dir"])
    cd = validate_absolute_custody(request["common_dir"])
    state = pointer_state(reader, wt, gd)
    kind, dir_id, _raw = state["git"]
    if kind == "dir":
        # Ordinary repository: the declared git_dir must be exactly this .git.
        if _chain_terminal_identity(reader, gd) != dir_id:
            raise CurrentSourceError("git_pointer_mismatch")
    if state["commondir"] is None:
        # No commondir file: the git_dir must itself be the common dir.
        if gd != cd:
            raise CurrentSourceError("commondir_mismatch")
    else:
        if (_resolve_pointer(_pointer_text(state["commondir"]), gd)
                != request["common_dir"]):
            raise CurrentSourceError("commondir_mismatch")
        back = state["gitdir"]
        if (back is None or _resolve_pointer(_pointer_text(back), gd)
                != request["worktree"] + "/.git"):
            raise CurrentSourceError("gitdir_backlink_mismatch")
    # Objects live only in the declared common store; a per-worktree git_dir
    # has no object directory of its own, and alternates/promisor markers are
    # refused on the store that is actually read.
    check_object_store(reader, cd)
    return state


def _pointer_leaf_state(reader: Reader, dir_parts, name: str):
    """Exact regular pointer leaf under a qualified chain: ``(bytes,
    identity)`` or None when absent.  Symlinks, unsafe modes, foreign owners,
    hardlinks and oversize payloads are refused by the Reader discipline; no
    new IO path is introduced."""
    fds, _edges = reader.walk_chain(dir_parts)
    try:
        try:
            info = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CurrentSourceError("custody_invalid", str(exc)) from exc
        if not stat.S_ISREG(info.st_mode):
            raise CurrentSourceError("custody_pointer_invalid", name)
        return reader.read_leaf(fds, name, MAX_POINTER_BYTES), identity(info)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _chain_snapshot(reader: Reader, parts):
    """Full identity snapshot of one qualified chain: the terminal identity
    plus the identity of every walked directory edge.  A snapshot of the whole
    chain, not just the terminal stat, is what makes an ancestor rename+restore
    -- which changes the renamed directory and its parent but no terminal --
    refuse the capture."""
    fds, edges = reader.walk_chain(parts)
    try:
        return (identity(os.fstat(fds[-1])),
                tuple(identity(info) for _part, info in edges))
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _chain_identity(reader: Reader, parts):
    """Full identity of a qualified chain terminal, held for the graph
    snapshot and re-verified after the capture."""
    return _chain_snapshot(reader, parts)[0]


def custody_graph_state(reader: Reader, wt_parts, gd_parts, cd_parts) -> dict:
    """Retained graph snapshot: worktree/.git classification, pointer leaf
    bytes with their identities, and the full identity snapshot -- terminal
    plus every walked directory edge -- of the worktree, git_dir and common
    chains.  Compared before and after the whole capture, so replacement by
    identical bytes, a changed-then-reverted pointer or an ancestor
    rename+restore is refused."""
    kind, dir_id, raw = _classify_git_link(reader, wt_parts, gd_parts)
    leaf = None if kind == "dir" else _pointer_leaf_state(reader, wt_parts, ".git")
    snapshots = tuple(_chain_snapshot(reader, parts)
                      for parts in (wt_parts, gd_parts, cd_parts))
    return {"git": (kind, dir_id, raw), "leaf": leaf,
            "commondir": _pointer_leaf_state(reader, gd_parts, "commondir"),
            "gitdir": _pointer_leaf_state(reader, gd_parts, "gitdir"),
            "dirs": tuple(snapshot[0] for snapshot in snapshots),
            "edges": tuple(snapshot[1] for snapshot in snapshots)}


class CustodyGraphGuard:
    """Held-descriptor custody graph guard for the resolution variant.

    After the finite resolution has produced the discovery graph, every
    directory of the worktree, git_dir and common_dir chains and every
    no-follow regular pointer leaf -- the exact ``.git`` gitfile when the link
    is a file, plus the linked ``commondir``/``gitdir`` leaves -- is held open
    through the existing Reader primitives.  ``verify`` re-derives the whole
    held graph, full chain edges included rather than a terminal stat alone,
    and compares it to the discovery snapshot, so an ancestor rename+restore,
    a same-byte leaf replacement, a changed-then-reverted pointer (new ctime)
    or a leaf that became a symlink, foreign, group-writable or hardlinked
    refuses before any object read.  Absent ordinary pointers must remain
    absent.  Every owned descriptor closes exactly once on every outcome.
    """

    def __init__(self, reader: Reader, graph: dict, wt_parts, gd_parts, cd_parts):
        self._reader = reader
        self._graph = graph
        kind = graph["git"][0]
        self._chains = (tuple(wt_parts), tuple(gd_parts), tuple(cd_parts))
        self._leaves = []
        if kind == "file":
            self._leaves.append((0, ".git", graph["leaf"]))
        self._leaves.append((1, "commondir", graph["commondir"]))
        self._leaves.append((1, "gitdir", graph["gitdir"]))
        self._fds = []
        self._held = []
        self._leaf_fds = []
        self._closed = False

    def hold(self):
        """Open and hold every custody chain and pointer leaf.  Descriptors
        are recorded as they are taken, so a refused hold still closes exactly
        what it opened."""
        for parts in self._chains:
            fds, edges = self._reader.walk_chain(parts)
            self._fds.extend(fds)
            self._held.append((fds, edges))
        for index, name, initial in self._leaves:
            self._hold_leaf(index, name, initial)
        return self

    def _hold_leaf(self, chain_index, name, initial):
        fds, _edges = self._held[chain_index]
        try:
            info = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
        except FileNotFoundError:
            if initial is not None:
                raise CurrentSourceError("changed_during_read")
            self._leaf_fds.append((chain_index, name, None))
            return
        except OSError as exc:
            raise CurrentSourceError("custody_invalid", str(exc)) from exc
        if initial is None:
            # An absent ordinary pointer must remain absent.
            raise CurrentSourceError("changed_during_read")
        if not stat.S_ISREG(info.st_mode):
            raise CurrentSourceError("custody_pointer_invalid", name)
        try:
            fd = self._reader._opener(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                      dir_fd=fds[-1])
        except OSError as exc:
            raise CurrentSourceError("filesystem_refused", str(exc)) from exc
        self._fds.append(fd)
        try:
            held = os.fstat(fd)
        except OSError as exc:
            raise CurrentSourceError("filesystem_refused", str(exc)) from exc
        self._reader._check_leaf(held)
        if identity(held) != initial[1]:
            raise CurrentSourceError("changed_during_read")
        self._leaf_fds.append((chain_index, name, fd))

    def verify(self):
        """Re-verify the full held graph against the discovery snapshot: every
        held directory edge and terminal through ``_reverify_chain``, every
        held leaf identity and bounded bytes through ``read_leaf``."""
        if self._closed:
            raise CurrentSourceError("custody_guard_closed")
        for index, (chain, initial_edges) in enumerate(zip(self._held,
                                                           self._graph["edges"])):
            fds, edges = chain
            self._reader._reverify_chain(fds, edges)
            if (tuple(identity(info) for _part, info in edges) != initial_edges
                    or identity(os.fstat(fds[-1])) != self._graph["dirs"][index]):
                raise CurrentSourceError("changed_during_read")
        for chain_index, name, fd in self._leaf_fds:
            initial = self._leaf_initial(chain_index, name)
            fds, _edges = self._held[chain_index]
            try:
                info = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
                missing = False
            except FileNotFoundError:
                missing = True
            except OSError as exc:
                raise CurrentSourceError("filesystem_refused", str(exc)) from exc
            if missing:
                # An absent ordinary pointer must remain absent.
                if fd is not None:
                    raise CurrentSourceError("changed_during_read")
                continue
            if fd is None:
                # Absent must stay absent; anything now there is a change.
                raise CurrentSourceError("changed_during_read")
            if (identity(info) != initial[1]
                    or identity(os.fstat(fd)) != initial[1]):
                raise CurrentSourceError("changed_during_read")
            if self._reader.read_leaf(fds, name, MAX_POINTER_BYTES) != initial[0]:
                raise CurrentSourceError("changed_during_read")

    def _leaf_initial(self, chain_index, name):
        for index, leaf_name, initial in self._leaves:
            if index == chain_index and leaf_name == name:
                return initial
        raise CurrentSourceError("custody_guard_unknown_leaf", name)

    def close(self):
        """Close every descriptor this guard owns; safe to call twice."""
        if self._closed:
            return
        self._closed = True
        for fd in reversed(self._fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds = []
        self._held = []
        self._leaf_fds = []


def _resolved_within(boundary_parts, parts):
    """A *derived* path must land strictly inside the declared boundary; an
    escape is a resolution failure, not merely a bad declaration."""
    if (len(parts) <= len(boundary_parts)
            or parts[:len(boundary_parts)] != boundary_parts):
        raise CurrentSourceError("custody_resolution_invalid", "boundary_escape")


def resolve_custody(reader: Reader, request):
    """Finite resolution of the custody variant: inspect the exact selected
    worktree/.git with strict Reader checks only and derive git_dir and
    common_dir inside the declared boundary, before any object store or object
    read.  An ordinary real directory resolves to
    ``git_dir = common_dir = <worktree>/.git``; a regular gitfile must resolve
    inside the boundary to the standard linked shape
    ``<common>/worktrees/<one component>`` with ``commondir`` inside the
    boundary and an exact ``<worktree>/.git`` backlink; a relocated separate
    git dir is refused.  There is no scan, no guessed path, no upward walk, no
    shell or Git discovery and no environment probe.  Returns
    ``(git_dir, common_dir, proof, graph)``."""
    custody = request["custody"]
    wt_parts = validate_absolute_custody(request["worktree"])
    boundary_parts = validate_custody_variant(custody)
    require_boundary_contains(boundary_parts, wt_parts)
    kind, dir_id, raw = _classify_git_link(reader, wt_parts)
    commondir_state = backlink_state = None
    if kind == "dir":
        git_parts = wt_parts + [".git"]
        for name in ("commondir", "gitdir"):
            # An ordinary .git carries no linked-worktree pointers; one that
            # does is a nonstandard shape, never silently adopted.
            if _pointer_leaf_state(reader, git_parts, name) is not None:
                raise CurrentSourceError("custody_resolution_invalid", name)
    else:
        git_parts = validate_absolute_custody(
            _resolve_pointer(_gitfile_target(raw), wt_parts))
        _resolved_within(boundary_parts, git_parts)
        commondir_state = _pointer_leaf_state(reader, git_parts, "commondir")
        if commondir_state is None:
            # Relocated nonlinked separate-git-dir: nothing here resolves it.
            raise CurrentSourceError("custody_resolution_invalid", "relocated")
        common_parts = validate_absolute_custody(
            _resolve_pointer(_pointer_lines(commondir_state[0], "commondir"),
                             git_parts))
        _resolved_within(boundary_parts, common_parts)
        if (git_parts[:len(common_parts)] != common_parts
                or len(git_parts) != len(common_parts) + 2
                or git_parts[len(common_parts)] != "worktrees"
                or not CUSTODY_COMPONENT.fullmatch(git_parts[-1])):
            raise CurrentSourceError("custody_resolution_invalid", "linked_shape")
        backlink_state = _pointer_leaf_state(reader, git_parts, "gitdir")
        if (backlink_state is None
                or _resolve_pointer(_pointer_lines(backlink_state[0], "gitdir"),
                                    git_parts)
                != "/" + "/".join(wt_parts) + "/.git"):
            raise CurrentSourceError("gitdir_backlink_mismatch")
    git_dir = "/" + "/".join(git_parts)
    common_dir = git_dir if kind == "dir" else "/" + "/".join(common_parts)
    snapshots = tuple(_chain_snapshot(reader, parts) for parts in
                      (wt_parts, git_parts,
                       git_parts if kind == "dir" else common_parts))
    graph = {"git": (kind, dir_id, raw),
             "leaf": None if kind == "dir" else _pointer_leaf_state(reader, wt_parts, ".git"),
             "commondir": commondir_state, "gitdir": backlink_state,
             "dirs": tuple(snapshot[0] for snapshot in snapshots),
             "edges": tuple(snapshot[1] for snapshot in snapshots)}
    proof = resolution_proof(request, graph, git_dir, common_dir)
    return git_dir, common_dir, proof, graph


def resolution_proof(request, graph, git_dir: str, common_dir: str) -> dict:
    """Bounded proof of the resolved graph: exact finite pointer bytes plus the
    graph shape and identity snapshot.  Shipped only for the custody variant
    and sealed with the rest of the response body."""
    kind, dir_id, raw = graph["git"]
    leaf = graph["leaf"]

    def entry(state):
        if state is None:
            return {"bytes_b64": None, "identity": None}
        pointer, info = state
        return {"bytes_b64": base64.b64encode(pointer).decode("ascii"),
                "identity": list(info)}

    return {"mode": request["custody"]["mode"],
            "boundary": request["custody"]["boundary"],
            "worktree": request["worktree"], "git_dir": git_dir,
            "common_dir": common_dir,
            "git_link": {"kind": kind,
                         "bytes_b64": None if raw is None else
                         base64.b64encode(raw).decode("ascii"),
                         "identity": None if leaf is None else list(leaf[1])},
            "commondir": entry(graph["commondir"]),
            "gitdir_backlink": entry(graph["gitdir"]),
            "dir_ids": {"worktree": list(graph["dirs"][0]),
                        "git_dir": list(graph["dirs"][1]),
                        "common_dir": list(graph["dirs"][2])}}


def custody_identity(paths):
    """before/after identity snapshot for declared custody directories."""
    snapshot = []
    for path in paths:
        snapshot.append(identity(os.stat(path, follow_symlinks=False)))
    return tuple(snapshot)


def select_git_binary() -> str:
    for candidate in GIT_CANDIDATES:
        try:
            info = os.stat(candidate)
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if info.st_uid not in (0, os.getuid()):
            continue
        if info.st_mode & 0o022 or not info.st_mode & 0o111:
            continue
        return candidate
    raise CurrentSourceError("packed_unsupported_no_git")


def git_environment(git_dir: str) -> dict:
    """Constructed from scratch: every inherited Git environment is cleared.
    No HOME, no shell, no config, no prompts, no discovery upward."""
    return {"PATH": "/usr/bin:/bin", "GIT_DIR": git_dir,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "protocol.allow", "GIT_CONFIG_VALUE_0": "never",
            "GIT_CONFIG_KEY_1": "protocol.file.allow", "GIT_CONFIG_VALUE_1": "never",
            "GIT_TERMINAL_PROMPT": "0", "GIT_CEILING_DIRECTORIES": "/",
            "LC_ALL": "C"}


def _git_limits():
    # This is the isolated, fixed Git reader child, never a provider process.
    import resource
    for kind, cap in ((resource.RLIMIT_AS, 512 * 1024 * 1024), (resource.RLIMIT_CORE, 0),
                      (resource.RLIMIT_FSIZE, 0)):
        soft, hard = resource.getrlimit(kind)
        bound = cap if hard == resource.RLIM_INFINITY else min(cap, hard)
        resource.setrlimit(kind, (bound, bound))


def _git_batch(reader: Reader, argv, payload: bytes, env, deadline: float):
    # A packed object can expand inside Git before stdout is capped. Only the
    # qualified Linux RLIMIT_AS path admits this child; other platforms refuse.
    if not sys.platform.startswith("linux"):
        raise CurrentSourceError("packed_limits_unavailable")
    if (len(argv) != 5 or argv[:3] != [select_git_binary()] + list(GIT_ARGV_PREFIX)
            or argv[3] != "cat-file" or argv[4] not in ("--batch", "--batch-check")):
        raise CurrentSourceError("argv_constrained")
    try:
        proc = reader._spawn(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, cwd="/", close_fds=True,
                             preexec_fn=_git_limits, start_new_session=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CurrentSourceError("process_refused", str(exc))
    import selectors
    end = min(time.monotonic() + deadline, getattr(reader, 'deadline', float('inf')))
    selector = selectors.DefaultSelector()
    buffers = {'out': bytearray(), 'err': bytearray()}
    try:
        proc.stdin.write(payload)
        proc.stdin.close()
        for stream, name in ((proc.stdout, 'out'), (proc.stderr, 'err')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise CurrentSourceError('process_deadline')
            for key, _ in selector.select(remaining):
                part = os.read(key.fileobj.fileno(), 65536)
                if not part:
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(part)
                limit = MAX_BYTES_TOTAL + 256 if key.data == 'out' else 16384
                if len(buffers[key.data]) > limit:
                    raise CurrentSourceError('process_output_limit')
        try:
            proc.wait(timeout=max(0.001, end - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise CurrentSourceError('process_deadline')
        if proc.returncode != 0:
            raise CurrentSourceError('process_failed')
        if buffers['err']:
            raise CurrentSourceError('process_stderr')
        return bytes(buffers['out'])
    finally:
        selector.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            stream.close()


def _verify_object(payload: bytes, oid: str, want_type: str, cap: int) -> bytes:
    """Raw SHA-1 proof over the Git ``<type> <len>\\0`` header plus bytes."""
    header_end = payload.find(b"\x00", 0, 64)
    if header_end < 0:
        raise CurrentSourceError("object_header_invalid")
    header = payload[:header_end]
    body = payload[header_end + 1:]
    fields = header.split(b" ")
    if len(fields) != 2 or not fields[1].isdigit():
        raise CurrentSourceError("object_header_invalid")
    object_type = fields[0].decode("ascii", "replace")
    if object_type not in ("commit", "tree", "blob"):
        raise CurrentSourceError("object_type_invalid")
    if object_type != want_type:
        raise CurrentSourceError("object_type_mismatch")
    if int(fields[1]) != len(body) or len(body) > cap:
        raise CurrentSourceError("object_size_mismatch")
    if hashlib.sha1(payload).hexdigest() != oid:
        raise CurrentSourceError("object_hash_mismatch")
    return body


def _loose_state(reader: Reader, common_parts, oid: str) -> str:
    """Presence probe for a loose object in the declared common store.  A
    pruned shard directory simply means the object lives in a pack; a symlink
    or non-directory shard is a hard refusal, never a silent fallback."""
    fds, edges = reader.walk_chain(common_parts + ["objects"])
    shard_fd = None
    try:
        reader._reverify_chain(fds, edges)
        try:
            shard = os.stat(oid[:2], dir_fd=fds[-1], follow_symlinks=False)
        except FileNotFoundError:
            return "missing"
        except OSError as exc:
            if exc.errno in (errno.ENOTDIR, errno.ELOOP):
                return "invalid"
            raise CurrentSourceError("filesystem_refused", str(exc))
        if not stat.S_ISDIR(shard.st_mode):
            return "invalid"
        reader._check_dir(0, shard)
        shard_fd = reader._opener(oid[:2], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=fds[-1])
        try:
            os.stat(oid[2:], dir_fd=shard_fd, follow_symlinks=False)
            return "present"
        except FileNotFoundError:
            return "missing"
        except OSError as exc:
            if exc.errno in (errno.ENOTDIR, errno.ELOOP):
                return "invalid"
            raise CurrentSourceError("filesystem_refused", str(exc))
    except OSError as exc:
        raise CurrentSourceError("filesystem_refused", str(exc))
    finally:
        if shard_fd is not None:
            os.close(shard_fd)
        for fd in reversed(fds):
            os.close(fd)


def _read_loose(reader: Reader, common_parts, oid: str, want_type: str, cap: int):
    raw = reader.read_git_relative(common_parts, ["objects", oid[:2], oid[2:]],
                                   cap + 4096)
    d = zlib.decompressobj()
    try:
        full = d.decompress(raw, cap + 1)
    except zlib.error as exc:
        raise CurrentSourceError("object_zlib_invalid", str(exc))
    if not d.eof or d.unconsumed_tail or d.unused_data:
        raise CurrentSourceError("object_size_limit")
    return _verify_object(full, oid, want_type, cap)


def packed_identity(reader, common_dir):
    """No symlink/alternate pack files; bound the directory and retain exact
    identities around Git's path-based reads. GC or rotation refuses this read."""
    parts = validate_absolute_custody(common_dir) + ['objects', 'pack']
    fds, edges = reader.walk_chain(parts)
    try:
        names = os.listdir(fds[-1])
        if len(names) > 512:
            raise CurrentSourceError('pack_count_limit')
        rows = []
        for name in sorted(names):
            if not re.fullmatch(r'pack-[0-9a-f]{40}\.(pack|idx|rev|bitmap)', name):
                raise CurrentSourceError('unsafe_pack_store')
            info = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
            reader._check_leaf(info)
            rows.append((name, identity(info)))
        reader._reverify_chain(fds, edges)
        return (identity(os.fstat(fds[-1])), tuple(rows))
    except OSError as exc:
        raise CurrentSourceError('filesystem_refused') from exc
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _read_packed(reader: Reader, common_dir: str, oid: str, want_type: str,
                 cap: int, deadline: float):
    before = packed_identity(reader, common_dir)
    git = select_git_binary()
    argv = [git] + list(GIT_ARGV_PREFIX) + ["cat-file"]
    env = git_environment(common_dir)
    check = _git_batch(reader, argv + ["--batch-check"], (oid + "\n").encode(),
                       env, deadline)
    lines = check.split(b"\n")
    if len(lines) != 2 or lines[1] != b"":
        raise CurrentSourceError("batch_check_invalid")
    fields = lines[0].split()
    if len(fields) != 3:
        if b"missing" in lines[0] or b"ambiguous" in lines[0]:
            raise CurrentSourceError("object_missing")
        raise CurrentSourceError("batch_check_invalid")
    if fields[0].decode("ascii", "replace") != oid:
        raise CurrentSourceError("batch_check_invalid")
    object_type = fields[1].decode("ascii", "replace")
    if object_type != want_type:
        raise CurrentSourceError("object_type_mismatch")
    if not fields[2].isdigit() or int(fields[2]) > cap:
        raise CurrentSourceError("size_limit")
    size = int(fields[2])
    out = _git_batch(reader, argv + ["--batch"], (oid + "\n").encode(), env, deadline)
    head, sep, body = out.partition(b"\n")
    if not sep or head.split() != [fields[0], fields[1], fields[2]]:
        raise CurrentSourceError("batch_header_invalid")
    if len(body) != size + 1 or not body.endswith(b"\n"):
        raise CurrentSourceError("object_size_mismatch")
    result = _verify_object(b"%s %d\x00%s" % (object_type.encode(), size, body[:-1]),
                            oid, want_type, cap)
    if packed_identity(reader, common_dir) != before:
        raise CurrentSourceError("changed_during_read")
    return result


def read_object(reader: Reader, common_parts, common_dir: str, oid: str,
                want_type: str, cap: int, deadline: float):
    """Read one object from the declared common store: loose first, packed
    through the constrained batch.  Returns (payload, store)."""
    if time.monotonic() > getattr(reader, "deadline", float('inf')):
        raise CurrentSourceError("process_deadline")
    loose = _loose_state(reader, common_parts, oid)
    if loose == "invalid":
        raise CurrentSourceError("loose_custody_invalid")
    if loose == "present":
        body, store = _read_loose(reader, common_parts, oid, want_type, cap), "loose"
    else:
        body, store = _read_packed(reader, common_dir, oid, want_type, cap, deadline), "packed"
    if hasattr(reader, 'git_proofs') and want_type in ('commit', 'tree'):
        reader.git_proofs[oid] = (want_type, body)
        if sum(len(raw) for _, raw in reader.git_proofs.values()) > MAX_BYTES_TOTAL:
            raise CurrentSourceError('proof_size_limit')
    return body, store


def parse_commit(payload: bytes) -> str:
    head = payload.split(b"\n", 1)[0].split()
    if len(head) != 2 or head[0] != b"tree" or not _is_str(head[1].decode("ascii", "replace"), SHA1):
        raise CurrentSourceError("commit_header_invalid")
    return head[1].decode("ascii")


def parse_tree(payload: bytes):
    entries = []
    offset = 0
    while offset < len(payload):
        space = payload.find(b" ", offset)
        nul = payload.find(b"\x00", space + 1) if space >= 0 else -1
        if space < 0 or nul < 0 or nul + 21 > len(payload):
            raise CurrentSourceError("tree_invalid")
        mode = payload[offset:space]
        name = payload[space + 1:nul]
        oid = payload[nul + 1:nul + 21].hex()
        try:
            mode_text = mode.decode("ascii")
            name_text = name.decode("utf-8")
        except UnicodeDecodeError:
            raise CurrentSourceError("tree_invalid")
        if not mode_text.isdigit() or not name_text:
            raise CurrentSourceError("tree_invalid")
        entries.append((mode_text, name_text, oid))
        offset = nul + 21
    return entries


def resolve_tree_path(reader: Reader, common_parts, common_dir: str, commit: str,
                     relpath: str, want_type: str, cap: int, deadline: float):
    """Prove path membership against the requested commit.  Returns
    (leaf payload, membership chain, leaf object store)."""
    commit_payload, commit_store = read_object(reader, common_parts, common_dir,
                                               commit, "commit", MAX_COMMIT_BYTES,
                                               deadline)
    current = parse_commit(commit_payload)
    membership = [{"component": "<commit>", "kind": "commit", "object_id": commit}]
    parts = relpath.split("/")
    for depth, component in enumerate(parts):
        last = depth == len(parts) - 1
        payload, store = read_object(reader, common_parts, common_dir, current,
                                     "tree", MAX_TREE_BYTES, deadline)
        entry = None
        for mode, name, oid in parse_tree(payload):
            if name == component:
                entry = (mode, oid)
                break
        if entry is None:
            raise CurrentSourceError("path_not_in_tree", relpath)
        mode, current = entry
        if last:
            kind = {"100644": "blob", "100755": "blob"}.get(mode)
            if kind is None:
                raise CurrentSourceError("unsupported_path_kind", mode)
            membership.append({"component": component, "kind": kind, "object_id": current})
            leaf, leaf_store = read_object(reader, common_parts, common_dir, current,
                                           want_type, cap, deadline)
            return leaf, membership, leaf_store
        if mode != "40000":
            raise CurrentSourceError("unsupported_path_kind", mode)
        membership.append({"component": component, "kind": "tree", "object_id": current})
    raise CurrentSourceError("path_not_in_tree", relpath)


def observe_remote(request, reader=None) -> dict:
    """Remote half: custody triple verification plus the bounded object reads.

    This function's reviewed source ships inside the generated reader, so the
    transport genuinely executes the safe object reader for the exact
    qualified request instead of merely validating a pre-baked response."""
    reader = reader if reader is not None else Reader()
    try:
        request_digest = validate_request(request)
    except CurrentSourceError as exc:
        return _remote_refusal(request, None, exc.reason)
    guard = None
    try:
        wt = validate_absolute_custody(request["worktree"])
        resolution = None
        if "custody" in request:
            # Resolved graph first, then the full existing triple proof against
            # the resolved paths -- boundary and linked-shape checks happen
            # before any object store or object read.
            git_dir, common_dir, resolution, graph = resolve_custody(reader, request)
            gd = validate_absolute_custody(git_dir)
            cd = validate_absolute_custody(common_dir)
            # Finite paths are resolved first; then the whole graph is held
            # open and compared to the discovery snapshot BEFORE
            # inspect_custody, check_object_store or any object read.
            guard = CustodyGraphGuard(reader, graph, wt, gd, cd)
            guard.hold()
            guard.verify()
            inspect_custody(reader, {"worktree": request["worktree"],
                                     "git_dir": git_dir, "common_dir": common_dir})
        else:
            gd = validate_absolute_custody(request["git_dir"])
            cd = validate_absolute_custody(request["common_dir"])
            inspect_custody(reader, request)
        worktree_path = "/" + "/".join(wt)
        git_path = "/" + "/".join(gd)
        common_path = "/" + "/".join(cd)
        if resolution is not None:
            before = (custody_identity([worktree_path, git_path, common_path]), graph)
        else:
            before = (custody_identity([worktree_path, git_path, common_path]),
                      pointer_state(reader, wt, gd))
        limits = request["limits"]
        deadline = limits["deadline_ms"] / 1000.0
        reader.deadline = time.monotonic() + deadline
        reader.git_proofs = {}
        if guard is not None:
            # Immediately before the first object read: the full held chains
            # and every held pointer leaf must still match the discovery
            # graph, or nothing at all is read.
            guard.verify()
        commit_raw, _ = read_object(reader, cd, common_path, request['commit'],
                                    'commit', MAX_COMMIT_BYTES, deadline)
        root_tree = parse_commit(commit_raw)
        read_object(reader, cd, common_path, root_tree, 'tree', MAX_TREE_BYTES, deadline)
        files = []
        remaining = limits["max_bytes_total"]
        for entry in request["sources"]:
            cap = min(limits["max_file_bytes"], remaining)
            if cap <= 0:
                raise CurrentSourceError("size_budget_exhausted", entry["path"])
            leaf, membership, store = resolve_tree_path(
                reader, cd, common_path, request["commit"], entry["path"],
                "blob", cap, deadline)
            if "blob" in entry and membership[-1]["object_id"] != entry["blob"]:
                raise CurrentSourceError("object_mismatch", entry["path"])
            if "size" in entry and len(leaf) != entry["size"]:
                raise CurrentSourceError("declared_size_mismatch", entry["path"])
            remaining -= len(leaf)
            files.append({"path": entry["path"], "kind": "source",
                          "status": "RETRIEVED", "bytes": len(leaf),
                          "sha256": hashlib.sha256(leaf).hexdigest(),
                          "content_b64": base64.b64encode(leaf).decode('ascii'),
                          "object_id": membership[-1]["object_id"],
                          "object_store": store, "membership": membership,
                          "remaining_budget": remaining})
        if resolution is not None:
            # After capture: the held graph is re-verified before the retained
            # snapshot comparison, so a mutation during the object reads never
            # yields source payload.
            guard.verify()
            after = (custody_identity([worktree_path, git_path, common_path]),
                     custody_graph_state(reader, wt, gd, cd))
        else:
            after = (custody_identity([worktree_path, git_path, common_path]),
                     pointer_state(reader, wt, gd))
        if after != before:
            raise CurrentSourceError("changed_during_read")
        body = {"schema": SCHEMA_OBSERVATION, "run_id": request["run_id"],
                "root": request["root"], "observer": request["observer"],
                "receiver": request["receiver"], "host": request["host"],
                "worktree": request["worktree"],
                "git_dir": request.get("git_dir", git_path),
                "common_dir": request.get("common_dir", common_path),
                "commit": request["commit"],
                "request_sha256": request_digest, "status": "OBSERVED",
                "reason": None, "files": files, "limits": dict(limits),
                "git_objects": [{'object_id': oid, 'kind': kind, 'bytes': len(raw),
                    'content_b64': base64.b64encode(raw).decode('ascii')}
                    for oid, (kind, raw) in sorted(reader.git_proofs.items())],
                "commitments": {"schema": SCHEMA_RECEIPT,
                                "no_claims": list(NO_CLAIMS)}}
        if resolution is not None:
            # Resolved actual paths plus the bounded graph proof, sealed with
            # the body under the exact request digest.
            body["custody"] = request["custody"]
            body["resolution"] = resolution
        if len(canonical(body)) > MAX_RESPONSE:
            return _remote_refusal(request, request_digest, "response_limit")
        return body
    except CurrentSourceError as exc:
        return _remote_refusal(request, request_digest,
                               exc.reason, "UNAVAILABLE"
                               if exc.reason == "changed_during_read" else "REFUSED")
    finally:
        # Every outcome -- observed, refused or mutated graph -- releases the
        # held custody descriptors.
        if guard is not None:
            guard.close()


def _remote_refusal(request, request_digest, reason, status="REFUSED") -> dict:
    """Bounded refusal body with echo fields when the request is a dict."""
    def echo(key):
        value = request.get(key) if type(request) is dict else None
        return value if _is_str(value, IDENTITY) or _is_str(value, HOST) else None
    def echo_path(key):
        value = request.get(key) if type(request) is dict else None
        return value if type(value) is str and value.startswith("/") else None
    return {"schema": SCHEMA_OBSERVATION, "run_id": echo("run_id"),
            "root": echo("root"), "observer": echo("observer"),
            "receiver": echo("receiver"), "host": echo("host"),
            "worktree": echo_path("worktree"), "git_dir": echo_path("git_dir"),
            "common_dir": echo_path("common_dir"), "commit": echo("commit"),
            "request_sha256": request_digest, "status": status, "reason": reason,
            "files": [], "git_objects": [], "limits": dict(DEFAULT_LIMITS),
            "commitments": {"schema": SCHEMA_RECEIPT, "no_claims": list(NO_CLAIMS)}}


BODY_KEYS = {"schema", "run_id", "root", "observer", "receiver", "host", "worktree",
             "git_dir", "common_dir", "commit", "request_sha256", "status", "reason",
             "files", "git_objects", "limits", "commitments"}
CUSTODY_BODY_KEYS = BODY_KEYS | {"custody", "resolution"}
RESOLUTION_KEYS = {"mode", "boundary", "worktree", "git_dir", "common_dir",
                   "git_link", "commondir", "gitdir_backlink", "dir_ids"}
GIT_LINK_KEYS = {"kind", "bytes_b64", "identity"}
POINTER_KEYS = {"bytes_b64", "identity"}
DIR_ID_KEYS = {"worktree", "git_dir", "common_dir"}
ADMISSION_KEYS = {"state", "scope_digest", "issued_by"}
RECEIPT_KEYS = {"schema", "response_sha256", "request_sha256", "admission_state",
                "scope_digest", "observer", "receiver", "root", "commit", "no_claims"}
RESPONSE_KEYS = BODY_KEYS | {"admission", "receipt"}
FILE_KEYS = {"path", "kind", "status", "bytes", "sha256", "object_id",
             "object_store", "membership", "remaining_budget", "content_b64"}
MEMBERSHIP_KEYS = {"component", "kind", "object_id"}
STATES = ("ADMITTED", "ADMISSION_MISSING", "ADMISSION_INVALID",
          "ADMISSION_REFUSED", "ADMISSION_REVOKED", "NOT_SEEKED")


def _admit(request, request_digest, invocation):
    """Authoritative admission gate.  Zero reads happen before it passes.
    Only a typed NativeInvocation minted at the owner boundary qualifies; a
    caller boolean, digest, mapping or label never does."""
    if invocation is None:
        return None, "ADMISSION_MISSING"
    if (type(invocation) is not NativeInvocation
            or invocation.request_sha256 != request_digest
            or not invocation.binds_request(request)):
        return None, "ADMISSION_INVALID"
    if not invocation.confirm_active():
        return None, "ADMISSION_REVOKED"
    return invocation, "ADMITTED"


def _identity_list(value) -> bool:
    # identity() is the fixed 8-field snapshot: (dev, ino, size, mtime_ns,
    # ctime_ns, mode, uid, nlink).
    return (type(value) is list and len(value) == 8
            and all(type(item) is int and not isinstance(item, bool) and item >= 0
                    for item in value))


def _incumbent_transport(alias: str):
    """The existing host-registry strict-SSH bounded transport; never raw SSH."""
    from artifact_delivery import transport
    return lambda request, _alias=alias: transport(_alias, request)


def validate_git_payloads(document):
    """Recompute Git identities and path membership from the delivered bytes."""
    rows = document.get('git_objects')
    if type(rows) is not list or not 2 <= len(rows) <= MAX_SOURCES * MAX_PATH_DEPTH + 2:
        raise CurrentSourceError('git_proofs_invalid')
    objects = {}; total = 0
    def decode(row, cap):
        if (type(row.get('content_b64')) is not str or type(row.get('bytes')) is not int
                or not 0 <= row['bytes'] <= cap or len(row['content_b64']) > MAX_RESPONSE):
            raise CurrentSourceError('git_payload_invalid')
        try:
            raw = base64.b64decode(row['content_b64'], validate=True)
        except ValueError:
            raise CurrentSourceError('git_payload_invalid')
        if len(raw) != row['bytes']:
            raise CurrentSourceError('git_payload_invalid')
        return raw
    for row in rows:
        if (type(row) is not dict or set(row) != {'object_id','kind','bytes','content_b64'}
                or not _is_str(row['object_id'], SHA1) or row['kind'] not in ('commit','tree')
                or row['object_id'] in objects):
            raise CurrentSourceError('git_proofs_invalid')
        cap = MAX_COMMIT_BYTES if row['kind'] == 'commit' else MAX_TREE_BYTES
        raw = decode(row, cap); total += len(raw)
        if total > MAX_BYTES_TOTAL:
            raise CurrentSourceError('proof_size_limit')
        _verify_object(row['kind'].encode() + b' ' + str(len(raw)).encode() + b'\0' + raw,
                       row['object_id'], row['kind'], cap)
        objects[row['object_id']] = (row['kind'], raw)
    def get(oid, kind):
        if oid not in objects or objects[oid][0] != kind:
            raise CurrentSourceError('git_proof_missing')
        used.add(oid)
        return objects[oid][1]
    used = set(); commit = document['commit']
    root = parse_commit(get(commit, 'commit'))
    get(root, 'tree')  # Required even when no file payload was requested.
    for item in document['files']:
        raw = decode(item, MAX_FILE_BYTES)
        oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if oid != item['object_id'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise CurrentSourceError('git_payload_mismatch')
        parts = validate_relative_path(item['path']).split('/')
        current = root
        expected = [{'component':'<commit>', 'kind':'commit', 'object_id':commit}]
        for index, part in enumerate(parts):
            entries = parse_tree(get(current, 'tree'))
            names = [name for _, name, _ in entries]
            if len(set(names)) != len(names):
                raise CurrentSourceError('tree_invalid')
            matches = [(mode, target) for mode, name, target in entries if name == part]
            if len(matches) != 1:
                raise CurrentSourceError('git_membership_mismatch')
            mode, current = matches[0]
            last = index == len(parts)-1
            if mode not in (('100644','100755') if last else ('40000',)):
                raise CurrentSourceError('git_membership_mismatch')
            expected.append({'component':part, 'kind':'blob' if last else 'tree',
                             'object_id':current})
        if current != oid or item['membership'] != expected:
            raise CurrentSourceError('git_membership_mismatch')
    if used != set(objects):
        raise CurrentSourceError('unexpected_git_proof')


def _proof_pointer(entry, parts, expected: str, what: str) -> None:
    """Decode one returned pointer entry and re-derive its exact resolved
    target from the finite bytes alone."""
    if (type(entry) is not dict or set(entry) != POINTER_KEYS
            or type(entry["bytes_b64"]) is not str
            or not _identity_list(entry["identity"])):
        raise CurrentSourceError("custody_proof_invalid", what)
    try:
        raw = base64.b64decode(entry["bytes_b64"], validate=True)
        resolved = _resolve_pointer(_pointer_lines(raw, what), parts)
    except (ValueError, CurrentSourceError):
        raise CurrentSourceError("custody_proof_invalid", what) from None
    if len(raw) > MAX_POINTER_BYTES or resolved != expected:
        raise CurrentSourceError("custody_proof_invalid", what)


def validate_resolution_proof(resolution, response) -> None:
    """Independent delivery-side validation of the custody variant's bounded
    proof: re-derive the resolved git_dir from the returned gitfile bytes, the
    common_dir from the returned commondir bytes and the exact
    ``<worktree>/.git`` backlink, then re-prove the boundary relationship and
    the standard linked shape.  No resolved path is accepted merely for lying
    inside the boundary.  Pure: no filesystem reads."""
    if type(resolution) is not dict or set(resolution) != RESOLUTION_KEYS:
        raise CurrentSourceError("custody_proof_invalid")
    custody = response["custody"]
    if (resolution["mode"] != custody["mode"]
            or resolution["boundary"] != custody["boundary"]
            or resolution["worktree"] != response["worktree"]
            or resolution["git_dir"] != response["git_dir"]
            or resolution["common_dir"] != response["common_dir"]):
        raise CurrentSourceError("custody_proof_invalid")
    boundary = validate_absolute_custody(resolution["boundary"])
    wt = validate_absolute_custody(resolution["worktree"])
    gd = validate_absolute_custody(resolution["git_dir"])
    cd = validate_absolute_custody(resolution["common_dir"])
    require_boundary_contains(boundary, wt)
    require_boundary_contains(boundary, gd)
    require_boundary_contains(boundary, cd)
    link = resolution["git_link"]
    if (type(link) is not dict or set(link) != GIT_LINK_KEYS
            or link["kind"] not in ("dir", "file")):
        raise CurrentSourceError("custody_proof_invalid", "git_link")
    if (type(resolution["dir_ids"]) is not dict
            or set(resolution["dir_ids"]) != DIR_ID_KEYS
            or not all(_identity_list(resolution["dir_ids"][key])
                       for key in DIR_ID_KEYS)):
        raise CurrentSourceError("custody_proof_invalid", "dir_ids")
    if link["kind"] == "dir":
        absent = {"bytes_b64": None, "identity": None}
        if (link["bytes_b64"] is not None or link["identity"] is not None
                or resolution["commondir"] != absent
                or resolution["gitdir_backlink"] != absent
                or resolution["git_dir"] != resolution["worktree"] + "/.git"
                or resolution["common_dir"] != resolution["git_dir"]):
            raise CurrentSourceError("custody_proof_invalid", "ordinary")
        return
    if type(link["bytes_b64"]) is not str or not _identity_list(link["identity"]):
        raise CurrentSourceError("custody_proof_invalid", "gitfile")
    try:
        raw = base64.b64decode(link["bytes_b64"], validate=True)
        target = _resolve_pointer(_gitfile_target(raw), wt)
    except (ValueError, CurrentSourceError):
        raise CurrentSourceError("custody_proof_invalid", "gitfile") from None
    if len(raw) > MAX_POINTER_BYTES or target != resolution["git_dir"]:
        raise CurrentSourceError("custody_proof_invalid", "gitfile_target")
    _proof_pointer(resolution["commondir"], gd, resolution["common_dir"], "commondir")
    _proof_pointer(resolution["gitdir_backlink"], gd,
                   resolution["worktree"] + "/.git", "gitdir_backlink")
    if (gd[:len(cd)] != cd or len(gd) != len(cd) + 2
            or gd[len(cd)] != "worktrees"
            or not CUSTODY_COMPONENT.fullmatch(gd[-1])):
        raise CurrentSourceError("custody_proof_invalid", "linked_shape")


def _resolution_binds(response) -> bool:
    """Scope-binding form of the proof check: the declared boundary and mode
    are held by the scope; the returned resolved paths and proof must re-derive
    exactly.  Any inconsistency refuses the binding."""
    try:
        validate_resolution_proof(response["resolution"], response)
    except (CurrentSourceError, KeyError, TypeError, ValueError):
        return False
    return True


def _validate_remote_body(body, request, request_digest) -> None:
    """Closed-world validation of one remote reader body against the exact
    qualified request: echo binding, digest, files, limits, commitments."""
    custody_mode = "custody" in request
    expected = CUSTODY_BODY_KEYS if custody_mode else BODY_KEYS
    if type(body) is not dict or set(body) not in (BODY_KEYS, expected):
        raise CurrentSourceError("remote_body_invalid")
    if body["schema"] != SCHEMA_OBSERVATION:
        raise CurrentSourceError("schema_mismatch")
    if body["status"] != "OBSERVED":
        # A closed refusal body surfaces its own reason; an OBSERVED custody
        # body must carry the full custody shape (checked below).
        raise CurrentSourceError(str(body["reason"]) or "remote_refused")
    if set(body) != expected:
        raise CurrentSourceError("remote_body_invalid")
    for key in ("run_id", "root", "observer", "receiver", "host", "worktree",
                "commit"):
        if body[key] != request[key]:
            raise CurrentSourceError("remote_echo_mismatch", key)
    if custody_mode:
        if body["custody"] != request["custody"]:
            raise CurrentSourceError("remote_echo_mismatch", "custody")
        validate_absolute_custody(body["git_dir"])
        validate_absolute_custody(body["common_dir"])
        validate_resolution_proof(body["resolution"], body)
    else:
        for key in ("git_dir", "common_dir"):
            if body[key] != request[key]:
                raise CurrentSourceError("remote_echo_mismatch", key)
    if body["request_sha256"] != request_digest:
        raise CurrentSourceError("remote_request_digest_mismatch")
    if body["limits"] != request["limits"]:
        raise CurrentSourceError("remote_limits_mismatch")
    commitments = body["commitments"]
    if (type(commitments) is not dict or set(commitments) != {"schema", "no_claims"}
            or commitments["schema"] != SCHEMA_RECEIPT
            or tuple(commitments["no_claims"]) != NO_CLAIMS):
        raise CurrentSourceError("commitments_invalid")
    expected_paths = [e["path"] for e in request["sources"]]
    files = body["files"]
    if type(files) is not list or len(files) != len(expected_paths):
        raise CurrentSourceError("remote_files_invalid")
    remaining = request["limits"]["max_bytes_total"]
    for entry, item in zip(request["sources"], files):
        if type(item) is not dict or set(item) != FILE_KEYS:
            raise CurrentSourceError("file_unknown_field")
        if (item["path"] != entry["path"] or item.get("kind") != "source"
                or item.get("status") != "RETRIEVED"):
            raise CurrentSourceError("remote_file_mismatch", entry["path"])
        if (type(item.get("bytes")) is not int or not 0 <= item["bytes"] <= request['limits']['max_file_bytes']
                or ('size' in entry and item['bytes'] != entry['size'])):
            raise CurrentSourceError("remote_file_bytes", entry["path"])
        if not _is_str(item.get("sha256"), SHA256):
            raise CurrentSourceError("digest_invalid", entry["path"])
        if not _is_str(item.get("object_id"), SHA1):
            raise CurrentSourceError("digest_invalid", entry["path"])
        if (('blob' in entry and item['object_id'] != entry['blob'])
                or item.get("object_store") not in ("loose", "packed")):
            raise CurrentSourceError("remote_object_mismatch", entry["path"])
        membership = item.get("membership")
        if (type(membership) is not list or not 2 <= len(membership) <= MAX_PATH_DEPTH + 1
                or membership[0] != {"component": "<commit>", "kind": "commit",
                                     "object_id": request["commit"]}
                or type(membership[-1]) is not dict
                or membership[-1].get("object_id") != item['object_id']):
            raise CurrentSourceError("remote_membership_invalid", entry["path"])
        for link in membership:
            if (type(link) is not dict or set(link) != MEMBERSHIP_KEYS
                    or not _is_str(link["object_id"], SHA1)
                    or link["kind"] not in ("commit", "tree", "blob")
                    or type(link["component"]) is not str or not link["component"]):
                raise CurrentSourceError("remote_membership_invalid", entry["path"])
        remaining -= item["bytes"]
        if (remaining < 0 or type(item.get("remaining_budget")) is not int
                or item["remaining_budget"] != remaining):
            raise CurrentSourceError("remote_budget_invalid")
    validate_git_payloads(body)


def _skeleton(request, request_digest, state, invocation, status, reason=None):
    request = request if type(request) is dict else {}
    response = {
        "schema": SCHEMA_OBSERVATION, "run_id": request.get("run_id"),
        "root": request.get("root"), "observer": request.get("observer"),
        "receiver": request.get("receiver"), "host": request.get("host"),
        "worktree": request.get("worktree"), "git_dir": request.get("git_dir"),
        "common_dir": request.get("common_dir"), "commit": request.get("commit"),
        "request_sha256": request_digest,
        "status": status, "reason": reason, "files": [], "git_objects": [],
        "limits": dict(DEFAULT_LIMITS),
        "commitments": {"schema": SCHEMA_RECEIPT, "no_claims": list(NO_CLAIMS)},
        "admission": {"state": state,
                      "scope_digest": invocation.scope_digest if invocation else None,
                      "issued_by": invocation.issued_by if invocation else None},
    }
    _seal(response, request_digest, state, invocation)
    return response


def _seal(response, request_digest, state, invocation):
    body = {k: v for k, v in response.items() if k != "receipt"}
    receipt = {"schema": SCHEMA_RECEIPT,
               "response_sha256": digest_of(body),
               "request_sha256": request_digest,
               "admission_state": state,
               "scope_digest": invocation.scope_digest if invocation else None,
               "observer": response["observer"], "receiver": response["receiver"],
               "root": response["root"], "commit": response["commit"],
               "no_claims": list(NO_CLAIMS)}
    response["receipt"] = receipt


def observe_current_source(request, invocation=None, transport=None) -> dict:
    """The single bounded CURRENT observation composition: qualified native
    invocation -> incumbent strict-SSH transport -> generated remote reader ->
    validated receiver-bound response.  No read happens without admission, and
    the response is re-validated delivery-side before its receipt is sealed."""
    try:
        request_digest = validate_request(request)
    except CurrentSourceError as exc:
        return _skeleton(request, None, "NOT_SEEKED", None, "REFUSED", exc.reason)
    scope, state = _admit(request, request_digest, invocation)
    if scope is None:
        return _skeleton(request, request_digest, state, None, "REFUSED",
                         "admission_" + state.lower())
    send = transport if transport is not None else None
    if send is None:
        return _skeleton(request, request_digest, state, scope, "REFUSED",
                         "transport_alias_missing")
    try:
        raw = send(request)
        if type(raw) is not bytes or len(raw) > MAX_RESPONSE:
            raise CurrentSourceError("response_limit")
        body = strict_json(raw)
        try:
            _validate_remote_body(body, request, request_digest)
        except CurrentSourceError:
            raise
        response = dict(body)
        response["admission"] = {"state": state, "scope_digest": scope.scope_digest,
                                 "issued_by": scope.issued_by}
        _seal(response, request_digest, state, scope)
        validate_response(response)
        return response
    except CurrentSourceError as exc:
        return _skeleton(request, request_digest, state, scope, "UNAVAILABLE"
                         if exc.reason == "changed_during_read" else "REFUSED",
                         exc.reason)
    except (OSError, ValueError, TypeError, KeyError, RecursionError,
            subprocess.SubprocessError) as exc:
        return _skeleton(request, request_digest, state, scope, "UNAVAILABLE",
                         "transport_unavailable")


def validate_response(response) -> None:
    """Pure delivery-side validation: closed keys, exact receipt re-hash,
    explicit negative commitments.  No reads, no admission, no mutation.  For
    the custody variant the resolved paths and bounded proof are independently
    re-derived from the returned pointer bytes."""
    custody_mode = "custody" in response
    allowed = CUSTODY_BODY_KEYS if custody_mode else BODY_KEYS
    if type(response) is not dict or set(response) != allowed | {"admission", "receipt"}:
        raise CurrentSourceError("response_unknown_field")
    if response["schema"] != SCHEMA_OBSERVATION:
        raise CurrentSourceError("schema_mismatch")
    for key in ("run_id", "root", "observer", "receiver"):
        if not _is_str(response[key], IDENTITY):
            raise CurrentSourceError("identity_invalid", key)
    if not _is_str(response["host"], HOST) or not _is_str(response["commit"], SHA1):
        raise CurrentSourceError("identity_invalid", "host_or_commit")
    validate_absolute_custody(response["worktree"])
    if custody_mode:
        require_boundary_contains(
            validate_custody_variant(response["custody"]),
            validate_absolute_custody(response["worktree"]))
        validate_absolute_custody(response["git_dir"])
        validate_absolute_custody(response["common_dir"])
        validate_resolution_proof(response["resolution"], response)
    else:
        validate_absolute_custody(response["git_dir"])
        validate_absolute_custody(response["common_dir"])
    if not _is_str(response["request_sha256"], SHA256):
        raise CurrentSourceError("digest_invalid", "request_sha256")
    admission = response["admission"]
    if (type(admission) is not dict or set(admission) != ADMISSION_KEYS
            or admission["state"] not in STATES
            or admission["state"] != "ADMITTED"
            or not _is_str(admission["scope_digest"], SHA256)
            or not _is_str(admission["issued_by"], IDENTITY)):
        raise CurrentSourceError("admission_block_invalid")
    if response["status"] != "OBSERVED":
        raise CurrentSourceError("status_invalid")
    files = response["files"]
    if type(files) is not list or not 0 <= len(files) <= MAX_RESPONSE_FILES:
        raise CurrentSourceError("files_invalid")
    for item in files:
        if type(item) is not dict or set(item) != FILE_KEYS:
            raise CurrentSourceError("file_unknown_field")
        validate_relative_path(item["path"])
        if (item["kind"] != "source" or item["status"] != "RETRIEVED"
                or type(item["bytes"]) is not int or item["bytes"] < 0
                or item["bytes"] > MAX_FILE_BYTES
                or not _is_str(item["sha256"], SHA256)
                or not _is_str(item["object_id"], SHA1)
                or item["object_store"] not in ("loose", "packed")
                or type(item["remaining_budget"]) is not int
                or item["remaining_budget"] < 0):
            raise CurrentSourceError("file_block_invalid")
        membership = item["membership"]
        if (type(membership) is not list or not 2 <= len(membership) <= MAX_PATH_DEPTH + 1):
            raise CurrentSourceError("membership_invalid")
        for link in membership:
            if (type(link) is not dict or set(link) != MEMBERSHIP_KEYS
                    or not _is_str(link["object_id"], SHA1)
                    or link["kind"] not in ("commit", "tree", "blob")):
                raise CurrentSourceError("membership_invalid")
    validate_git_payloads(response)
    limits = response["limits"]
    if type(limits) is not dict or set(limits) != set(LIMIT_KEYS):
        raise CurrentSourceError("limits_invalid")
    for key in LIMIT_KEYS:
        value = limits[key]
        if type(value) is not int or isinstance(value, bool) or not 1 <= value <= LIMIT_CAPS[key]:
            raise CurrentSourceError("limits_invalid", key)
    commitments = response["commitments"]
    if (type(commitments) is not dict or set(commitments) != {"schema", "no_claims"}
            or commitments["schema"] != SCHEMA_RECEIPT
            or tuple(commitments["no_claims"]) != NO_CLAIMS):
        raise CurrentSourceError("commitments_invalid")
    receipt = response["receipt"]
    if type(receipt) is not dict or set(receipt) != RECEIPT_KEYS:
        raise CurrentSourceError("receipt_invalid")
    if (receipt["schema"] != SCHEMA_RECEIPT
            or receipt["admission_state"] != admission["state"]
            or receipt["scope_digest"] != admission["scope_digest"]):
        raise CurrentSourceError("receipt_invalid")
    if (receipt["observer"] != response["observer"]
            or receipt["receiver"] != response["receiver"]
            or receipt["root"] != response["root"]
            or receipt["commit"] != response["commit"]
            or receipt["request_sha256"] != response["request_sha256"]):
        raise CurrentSourceError("receipt_binding_invalid")
    if digest_of({k: v for k, v in response.items() if k != "receipt"}) != receipt["response_sha256"]:
        raise CurrentSourceError("receipt_hash_mismatch")


def _incumbent_reserve(destination_dir: str):
    """The incumbent exclusive destination reservation (fresh 0700 leaf under
    the approved evidence root, held as a verified directory chain)."""
    from artifact_delivery import reserve_destination
    return reserve_destination(destination_dir)


def publish_observation(response, destination_dir, invocation, reserve=None,
                        writer=None, _reserved_chain=None) -> str:
    """Receiver-bound exclusive atomic publication of one observation receipt.

    Requires the same active invocation that admitted the read, a fresh
    publication authorization from its owner, and a re-checked activation
    immediately before the final atomic link.  An interrupted attempt leaves
    no final file; a duplicate destination fails closed."""
    validate_response(response)
    if (type(invocation) is not NativeInvocation
            or response["admission"]["scope_digest"] != invocation.scope_digest
            or not invocation.binds_observation(response)):
        raise NativeRefused("native_scope_caller_mismatch")
    if not invocation.confirm_active():
        raise NativeRefused("native_scope_revoked")
    owner = invocation._owner
    if not isinstance(owner, NativeInvocationOwner) or not owner.authorize_publication(invocation):
        raise NativeRefused("native_publication_refused_by_owner")
    dest_parts = validate_absolute_custody(destination_dir)
    payload = canonical(response)
    if len(payload) > MAX_RESPONSE:
        raise CurrentSourceError("response_limit")
    chain = (_reserved_chain if _reserved_chain is not None else
             (reserve if reserve is not None else _incumbent_reserve)(destination_dir))
    part_fd = None
    published = False
    try:
        chain.verify()
        name = "current-source-%s.json" % response["receipt"]["response_sha256"][:16]
        part = "." + name + ".part"
        part_fd = os.open(part, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                          0o600, dir_fd=chain.fd)
        if writer is None:
            offset = 0
            while offset < len(payload):
                offset += os.write(part_fd, payload[offset:])
        else:
            writer(part_fd)
        os.fsync(part_fd)
        if os.pread(part_fd, len(payload) + 1, 0) != payload:
            raise CurrentSourceError("publication_verification_failed")
        info = os.fstat(part_fd)
        if (info.st_size != len(payload) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise CurrentSourceError("publication_verification_failed")
        os.close(part_fd)
        part_fd = None
        chain.verify()
        # Revocation between the read and this final publication refuses here:
        # the staged bytes are unlinked and no final file is ever created.
        if not invocation.confirm_active() or not owner.invocation_active(invocation):
            raise NativeRefused("native_scope_revoked_before_publication")
        try:
            os.link(part, name, src_dir_fd=chain.fd, dst_dir_fd=chain.fd,
                    follow_symlinks=False)
        except FileExistsError:
            raise CurrentSourceError("duplicate_destination", name)
        published = True
        os.unlink(part, dir_fd=chain.fd)
        os.fsync(chain.fd)
        final = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
        if (not stat.S_ISREG(final.st_mode) or final.st_size != len(payload)
                or stat.S_IMODE(final.st_mode) != 0o600):
            raise CurrentSourceError("publication_verification_failed")
        return "/" + "/".join(dest_parts + [name])
    finally:
        if part_fd is not None:
            try:
                os.close(part_fd)
            except OSError:
                pass
        if not published:
            try:
                os.unlink(part, dir_fd=chain.fd)
            except (OSError, NameError, UnboundLocalError):
                pass
        if _reserved_chain is None:
            chain.close()


def _incumbent_request_loader(path):
    from artifact_delivery import local_file
    return local_file(Path(path), MAX_REQUEST)


def native_current_source_receipt(request_path, destination_dir, owner_factory,
                                  *, transport=None, reserve=None,
                                  load_request=None) -> dict:
    """One inert composition: owned request read -> qualified native
    invocation -> bounded observation -> validated receiver-bound exclusive
    receipt.  ``owner_factory`` is invoked with the validated request digest
    and must return the native owner that admits exactly that invocation."""
    load = load_request if load_request is not None else _incumbent_request_loader
    raw = load(request_path)
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST:
        raise CurrentSourceError("request_limit")
    request = strict_json(raw)
    request_digest = validate_request(request)
    owner = owner_factory(request_digest)
    invocation = NativeInvocation.mint(NativeInvocationView.of(request, request_digest),
                                       owner, os.getuid())
    if transport is not None:
        send = transport
    else:
        alias = owner.transport_alias(NativeInvocationView.of(request, request_digest))
        if not _is_str(alias, re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")):
            raise NativeRefused("native_transport_alias_refused")
        send = _incumbent_transport(alias)
    # Reserve through the incumbent owner before any remote read. A duplicate
    # or interrupted destination cannot silently trigger another export.
    chain = (reserve if reserve is not None else _incumbent_reserve)(destination_dir)
    try:
        response = observe_current_source(request, invocation, send)
        if response["status"] != "OBSERVED":
            return {"schema": SCHEMA_SUMMARY, "state": "REFUSED",
                    "reason": response["reason"],
                    "admission_state": response["admission"]["state"]}
        final = publish_observation(response, destination_dir, invocation,
                                    _reserved_chain=chain)
        return {"schema": SCHEMA_SUMMARY, "state": "PUBLISHED",
                "observation_sha256": response["receipt"]["response_sha256"],
                "receiver": response["receiver"], "destination": final,
                "receipt": response["receipt"]}
    finally:
        chain.close()


GENERATED_IMPORTS = ("import base64\nimport errno\nimport hashlib\nimport json\nimport os\n"
                     "import re\nimport stat\nimport subprocess\nimport sys\n"
                     "import zlib\nimport time\n")

REMOTE_CONSTANTS = ("SCHEMA_REQUEST", "SCHEMA_OBSERVATION", "SCHEMA_RECEIPT",
                    "CUSTODY_MODE",
                    "MAX_REQUEST", "MAX_RESPONSE", "MAX_SOURCES", "MAX_FILE_BYTES",
                    "MAX_BYTES_TOTAL", "MAX_COMMIT_BYTES", "MAX_TREE_BYTES",
                    "MAX_POINTER_BYTES", "MAX_PATH_DEPTH", "IDENTITY", "HOST",
                    "SHA1", "SHA256", "COMPONENT", "CUSTODY_COMPONENT",
                    "GIT_CANDIDATES", "GIT_ARGV_PREFIX", "LIMIT_KEYS",
                    "LIMIT_CAPS", "DEFAULT_LIMITS", "NO_CLAIMS")

REMOTE_SOURCE = ("CurrentSourceError", "canonical", "strict_json", "digest_of",
                 "identity", "_is_str", "validate_absolute_custody",
                 "validate_relative_path", "_validate_source_entries",
                 "validate_custody_variant", "require_boundary_contains",
                 "validate_request", "Reader", "read_pointer", "_pointer_text",
                 "_pointer_lines",
                 "_resolve_pointer", "_gitfile_target", "_classify_git_link",
                 "_chain_terminal_identity", "_chain_identity", "_chain_snapshot",
                 "_pointer_leaf_state", "custody_graph_state", "CustodyGraphGuard",
                 "check_object_store", "pointer_state", "inspect_custody",
                 "_resolved_within", "resolve_custody", "resolution_proof",
                 "custody_identity", "select_git_binary", "git_environment",
                 "_git_limits", "_git_batch", "_verify_object", "_loose_state", "_read_loose",
                 "packed_identity",
                 "_read_packed", "read_object", "parse_commit", "parse_tree",
                 "resolve_tree_path", "observe_remote", "_remote_refusal")

GENERATED_MAIN = '''

def main_stream(in_stream, out_stream) -> int:
    """One bounded remote read for the exact request on ``in_stream``."""
    raw = in_stream.read(MAX_REQUEST + 1)
    if type(raw) is not bytes or len(raw) > MAX_REQUEST:
        return 65
    try:
        request = strict_json(raw)
    except CurrentSourceError:
        return 65
    body = observe_remote(request)
    payload = canonical(body)
    if len(payload) > MAX_RESPONSE:
        payload = canonical(_remote_refusal(request, body["request_sha256"],
                                            "response_limit"))
    out_stream.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_stream(sys.stdin.buffer, sys.stdout.buffer))
'''


def generated_reader_source() -> str:
    """Fixed generated-reader seam: the exact remote program the incumbent
    transport executes for a CURRENT request.  Composed only from this
    module's reviewed source, so the remote half genuinely performs the
    bounded custody checks and object reads."""
    constants = {name: globals()[name] for name in REMOTE_CONSTANTS}
    parts = ['"""Generated CURRENT Git source reader (fixed seam)."""',
             GENERATED_IMPORTS,
             "REMOTE_CONSTANTS = %r" % (constants,),
             "globals().update(REMOTE_CONSTANTS)"]
    parts.extend(getsource(globals()[name]) for name in REMOTE_SOURCE)
    parts.append(GENERATED_MAIN)
    return "\n\n".join(parts) + "\n"


def main(argv) -> int:
    """Offline validation only.  There is deliberately no CLI path that can
    authorize a read or a publication: CLI self-authorization is refused."""
    raw = sys.stdin.buffer.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        return 65
    try:
        document = strict_json(raw)
    except CurrentSourceError:
        return 65
    if type(document) is dict and "sources" in document:
        sys.stderr.write("cli_self_authorize_refused\n")
        return 66
    try:
        validate_response(document)
    except CurrentSourceError as exc:
        sys.stderr.write(exc.reason + "\n")
        return 65
    sys.stdout.buffer.write(canonical({"validated": True,
                                       "response_sha256":
                                       document["receipt"]["response_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
