"""project_creation_operation.py — bounded C1 typed CREATE recipe adapter.

A pure, in-memory adapter that turns one closed, explicitly profiled project
selection into the actual canonical Macro proposal compiler's DRAFT_ONLY
envelope, and restores that same operation from its own private payload.

BOUNDARY — what this module is NOT:

* Not a store writer, Git client, transport, job runner, controller or
  publisher.  It reads nothing, writes nothing, talks to nothing and derives
  nothing from the clock.  Carrying a compiled draft into a store, minting or
  advancing a commit, and publishing anything are separate steps this module
  can neither perform nor prove.
* Not an authority.  A prepared operation, a recipe envelope and a safe
  metadata dict grant nothing: no source publication, no Runtime admission,
  no writer, no claim.  Events, the private-payload wrapper and the immutable
  beforeReview/claim/auth/publisher controls belong to the parent integration
  layer; this adapter is integration-layer code, not the core.
* Not a source authenticator.  ``source_binding`` records obligations about
  the captured Macro sources (exact repository, exact paths, one shared
  commit, per-file content digests).  Those refs do not authenticate the
  injected compiler module and never prove that a module's bytes match them;
  actual metadata/source qualification belongs to the installed factory.
* Not a profile owner.  There is no default profile and no implicit
  selection: the request must name one captured profile at its exact authored
  revision, and neither this adapter nor a selected profile grants
  publication or Runtime execution.
* Not an importer of Macro dynamic code.  The actual compiler module is
  injected; this adapter never imports it, or anything else, by path.

DELEGATION.  Composition stays with the incumbent
``build_profiled_proposal_request`` and compilation stays with the injected
actual ``compile_proposal``.  This adapter never re-declares their law and
never recaptures or rebases a restored operation.  It adds only the typed
operation boundary:

* a closed refusal vocabulary (:class:`ProjectCreationOperationError`); no
  refusal message ever carries request, goal, profile or payload content;
* closed checks over the actual compiler's returned envelope (schema, exact
  keys, DRAFT_ONLY state, request id, expected commit, work ref/path
  agreement, content digest);
* the trusted recipe fingerprint, which is the compiler's own
  ``request_sha256`` — never a hash of the public profile request;
* the exact six-key private payload and the exact seven-key safe metadata
  (never the goal, never the body);
* :meth:`restore`, which revalidates actor scope, source binding, captured
  programmes/profiles and the canonical input, then recompiles the original
  input through the actual compiler and refuses on any difference.

Detachment: every constructor input is copied, every returned payload and
recipe envelope is rebuilt from prepared state, and no mutable structure is
shared with a caller.
"""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from types import ModuleType

from common.executive_workspace_contract import canonical
from integrations.mastermind_workspace_app.source_operation_principal import source_principal_scope
from integrations.mastermind_workspace_app.project_profiles import (
    SELECTION_SCHEMA,
    build_profiled_proposal_request,
    validate_profiles,
)

__all__ = [
    "MACRO_REPOSITORY",
    "PREPARED_ACTION",
    "PRIVATE_PAYLOAD_SCHEMA",
    "PreparedProjectCreation",
    "ProjectCreationOperationError",
    "ProjectCreationRecipeAdapter",
    "ProjectCreationSourceRef",
]

MACRO_REPOSITORY = "mastermindx-market-intelligence/macro"
COMPILER_SOURCE_PATH = "scripts/agentos_project_proposal.py"
OWNER_SOURCE_PATH = "scripts/agentos.py"
PROGRAMMES_SOURCE_PATH = "config/mastermind_programs.yml"

PRIVATE_PAYLOAD_SCHEMA = "mastermind.project_source_original_input.v1"
PREPARED_ACTION = "publish_project_proposal"

