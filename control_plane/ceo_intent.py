"""control_plane.ceo_intent — the bounded CEO → Executive OS write bridge.

Phase 1D-A gave the AI CEO seat a way to *read* organizational state
(:mod:`control_plane.ceo_boot_packet`).  This module is the deliberately narrow
inverse: a trusted local caller submits one typed ``mastermind.ceo_intent.v1``
envelope, it is validated, adjudicated by the existing authority policy, and
turned into exactly one durable QUEUED Job through the existing
``Runtime.jobs.create_job(...)``.  Then it stops.

Design laws
-----------
* **Adapter, not a control plane.**  This module adds no queue, no scheduler, no
  intent database, no state machine, and no table.  Every durable fact it
  produces already had a home: the Job row and its ``JOB_CREATED`` event.  A
  second control plane hung off CEO intent is precisely what the Mastermind
  ``constraints.duplicate_control_planes`` prohibition names — see
  :mod:`control_plane.strategic_state`.
* **Submission is never execution — but that is "no AUTOMATIC dispatch", not
  "unexecutable".**  Accepting an intent creates a QUEUED Job and nothing else.
  Nothing here dispatches, claims, leases, starts a process, or touches a
  supervisor, and this module imports no module that can:  not
  :mod:`control_plane.executive_supervisor`, not
  :mod:`control_plane.executive_worker_broker`, not
  :mod:`control_plane.codex_worker`.  The receipt carries an always-``False``
  ``dispatched`` field so a caller can never read acceptance as execution.
  ``ExecutiveControlService.dispatch``/``requeue`` additionally refuse any job
  that is not the fixed proof job, so the *service* will not run a CEO job.

  Do not over-read that.  ``scripts/executive_os_phase1b.py run-once`` calls
  ``ExecutiveSupervisor.run_once``, which has **no** proof-job gate: it claims
  and executes ANY queued job, building its launch spec from that job's own
  ``worktree``, ``allowed_write_paths``, and ``validation_commands``.  So the
  containment here is that nothing *automatically* runs a CEO job — an operator
  invoking ``run-once`` can.  What is genuinely new in this phase is the
  PRINCIPAL: this is the first path on which an LLM-authored JSON envelope
  determines a job's worktree and argv.  That is why the worktree is fenced to a
  configured workspace root and argv[0] is shape-bounded below, and why neither
  fence may be relaxed without review.
* **Authority is downstream truth — the CEO is provenance, not root.**  The
  requested authorities travel to :meth:`JobRegistry.create_job` unchanged and
  are adjudicated there by :class:`~control_plane.executive_authority.
  ExecutiveAuthorityPolicy`.  This module never widens, substitutes, defaults,
  or re-signs a grant, and ``actor`` is recorded provenance with no privilege
  attached to its value.  A forbidden authority is refused by the policy, not by
  a courtesy check here.
* **Agent OS is never written from here.**  ``workstream`` is a string pointer
  for provenance only.  Nothing in this path opens, resolves, or mutates the
  Macro ``agentos/`` store; Executive OS reads Agent OS and writes only its own
  runtime.
* **Idempotency rides the existing UNIQUE index.**  The events table declares
  ``command_id TEXT NOT NULL UNIQUE``.  A CEO intent derives its command id from
  its ``intent_id``, so a retry reconciles against the durable event instead of
  creating a second Job, and two *concurrent* identical submissions are settled
  atomically by SQLite: the loser's INSERT fails inside its transaction and its
  whole Job row rolls back with it.  No advisory lock, no dedupe table.
* **Fail closed on anything unrecognized.**  Key sets are exact at every level;
  an unknown key, a shell string where argv is required, a short or uppercase
  grounding SHA, or a fingerprint that disagrees with an already-accepted
  ``intent_id`` is an error, never a silent repair.  A malformed grounding SHA
  is *never* replaced with current HEAD — the caller's claim about what it read
  is the durable record.
* **Import-time stdlib only.**  :mod:`control_plane.executive_runtime` and
  :mod:`control_plane.executive_authority` are themselves import-time stdlib, so
  importing this module pulls in no third-party code.

Usage
-----
    from control_plane.ceo_intent import submit_intent, validate_intent
    receipt = submit_intent(runtime, envelope)     # -> QUEUED Job + receipt
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from control_plane.executive_runtime import Job, StateConflict

#: Schema of the envelope this module accepts.  A bump means a migration.
INTENT_SCHEMA = "mastermind.ceo_intent.v1"

#: Schema of the receipt this module returns.
RECEIPT_SCHEMA = "mastermind.ceo_intent_receipt.v1"

#: Namespace for the durable event ``command_id``.  The prefix keeps CEO intent
#: ids from colliding with the runtime's own ``uuid4().hex`` command ids, which
#: carry no colon.  It is a namespace, NOT an authenticity claim: any in-process
#: caller with control-plane access can append an event under this prefix, so
#: :func:`_receipt_from_event` re-verifies the provenance schema tag and intent
#: id before it will build a receipt from a record.
COMMAND_ID_PREFIX = "ceo-intent:"

#: An intent id is caller-chosen but must stay a safe, quotable identifier: it
#: becomes part of a durable command id and travels over the control protocol,
#: whose own id validator is a superset of this pattern.
INTENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

#: Grounding SHAs are full, lowercase, 40-hex Git object ids.  Short or
#: uppercase input fails closed rather than being expanded or folded.
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$")
_DEPARTMENT_RE = re.compile(r"^[a-z][a-z0-9._-]{1,63}$")
_AUTHORITY_LEVEL_RE = re.compile(r"^A[0-7]$")
_AUTHORITY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_WORKSTREAM_RE = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")

_REQUIRED_KEYS = frozenset(
    {
        "schema",
        "intent_id",
        "actor",
        "objective",
        "department",
        "priority",
        "grounding",
        "execution_contract",
    }
)
_OPTIONAL_KEYS = frozenset({"workstream"})

_GROUNDING_REQUIRED = frozenset({"mastermind_sha", "macro_sha"})
_GROUNDING_OPTIONAL = frozenset({"boot_packet_schema"})

#: The reviewed execution surface.  Every name here is a ``create_job``
#: parameter spelled exactly as the runtime spells it — no synonyms, no
#: convenience aliases, nothing that has to be translated at the call site.
_CONTRACT_REQUIRED = frozenset({"requested_authorities"})
_CONTRACT_OPTIONAL = frozenset(
    {
        "allowed_write_paths",
        "validation_commands",
        "authority_level",
        "branch",
        "worktree",
        "attempt_limit",
        "constraints",
    }
)

#: Constraints reach ``_normalise_constraints`` unchanged, so this set is the
#: fence.  ``provider``/``model`` are deliberately absent: choosing the provider
#: or credential home is worker composition, reviewed on the host, never a
#: field a submitted intent may set.
_CONSTRAINT_KEYS = frozenset(
    {
        "required_capabilities",
        "eligible_quota_classes",
        "effort",
        "cost_class",
        "base_sha",
    }
)

#: Concepts a CEO intent may never carry, at any nesting level.  Exact key sets
#: already reject all of these structurally; this table exists so the REFUSAL IS
#: LEGIBLE — the caller is told which forbidden concept it reached for instead
#: of a bare "unexpected key".
_FORBIDDEN_CONCEPTS: dict[str, str] = {}


def _forbid(reason: str, *names: str) -> None:
    for name in names:
        _FORBIDDEN_CONCEPTS[name] = reason


_forbid(
    "environment variables are composed on the reviewed host, never submitted",
    "env", "envs", "environ", "environment", "environment_variables", "envvars",
)
_forbid(
    "credentials, tokens, and secrets never travel in an intent",
    "auth", "authorization", "api_key", "api_token", "apikey", "credential",
    "credentials", "key", "keys", "password", "passwords", "secret", "secrets",
    "token", "tokens",
)
_forbid(
    "shell strings and caller-chosen executables are refused; declare argv "
    "validation_commands instead",
    "argv0", "bash", "binary", "cmd", "command", "commands", "entrypoint",
    "exec", "executable", "interpreter", "script", "sh", "shell",
)
_forbid(
    "raw SQL and database paths are runtime-owned",
    "database", "database_path", "db", "db_path", "query", "runtime_root", "sql",
    "sqlite", "sqlite_path", "statement", "store_path", "table",
)
_forbid(
    "sockets, hosts, and network endpoints are host configuration",
    "control_socket_path", "endpoint", "host", "hostname", "port", "socket",
    "socket_path", "url",
)
_forbid(
    "worker uid/gid and run-as identity are reviewed host composition",
    "become", "gid", "group", "run_as", "uid", "user", "username", "worker_gid",
    "worker_uid",
)
_forbid(
    "service-control and dispatch verbs are not intent fields; submission is "
    "never execution",
    "dispatch", "execute", "launchctl", "launchd", "reboot", "restart", "run",
    "service", "service_control", "supervisor", "systemctl",
)
_forbid(
    "provider and credential-home selection is reviewed host composition",
    "account", "account_label", "credential_home", "home", "model", "provider",
    "provider_home",
)

#: ``argv[0]`` must be a bare program name.  The handoff forbids "executable
#: paths chosen by the caller", and the supervisor runs ``job.validation_commands``
#: verbatim, so a caller-supplied ``/bin/sh`` or ``/usr/bin/env`` would be exactly
#: the shell escape the argv-list rule exists to prevent.
#:
#: HONEST SCOPE: this bounds the SHAPE only.  It removes caller-chosen executable
#: paths and the obvious interpreter escapes; the program name still resolves
#: through the worker's own PATH at execution time, which this module neither
#: sees nor controls.  It is not a sandbox and is not claimed to be one.
_PROGRAM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
FORBIDDEN_PROGRAMS = frozenset(
    {"sh", "bash", "zsh", "dash", "ksh", "csh", "tcsh", "fish", "env", "command"}
)

#: Bounds.  Every one of these is a refusal boundary, not a hint.
#:
#: They are also sized so the published contract is REACHABLE: a maximal legal
#: envelope must fit inside the control service's request ceiling
#: (``DEFAULT_MAX_REQUEST_BYTES``, 64 KiB), or a caller obeying this contract
#: would get a generic ``request_too_large`` naming no field.  A test constructs
#: the maximal envelope and pins its wire size.
MAX_OBJECTIVE_CHARS = 4000
MAX_PRIORITY = 100
MIN_PRIORITY = -100
MAX_ATTEMPT_LIMIT = 20
MAX_AUTHORITIES = 8
MAX_WRITE_PATHS = 32
MAX_WRITE_PATH_CHARS = 256
MAX_VALIDATION_COMMANDS = 4
MAX_ARGV_ITEMS = 12
MAX_ARGV_ITEM_CHARS = 256
MAX_CONSTRAINT_ITEMS = 16
MAX_CONSTRAINT_LIST_ITEMS = 16
MAX_WORKTREE_CHARS = 1024
MAX_BRANCH_CHARS = 200
MAX_STRING_CHARS = 512
MAX_DEPTH = 8

#: Hard ceiling on the canonically-encoded envelope, well under the service's
#: 64 KiB request ceiling.  The per-field bounds above count CHARACTERS while the
#: wire carries UTF-8 BYTES, so a maximal all-ASCII envelope (~29 KB) and a
#: maximal 4-byte-per-character one are wildly different sizes.  This check is
#: what makes the published bounds honest for both.
MAX_ENVELOPE_BYTES = 48 * 1024


class CeoIntentError(ValueError):
    """A CEO intent envelope, or its reconciliation, was refused.

    Deliberately a :class:`ValueError`.  ``ExecutiveControlService`` already maps
    ``ValueError`` onto the ``request_failed`` error code, so a refusal reaches
    the caller as a legible bounded message instead of ``internal_error``.
    """


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def _scan_forbidden(value: Any, *, path: str = "intent", depth: int = 0) -> None:
    """Name the forbidden concept before exact-key-set validation hides it."""

    if depth > MAX_DEPTH:
        raise CeoIntentError(f"{path} is nested deeper than {MAX_DEPTH} levels")
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CeoIntentError(f"{path} has a non-string key {key!r}")
            reason = _FORBIDDEN_CONCEPTS.get(key.strip().lower())
            if reason is not None:
                raise CeoIntentError(
                    f"{path}.{key} is a forbidden CEO intent field: {reason}"
                )
            _scan_forbidden(value[key], path=f"{path}.{key}", depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _scan_forbidden(item, path=f"{path}[{index}]", depth=depth + 1)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CeoIntentError(f"{name} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], name: str, required: frozenset[str], optional: frozenset[str]) -> None:
    keys = set(value)
    unexpected = sorted(keys - required - optional)
    if unexpected:
        raise CeoIntentError(f"{name} has unexpected key(s): {unexpected}")
    missing = sorted(required - keys)
    if missing:
        raise CeoIntentError(f"{name} is missing required key(s): {missing}")


def _text(value: Any, name: str, *, pattern: re.Pattern[str] | None = None, max_chars: int = MAX_STRING_CHARS) -> str:
    if not isinstance(value, str):
        raise CeoIntentError(f"{name} must be a string")
    text = value.strip()
    if not text:
        raise CeoIntentError(f"{name} must be a non-empty string")
    if len(text) > max_chars:
        raise CeoIntentError(f"{name} exceeds {max_chars} characters")
    if "\x00" in text:
        raise CeoIntentError(f"{name} contains a NUL byte")
    try:
        # A lone surrogate survives json.loads but cannot be encoded, so without
        # this the refusal would surface as a raw UnicodeEncodeError out of the
        # fingerprint rather than as a bounded, field-named error.
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CeoIntentError(
            f"{name} is not encodable UTF-8 text (unpaired surrogate?)"
        ) from exc
    if pattern is not None and pattern.fullmatch(text) is None:
        raise CeoIntentError(f"{name} has an unsupported form: {text!r}")
    return text


def _integer(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    # ``bool`` is an ``int`` in Python; a boolean here is a type error, not a 0/1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise CeoIntentError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise CeoIntentError(f"{name} must be between {minimum} and {maximum}")
    return value


def _sequence(value: Any, name: str, *, max_items: int) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise CeoIntentError(f"{name} must be a list")
    if len(value) > max_items:
        raise CeoIntentError(f"{name} holds more than {max_items} entries")
    return value


def _grounding(value: Any) -> dict[str, Any]:
    raw = _mapping(value, "grounding")
    _exact_keys(raw, "grounding", _GROUNDING_REQUIRED, _GROUNDING_OPTIONAL)
    result: dict[str, Any] = {}
    for key in sorted(_GROUNDING_REQUIRED):
        sha = raw[key]
        if not isinstance(sha, str) or SHA_RE.fullmatch(sha) is None:
            # Never repaired, never expanded, never replaced with current HEAD:
            # the caller's claim about what it read IS the durable record.
            raise CeoIntentError(
                f"grounding.{key} must be a full 40-character lowercase Git SHA"
            )
        result[key] = sha
    if "boot_packet_schema" in raw:
        result["boot_packet_schema"] = _text(
            raw["boot_packet_schema"], "grounding.boot_packet_schema", max_chars=128
        )
    return result


def _authorities(value: Any) -> list[str]:
    items = _sequence(value, "execution_contract.requested_authorities", max_items=MAX_AUTHORITIES)
    if not items:
        raise CeoIntentError("execution_contract.requested_authorities must not be empty")
    resolved = set()
    for index, item in enumerate(items):
        text = _text(
            item,
            f"execution_contract.requested_authorities[{index}]",
            max_chars=32,
        ).upper()
        if _AUTHORITY_RE.fullmatch(text) is None:
            raise CeoIntentError(
                f"execution_contract.requested_authorities[{index}] is not an authority name"
            )
        resolved.add(text)
    # Sorted+deduplicated exactly the way the authority policy stores them, so
    # two spellings of one grant are one intent identity.  Whether each name is
    # GRANTED is decided downstream by the policy, never here.
    return sorted(resolved)


def _write_paths(value: Any) -> list[str]:
    items = _sequence(value, "execution_contract.allowed_write_paths", max_items=MAX_WRITE_PATHS)
    resolved = set()
    for index, item in enumerate(items):
        resolved.add(
            _text(
                item,
                f"execution_contract.allowed_write_paths[{index}]",
                max_chars=MAX_WRITE_PATH_CHARS,
            )
        )
    return sorted(resolved)


def _program_name(value: str, name: str) -> str:
    """Refuse caller-chosen executable paths and the shell/interpreter escapes.

    ``["bash", "-c", "..."]`` and ``["/usr/bin/env", "python3", "-c", "..."]`` are
    well-formed argv lists, so the argv-list rule alone does NOT stop a caller
    from handing the worker a shell.  The supervisor runs these verbatim, so the
    program name is fenced here as well.
    """

    if "/" in value or "\\" in value:
        raise CeoIntentError(
            f"{name} must be a bare program name, never a caller-chosen "
            f"executable path: {value!r}"
        )
    if _PROGRAM_NAME_RE.fullmatch(value) is None:
        raise CeoIntentError(f"{name} is not a valid program name: {value!r}")
    if value.lower() in FORBIDDEN_PROGRAMS:
        raise CeoIntentError(
            f"{name} may not be a shell or interpreter escape ({value!r}); "
            f"refused programs: {sorted(FORBIDDEN_PROGRAMS)}"
        )
    return value


def _validation_commands(value: Any) -> list[list[str]]:
    items = _sequence(
        value, "execution_contract.validation_commands", max_items=MAX_VALIDATION_COMMANDS
    )
    commands: list[list[str]] = []
    for index, raw in enumerate(items):
        name = f"execution_contract.validation_commands[{index}]"
        if isinstance(raw, (str, bytes)):
            # First line of defence.  ``ExecutiveAuthorityPolicy._validation_commands``
            # is the second and refuses the same shape independently.
            raise CeoIntentError(
                f"{name} must be an argv list, never a shell string"
            )
        argv_items = _sequence(raw, name, max_items=MAX_ARGV_ITEMS)
        if not argv_items:
            raise CeoIntentError(f"{name} must contain at least the program name")
        argv = [
            _text(item, f"{name}[{position}]", max_chars=MAX_ARGV_ITEM_CHARS)
            for position, item in enumerate(argv_items)
        ]
        _program_name(argv[0], f"{name}[0]")
        commands.append(argv)
    return commands


def _constraints(value: Any) -> dict[str, Any]:
    raw = _mapping(value, "execution_contract.constraints")
    if len(raw) > MAX_CONSTRAINT_ITEMS:
        raise CeoIntentError(
            f"execution_contract.constraints holds more than {MAX_CONSTRAINT_ITEMS} keys"
        )
    _exact_keys(raw, "execution_contract.constraints", frozenset(), _CONSTRAINT_KEYS)
    result: dict[str, Any] = {}
    for key in ("required_capabilities", "eligible_quota_classes"):
        if key in raw:
            items = _sequence(
                raw[key],
                f"execution_contract.constraints.{key}",
                max_items=MAX_CONSTRAINT_LIST_ITEMS,
            )
            result[key] = [
                _text(item, f"execution_contract.constraints.{key}[{index}]", max_chars=64)
                for index, item in enumerate(items)
            ]
    for key in ("effort", "cost_class"):
        if key in raw:
            result[key] = _text(raw[key], f"execution_contract.constraints.{key}", max_chars=64)
    if "base_sha" in raw:
        base_sha = raw["base_sha"]
        if not isinstance(base_sha, str) or SHA_RE.fullmatch(base_sha) is None:
            raise CeoIntentError(
                "execution_contract.constraints.base_sha must be a full 40-character "
                "lowercase Git SHA"
            )
        result["base_sha"] = base_sha
    return result


def _execution_contract(value: Any) -> dict[str, Any]:
    raw = _mapping(value, "execution_contract")
    _exact_keys(raw, "execution_contract", _CONTRACT_REQUIRED, _CONTRACT_OPTIONAL)
    result: dict[str, Any] = {"requested_authorities": _authorities(raw["requested_authorities"])}
    if "allowed_write_paths" in raw:
        result["allowed_write_paths"] = _write_paths(raw["allowed_write_paths"])
    if "validation_commands" in raw:
        result["validation_commands"] = _validation_commands(raw["validation_commands"])
    if "authority_level" in raw:
        result["authority_level"] = _text(
            raw["authority_level"], "execution_contract.authority_level",
            pattern=_AUTHORITY_LEVEL_RE, max_chars=8,
        )
    if "branch" in raw:
        result["branch"] = _text(
            raw["branch"], "execution_contract.branch", pattern=_BRANCH_RE,
            max_chars=MAX_BRANCH_CHARS,
        )
        if ".." in result["branch"]:
            raise CeoIntentError("execution_contract.branch must not traverse with '..'")
    if "worktree" in raw:
        worktree = _text(
            raw["worktree"], "execution_contract.worktree", max_chars=MAX_WORKTREE_CHARS
        )
        if not worktree.startswith("/") or ".." in worktree.split("/"):
            raise CeoIntentError(
                "execution_contract.worktree must be an absolute path without '..'"
            )
        result["worktree"] = worktree
    if "attempt_limit" in raw:
        result["attempt_limit"] = _integer(
            raw["attempt_limit"], "execution_contract.attempt_limit",
            minimum=1, maximum=MAX_ATTEMPT_LIMIT,
        )
    if "constraints" in raw:
        result["constraints"] = _constraints(raw["constraints"])
    return result


def validate_intent(payload: Any) -> dict[str, Any]:
    """Return the canonical form of one ``mastermind.ceo_intent.v1`` envelope.

    Pure: no I/O, no clock, no database, no authority load.  Raises
    :class:`CeoIntentError` with a precise message on anything unrecognized.
    """

    raw = _mapping(payload, "intent")
    _scan_forbidden(raw)
    _exact_keys(raw, "intent", _REQUIRED_KEYS, _OPTIONAL_KEYS)

    schema = _text(raw["schema"], "intent.schema", max_chars=128)
    if schema != INTENT_SCHEMA:
        raise CeoIntentError(
            f"intent.schema must be {INTENT_SCHEMA!r}; got {schema!r}"
        )
    intent: dict[str, Any] = {
        "schema": INTENT_SCHEMA,
        "intent_id": _text(raw["intent_id"], "intent.intent_id", pattern=INTENT_ID_RE, max_chars=64),
        "actor": _text(raw["actor"], "intent.actor", pattern=_ACTOR_RE, max_chars=64),
        "objective": _text(raw["objective"], "intent.objective", max_chars=MAX_OBJECTIVE_CHARS),
        "department": _text(
            raw["department"], "intent.department", pattern=_DEPARTMENT_RE, max_chars=64
        ),
        "priority": _integer(
            raw["priority"], "intent.priority", minimum=MIN_PRIORITY, maximum=MAX_PRIORITY
        ),
        "grounding": _grounding(raw["grounding"]),
        "execution_contract": _execution_contract(raw["execution_contract"]),
    }
    if "workstream" in raw:
        # A pointer into the Agent OS knowledge plane, recorded for provenance.
        # Nothing in this path opens, resolves, or writes that store.
        intent["workstream"] = _text(
            raw["workstream"], "intent.workstream", pattern=_WORKSTREAM_RE, max_chars=72
        )
    size = len(canonical_bytes(intent))
    if size > MAX_ENVELOPE_BYTES:
        raise CeoIntentError(
            f"intent is {size} canonical bytes, over the {MAX_ENVELOPE_BYTES}-byte "
            "envelope ceiling"
        )
    return intent


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------


def canonical_bytes(intent: Mapping[str, Any]) -> bytes:
    """Canonical UTF-8 encoding of an envelope — the identity and the wire size."""

    try:
        canonical = json.dumps(
            intent, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        return canonical.encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CeoIntentError(f"intent is not canonical JSON data: {exc}") from exc
    except UnicodeEncodeError as exc:
        # Belt-and-braces: ``_text`` already refuses unpaired surrogates field by
        # field, so reaching here means a caller passed an un-normalized mapping.
        raise CeoIntentError("intent is not encodable UTF-8 text") from exc


def intent_fingerprint(intent: Mapping[str, Any]) -> str:
    """sha256 over canonical JSON of the WHOLE normalized envelope.

    Nothing is excluded: the entire payload is the identity, so a changed
    objective, a changed authority, or a changed grounding SHA is a different
    intent even under a reused ``intent_id`` — which is exactly the conflict the
    retry path must refuse rather than silently accept.
    """

    return hashlib.sha256(canonical_bytes(intent)).hexdigest()


def command_id_for(intent_id: str) -> str:
    """Durable command id for one intent — the events UNIQUE index key."""

    return f"{COMMAND_ID_PREFIX}{intent_id}"


# ---------------------------------------------------------------------------
# receipts
# ---------------------------------------------------------------------------


def _receipt(
    job: Job,
    *,
    intent_id: str,
    fingerprint: str,
    grounding: Mapping[str, Any],
    duplicate: bool,
    created_at_ms: int,
) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "intent_id": intent_id,
        "fingerprint": fingerprint,
        "job_id": job.job_id,
        "status": job.status.value,
        "accepted": True,
        "duplicate": bool(duplicate),
        # ALWAYS False.  This field exists so a caller can never confuse
        # acceptance with execution: nothing on this path dispatches, and the
        # control service structurally refuses to dispatch a CEO-created job.
        "dispatched": False,
        "authority": {
            # Read off the DURABLE Job, never echoed back from the request.
            "requested": list(job.requested_authorities),
            "policy_sha256": job.authority_policy_hash,
            "authority_level": job.authority_level,
        },
        "grounding": dict(grounding),
        "created_at_ms": int(created_at_ms),
    }


def build_receipt(
    job: Job,
    *,
    intent: Mapping[str, Any],
    fingerprint: str,
    duplicate: bool,
    created_at_ms: int,
) -> dict[str, Any]:
    """Assemble the ``mastermind.ceo_intent_receipt.v1`` envelope."""

    return _receipt(
        job,
        intent_id=str(intent["intent_id"]),
        fingerprint=fingerprint,
        grounding=intent["grounding"],
        duplicate=duplicate,
        created_at_ms=created_at_ms,
    )


def _provenance(intent: Mapping[str, Any], fingerprint: str) -> dict[str, Any]:
    """The durable record of WHO asked, for WHAT, grounded on WHICH revisions."""

    value = {
        "schema": INTENT_SCHEMA,
        "intent_id": intent["intent_id"],
        "actor": intent["actor"],
        "fingerprint": fingerprint,
        "grounding": dict(intent["grounding"]),
    }
    if "workstream" in intent:
        value["workstream"] = intent["workstream"]
    return value


def _receipt_from_event(
    runtime: Any,
    event: Mapping[str, Any],
    *,
    intent_id: str,
    fingerprint: str | None,
) -> dict[str, Any]:
    """Reconcile an already-accepted intent into the receipt it first produced."""

    if event.get("event_type") != "JOB_CREATED":
        raise CeoIntentError(
            f"intent {intent_id!r} resolves to a {event.get('event_type')!r} event, "
            "not a job creation"
        )
    payload = event.get("payload") or {}
    provenance = payload.get("provenance") if isinstance(payload, Mapping) else None
    if not isinstance(provenance, Mapping):
        raise CeoIntentError(f"intent {intent_id!r} has no durable provenance record")
    # The command-id prefix is a namespace, not proof of origin.  Re-verify the
    # record before treating it as a CEO intent so a malformed or foreign event
    # under this prefix is a legible refusal, never a receipt for an objective
    # the CEO never sent.
    if provenance.get("schema") != INTENT_SCHEMA:
        raise CeoIntentError(
            f"intent {intent_id!r} resolves to a record whose provenance schema is "
            f"{provenance.get('schema')!r}, not {INTENT_SCHEMA!r}"
        )
    if provenance.get("intent_id") != intent_id:
        raise CeoIntentError(
            f"intent {intent_id!r} resolves to a record naming intent "
            f"{provenance.get('intent_id')!r}"
        )
    recorded = provenance.get("fingerprint")
    if not isinstance(recorded, str) or _FINGERPRINT_RE.fullmatch(recorded) is None:
        raise CeoIntentError(
            f"intent {intent_id!r} has no well-formed fingerprint in its durable record"
        )
    if fingerprint is not None and recorded != fingerprint:
        raise CeoIntentError(
            f"intent_id {intent_id!r} was already accepted with a different envelope: "
            f"recorded fingerprint {recorded} != submitted fingerprint {fingerprint}. "
            "Submit a new intent_id; an accepted intent is never rewritten."
        )
    job_id = event.get("job_id")
    job = runtime.jobs.get_job(job_id) if job_id else None
    if job is None:
        raise CeoIntentError(f"intent {intent_id!r} names job {job_id!r}, which does not exist")
    grounding = provenance.get("grounding")
    return _receipt(
        job,
        intent_id=intent_id,
        fingerprint=str(recorded),
        grounding=grounding if isinstance(grounding, Mapping) else {},
        duplicate=True,
        created_at_ms=int(event.get("created_at_ms") or 0),
    )


# ---------------------------------------------------------------------------
# the adapter
# ---------------------------------------------------------------------------


def _require_workspace(intent: Mapping[str, Any], workspace_root: Path | None) -> None:
    """Fence the caller-chosen worktree to the host's configured workspace root.

    Without this, ``worktree`` is any absolute path on the box: a ``WRITE_BRANCH``
    intent could be queued against the Macro checkout, ``$HOME`` (with
    ``.ssh/authorized_keys`` declared), ``/etc``, or this repository itself.  No
    write happens at submission — but the durable job carries that scope, and
    an operator ``run-once`` builds its launch spec from exactly those fields.

    Paths are compared RESOLVED, not as strings.  ``authorize()`` itself stores
    the resolved worktree, so ``/etc`` is durably recorded as ``/private/etc`` on
    Darwin: a raw-string prefix check would compare the wrong two things, and
    ``.resolve()`` is also what collapses ``..`` and follows a symlinked
    workspace out of its root.
    """

    worktree = intent["execution_contract"].get("worktree")
    if worktree is None:
        return
    if workspace_root is None:
        raise CeoIntentError(
            "execution_contract.worktree requires a configured workspace root; "
            "this submission path has none, so no worktree may be assigned"
        )
    resolved = Path(worktree).expanduser().resolve(strict=False)
    root = Path(workspace_root).expanduser().resolve(strict=False)
    if root not in resolved.parents:
        raise CeoIntentError(
            "execution_contract.worktree must resolve to a path under the "
            f"configured workspace root; {str(resolved)!r} does not"
        )


def submit_intent(
    runtime: Any, payload: Any, *, workspace_root: "Path | str | None" = None
) -> dict[str, Any]:
    """Validate one intent and turn it into exactly one durable QUEUED Job.

    Never dispatches, never starts a process, never touches a supervisor.  The
    three idempotency behaviours are: an identical retry reconciles to the same
    Job with ``duplicate: True``; a conflicting retry under the same
    ``intent_id`` is refused; a concurrent identical submission is settled by
    the events ``command_id`` UNIQUE index so exactly one Job survives.

    ``workspace_root`` is the reviewed host directory every assigned worktree
    must live under.  It is a caller-supplied fence, never read from the intent:
    when it is omitted, an intent carrying ``worktree`` is refused outright.
    """

    intent = validate_intent(payload)
    _require_workspace(intent, Path(workspace_root) if workspace_root else None)
    fingerprint = intent_fingerprint(intent)
    intent_id = intent["intent_id"]
    command_id = command_id_for(intent_id)

    existing = runtime.store.find_event_by_command_id(command_id)
    if existing is not None:
        return _receipt_from_event(
            runtime, existing, intent_id=intent_id, fingerprint=fingerprint
        )

    contract = intent["execution_contract"]
    try:
        job = runtime.jobs.create_job(
            intent["objective"],
            department=intent["department"],
            priority=intent["priority"],
            authority_level=contract.get("authority_level", "A0"),
            branch=contract.get("branch"),
            worktree=contract.get("worktree"),
            constraints=contract.get("constraints"),
            attempt_limit=contract.get("attempt_limit", 10),
            # The REQUEST's authorities travel unchanged; the policy inside
            # create_job is the adjudicator.  Substituting a constant here
            # would be exactly the bypass this bridge must not contain.
            requested_authorities=contract["requested_authorities"],
            allowed_write_paths=contract.get("allowed_write_paths"),
            validation_commands=contract.get("validation_commands"),
            command_id=command_id,
            provenance=_provenance(intent, fingerprint),
        )
    except StateConflict as exc:
        # ``RuntimeStore.transaction`` converts the UNIQUE-index rejection into
        # StateConflict, so a lost concurrency race and an authority denial
        # arrive as the same class.  The durable event decides which happened:
        # if the command id is now present, a sibling won and this caller reads
        # the winner's receipt; otherwise the refusal is real and is re-raised.
        settled = runtime.store.find_event_by_command_id(command_id)
        if settled is not None:
            return _receipt_from_event(
                runtime, settled, intent_id=intent_id, fingerprint=fingerprint
            )
        raise CeoIntentError(str(exc)) from exc

    created = runtime.store.find_event_by_command_id(command_id)
    return build_receipt(
        job,
        intent=intent,
        fingerprint=fingerprint,
        duplicate=False,
        created_at_ms=int((created or {}).get("created_at_ms") or 0),
    )


def resolve_intent(runtime: Any, intent_id: str) -> dict[str, Any]:
    """Rebuild the receipt for an accepted intent from durable state only.

    No new store, no cache, no status table — the ``JOB_CREATED`` event and the
    Job row are the whole record.
    """

    resolved = _text(intent_id, "intent_id", pattern=INTENT_ID_RE, max_chars=64)
    event = runtime.store.find_event_by_command_id(command_id_for(resolved))
    if event is None:
        raise CeoIntentError(f"no accepted CEO intent named {resolved!r}")
    receipt = _receipt_from_event(runtime, event, intent_id=resolved, fingerprint=None)
    # A read-back is not a second acceptance; ``duplicate`` describes submission.
    receipt["duplicate"] = False
    return receipt


__all__ = [
    "COMMAND_ID_PREFIX",
    "CeoIntentError",
    "FORBIDDEN_PROGRAMS",
    "INTENT_ID_RE",
    "INTENT_SCHEMA",
    "MAX_ENVELOPE_BYTES",
    "RECEIPT_SCHEMA",
    "SHA_RE",
    "build_receipt",
    "canonical_bytes",
    "command_id_for",
    "intent_fingerprint",
    "resolve_intent",
    "submit_intent",
    "validate_intent",
]
