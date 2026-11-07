"""Capture the fixed Macro plan-adoption compiler inside a bounded read-only bracket.

One request-local capture reads the three fixed plan-adoption sources (owner,
contract, adoption compiler) at one actual qualified Git commit and executes
exactly those captured bytes under scoped ``scripts.*`` module aliases.
Working-file or ambient imports can never substitute their bytes, and
current-DATA code is never executed: code bytes are read only at the qualified
code commit while the current HEAD is used only for identity, so advancing
DATA never changes an existing capture.

BOUNDARY -- what this module is NOT:

* Not a writer, transport, fetch, branch, reset or checkout.  Every Git call
  is the incumbent read-only plumbing run through the installed bounded child
  runner with its sanitized environment; caller Git config redirects are never
  honored, replace refs are ignored and a missing object fails closed instead
  of lazy-fetching from any remote.
* Not an authority.  A capture object, its source binding and the captured
  module objects grant nothing: no publication, no Runtime admission, no
  writer, no claim, and no model-output or prompt execution.  Caller source
  metadata is not authority either -- every identity is rederived from the
  actual repository through bounded read-only Git, never from the caller.
* Not a seal issuer.  The outer installed collector seal before and after the
  parent's actual adapter call is parent-owned and is neither performed nor
  recorded here.
* Not a registry, lifecycle or cache: nothing is stored between calls, no
  capture is retained anywhere, and two captures share no state.
* Not a replacement for, or an edit of, the incumbent six-source planning
  capture: this leaf reuses the incumbent private bounded-Git, tree-entry and
  alias-scope plumbing plus its closed refusal vocabulary unchanged, and it
  adds no source to the incumbent's fixed planning set and no new lock.

Law:

* The fixed source set is exactly three paths (owner, contract, adoption
  compiler).  Each entry must be a full ``100644`` regular blob at the
  qualified code commit; the code commit must be an ancestor of the exact
  expected HEAD; every content read is byte-bounded and deadline-bounded under
  one cumulative capture cap.
* Captured bytes execute only under scoped module aliases serialized on the
  incumbent shared alias lock; the exact prior ``sys.modules``/``sys.path``
  state is restored on every edge -- success, captured faults and
  ``SystemExit`` alike.  The captured contract is bound into the captured
  owner exactly as the incumbent canonical-basis capture does, because the
  owner's own lazy contract import would otherwise resolve outside the
  captured alias scope after restoration.
* :meth:`CapturedProjectPlanAdoptionCompilers.check` requalifies the exact
  HEAD and code identities; :meth:`._scope` requalifies before and after the
  caller's actual compiler call while holding the shared alias bracket.  Any
  drift raises the closed source-changed refusal and never falls back or
  recaptures.
* The captured compiler's own refusals propagate unchanged -- they are the
  pinned compiler's own closed vocabulary; this leaf adds no translation and
  never fabricates a compiler result.
"""
from __future__ import annotations

import hashlib
import re
import time
import types
from contextlib import contextmanager
from pathlib import Path

from control_plane.ceo_boot_packet import bounded_subprocess_runner
from control_plane.project_planning_compiler_source import (
    COMMIT_RE,
    REPOSITORY,
    ProjectPlanningCompilerSourceChanged,
    ProjectPlanningCompilerUnavailable,
    _MAX_CODE_BYTES,
    _MAX_IDENTITY_BYTES,
    _MAX_TIMEOUT_SECONDS,
    _MAX_WITNESS_BYTES,
    _SCOPE_LOCK,
    _acquire_scope_lock,
    _bounded_git,
    _install_scope,
    _restore_scope,
    _tree_entry,
)

__all__ = [
    "ADOPTION_SOURCE_ROLES",
    "ADOPT_COMPILER_SOURCE_PATH",
    "CAPTURE_SCHEMA",
    "REPOSITORY",
    "CapturedProjectPlanAdoptionCompilers",
    "capture_project_plan_adoption_compilers",
]

CAPTURE_SCHEMA = "mastermind.project_plan_adoption_compiler_capture.v1"

ADOPT_COMPILER_SOURCE_PATH = "scripts/agentos_plan_adoption.py"
CONTRACT_SOURCE_PATH = "scripts/agentos_project_plan_contract.py"
OWNER_SOURCE_PATH = "scripts/agentos.py"

# The fixed source set: capture keys to exact repository paths.  The key names
# are exactly the accepted adoption source roles.
_FIXED_ROLE_KEYS = {
    "owner": OWNER_SOURCE_PATH,
    "contract": CONTRACT_SOURCE_PATH,
    "compiler": ADOPT_COMPILER_SOURCE_PATH,
}
_MODULE_FOR_KEY = {
    "owner": "scripts.agentos",
    "contract": "scripts.agentos_project_plan_contract",
    "compiler": "scripts.agentos_plan_adoption",
}
_MODULE_NAMES = ("scripts",) + tuple(_MODULE_FOR_KEY.values())
ADOPTION_SOURCE_ROLES = tuple(_FIXED_ROLE_KEYS)

