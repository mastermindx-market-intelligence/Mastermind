"""control_plane.ceo_request — the shared CEO_REQUEST_V1 normalization/derivation law.

MAS-75 PR-A (child of MAS-48).  This module is a first-party **Python**
normalization/derivation law, not a new serialized public protocol (adjudication
§4).  It exists so the existing Executive MCP transport and the future dedicated
Slack ``CeoIngress`` transport (PR-A/PR-B) share exactly one implementation of:

* the high-level bounded CEO-request normalization semantics (§4.1/§4.2/§4.3);
* the trusted v1 derivation law every accepted request receives (§5);
* the two transport-specific, cross-transport-namespaced canonical intent
  identity functions (§6) — the existing frozen MCP one and the new Slack one.

Design laws
-----------
* **Bounded law, not a control plane.**  This module holds no clock, no I/O, no
  database handle, and no queue.  Every function here is pure: same input,
  same output, always.
* **Never imports the MCP surface.**  The MCP gateway package (or any MCP/Slack
  SDK) is never imported here (adjudication §3) — the direction of delegation
  is the transport wrapper importing this module, never the reverse.  Doing
  otherwise would let a UI-facing schema concern leak into the shared law, and
  would make this module unusable from a future dedicated Slack ingress that
  must not carry the MCP SDK as a transitive dependency.
* **The MCP identity is frozen byte-for-byte.**  :func:`mcp_intent_id` is an
  independent re-implementation of the existing MCP gateway module's own
  ``derive_intent_id`` domain/prefix law (adjudication §6.1); both must and do
  produce identical output for every operation key — proven by the literal
  regression vectors in ``tests/test_executive_ceo_request.py``.
  :func:`slack_intent_id` is the new, separately namespaced Slack identity
  (§6.2). Cross-transport dedupe is deliberately NOT inferred: an MCP submit
  and a Slack submit of the same ``operation_key`` mint two different,
  independent intent ids.
* **Caller/model authors intent, never authority.**  ``actor``, canonical
  schema, authority level, branch, worktree, and requested authorities are
  never accepted from a caller; they are derived here from reviewed constants
  and the reviewed execution-profile table (§4.1, §5).
* **Errors are typed, not stringly.**  :class:`CeoRequestError` and its two
  subclasses let every transport wrapper map to its OWN public error
  vocabulary/messages without depending on this module's text (§4.4). This
  module never imports the MCP gateway module's ``GatewayError``.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from control_plane import ceo_intent

__all__ = [
    "ACTOR",
    "AUTOMATED_INTENT_ID_PREFIX",
    "AUTOMATED_OPTIONAL_FIELDS",
    "AUTOMATED_REQUEST_REF_RE",
    "AUTOMATED_REQUIRED_FIELDS",
    "AUTHORITY_LEVEL",
    "CeoRequestError",
    "CeoRequestInternalError",
    "CeoRequestInvalid",
    "DEFAULT_ATTEMPT_LIMIT",
    "EXECUTION_PROFILES",
    "MAX_ATTEMPT_LIMIT",
    "MAX_COMPILEALL_PATHS",
    "MAX_OBJECTIVE_CHARS",
    "MAX_OPERATION_KEY_CHARS",
    "MAX_PRIORITY",
    "MAX_PYTEST_TARGETS",
    "MAX_WRITE_PATHS",
    "MAX_WRITE_PATH_CHARS",
    "MCP_INTENT_ID_PREFIX",
    "MIN_ATTEMPT_LIMIT",
    "MIN_PRIORITY",
    "OPTIONAL_FIELDS",
    "PROFILE_CAPABILITY_CEILING",
    "REQUIRED_FIELDS",
    "SLACK_INTENT_ID_PREFIX",
    "VALIDATION_KEYS",
    "automated_intent_id",
    "build_trusted_envelope",
    "build_validation_commands",
    "derive_authorities",
    "derive_branch",
    "derive_worktree",
    "mcp_intent_id",
    "normalize_automated_request",
    "normalize_high_level_request",
    "slack_intent_id",
]


# ---------------------------------------------------------------------------
# errors (adjudication §4.4)
# ---------------------------------------------------------------------------


class CeoRequestError(Exception):
    """Base of every error this module raises.

    ``caller_fault`` is ``True`` for a bad high-level request/field (the
    caller's mistake) and ``False`` for an internal policy/configuration
    defect (never a caller mistake — e.g. a reviewed profile naming a
    capability outside its own ceiling).  A transport wrapper reads this flag
    to choose its own public error code rather than parsing message text.
    """

    def __init__(self, message: str, *, caller_fault: bool) -> None:
        super().__init__(message)
        self.message = message
        self.caller_fault = caller_fault


class CeoRequestInvalid(CeoRequestError):
    """The caller-supplied high-level request, or one of its fields, is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, caller_fault=True)


