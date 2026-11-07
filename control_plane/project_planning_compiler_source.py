"""Capture the fixed Macro planning compilers inside a bounded read-only bracket.

One request-local capture reads the six fixed planning sources at one actual
qualified Git commit and executes exactly those captured bytes under scoped
``scripts.*`` module aliases.  Working-file or ambient imports can never
substitute their bytes, and current-DATA code is never executed: code bytes are
read only at the qualified code commit while the current HEAD is used only for
identity, so advancing DATA never changes an existing capture.

BOUNDARY -- what this module is NOT:

* Not a writer, transport, fetch, branch, reset or checkout.  Every Git call is
  read-only plumbing (``rev-parse``, ``merge-base --is-ancestor``, ``ls-tree``,
  ``show``) run through the installed bounded child runner with a sanitized
  environment (``GIT_CONFIG_GLOBAL=/dev/null``, ``GIT_CONFIG_NOSYSTEM=1``,
  ``GIT_NO_LAZY_FETCH=1``, ``GIT_NO_REPLACE_OBJECTS=1``,
  ``GIT_TERMINAL_PROMPT=0``): caller Git config redirects are never honored,
  replace refs are ignored, and a missing object fails closed instead of
  lazy-fetching from any remote.
* Not an authority.  A capture object, its source bindings and the captured
  module objects grant nothing: no publication, no Runtime admission, no
  writer, no claim, and no model-output or prompt execution.  Caller source
  metadata is not authority either -- every identity is rederived from the
  actual repository through bounded read-only Git, never from the caller.
* Not a seal issuer.  The actual outer collector seal qualification before and
  after the actual engine call is parent-owned and is neither performed nor
  recorded here; :meth:`CapturedProjectPlanningCompilers.material` records only
  that standing obligation.
* Not a registry, lifecycle or cache.  Nothing is stored between calls, no
  capture is retained anywhere, and two captures share no state.
* Not a global import coordinator.  ``sys.modules``/``sys.path`` are process
  globals, so the two alias mutation windows below are serialized by one
  private module re-entrant lock.  That lock covers exactly this module's own
  capture-exec and compiler-call brackets: it is not a Python import lock, and
  unrelated code that mutates ``sys.modules``/``sys.path`` on another thread
  outside those brackets is not coordinated with it.  Waiting on the lock is
  bounded by the already-running capture deadline (capture path) or the same
  per-call ``timeout`` budget the wrapper requalifications already spend
  (compile path); it never blocks unboundedly and never mints a renewed clock.

Law:

* The fixed source set is exactly six paths (owner, contract, creation
  compiler, declaration, proposal compiler, programmes).  Each entry must be a
  full ``100644`` regular blob at the qualified code commit; the code commit
  must be an ancestor of the exact expected HEAD; every content read is
  byte-bounded and deadline-bounded with a total capture cap.
* Captured bytes execute only under scoped module aliases; the exact prior
  ``sys.modules``/``sys.path`` state is restored on every edge, including
  refusals and captured-code failures.  The captured contract is bound into
  the captured owner exactly as the existing canonical-basis capture does,
  because the pin's own lazy contract import would otherwise resolve outside
  the captured alias scope after restoration.
* ``check()`` and every compiler wrapper requalify the exact HEAD and code
  identities through the same bounded read-only Git before and after the
  wrapped call; any drift raises the source-changed refusal and never falls
  back or recaptures.
* Captured compiler refusals propagate unchanged -- they are the pinned
  compiler's own closed vocabulary; this leaf adds no translation and never
  fabricates a compiler result.  Closed DRAFT_ONLY envelope checks belong to
  the parent adapters.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
import types
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from control_plane.ceo_boot_packet import bounded_subprocess_runner

__all__ = [
    "CAPTURE_SCHEMA",
    "CREATION_SOURCE_ROLES",
    "PROPOSAL_SOURCE_ROLES",
    "REPOSITORY",
    "CapturedProjectPlanningCompilers",
    "ProjectPlanningCompilerSourceChanged",
    "ProjectPlanningCompilerUnavailable",
    "capture_project_planning_compilers",
]

CAPTURE_SCHEMA = "mastermind.project_planning_compiler_capture.v1"
REPOSITORY = "mastermindx-market-intelligence/macro"

OWNER_SOURCE_PATH = "scripts/agentos.py"
CONTRACT_SOURCE_PATH = "scripts/agentos_project_plan_contract.py"
CREATION_COMPILER_SOURCE_PATH = "scripts/agentos_project_proposal.py"
DECLARATION_SOURCE_PATH = "scripts/agentos_plan_proposal.py"
PROPOSAL_COMPILER_SOURCE_PATH = "scripts/agentos_plan_proposal_recipe.py"
PROGRAMMES_SOURCE_PATH = "config/mastermind_programs.yml"

CREATION_SOURCE_ROLES = ("compiler", "owner", "programs")
PROPOSAL_SOURCE_ROLES = ("compiler", "declaration", "owner", "contract")

# The fixed source set: capture keys to exact repository paths.
_FIXED_ROLE_KEYS = {
    "owner": OWNER_SOURCE_PATH,
    "contract": CONTRACT_SOURCE_PATH,
    "creation_compiler": CREATION_COMPILER_SOURCE_PATH,
    "declaration": DECLARATION_SOURCE_PATH,
    "proposal_compiler": PROPOSAL_COMPILER_SOURCE_PATH,
    "programs": PROGRAMMES_SOURCE_PATH,
}
_CREATION_ROLE_KEYS = {"compiler": "creation_compiler", "owner": "owner", "programs": "programs"}
_PROPOSAL_ROLE_KEYS = {
    "compiler": "proposal_compiler",
    "declaration": "declaration",
    "owner": "owner",
    "contract": "contract",
}
_MODULE_FOR_KEY = {
    "owner": "scripts.agentos",
    "contract": "scripts.agentos_project_plan_contract",
    "creation_compiler": "scripts.agentos_project_proposal",
    "declaration": "scripts.agentos_plan_proposal",
    "proposal_compiler": "scripts.agentos_plan_proposal_recipe",
}
_MODULE_NAMES = ("scripts",) + tuple(_MODULE_FOR_KEY.values())

# The sanitized child environment of the installed bounded runner: caller Git
# config redirects, replace objects and lazy promisor fetches are all refused,
# so a missing object fails closed instead of dialing out.
_GIT_ENV = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "LC_ALL": "C",
}
_GIT_ARGV_PREFIX = ("git", "--no-optional-locks", "--no-replace-objects", "-C")

_MAX_TIMEOUT_SECONDS = 15.0
_MAX_TOTAL_BYTES = 16777216
_MAX_CODE_BYTES = 1048576
_MAX_PROGRAMME_BYTES = 262144
_MAX_WITNESS_BYTES = 2048
_MAX_IDENTITY_BYTES = 1024
_MAX_MATERIAL_BYTES = 65536

COMMIT_RE = re.compile(r"[0-9a-f]{40}")

_UNAVAILABLE = "project_planning_compiler_unavailable"
_SOURCE_CHANGED = "project_planning_compiler_source_changed"

# The one private serialization point for the two process-global alias windows
# below.  Re-entrant so a nested same-thread capture or compiler call inside an
# open window stays legal (the inner bracket snapshots and restores the outer
# window's aliases exactly); held for the whole window so a waiter can never
# observe, install over, or restore across another window's half-installed
# state.
_SCOPE_LOCK = threading.RLock()


def _acquire_scope_lock(deadline):
    """Take the alias-window lock bounded by the caller's already-running clock.

    Same-thread re-entry succeeds immediately; a contended lock is waited on
    only until ``deadline`` and a timed-out wait refuses closed.  No new
    timeout budget is minted and the wait is never unbounded.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    if not _SCOPE_LOCK.acquire(blocking=False):
        if not _SCOPE_LOCK.acquire(timeout=remaining):
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    if time.monotonic() >= deadline:
        _SCOPE_LOCK.release()
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)