_MAX_TOTAL_BYTES = 4194304

_SHA256_RE = re.compile(r"[0-9a-f]{64}")

_UNAVAILABLE = "project_plan_adoption_compiler_unavailable"
_SOURCE_CHANGED = "project_plan_adoption_compiler_source_changed"


class CapturedProjectPlanAdoptionCompilers:
    """One request-local capture of the fixed Macro plan-adoption compiler.

    ``compiler`` and ``owner`` are the actual captured module objects and
    ``source_binding`` records the exact accepted compiler/contract/owner
    source roles.  None of these are authority: module objects prove nothing
    about future reads, the binding is an obligation about recorded bytes, and
    nothing here grants publication, admission, a writer or a claim.  The
    outer installed seal around the parent's actual adapter call is
    parent-owned; this object neither performs nor records it.
    """

    __slots__ = (
        "compiler",
        "owner",
        "source_binding",
        "_expected_macro_sha",
        "_code_commit",
        "_macro_root",
        "_runner",
        "_timeout",
        "_objects",
        "_identity",
    )

    def __init__(
        self,
        *,
        compiler,
        owner,
        source_binding,
        expected_macro_sha,
        code_commit,
        macro_root,
        runner,
        timeout,
        objects,
        identity,
    ):
        if (
            type(compiler) is not types.ModuleType
            or type(owner) is not types.ModuleType
            or not _binding_ok(source_binding, code_commit)
            or type(objects) is not dict
            or set(objects) != set(_MODULE_NAMES)
            or any(type(module) is not types.ModuleType for module in objects.values())
            or type(identity) is not dict
            or set(identity) != set(_FIXED_ROLE_KEYS)
            or any(
                type(oid) is not str or COMMIT_RE.fullmatch(oid) is None
                for oid in identity.values()
            )
            or not isinstance(macro_root, Path)
            or not callable(runner)
            or type(expected_macro_sha) is not str
            or COMMIT_RE.fullmatch(expected_macro_sha) is None
            or type(code_commit) is not str
            or COMMIT_RE.fullmatch(code_commit) is None
            or type(timeout) not in (int, float)
            or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
        ):
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        self.compiler = compiler
        self.owner = owner
        self.source_binding = source_binding
        self._expected_macro_sha = expected_macro_sha
        self._code_commit = code_commit
        self._macro_root = macro_root
        self._runner = runner
        self._timeout = timeout
        self._objects = objects
        self._identity = identity

    # -------------------------------------------------------- requalification

    def check(self):
        """Requalify the exact HEAD and code identities; drift refuses.

        Bounded read-only Git in the configured repository only: the current
        HEAD is used for identity, the code commit must still be its
        ancestor, and each fixed path must still be the exact recorded full
        ``100644`` blob at the qualified code commit.
        """
        deadline = time.monotonic() + self._timeout
        observed = _bounded_git(
            self._runner, self._macro_root, ["rev-parse", "HEAD"],
            cap=_MAX_IDENTITY_BYTES, deadline=deadline,
        ).strip()
        if observed != self._expected_macro_sha:
            raise ProjectPlanningCompilerSourceChanged(_SOURCE_CHANGED)
        _bounded_git(
            self._runner, self._macro_root,
            ["merge-base", "--is-ancestor", self._code_commit, self._expected_macro_sha],
            cap=_MAX_IDENTITY_BYTES, deadline=deadline,
        )
        for key, path in _FIXED_ROLE_KEYS.items():
            listed = _bounded_git(
                self._runner, self._macro_root,
                ["ls-tree", "-z", self._code_commit, "--", path],
                cap=_MAX_WITNESS_BYTES, deadline=deadline,
            )
            if _tree_entry(listed, path) != self._identity[key]:
                raise ProjectPlanningCompilerSourceChanged(_SOURCE_CHANGED)

    @contextmanager
    def _scope(self, *, deadline=None):
        """Requalified shared-alias bracket around one actual compiler call.

        Requalifies the exact source identity before the caller's actual call
        and again after it, while the captured ``scripts.*`` aliases are
        installed on the incumbent shared alias lock for the whole bracket --
        so a concurrent capture or compiler call can never interleave
        ``sys.modules``/``sys.path`` mutations or observe half-installed
        aliases.  The lock wait is bounded by the same per-call ``timeout``
        budget; a contended wait that outlives it refuses closed without
        installing anything.  The exact prior state is restored on every
        edge, including a failing body, before the lock is released.
        """
        if deadline is None:
            deadline = time.monotonic() + self._timeout
        self.check()
        _acquire_scope_lock(deadline)
        try:
            previous, old_path = _install_scope(self._objects)
            try:
                yield
            finally:
                _restore_scope(previous, old_path)
        finally:
            _SCOPE_LOCK.release()
        self.check()


