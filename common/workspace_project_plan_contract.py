"""Closed read-contract for one authored Agent OS workstream plan projection.

This module is the contract half of the ``project_plan`` read operation: schema
identifiers, the strict selection (``WS:`` work reference) and source-identity
validators, and the closed unavailable-body shape.  It is PURE: no I/O, no
clock, no network, no parser, no transport, no cache.  A selector or a
content digest is a *source fact* used to address and pin bytes -- it is never
an authorization grant.  The authenticated reader, the sealed Agent OS parser
(``scripts/agentos.py``) and the Workspace transport are composed by the
integrating parent, not here.

Producer facts this contract is bound to (inspected ``scripts/agentos.py``,
repo ``mastermindx-market-intelligence/macro`` at 9dc1290e, blob
5aae3c5e97dcdcf85d0745062fe9424f1ed7c0c7):

* ``parse_record(path) -> (frontmatter dict, body str)``.  The raw body can
  carry history and secrets, so it is NEVER projected; projection is by
  explicit frontmatter field only.
* Canonical Store key ``WS/<KEY>`` at the exact path
  ``agentos/workstreams/WS-<KEY>.md``; ``KEY_RE = ^[A-Z0-9]+(?:-[A-Z0-9]+)*$``
  and the ``WS:`` selector convention (``startswith("WS:")`` plus ``KEY_RE``
  on the remainder).
* Authored status vocabularies are owned by the producer, not re-enumerated
  here on purpose.  The commissioned summary listed workstream statuses
  ``{proposed, active, blocked, awaiting_ci, awaiting_review, done,
  dropped}``, while both inspected producer pins carry ``{proposed, active,
  blocked, awaiting_ci, awaiting_review, done, parked, killed}`` for
  workstreams and ``{todo, in_progress, awaiting_ci, done, dropped}`` for
  waves.  A private projector enum would silently reject records the
  producer accepts (e.g. ``parked``), so this contract bounds lengths and
  lets the projector pass authored status values through verbatim.
* No generic plan-adoption or plan-version field exists in the canonical
  record.  Anything claiming otherwise is unauthored metadata; the closed
  bodies below therefore keep adoption/version availability explicitly
  UNAVAILABLE.  Authored ``done`` status is record state, never runtime
  acceptance, Git publication or approval.

Malformed *caller* input (a selector or source identity that is not exactly
the closed shape) raises ``ValueError`` carrying one closed constant -- never
a fragment of the offending value, which could leak it into a response.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

BODY_SCHEMA = "mastermind.workspace_project_plan.v1"
BODY_SCHEMA_V2 = "mastermind.workspace_project_plan.v2"
BODY_SCHEMAS = (BODY_SCHEMA, BODY_SCHEMA_V2)
FRAME_SCHEMA = "mastermind.workspace_project_plan_read.v1"
OPERATION = "project_plan"
MAX_RESPONSE_BYTES = 131072

# Exact source repository this operation may address.  A source identity
# naming anything else is malformed for this operation, not merely "elsewhere".
CANONICAL_REPOSITORY = "mastermindx-market-intelligence/macro"

AVAILABILITY_AVAILABLE = "AVAILABLE"
AVAILABILITY_UNAVAILABLE = "UNAVAILABLE"
AVAILABILITIES = (AVAILABILITY_AVAILABLE, AVAILABILITY_UNAVAILABLE)

# Closed reason vocabulary.  SOURCE_CHANGED is emitted by the parent when a
# re-digest of the fetched bytes disagrees with the pinned content_sha256; the
# pure projector cannot observe bytes and so never emits it itself.
REASON_SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
REASON_SOURCE_CHANGED = "SOURCE_CHANGED"
REASON_RECORD_NOT_FOUND = "RECORD_NOT_FOUND"
REASON_RECORD_INVALID = "RECORD_INVALID"
REASON_CONTENT_OVER_BUDGET = "CONTENT_OVER_BUDGET"
REASON_CODES = (
    REASON_SOURCE_UNAVAILABLE,
    REASON_SOURCE_CHANGED,
    REASON_RECORD_NOT_FOUND,
    REASON_RECORD_INVALID,
    REASON_CONTENT_OVER_BUDGET,
)

WORK_REF_PREFIX = "WS:"
# Mirrors the producer's KEY_RE (see module docstring).
WORK_REF_PATTERN = r"[A-Z0-9]+(?:-[A-Z0-9]+)*"
WORK_REF_RE = re.compile(rf"^{WORK_REF_PATTERN}$")
MIN_WORK_REF_KEY_CHARS = 2
MAX_WORK_REF_KEY_CHARS = 64

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
CONTENT_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SOURCE_REPOSITORY = "repository"
SOURCE_COMMIT = "commit"
SOURCE_PATH = "path"
SOURCE_CONTENT_SHA256 = "content_sha256"
SOURCE_KEYS = (
    SOURCE_REPOSITORY,
    SOURCE_COMMIT,
    SOURCE_PATH,
    SOURCE_CONTENT_SHA256,
)

# Closed ValueError constants.  Deliberately value-free: echoing the rejected
# input into an exception message would leak it into caller-owned logs.
INVALID_WORK_REF_MESSAGE = "INVALID_WORK_REF_SELECTOR"
INVALID_SOURCE_MESSAGE = "INVALID_SOURCE_IDENTITY"
INVALID_REASON_MESSAGE = "INVALID_UNAVAILABLE_REASON"

BODY_KEYS = (
    "schema",
    "selection",
    "availability",
    "source",
    "plan",
    "reason_codes",
)


def canonical_record_path(key: str) -> str:
    """Exact canonical Store path for one workstream record."""
    return f"agentos/workstreams/WS-{key}.md"


def work_ref_key(work_ref: object) -> str:
    """Validate one ``WS:<KEY>`` selector string and return its key part.

    Raises ``ValueError`` with the closed constant for anything that is not a
    strict ``WS:`` UPPER-KEBAB reference of 2..64 key characters (single
    dashes between groups, no leading/trailing/double dash, no path or Job
    selector shape).
    """
    if not isinstance(work_ref, str) or not work_ref.startswith(WORK_REF_PREFIX):
        raise ValueError(INVALID_WORK_REF_MESSAGE)
    key = work_ref[len(WORK_REF_PREFIX):]
    if not (MIN_WORK_REF_KEY_CHARS <= len(key) <= MAX_WORK_REF_KEY_CHARS):
        raise ValueError(INVALID_WORK_REF_MESSAGE)
    if WORK_REF_RE.fullmatch(key) is None:
        raise ValueError(INVALID_WORK_REF_MESSAGE)
    return key


def is_valid_work_ref(work_ref: object) -> bool:
    """Quiet predicate form of :func:`work_ref_key`."""
    try:
        work_ref_key(work_ref)
    except ValueError:
        return False
    return True


def validate_selection(value: object) -> dict:
    """Validate a selection and return a detached ``{'work_ref': ...}`` dict.

    The mapping must carry EXACTLY the ``work_ref`` key: no caller-supplied
    ``path``, ``commit``, ``job`` or any other selector companion is accepted,
    because addressing is fixed by the canonical Store layout and any second
    key would claim an authority this read contract does not have.
    """
    if not isinstance(value, Mapping) or set(value.keys()) != {"work_ref"}:
        raise ValueError(INVALID_WORK_REF_MESSAGE)
    work_ref_key(value["work_ref"])
    # Echo the validated selector verbatim: every closed body carries the same
    # ``WS:<KEY>`` string the caller selected, never a re-derived key.
    return {"work_ref": value["work_ref"]}


def validate_source(value: object, work_ref: object) -> dict:
    """Validate one source identity against the selected work reference.

    Requires EXACTLY ``repository``, ``commit``, ``path`` and
    ``content_sha256``: the canonical repository, a 40-char lowercase hex
    commit, the exact canonical Store path of the selected record, and a
    64-char lowercase hex content digest.  These are addressing and pinning
    facts, never authorization.  Returns a detached dict; raises
    ``ValueError`` with the closed constant on any mismatch.
    """
    key = work_ref_key(work_ref)
    if not isinstance(value, Mapping) or set(value.keys()) != set(SOURCE_KEYS):
        raise ValueError(INVALID_SOURCE_MESSAGE)
    repository = value[SOURCE_REPOSITORY]
    commit = value[SOURCE_COMMIT]
    path = value[SOURCE_PATH]
    content_sha256 = value[SOURCE_CONTENT_SHA256]
    if repository != CANONICAL_REPOSITORY:
        raise ValueError(INVALID_SOURCE_MESSAGE)
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        raise ValueError(INVALID_SOURCE_MESSAGE)
    if not isinstance(path, str) or path != canonical_record_path(key):
        raise ValueError(INVALID_SOURCE_MESSAGE)
    if not isinstance(content_sha256, str) or CONTENT_SHA256_RE.fullmatch(content_sha256) is None:
        raise ValueError(INVALID_SOURCE_MESSAGE)
    return {
        SOURCE_REPOSITORY: repository,
        SOURCE_COMMIT: commit,
        SOURCE_PATH: path,
        SOURCE_CONTENT_SHA256: content_sha256,
    }


def unavailable(work_ref: object, reason: str) -> dict:
    """Build the closed unavailable body for one reason code.

    Fixed EXACT keys and value-free content: no error text, no raw body, no
    partial plan.  Raises ``ValueError`` with a closed constant for a
    malformed selector or a reason outside the closed enum.
    """
    work_ref_key(work_ref)
    if reason not in REASON_CODES:
        raise ValueError(INVALID_REASON_MESSAGE)
    return {
        "schema": BODY_SCHEMA,
        "selection": {"work_ref": work_ref},
        "availability": AVAILABILITY_UNAVAILABLE,
        "source": None,
        "plan": None,
        "reason_codes": [reason],
    }


__all__ = [
    "AVAILABILITIES",
    "BODY_KEYS",
    "AVAILABILITY_AVAILABLE",
    "AVAILABILITY_UNAVAILABLE",
    "BODY_SCHEMA",
    "CANONICAL_REPOSITORY",
    "COMMIT_RE",
    "CONTENT_SHA256_RE",
    "FRAME_SCHEMA",
    "INVALID_REASON_MESSAGE",
    "INVALID_SOURCE_MESSAGE",
    "INVALID_WORK_REF_MESSAGE",
    "MAX_RESPONSE_BYTES",
    "MAX_WORK_REF_KEY_CHARS",
    "MIN_WORK_REF_KEY_CHARS",
    "OPERATION",
    "REASON_CODES",
    "REASON_CONTENT_OVER_BUDGET",
    "REASON_RECORD_INVALID",
    "REASON_RECORD_NOT_FOUND",
    "REASON_SOURCE_CHANGED",
    "REASON_SOURCE_UNAVAILABLE",
    "SOURCE_COMMIT",
    "SOURCE_CONTENT_SHA256",
    "SOURCE_KEYS",
    "SOURCE_PATH",
    "SOURCE_REPOSITORY",
    "WORK_REF_PATTERN",
    "WORK_REF_PREFIX",
    "WORK_REF_RE",
    "canonical_record_path",
    "is_valid_work_ref",
    "unavailable",
    "validate_selection",
    "validate_source",
    "work_ref_key",
]


def validate_frame(value):
    """Reuse the incumbent Workspace READ principal contract, without a Job."""
    from common import executive_workspace_contract as workspace
    if (type(value) is not dict
            or set(value) != {"schema", "operation", "selection", "principal"}
            or value["schema"] != FRAME_SCHEMA or value["operation"] != OPERATION):
        raise ValueError("invalid_input")
    selected = validate_selection(value["selection"])
    workspace.validate_frame({"schema": workspace.FRAME_SCHEMA,
        "operation": "programs", "selection": None, "principal": value["principal"]})
    if len(workspace.canonical(value)) + 1 > workspace.MAX_REQUEST_BYTES:
        raise ValueError("invalid_input")
    return {"schema": FRAME_SCHEMA, "operation": OPERATION,
        "selection": selected, "principal": dict(value["principal"], scopes=list(value["principal"]["scopes"]))}


def validate_body(value):
    """Validate the closed owner projection before any public transport publishes it."""
    if type(value) is dict and value.get("schema") == BODY_SCHEMA_V2:
        from common.project_plan_continuity_contract import validate_body_v2
        return validate_body_v2(value)
    from datetime import datetime
    from common.executive_workspace_contract import bounded_canonical
    from control_plane.workspace_project_plan import project_workstream_plan
    if type(value) is not dict or set(value) != set(BODY_KEYS) or value["schema"] != BODY_SCHEMA:
        raise ValueError("invalid_project_plan")
    selected = validate_selection(value["selection"])
    work_ref = selected["work_ref"]
    if value["availability"] == AVAILABILITY_UNAVAILABLE:
        reasons = value["reason_codes"]
        if (type(reasons) is not list or len(reasons) != 1 or reasons[0] not in REASON_CODES
                or value != unavailable(work_ref, reasons[0])):
            raise ValueError("invalid_project_plan")
    elif value["availability"] == AVAILABILITY_AVAILABLE:
        source = validate_source(value["source"], work_ref)
        plan = value["plan"]
        if (type(plan) is not dict
                or set(plan) != {"title", "objective", "status", "owner", "next_action", "waves", "adoption", "version_history"}
                or type(plan["waves"]) is not list or value["reason_codes"] != []):
            raise ValueError("invalid_project_plan")
        waves = []
        for wave in plan["waves"]:
            if type(wave) is not dict or set(wave) != {"id", "title", "status", "depends_on", "next_action", "prs"}:
                raise ValueError("invalid_project_plan")
            if (type(wave["prs"]) is not list
                    or any(type(pr) is not int or not 0 < pr <= 9007199254740991 for pr in wave["prs"])):
                raise ValueError("invalid_project_plan")
            waves.append({key: item for key, item in wave.items() if key != "prs"} | {"pr": wave["prs"]})
        reconstructed = project_workstream_plan({"key": work_ref_key(work_ref),
            **{key: plan[key] for key in ("title", "objective", "status", "owner", "next_action")},
            "waves": waves}, work_ref=work_ref, source=source)
        if reconstructed["availability"] != AVAILABILITY_AVAILABLE:
            raise ValueError("invalid_project_plan")
        history = plan["version_history"]
        if type(history) is not dict:
            raise ValueError("invalid_project_plan")
        if history.get("state") == "UNAVAILABLE":
            if set(history) != {"state", "reason"} or history["reason"] not in {"NOT_SUPPLIED_BY_OWNER", "SOURCE_UNAVAILABLE"}:
                raise ValueError("invalid_project_plan")
        elif history.get("state") == "AVAILABLE":
            if (set(history) != {"state", "kind", "revisions"}
                    or history["kind"] != "GIT_RECORD_REVISIONS"
                    or type(history["revisions"]) is not list or not 1 <= len(history["revisions"]) <= 8):
                raise ValueError("invalid_project_plan")
            seen = set()
            for revision in history["revisions"]:
                if (type(revision) is not dict or set(revision) != {"commit", "committed_at", "content_sha256"}
                        or type(revision["commit"]) is not str or COMMIT_RE.fullmatch(revision["commit"]) is None
                        or revision["commit"] in seen
                        or type(revision["content_sha256"]) is not str or CONTENT_SHA256_RE.fullmatch(revision["content_sha256"]) is None
                        or type(revision["committed_at"]) is not str or len(revision["committed_at"]) > 40):
                    raise ValueError("invalid_project_plan")
                try:
                    stamp = datetime.fromisoformat(revision["committed_at"].replace("Z", "+00:00"))
                    if stamp.utcoffset() is None:
                        raise ValueError("invalid_project_plan")
                except (ValueError, OverflowError):
                    raise ValueError("invalid_project_plan") from None
                seen.add(revision["commit"])
            if history["revisions"][0]["content_sha256"] != source["content_sha256"]:
                raise ValueError("invalid_project_plan")
        else:
            raise ValueError("invalid_project_plan")
        reconstructed["plan"]["version_history"] = history
        if reconstructed != value:
            raise ValueError("invalid_project_plan")
    else:
        raise ValueError("invalid_project_plan")
    # The socket envelope, including its line delimiter, shares the public cap.
    bounded_canonical({"ok": True, "result": value}, limit=MAX_RESPONSE_BYTES - 1)
    import copy
    return copy.deepcopy(value)