REQUEST_ID_RE = re.compile(r"mmos-project-create-[0-9a-f]{40}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
CONTENT_SHA_RE = re.compile(r"[0-9a-f]{64}")

MAX_GOAL_BYTES = 4000

_SELECTION_KEYS = frozenset(
    {"schema", "request_id", "goal", "expected_macro_sha", "profile_id", "profile_sha256"}
)
_DRAFT_KEYS = frozenset(
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
_PAYLOAD_KEYS = frozenset({"schema", "action", "request", "actor", "initial_snapshot", "source_binding"})
_SNAPSHOT_KEYS = frozenset({"compiler_request", "programs", "profiles"})
_REF_KEYS = frozenset({"repository", "path", "commit", "content_sha256"})
_BINDING_ROLES = ("compiler", "owner", "programs")
_ROLE_PATHS = {
    "compiler": COMPILER_SOURCE_PATH,
    "owner": OWNER_SOURCE_PATH,
    "programs": PROGRAMMES_SOURCE_PATH,
}


class ProjectCreationOperationError(ValueError):
    """The adapter refused an input or a state transition.

    A closed vocabulary: every refusal carries one fixed ``code`` and one
    fixed message from the table below.  No message is ever formatted with
    request, goal, profile, payload or catalogue content, so a caller can
    surface the error without leaking private input.  Subclasses ``ValueError``
    so callers can catch the plain builtin.
    """

    _MESSAGES = {
        "invalid_configuration": (
            "adapter configuration refused: the injected compiler module or the "
            "captured programme catalogue is not the required actual shape"
        ),
        "invalid_profiles": (
            "captured profile catalogue refused by the current profile helper"
        ),
        "invalid_source_binding": (
            "source binding refused: three exact Macro code refs sharing one "
            "commit are required"
        ),
        "invalid_request": (
            "profile selection refused: one explicit closed selection naming a "
            "captured profile at an exact revision is required"
        ),
        "invalid_principal": (
            "principal refused: an actual verified principal frame is required"
        ),
        "profile_refused": (
            "incumbent profile composition refused this selection at the "
            "captured catalogue"
        ),
        "source_changed": (
            "captured source changed: expected commit, code refs, programmes or "
            "profiles no longer match the recorded original"
        ),
        "compiler_refused": "the actual compiler refused the canonical input",
        "compiler_output_invalid": (
            "the actual compiler returned an envelope that fails the closed "
            "DRAFT_ONLY checks"
        ),
        "invalid_private_payload": "private payload refused: not the exact recorded shape",
        "principal_scope_changed": (
            "restore refused: the current principal scope differs from the "
            "recorded actor"
        ),
        "invalid_fingerprint": "trusted recipe fingerprint refused: not a lowercase SHA-256",
        "recipe_changed": (
            "restore/use refused: the canonical input or the recipe fingerprint "
            "differs; no recapture and no rebase is attempted"
        ),
        "prepared_required": (
            "proposal_recipe requires a prepared operation produced by this "
            "exact adapter configuration"
        ),
    }
    CODES = frozenset(_MESSAGES)

    def __init__(self, code):
        message = self._MESSAGES.get(code)
        if message is None:
            raise ValueError("internal: unknown ProjectCreationOperationError code")
        self.code = code
        super().__init__(code + ": " + message)


@dataclass(frozen=True)
class ProjectCreationSourceRef:
    """One captured Macro code ref.  An obligation, not an authentication."""

    repository: str
    path: str
    commit: str
    content_sha256: str

    def as_dict(self):
        return {
            "repository": self.repository,
            "path": self.path,
            "commit": self.commit,
            "content_sha256": self.content_sha256,
        }


def _coerce_source_ref(value, role):
    """Accept a ref object or its exact dict form; validate the exact shape."""
    if isinstance(value, ProjectCreationSourceRef):
        ref = value
    elif type(value) is dict and set(value) == _REF_KEYS and all(
        type(item) is str for item in value.values()
    ):
        ref = ProjectCreationSourceRef(**value)
    else:
        raise ProjectCreationOperationError("invalid_source_binding")
    if ref.repository != MACRO_REPOSITORY:
        raise ProjectCreationOperationError("invalid_source_binding")
    if ref.path != _ROLE_PATHS[role]:
        raise ProjectCreationOperationError("invalid_source_binding")
    if COMMIT_RE.fullmatch(ref.commit) is None:
        raise ProjectCreationOperationError("invalid_source_binding")
    if CONTENT_SHA_RE.fullmatch(ref.content_sha256) is None:
        raise ProjectCreationOperationError("invalid_source_binding")
    return ref


def _clean_programme_keys(value):
    """The captured programme catalogue: a non-empty set of clean key strings."""
    if type(value) not in (set, frozenset):
        raise ProjectCreationOperationError("invalid_configuration")
    if not value:
        raise ProjectCreationOperationError("invalid_configuration")
    for name in value:
        if type(name) is not str or not name or name != name.strip():
            raise ProjectCreationOperationError("invalid_configuration")
        for char in name:
            if unicodedata.category(char) == "Cc":
                raise ProjectCreationOperationError("invalid_configuration")
    return frozenset(value)


@dataclass(frozen=True)
class PreparedProjectCreation:
    """One prepared CREATE operation.

    Public fields describe the compiled DRAFT_ONLY envelope for display and
    routing only; they grant nothing.  The private fields carry the recorded
    original input and are exposed only through :meth:`private_payload`.
    ``fingerprint_sha256`` is the actual compiler's own ``request_sha256`` —
    the trusted recipe fingerprint — never a hash of the public request.
    """

    fingerprint_sha256: str
    request_id: str
    work_ref: str
    expected_commit: str
    path: str
    content_sha256: str
    _action: str = field(repr=False)
    _principal_scope: str = field(repr=False)
    _original_request: dict = field(repr=False)
    _compiler_request: dict = field(repr=False)
    _compiled_draft: dict = field(repr=False)
    _programmes: frozenset = field(repr=False)
    _profiles: dict = field(repr=False)
    _source_binding: dict = field(repr=False)
    _adapter_binding: str = field(repr=False)

    def safe_metadata(self):
        """Exactly the seven routable fields.  Never the goal, never the body."""
        return {
            "action": self._action,
            "request_id": self.request_id,
            "work_ref": self.work_ref,
            "expected_commit": self.expected_commit,
            "path": self.path,
            "content_sha256": self.content_sha256,
            "fingerprint_sha256": self.fingerprint_sha256,
        }

    def private_payload(self):
        """The exact six-key private original input, rebuilt fresh each call.

        This may carry the literal goal and the captured catalogue bytes; the
        parent's private wrapper, not this adapter, decides who may hold it.
        """
        return {
            "schema": PRIVATE_PAYLOAD_SCHEMA,
            "action": self._action,
            "request": copy.deepcopy(self._original_request),
            "actor": {"principal_scope": self._principal_scope},
            "initial_snapshot": {
                "compiler_request": copy.deepcopy(self._compiler_request),
                "compiled_recipe": copy.deepcopy(self._compiled_draft),
                "programs": sorted(self._programmes),
                "profiles": copy.deepcopy(self._profiles),
            },
            "source_binding": {role: dict(self._source_binding[role]) for role in _BINDING_ROLES},
        }


class ProjectCreationRecipeAdapter:
    """Typed CREATE recipe adapter over the actual Macro proposal compiler.

    Constructor inputs (all validated, all detached):

    * ``compiler`` — the actual ``scripts.agentos_project_proposal`` module
      (a real module type exposing ``compile_proposal`` plus its own
      ``OUTPUT_SCHEMA`` / ``DRAFT_STATE`` / ``WORKSTREAM_DIR`` law);
    * ``captured_programs`` — the detached actual programme catalogue, passed
      straight through to ``compile_proposal(request, programs=...)``;
    * ``captured_profiles`` — the actual explicit profile catalogue, accepted
      only if the current profile helper (``validate_profiles``) accepts it;
    * ``source_binding`` — the three exact code refs (compiler, owner,
      programmes) sharing one commit.

    The adapter is pure: no I/O, no clock, no transport, no Git, no auth
    issuance, no store.  Errors are always
    :class:`ProjectCreationOperationError`.
    """

    def __init__(self, compiler, captured_programs, captured_profiles, source_binding):
        from control_plane.project_creation_compilation import CapturedProjectCreationCompilation
        if type(compiler) not in (ModuleType, CapturedProjectCreationCompilation):
            raise ProjectCreationOperationError("invalid_configuration")
        compile_proposal = getattr(compiler, "compile_proposal", None)
        if not callable(compile_proposal):
            raise ProjectCreationOperationError("invalid_configuration")
        output_schema = getattr(compiler, "OUTPUT_SCHEMA", None)
        draft_state = getattr(compiler, "DRAFT_STATE", None)
        workstream_dir = getattr(compiler, "WORKSTREAM_DIR", None)
        if (
            output_schema != "agentos.project_proposal.v1"
            or draft_state != "DRAFT_ONLY"
            or workstream_dir != "agentos/workstreams"
            or workstream_dir.startswith("/")
            or workstream_dir.endswith("/")
            or "\\" in workstream_dir
        ):
            raise ProjectCreationOperationError("invalid_configuration")
        self._compiler = compiler
        self._compile_proposal = compile_proposal
        self._output_schema = output_schema
        self._draft_state = draft_state
        self._workstream_dir = workstream_dir
        self._programs = _clean_programme_keys(captured_programs)
        if type(captured_profiles) is not dict:
            raise ProjectCreationOperationError("invalid_profiles")
        try:
            self._profiles = validate_profiles(captured_profiles)
        except ProjectCreationOperationError:
            raise
        except Exception:
            raise ProjectCreationOperationError("invalid_profiles") from None
        if type(source_binding) is not dict or set(source_binding) != set(_BINDING_ROLES):
            raise ProjectCreationOperationError("invalid_source_binding")
        refs = {role: _coerce_source_ref(source_binding[role], role) for role in _BINDING_ROLES}
        commits = {refs[role].commit for role in _BINDING_ROLES}
        if len(commits) != 1:
            raise ProjectCreationOperationError("invalid_source_binding")
        self._commit = refs["compiler"].commit
        self._source_binding = {role: refs[role].as_dict() for role in _BINDING_ROLES}
        self._adapter_binding = self._configuration_digest()

    def _configuration_digest(self):
        """Binds a prepared operation to this exact captured configuration."""
        material = {
            "repository": MACRO_REPOSITORY,
            "commit": self._commit,
            "source_binding": self._source_binding,
            "captured_programmes": sorted(self._programs),
            "captured_profiles": self._profiles,
        }
        try:
            return hashlib.sha256(canonical(material)).hexdigest()
        except ProjectCreationOperationError:
            raise
        except Exception:
            raise ProjectCreationOperationError("invalid_configuration") from None

    # ------------------------------------------------------------ prepare

    def prepare(self, request, principal):
        """Compose and compile one closed profile selection into a prepared op."""
        self._validate_selection(request)
        scope = self._principal_scope(principal)
        self._require_source_commit(request["expected_macro_sha"])
        canonical_request = self._compose(request, principal)
        draft = self._compile(canonical_request)
        fingerprint = self._require_closed_draft(
            draft, canonical_request, request["request_id"], request["expected_macro_sha"]
        )
        return self._prepared(draft, canonical_request, request, scope)

    # ------------------------------------------------------------ restore

    def restore(self, private_payload, trusted_recipe_fingerprint, principal):
        """Revalidate a recorded original input and return its prepared op.

        Refuses on any differing actor, date-independent scope drift, request,
        source binding, profile, programme catalogue or canonical recipe
        fingerprint.  Nothing is recaptured and nothing is rebased: the only
        inputs are the payload, the trusted fingerprint, the current principal
        and this adapter's own captured configuration.
        """
        self._validate_payload(private_payload)
        if type(trusted_recipe_fingerprint) is not str or CONTENT_SHA_RE.fullmatch(
            trusted_recipe_fingerprint
        ) is None:
            raise ProjectCreationOperationError("invalid_fingerprint")
        scope = self._principal_scope(principal)
        if scope != private_payload["actor"]["principal_scope"]:
            raise ProjectCreationOperationError("principal_scope_changed")
        if private_payload["source_binding"] != self._source_binding:
            raise ProjectCreationOperationError("source_changed")
        snapshot = private_payload["initial_snapshot"]
        recorded_programmes = snapshot["programs"]
        if (
            type(recorded_programmes) is not list
            or not all(type(name) is str for name in recorded_programmes)
            or set(recorded_programmes) != set(self._programs)
            or len(recorded_programmes) != len(self._programs)
        ):
            raise ProjectCreationOperationError("source_changed")
        if type(snapshot["profiles"]) is not dict or snapshot["profiles"] != self._profiles:
            raise ProjectCreationOperationError("source_changed")
        request = private_payload["request"]
        try:
            self._validate_selection(request)
        except ProjectCreationOperationError:
            raise ProjectCreationOperationError("invalid_private_payload") from None
        canonical_request = self._compose(request, principal)
        if snapshot["compiler_request"] != canonical_request:
            raise ProjectCreationOperationError("recipe_changed")
        draft = self._compile(canonical_request)
        fingerprint = self._require_closed_draft(
            draft, canonical_request, request["request_id"], request["expected_macro_sha"]
        )
        if fingerprint != trusted_recipe_fingerprint:
            raise ProjectCreationOperationError("recipe_changed")
        return self._prepared(draft, canonical_request, request, scope)

    # ----------------------------------------------------- proposal_recipe

    def proposal_recipe(self, prepared):
        """Return the detached DRAFT_ONLY envelope, recompiled and rechecked.

        Every use recompiles the recorded canonical input through the actual
        compiler and re-checks the recipe fingerprint before anything is
        returned.
        """
        if (
            type(prepared) is not PreparedProjectCreation
            or prepared._adapter_binding != self._adapter_binding
        ):
            raise ProjectCreationOperationError("prepared_required")
        canonical_request = prepared._compiler_request
        draft = self._compile(canonical_request)
        fingerprint = self._require_closed_draft(
            draft, canonical_request, prepared.request_id, prepared.expected_commit
        )
        if fingerprint != prepared.fingerprint_sha256:
            raise ProjectCreationOperationError("recipe_changed")
        return copy.deepcopy(draft)

    # ------------------------------------------------------------- helpers

    def _validate_selection(self, request):
        """Shape-check the closed public selection before the incumbent sees it."""
        if (
            type(request) is not dict
            or set(request) != _SELECTION_KEYS
            or request["schema"] != SELECTION_SCHEMA
            or type(request["request_id"]) is not str
            or REQUEST_ID_RE.fullmatch(request["request_id"]) is None
            or type(request["profile_id"]) is not str
            or type(request["goal"]) is not str
            or not request["goal"].strip()
            or type(request["expected_macro_sha"]) is not str
            or COMMIT_RE.fullmatch(request["expected_macro_sha"]) is None
            or type(request["profile_sha256"]) is not str
            or CONTENT_SHA_RE.fullmatch(request["profile_sha256"]) is None
        ):
            raise ProjectCreationOperationError("invalid_request")
        try:
            goal_bytes = request["goal"].encode("utf-8")
        except UnicodeEncodeError:
            raise ProjectCreationOperationError("invalid_request") from None
        if len(goal_bytes) > MAX_GOAL_BYTES:
            raise ProjectCreationOperationError("invalid_request")

    def _principal_scope(self, principal):
        """The stable workspace scope of an actual verified principal."""
        if principal is None:
            raise ProjectCreationOperationError("invalid_principal")
        try:
            return source_principal_scope(principal)
        except ProjectCreationOperationError:
            raise
        except Exception:
            raise ProjectCreationOperationError("invalid_principal") from None

    def _require_source_commit(self, expected_commit):
        """The pinned source commit must equal all three captured code refs."""
        if expected_commit != self._commit:
            raise ProjectCreationOperationError("source_changed")

    def _compose(self, request, principal):
        """Incumbent composition: explicit profile at its exact authored revision."""
        try:
            return build_profiled_proposal_request(
                request, principal=principal, captured_catalogue=self._profiles
            )
        except ProjectCreationOperationError:
            raise
        except Exception:
            raise ProjectCreationOperationError("profile_refused") from None

    def _compile(self, canonical_request):
        """The actual compiler compiles the canonical input; no path imports."""
        try:
            return self._compile_proposal(canonical_request, programs=self._programs)
        except ProjectCreationOperationError:
            raise
        except Exception:
            raise ProjectCreationOperationError("compiler_refused") from None

    def _require_closed_draft(self, draft, canonical_request, request_id, expected_commit):
        """Closed checks over the actual compiler's returned envelope."""
        if type(draft) is not dict or set(draft) != _DRAFT_KEYS:
            raise ProjectCreationOperationError("compiler_output_invalid")
        if draft["schema"] != self._output_schema or draft["state"] != self._draft_state:
            raise ProjectCreationOperationError("compiler_output_invalid")
        if type(draft["request_id"]) is not str or draft["request_id"] != request_id:
            raise ProjectCreationOperationError("compiler_output_invalid")
        if type(draft["expected_commit"]) is not str or draft["expected_commit"] != expected_commit:
            raise ProjectCreationOperationError("compiler_output_invalid")
        key = canonical_request["record"]["key"]
        if type(draft["work_ref"]) is not str or draft["work_ref"] != "WS:" + key:
            raise ProjectCreationOperationError("compiler_output_invalid")
        expected_path = self._workstream_dir + "/WS-" + key + ".md"
        if type(draft["path"]) is not str or draft["path"] != expected_path:
            raise ProjectCreationOperationError("compiler_output_invalid")
        content = draft["content_utf8"]
        if type(content) is not str:
            raise ProjectCreationOperationError("compiler_output_invalid")
        content_sha256 = draft["content_sha256"]
        if (
            type(content_sha256) is not str
            or CONTENT_SHA_RE.fullmatch(content_sha256) is None
            or content_sha256 != hashlib.sha256(content.encode("utf-8")).hexdigest()
        ):
            raise ProjectCreationOperationError("compiler_output_invalid")
        fingerprint = draft["request_sha256"]
        if type(fingerprint) is not str or CONTENT_SHA_RE.fullmatch(fingerprint) is None:
            raise ProjectCreationOperationError("compiler_output_invalid")
        return fingerprint

    def _prepared(self, draft, canonical_request, request, scope):
        return PreparedProjectCreation(
            fingerprint_sha256=draft["request_sha256"],
            request_id=draft["request_id"],
            work_ref=draft["work_ref"],
            expected_commit=draft["expected_commit"],
            path=draft["path"],
            content_sha256=draft["content_sha256"],
            _action=PREPARED_ACTION,
            _principal_scope=scope,
            _original_request=copy.deepcopy(request),
            _compiler_request=copy.deepcopy(canonical_request),
            _compiled_draft=copy.deepcopy(draft),
            _programmes=self._programs,
            _profiles=self._profiles,
            _source_binding={role: dict(self._source_binding[role]) for role in _BINDING_ROLES},
            _adapter_binding=self._adapter_binding,
        )

    def _validate_payload(self, payload):
        """Exact six-key payload shape; content gates follow."""
        if type(payload) is not dict or set(payload) != _PAYLOAD_KEYS:
            raise ProjectCreationOperationError("invalid_private_payload")
        if payload["schema"] != PRIVATE_PAYLOAD_SCHEMA or payload["action"] != PREPARED_ACTION:
            raise ProjectCreationOperationError("invalid_private_payload")
        actor = payload["actor"]
        if (
            type(actor) is not dict
            or set(actor) != {"principal_scope"}
            or type(actor["principal_scope"]) is not str
            or CONTENT_SHA_RE.fullmatch(actor["principal_scope"]) is None
        ):
            raise ProjectCreationOperationError("invalid_private_payload")
        snapshot = payload["initial_snapshot"]
        if type(snapshot) is not dict or set(snapshot) not in (_SNAPSHOT_KEYS, _SNAPSHOT_KEYS | {"compiled_recipe"}):
            raise ProjectCreationOperationError("invalid_private_payload")
        if type(snapshot["compiler_request"]) is not dict:
            raise ProjectCreationOperationError("invalid_private_payload")
        if type(snapshot["programs"]) is not list:
            raise ProjectCreationOperationError("invalid_private_payload")
        if type(snapshot["profiles"]) is not dict:
            raise ProjectCreationOperationError("invalid_private_payload")
        binding = payload["source_binding"]
        if type(binding) is not dict or set(binding) != set(_BINDING_ROLES):
            raise ProjectCreationOperationError("invalid_private_payload")
        for role in _BINDING_ROLES:
            ref = binding[role]
            if (
                type(ref) is not dict
                or set(ref) != _REF_KEYS
                or any(type(item) is not str for item in ref.values())
                or COMMIT_RE.fullmatch(ref["commit"]) is None
                or CONTENT_SHA_RE.fullmatch(ref["content_sha256"]) is None
            ):
                raise ProjectCreationOperationError("invalid_private_payload")