class CeoRequestInternalError(CeoRequestError):
    """An internal policy/configuration defect — never a caller mistake."""

    def __init__(self, message: str) -> None:
        super().__init__(message, caller_fault=False)


# ---------------------------------------------------------------------------
# trusted derivation constants (adjudication §5)
# ---------------------------------------------------------------------------

#: CEO provenance, never transport identity (§5).  Identical for MCP and Slack.
ACTOR = "ceo-sol"

#: Every PR-A v1 intent is authority level A0 (§5).
AUTHORITY_LEVEL = "A0"

#: Hex characters of the digest carried into every transport's intent id.
INTENT_ID_DIGEST_CHARS = 32

#: Existing MCP identity — frozen byte-for-byte (§6.1).  Reproduced here
#: (never imported from the MCP gateway module) so this module never depends
#: on the MCP package; byte-identity with the existing MCP derivation is a
#: regression-tested property, not an import.
MCP_INTENT_ID_PREFIX = "mcp-"
_MCP_INTENT_ID_DOMAIN = b"mastermind.executive_mcp.operation_key.v1\x00"

#: New Slack identity — frozen here (§6.2).  Separately namespaced: an MCP and
#: a Slack submission of the same ``operation_key`` never collide.
SLACK_INTENT_ID_PREFIX = "slack-"
_SLACK_INTENT_ID_DOMAIN = b"mastermind.executive_slack.operation_key.v1\x00"

#: Additive automated identity for already-identified request instances.  It
#: is deliberately independent of ingress transport; historical MCP/Slack v1
#: identities above remain byte-frozen compatibility law.
AUTOMATED_INTENT_ID_PREFIX = "auto-"
_AUTOMATED_INTENT_ID_DOMAIN = b"mastermind.executive_automated_request.v1\x00"
AUTOMATED_REQUEST_REF_RE = re.compile(r"^req-[a-z0-9][a-z0-9._-]{7,95}$")


# ---------------------------------------------------------------------------
# high-level request law (adjudication §4)
# ---------------------------------------------------------------------------

#: §4.1 — required/optional business fields.  Nothing else is accepted.
REQUIRED_FIELDS = frozenset(
    {"operation_key", "objective", "department", "priority", "execution_profile"}
)
OPTIONAL_FIELDS = frozenset(
    {"workstream", "allowed_write_paths", "validation", "attempt_limit"}
)
#: AD-ID1 automated requests carry semantic intent only.  Their trusted
#: ``request_ref`` is the outer-frame identity and ``operation_key`` is never
#: accepted inside the semantic request.
AUTOMATED_REQUIRED_FIELDS = frozenset(
    {"objective", "department", "priority", "execution_profile"}
)
AUTOMATED_OPTIONAL_FIELDS = OPTIONAL_FIELDS
VALIDATION_KEYS = frozenset({"pytest_targets", "compileall_paths", "git_diff_check"})

#: §4.3 — exactly these two execution profiles.  Nothing here may ever grow
#: ``OPEN_PR``, ``PUSH_BRANCH``, ``MERGE``, ``DEPLOY``, ``SERVICE_CONTROL``, or
#: ``CROSS_REPO_PUBLISH``.
EXECUTION_PROFILES: dict[str, tuple[str, ...]] = {
    "research_only": ("READ", "RESEARCH"),
    "bounded_code_change": ("READ", "RUN_TESTS", "WRITE_BRANCH"),
}

#: Every capability any profile may ever emit.  A profile naming anything
#: outside this set is a defect in THIS module, refused at derivation time.
PROFILE_CAPABILITY_CEILING = frozenset({"READ", "RESEARCH", "RUN_TESTS", "WRITE_BRANCH"})

MAX_OBJECTIVE_CHARS = 4000
MAX_OPERATION_KEY_CHARS = 96
MIN_PRIORITY = -100
MAX_PRIORITY = 100
MAX_WRITE_PATHS = 16
MAX_WRITE_PATH_CHARS = 256
MAX_PYTEST_TARGETS = 8
MAX_COMPILEALL_PATHS = 8
MIN_ATTEMPT_LIMIT = 1
MAX_ATTEMPT_LIMIT = 3
DEFAULT_ATTEMPT_LIMIT = 2

_OPERATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,95}$")
_DEPARTMENT_RE = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_WORKSTREAM_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")

#: Git internals a declared write path may never name.
_GIT_INTERNAL_SEGMENTS = frozenset({".git", ".gitmodules"})


# ---------------------------------------------------------------------------
# primitive validators (exact semantics of the current MCP law — §4.2)
# ---------------------------------------------------------------------------


def _plain_text(value: Any, field: str, *, max_chars: int) -> str:
    if not isinstance(value, str):
        raise CeoRequestInvalid(f"{field} must be a string")
    if len(value) > max_chars:
        raise CeoRequestInvalid(f"{field} exceeds {max_chars} characters")
    for char in value:
        if unicodedata.category(char) in ("Cc", "Cs"):
            raise CeoRequestInvalid(
                f"{field} contains a control or surrogate character"
            )
    return value


def _bounded_int(value: Any, field: str, *, minimum: int, maximum: int) -> int:
    # ``bool`` is an ``int`` in Python.  ``priority: true`` is a type error, not 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise CeoRequestInvalid(f"{field} must be an integer")
    if not minimum <= value <= maximum:
        raise CeoRequestInvalid(f"{field} must be between {minimum} and {maximum}")
    return value


def _bounded_list(value: Any, field: str, *, max_items: int) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise CeoRequestInvalid(f"{field} must be a list")
    if len(value) > max_items:
        raise CeoRequestInvalid(f"{field} holds more than {max_items} entries")
    return list(value)