def _binding_ok(source_binding, code_commit):
    """The exact three-role binding: fixed paths, this code commit, sha256."""
    if type(source_binding) is not dict or set(source_binding) != set(_FIXED_ROLE_KEYS):
        return False
    for role, ref in source_binding.items():
        if (
            type(ref) is not dict
            or set(ref) != {"repository", "path", "commit", "content_sha256"}
            or ref["repository"] != REPOSITORY
            or ref["path"] != _FIXED_ROLE_KEYS[role]
            or ref["commit"] != code_commit
            or type(ref["content_sha256"]) is not str
            or _SHA256_RE.fullmatch(ref["content_sha256"]) is None
        ):
            return False
    return True


def capture_project_plan_adoption_compilers(
    *, macro_root, expected_macro_sha, code_commit, runner=None, timeout=10.0
):
    """Capture the three fixed plan-adoption sources at one qualified commit.

    ``macro_root``, ``expected_macro_sha`` and ``code_commit`` are private
    installed coordinates; they select what is read, never what is believed.
    The qualified ``code_commit`` must be an ancestor of the exact
    ``expected_macro_sha`` HEAD.  Returns one request-local
    :class:`CapturedProjectPlanAdoptionCompilers` after a strict post-capture
    requalification; the caller must bracket the actual adapter call with the
    parent-owned outer installed seal, which this capture neither performs nor
    records, and run the actual compiler call under :meth:`._scope`.

    The captured-exec alias window holds the incumbent shared alias lock for
    its whole bracket, bounded by the remaining capture deadline: a
    concurrent capture or compiler call serializes behind it, and a wait that
    outlives the deadline refuses closed without installing anything.
    """
    try:
        root = Path(macro_root)
    except (TypeError, ValueError):
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE) from None
    if (
        not root.is_absolute()
        or any(
            type(value) is not str or COMMIT_RE.fullmatch(value) is None
            for value in (expected_macro_sha, code_commit)
        )
        or type(timeout) not in (int, float)
        or not 0 < timeout <= _MAX_TIMEOUT_SECONDS
        or (runner is not None and not callable(runner))
    ):
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    run = bounded_subprocess_runner if runner is None else runner
    deadline = time.monotonic() + timeout
    total = 0

    def git(args, *, cap):
        nonlocal total
        stdout = _bounded_git(run, root, args, cap=cap, deadline=deadline)
        total += len(stdout)
        if total > _MAX_TOTAL_BYTES:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        return stdout

    if git(["rev-parse", "HEAD"], cap=_MAX_IDENTITY_BYTES).strip() != expected_macro_sha:
        raise ProjectPlanningCompilerSourceChanged(_SOURCE_CHANGED)
    git(["merge-base", "--is-ancestor", code_commit, expected_macro_sha], cap=_MAX_IDENTITY_BYTES)

    texts, identity = {}, {}
    for key, path in _FIXED_ROLE_KEYS.items():
        listed = git(["ls-tree", "-z", code_commit, "--", path], cap=_MAX_WITNESS_BYTES)
        identity[key] = _tree_entry(listed, path)
        texts[key] = git(["show", code_commit + ":" + path], cap=_MAX_CODE_BYTES)

    source_binding = {
        role: {
            "repository": REPOSITORY,
            "path": _FIXED_ROLE_KEYS[role],
            "commit": code_commit,
            "content_sha256": hashlib.sha256(texts[role].encode("utf-8")).hexdigest(),
        }
        for role in _FIXED_ROLE_KEYS
    }

    package = types.ModuleType("scripts")
    package.__path__ = []
    modules = {"scripts": package}
    for key, name in _MODULE_FOR_KEY.items():
        module = types.ModuleType(name)
        module.__file__ = str(root / _FIXED_ROLE_KEYS[key])
        modules[name] = module

    _acquire_scope_lock(deadline)
    try:
        previous, old_path = _install_scope(modules)
        try:
            for key in ("owner", "contract", "compiler"):
                module = modules[_MODULE_FOR_KEY[key]]
                exec(compile(texts[key], module.__file__, "exec"), module.__dict__)
            owner = modules["scripts.agentos"]
            contract = modules["scripts.agentos_project_plan_contract"]
            # Bind the captured contract into the captured owner exactly as
            # the incumbent canonical-basis capture does: the owner's own
            # lazy contract import would otherwise resolve outside the
            # captured alias scope after restoration.
            owner._project_plan_contract = lambda: contract
        except ProjectPlanningCompilerUnavailable:
            raise
        except SystemExit:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE) from None
        except Exception:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE) from None
        finally:
            _restore_scope(previous, old_path)
    finally:
        _SCOPE_LOCK.release()

    captured = CapturedProjectPlanAdoptionCompilers(
        compiler=modules["scripts.agentos_plan_adoption"],
        owner=modules["scripts.agentos"],
        source_binding=source_binding,
        expected_macro_sha=expected_macro_sha,
        code_commit=code_commit,
        macro_root=root,
        runner=run,
        timeout=timeout,
        objects=modules,
        identity=identity,
    )
    # Strict post-capture requalification before anything is exposed.
    captured.check()
    return captured