class ProjectPlanningCompilerUnavailable(ValueError):
    """One fixed planning source or its bounded capture is not available.

    The closed refusal message is one value-free code: no path, digest,
    revision, catalogue or content value is ever carried.
    """


class ProjectPlanningCompilerSourceChanged(ProjectPlanningCompilerUnavailable):
    """The exact HEAD or captured code identity drifted from the capture.

    Never healed, recaptured or rebased here: the caller re-captures only
    through its own qualified source operation.
    """


class _CapturedProgrammes:
    """Read-only text proxy over exactly the captured programme bytes."""

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    def exists(self):
        return True

    def read_text(self, *, encoding):
        if encoding != "utf-8":
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        return self._raw


def _install_scope(objects):
    """Install the captured ``scripts.*`` aliases and return the prior state."""
    package = objects["scripts"]
    previous = {name: sys.modules.get(name) for name in objects}
    old_path = list(sys.path)
    sys.modules.update(objects)
    for name, module in objects.items():
        if name != "scripts":
            setattr(package, name.split(".", 1)[1], module)
    return previous, old_path


def _restore_scope(previous, old_path):
    """Restore the exact prior ``sys.modules``/``sys.path`` state."""
    sys.path[:] = old_path
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def _bounded_git(runner, root, args, *, cap, deadline):
    """One bounded read-only Git call through the installed child runner.

    The argv is frozen (no caller config redirects), the child environment is
    the sanitized fixed mapping, and any timeout, output-limit or decode
    failure fails closed.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    argv = [*_GIT_ARGV_PREFIX, str(root), *args]
    result = runner(argv, cwd=root, timeout=remaining, max_bytes=cap, env=dict(_GIT_ENV))
    if (
        type(result) is not dict
        or result.get("code") != 0
        or type(result.get("stdout")) is not str
        or any(result.get(key) is True for key in ("timed_out", "limit_exceeded", "invalid_utf8"))
    ):
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    return result["stdout"]


def _tree_entry(listed, path):
    """The exact one-line full ``100644`` blob identity for ``path``."""
    found = re.fullmatch(r"100644 blob ([0-9a-f]{40})\t" + re.escape(path) + "\x00", listed)
    if found is None:
        raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
    return found.group(1)


class CapturedProjectPlanningCompilers:
    """One request-local capture of the fixed Macro planning compilers.

    ``creation_compiler``, ``proposal_compiler``, ``declaration`` and ``owner``
    are the actual captured module objects; ``programs`` is the captured
    programme catalogue; ``creation_source_binding`` and
    ``proposal_source_binding`` record the exact accepted source roles.  None
    of these are authority: module objects prove nothing about future reads,
    source bindings are obligations about recorded bytes, and nothing here
    grants publication, admission, a writer or a claim.

    There is no registry, no lifecycle and no cache.  Each ``check()`` and
    each wrapped compiler call requalifies the exact HEAD and code identities
    through bounded read-only Git in the configured repository, never
    remotely.  The outer collector seal around the actual engine call is
    parent-owned; this object neither performs nor records such a
    qualification.
    """

    __slots__ = (
        "creation_compiler",
        "proposal_compiler",
        "declaration",
        "owner",
        "programs",
        "creation_source_binding",
        "proposal_source_binding",
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
        creation_compiler,
        proposal_compiler,
        declaration,
        owner,
        programs,
        creation_source_binding,
        proposal_source_binding,
        expected_macro_sha,
        code_commit,
        macro_root,
        runner,
        timeout,
        objects,
        identity,
    ):
        if (
            any(
                type(module) is not types.ModuleType
                for module in (creation_compiler, proposal_compiler, declaration, owner)
            )
            or type(programs) is not frozenset
            or type(creation_source_binding) is not dict
            or type(proposal_source_binding) is not dict
            or type(objects) is not dict
            or type(identity) is not dict
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
        self.creation_compiler = creation_compiler
        self.proposal_compiler = proposal_compiler
        self.declaration = declaration
        self.owner = owner
        self.programs = programs
        self.creation_source_binding = creation_source_binding
        self.proposal_source_binding = proposal_source_binding
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
        HEAD is used for identity, and each fixed path must still be the exact
        recorded full ``100644`` blob at the qualified code commit.
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
                self._runner, self._macro_root, ["ls-tree", "-z", self._code_commit, "--", path],
                cap=_MAX_WITNESS_BYTES, deadline=deadline,
            )
            if _tree_entry(listed, path) != self._identity[key]:
                raise ProjectPlanningCompilerSourceChanged(_SOURCE_CHANGED)

    @contextmanager
    def _scope(self, *, deadline=None):
        """The scoped captured-alias bracket around one actual compiler call.

        The whole bracket -- install, the actual call, restore -- holds the
        private module alias lock, so two concurrent compiler calls (or a
        concurrent capture's exec window) can never interleave their
        ``sys.modules``/``sys.path`` mutations or observe each other's
        aliases.  The wait is bounded by the same per-call ``timeout`` budget
        the wrapper requalifications already spend; a contended wait that
        outlives it refuses closed without installing anything.  Same-thread
        nesting stays legal through the re-entrant lock, and any captured
        failure still restores the exact prior state before the lock is
        released.
        """
        if deadline is None:deadline = time.monotonic() + self._timeout
        _acquire_scope_lock(deadline)
        try:
            previous, old_path = _install_scope(self._objects)
            try:
                yield
            finally:
                _restore_scope(previous, old_path)
        finally:
            _SCOPE_LOCK.release()

    # ------------------------------------------------------- compiler calls

    def compile_creation(self, request):
        """Compile one creation request through the captured creation compiler.

        The exact source identity is requalified before and after the call,
        the call runs under the scoped captured aliases, and the input and the
        returned draft are detached deep copies.  The captured compiler's own
        refusals propagate unchanged.
        """
        deadline=time.monotonic()+self._timeout
        self.check()
        if type(request) is not dict:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        payload = deepcopy(request)
        with self._scope(deadline=deadline):
            draft = self.creation_compiler.compile_proposal(payload, programs=self.programs)
        if type(draft) is not dict:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        self.check()
        return deepcopy(draft)

    def compile_proposal_recipe(self, request, snapshot, planning_result, actor):
        """Compile one proposal recipe through the captured proposal compiler.

        The captured owner and captured declaration modules are bound as the
        compiler's ``owner`` / ``declaration_owner``; the exact source identity
        is requalified before and after the call; inputs and the returned
        recipe are detached deep copies.
        """
        deadline=time.monotonic()+self._timeout
        self.check()
        payload = (
            deepcopy(request),
            deepcopy(snapshot),
            deepcopy(planning_result),
            deepcopy(actor),
        )
        with self._scope(deadline=deadline):
            recipe = self.proposal_compiler.compile_proposal_recipe(
                *payload, owner=self.owner, declaration_owner=self.declaration
            )
        if type(recipe) is not dict:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        self.check()
        return deepcopy(recipe)

    # ------------------------------------------------------------- material

    def material(self):
        """A display-only capture record; not an authority and not a seal."""
        record = {
            "schema": CAPTURE_SCHEMA,
            "repository": REPOSITORY,
            "head": self._expected_macro_sha,
            "code_commit": self._code_commit,
            "programs": sorted(self.programs),
            "creation_source_binding": deepcopy(self.creation_source_binding),
            "proposal_source_binding": deepcopy(self.proposal_source_binding),
            "outer_collector_seal": "PARENT_OWNED_REQUIRED_NOT_RECORDED_HERE",
        }
        raw = json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        if len(raw) + 1 > _MAX_MATERIAL_BYTES:
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        return record


def capture_project_planning_compilers(
    *, macro_root, expected_macro_sha, code_commit, runner=None, timeout=10.0
):
    """Capture the six fixed planning sources at one qualified code commit.

    ``macro_root``, ``expected_macro_sha`` and ``code_commit`` are private
    installed coordinates; they select what is read, never what is believed.
    The qualified ``code_commit`` must be an ancestor of the exact
    ``expected_macro_sha`` HEAD.  Returns one request-local
    :class:`CapturedProjectPlanningCompilers`; the caller must bracket the
    actual engine call with the parent-owned outer collector seals, which this
    capture neither performs nor records.

    The captured-exec alias window holds the private module alias lock for its
    whole bracket, bounded by the remaining capture deadline: a concurrent
    capture or compiler call serializes behind it instead of installing its
    own aliases over this one, and a wait that outlives the remaining
    deadline refuses closed without installing anything.
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
        cap = _MAX_PROGRAMME_BYTES if key == "programs" else _MAX_CODE_BYTES
        texts[key] = git(["show", code_commit + ":" + path], cap=cap)

    def source_ref(key):
        path = _FIXED_ROLE_KEYS[key]
        return {
            "repository": REPOSITORY,
            "commit": code_commit,
            "path": path,
            "content_sha256": hashlib.sha256(texts[key].encode("utf-8")).hexdigest(),
        }

    creation_source_binding = {role: source_ref(key) for role, key in _CREATION_ROLE_KEYS.items()}
    proposal_source_binding = {role: source_ref(key) for role, key in _PROPOSAL_ROLE_KEYS.items()}

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
            for key in ("owner", "contract", "creation_compiler", "declaration", "proposal_compiler"):
                module = modules[_MODULE_FOR_KEY[key]]
                exec(compile(texts[key], module.__file__, "exec"), module.__dict__)
            owner = modules["scripts.agentos"]
            contract = modules["scripts.agentos_project_plan_contract"]
            # Bind the captured contract into the captured owner exactly as the
            # existing canonical-basis capture does: the pin's own lazy contract
            # import would otherwise resolve outside the captured alias scope
            # after restoration.
            owner._project_plan_contract = lambda: contract
            owner._PROGRAMS = _CapturedProgrammes(texts["programs"])
            programs = owner._load_programs()
            if (
                type(programs) not in (set, frozenset)
                or not programs
                or any(type(name) is not str or not name for name in programs)
            ):
                raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE)
        except ProjectPlanningCompilerUnavailable:
            raise
        except (
            SyntaxError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ImportError,
            OSError,
            UnicodeError,
            RecursionError,
            OverflowError,
        ):
            raise ProjectPlanningCompilerUnavailable(_UNAVAILABLE) from None
        finally:
            _restore_scope(previous, old_path)
    finally:
        _SCOPE_LOCK.release()

    captured = CapturedProjectPlanningCompilers(
        creation_compiler=modules["scripts.agentos_project_proposal"],
        proposal_compiler=modules["scripts.agentos_plan_proposal_recipe"],
        declaration=modules["scripts.agentos_plan_proposal"],
        owner=modules["scripts.agentos"],
        programs=frozenset(programs),
        creation_source_binding=creation_source_binding,
        proposal_source_binding=proposal_source_binding,
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