def _exact_keys(
    value: Any, field: str, required: frozenset[str], optional: frozenset[str]
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CeoRequestInvalid(f"{field} must be an object")
    keys = {str(key) for key in value}
    unexpected = sorted(keys - required - optional)
    if unexpected:
        raise CeoRequestInvalid(f"{field} has unexpected field(s): {unexpected}")
    missing = sorted(required - keys)
    if missing:
        raise CeoRequestInvalid(f"{field} is missing required field(s): {missing}")
    return value


def _matches(value: Any, field: str, pattern: re.Pattern[str], *, max_chars: int) -> str:
    text = _plain_text(value, field, max_chars=max_chars)
    if pattern.fullmatch(text) is None:
        raise CeoRequestInvalid(f"{field} has an unsupported form")
    return text


def _repo_relative_path(value: Any, field: str) -> str:
    """Normalize one caller-supplied repository-relative path, or refuse.

    Refuses: absolute paths, ``..`` at any position, NUL/control characters,
    backslash separators, ``.git`` and Git internals, an empty path, and any
    segment that is not a conservative filename.  Exact semantics of the
    current MCP ``_repo_relative_path`` law.
    """

    text = _plain_text(value, field, max_chars=MAX_WRITE_PATH_CHARS).strip()
    if not text:
        raise CeoRequestInvalid(f"{field} must be a non-empty path")
    if "\\" in text:
        raise CeoRequestInvalid(f"{field} must use '/' separators, never '\\'")
    if text.startswith("/") or text.startswith("~"):
        raise CeoRequestInvalid(f"{field} must be repository-relative, not absolute")
    segments = [segment for segment in text.split("/") if segment not in ("", ".")]
    if not segments:
        raise CeoRequestInvalid(f"{field} must name a path inside the repository")
    for segment in segments:
        if segment == "..":
            raise CeoRequestInvalid(f"{field} must not traverse with '..'")
        if segment.lower() in _GIT_INTERNAL_SEGMENTS:
            raise CeoRequestInvalid(
                f"{field} must not name Git internals ({segment})"
            )
        if _PATH_SEGMENT_RE.fullmatch(segment) is None:
            raise CeoRequestInvalid(
                f"{field} has an unsupported path segment {segment!r}"
            )
    return "/".join(segments)


def _pytest_target(value: Any, field: str) -> str:
    path = _repo_relative_path(value, field)
    if not path.startswith("tests/"):
        raise CeoRequestInvalid(f"{field} must resolve under 'tests/'")
    if not path.endswith(".py"):
        raise CeoRequestInvalid(f"{field} must name a '.py' test file")
    return path


def _compileall_path(value: Any, field: str) -> str:
    path = _repo_relative_path(value, field)
    if path.endswith(".py"):
        raise CeoRequestInvalid(
            f"{field} must name a package/module directory, not a file"
        )
    return path


# ---------------------------------------------------------------------------
# normalization (adjudication §4.2/§4.3)
# ---------------------------------------------------------------------------


def normalize_high_level_request(payload: Any) -> dict[str, Any]:
    """Normalize one bounded high-level CEO request (§4), or refuse.

    Pure: no I/O, no clock, no derivation.  Preserves the exact current MCP
    normalization semantics (§4.2): no-strip fields (``operation_key``,
    ``department``, ``execution_profile``, ``workstream``), the ``objective``
    strip-then-refuse-empty rule, ``allowed_write_paths``/validation path
    normalization+dedup+sort, the ``git_diff_check`` false-removal rule, the
    ``1..3`` bool-rejecting ``attempt_limit`` bound (default 2), and the two
    execution-profile coherence rules (§4.3).

    Raises :class:`CeoRequestInvalid` on any refusal.  Never accepts ``actor``,
    ``schema``, grounding, raw authorities, ``authority_level``, raw argv,
    ``branch``, ``worktree``, Job id/status, or any other privileged field —
    those are structurally outside :data:`REQUIRED_FIELDS`/:data:`OPTIONAL_FIELDS`
    and refused by the exact-key-set check below.
    """

    _exact_keys(payload, "request", REQUIRED_FIELDS, OPTIONAL_FIELDS)

    profile = _plain_text(payload["execution_profile"], "execution_profile", max_chars=64)
    if profile not in EXECUTION_PROFILES:
        raise CeoRequestInvalid(
            f"execution_profile must be one of {sorted(EXECUTION_PROFILES)}"
        )

    result: dict[str, Any] = {
        "operation_key": _matches(
            payload["operation_key"], "operation_key", _OPERATION_KEY_RE,
            max_chars=MAX_OPERATION_KEY_CHARS,
        ),
        "objective": _plain_text(
            payload["objective"], "objective", max_chars=MAX_OBJECTIVE_CHARS
        ).strip(),
        "department": _matches(
            payload["department"], "department", _DEPARTMENT_RE, max_chars=64
        ),
        "priority": _bounded_int(
            payload["priority"], "priority", minimum=MIN_PRIORITY, maximum=MAX_PRIORITY
        ),
        "execution_profile": profile,
    }
    if not result["objective"]:
        raise CeoRequestInvalid("objective must be a non-empty string")

    if "workstream" in payload:
        result["workstream"] = _matches(
            payload["workstream"], "workstream", _WORKSTREAM_RE, max_chars=72
        )

    raw_paths = payload.get("allowed_write_paths")
    paths: list[str] = []
    if raw_paths is not None:
        items = _bounded_list(raw_paths, "allowed_write_paths", max_items=MAX_WRITE_PATHS)
        paths = sorted(
            {
                _repo_relative_path(item, f"allowed_write_paths[{index}]")
                for index, item in enumerate(items)
            }
        )
    result["allowed_write_paths"] = paths

    raw_validation = payload.get("validation")
    validation: dict[str, Any] = {}
    if raw_validation is not None:
        _exact_keys(raw_validation, "validation", frozenset(), VALIDATION_KEYS)
        targets = raw_validation.get("pytest_targets")
        if targets is not None:
            items = _bounded_list(
                targets, "validation.pytest_targets", max_items=MAX_PYTEST_TARGETS
            )
            validation["pytest_targets"] = sorted(
                {
                    _pytest_target(item, f"validation.pytest_targets[{index}]")
                    for index, item in enumerate(items)
                }
            )
        compile_paths = raw_validation.get("compileall_paths")
        if compile_paths is not None:
            items = _bounded_list(
                compile_paths, "validation.compileall_paths", max_items=MAX_COMPILEALL_PATHS
            )
            validation["compileall_paths"] = sorted(
                {
                    _compileall_path(item, f"validation.compileall_paths[{index}]")
                    for index, item in enumerate(items)
                }
            )
        if "git_diff_check" in raw_validation:
            flag = raw_validation["git_diff_check"]
            if not isinstance(flag, bool):
                raise CeoRequestInvalid("validation.git_diff_check must be a boolean")
            validation["git_diff_check"] = flag
    # Drop empty/false so an all-empty recipe is indistinguishable from none.
    validation = {key: value for key, value in validation.items() if value}
    result["validation"] = validation

    result["attempt_limit"] = (
        _bounded_int(
            payload["attempt_limit"], "attempt_limit",
            minimum=MIN_ATTEMPT_LIMIT, maximum=MAX_ATTEMPT_LIMIT,
        )
        if "attempt_limit" in payload
        else DEFAULT_ATTEMPT_LIMIT
    )

    # --- profile coherence (§4.3) ------------------------------------------
    if profile == "research_only":
        if paths:
            raise CeoRequestInvalid(
                "execution_profile 'research_only' grants no write authority; "
                "allowed_write_paths is refused"
            )
        if validation:
            raise CeoRequestInvalid(
                "execution_profile 'research_only' grants no test authority; "
                "validation is refused"
            )
    else:  # bounded_code_change
        if not paths:
            raise CeoRequestInvalid(
                "execution_profile 'bounded_code_change' requires at least one "
                "allowed_write_paths entry"
            )
        if not validation:
            raise CeoRequestInvalid(
                "execution_profile 'bounded_code_change' requires at least one "
                "validation entry"
            )
    return result


def normalize_automated_request(payload: Any) -> dict[str, Any]:
    """Normalize one additive automated semantic request, or refuse.

    The normalization and profile-coherence law is exactly the historical v1
    implementation above.  A private, known-legal placeholder lets this
    wrapper delegate to that single law after first enforcing the automated
    path's smaller exact key set; the placeholder is removed from the result
    and never becomes request identity or durable provenance.
    """

    _exact_keys(
        payload,
        "request",
        AUTOMATED_REQUIRED_FIELDS,
        AUTOMATED_OPTIONAL_FIELDS,
    )
    compatible = dict(payload)
    compatible["operation_key"] = "automated-request-placeholder"
    normalized = normalize_high_level_request(compatible)
    del normalized["operation_key"]
    return normalized


def build_validation_commands(validation: Mapping[str, Any] | None) -> list[list[str]]:
    """Construct the reviewed argv list from a validation *recipe*.

    The caller never supplies argv.  It names targets; this function writes
    the commands.  Argv family ordering is fixed: pytest, compileall, then
    ``git diff --check`` (§4.2).
    """

    if not validation:
        return []
    commands: list[list[str]] = []
    targets = validation.get("pytest_targets") or []
    if targets:
        commands.append(["python3", "-m", "pytest", "-q", *targets])
    paths = validation.get("compileall_paths") or []
    if paths:
        commands.append(["python3", "-m", "compileall", *paths])
    if validation.get("git_diff_check"):
        commands.append(["git", "diff", "--check"])
    return commands


def derive_authorities(execution_profile: str) -> list[str]:
    """Profile name -> reviewed, sorted capability list (§4.3/§5)."""

    capabilities = EXECUTION_PROFILES.get(execution_profile)
    if capabilities is None:
        raise CeoRequestInvalid(
            f"execution_profile must be one of {sorted(EXECUTION_PROFILES)}"
        )
    escaped = set(capabilities) - PROFILE_CAPABILITY_CEILING
    if escaped:
        # A profile that grew a capability outside the reviewed ceiling is a
        # defect in THIS module, never a caller mistake.
        raise CeoRequestInternalError(
            f"execution profile {execution_profile!r} names unreviewed capabilities"
        )
    return sorted(capabilities)


# ---------------------------------------------------------------------------
# transport-specific intent identity (adjudication §6)
# ---------------------------------------------------------------------------


def _validated_operation_key(operation_key: Any) -> str:
    return _matches(
        operation_key, "operation_key", _OPERATION_KEY_RE, max_chars=MAX_OPERATION_KEY_CHARS
    )


def _transport_intent_id(prefix: str, domain: bytes, operation_key: str) -> str:
    key = _validated_operation_key(operation_key)
    digest = hashlib.sha256(domain + key.encode("utf-8")).hexdigest()
    intent_id = prefix + digest[:INTENT_ID_DIGEST_CHARS]
    if ceo_intent.INTENT_ID_RE.fullmatch(intent_id) is None or len(intent_id) > 64:
        # Unreachable with the constants above; asserted rather than assumed so
        # a future prefix/digest-length change cannot quietly mint an id the
        # existing upstream validator would refuse.
        raise CeoRequestInternalError("derived intent id is not upstream-legal")
    return intent_id


def mcp_intent_id(operation_key: str) -> str:
    """``mcp-<32 hex>`` — existing MCP identity, frozen byte-for-byte (§6.1).

    ``sha256(b"mastermind.executive_mcp.operation_key.v1\\x00" + operation_key)``,
    first 32 lowercase hex digest characters, ``mcp-`` prefix.  Byte-identical
    to the existing MCP gateway module's own ``derive_intent_id`` for every
    legal operation key — pinned by the literal regression vectors in
    ``tests/test_executive_ceo_request.py``.
    """

    return _transport_intent_id(MCP_INTENT_ID_PREFIX, _MCP_INTENT_ID_DOMAIN, operation_key)


def slack_intent_id(operation_key: str) -> str:
    """``slack-<32 hex>`` — new Slack identity, frozen here (§6.2).

    Separately namespaced from :func:`mcp_intent_id`: the same
    ``operation_key`` submitted over MCP and over Slack mints two different,
    independent canonical intent ids. Cross-transport dedupe is deliberately
    not inferred.
    """

    return _transport_intent_id(SLACK_INTENT_ID_PREFIX, _SLACK_INTENT_ID_DOMAIN, operation_key)


def automated_intent_id(request_ref: str) -> str:
    """Return the global ``auto-<32 hex>`` id for one exact request instance.

    ``request_ref`` is not stripped, case-folded, transport-namespaced, or
    combined with semantic payload.  Reusing it with a changed normalized
    envelope is therefore detected by the existing durable fingerprint law.
    """

    ref = _matches(
        request_ref,
        "request_ref",
        AUTOMATED_REQUEST_REF_RE,
        max_chars=100,
    )
    digest = hashlib.sha256(
        _AUTOMATED_INTENT_ID_DOMAIN + ref.encode("utf-8")
    ).hexdigest()
    intent_id = AUTOMATED_INTENT_ID_PREFIX + digest[:INTENT_ID_DIGEST_CHARS]
    if ceo_intent.INTENT_ID_RE.fullmatch(intent_id) is None or len(intent_id) > 64:
        raise CeoRequestInternalError("derived automated intent id is not upstream-legal")
    return intent_id


def derive_branch(intent_id: str) -> str:
    """``codex/<intent-id>`` — deterministic, always under the reviewed prefix (§5)."""

    return f"codex/{intent_id}"


def derive_worktree(workspace_root: str, intent_id: str) -> str:
    """``<reviewed workspace root>/<intent-id>`` (§5).

    ``workspace_root`` is host configuration the caller passes in — the
    existing ``ServiceConfig.proof_workspace_root`` value — never read from
    config by this module and never a request field.
    """

    root = str(workspace_root).rstrip("/")
    if not root.startswith("/"):
        raise CeoRequestInternalError("workspace root must be absolute")
    return f"{root}/{intent_id}"


# ---------------------------------------------------------------------------
# trusted v1 envelope assembly (adjudication §5)
# ---------------------------------------------------------------------------


def build_trusted_envelope(
    normalized_request: Mapping[str, Any],
    *,
    intent_id: str,
    workspace_root: str,
    grounding: Mapping[str, Any],
) -> dict[str, Any]:
    """Assemble one ``mastermind.ceo_intent.v1`` envelope from trusted derivations.

    ``normalized_request`` must already be the output of
    :func:`normalize_high_level_request`. ``grounding`` is an already-validated
    mapping (this module never discovers or refreshes grounding — that is the
    caller's trusted-grounding-provider responsibility, out of PR-A ceo_request
    scope). The result is ready for
    ``control_plane.ceo_intent.validate_intent``/``submit_intent``; it is not
    itself validated here (validation stays the sink's job, per the one v1
    mutation authority law).
    """

    authorities = derive_authorities(str(normalized_request["execution_profile"]))
    contract: dict[str, Any] = {
        "requested_authorities": authorities,
        "authority_level": AUTHORITY_LEVEL,
        "branch": derive_branch(intent_id),
        "worktree": derive_worktree(workspace_root, intent_id),
        "attempt_limit": int(normalized_request["attempt_limit"]),
    }
    paths = list(normalized_request.get("allowed_write_paths") or [])
    if paths:
        contract["allowed_write_paths"] = paths
    commands = build_validation_commands(normalized_request.get("validation"))
    if commands:
        contract["validation_commands"] = commands

    envelope: dict[str, Any] = {
        "schema": ceo_intent.INTENT_SCHEMA,
        "intent_id": intent_id,
        # Injected by trusted code.  Provenance, never authentication: no
        # caller may set it and its value confers no privilege.
        "actor": ACTOR,
        "objective": str(normalized_request["objective"]),
        "department": str(normalized_request["department"]),
        "priority": int(normalized_request["priority"]),
        "grounding": dict(grounding),
        "execution_contract": contract,
    }
    if normalized_request.get("workstream"):
        envelope["workstream"] = str(normalized_request["workstream"])
    return envelope
