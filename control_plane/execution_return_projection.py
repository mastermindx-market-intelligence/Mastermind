"""control_plane.execution_return_projection — the pure execution-return projector.

DONE_WHEN row 5 (T3_HANDOFF_V2 §0): when a T3-owned coding attempt settles,
ONE authoritative ``mastermind.execution_return/v1`` record projects the
sealed result, artifacts and GitHub evidence (branch / PR / checks / merge,
each possibly UNKNOWN) and binds it to the ORIGINAL requester — the Hermes
teammate conversation / project that asked for the work.

Design laws (mirrors :mod:`control_plane.executive_terminal_return` and
:mod:`control_plane.fabric_result_projection`):

* **Pure.**  No I/O, no clock, no store, no transport, no retry.  The caller
  supplies freshly read sealed attempt facts; this module only validates and
  reduces them into the closed wire record.
* **Delivery ≠ acceptance.**  ``acceptance`` is closed to ``not_accepted``
  in v1: this module NEVER projects acceptance, and an input that claims
  acceptance is recorded as a refused claim (``acceptance_claim_refused``)
  and still projects ``not_accepted``.  User acceptance is a separate act by
  its own future owner under its own schema revision.
* **Unknown is never green.**  GitHub evidence that was not observed stays
  ``null`` / ``unknown`` in the record; the derived ``stage`` only advances
  as far as evidence PROVES.  Checks with any unconcluded member can never
  yield ``checks_green``; an unobserved merge is ``unknown``, not merged.
* **The original binding is load-bearing.**  A record with no original
  requester (teammate / conversation / project) is refused, as is a fact set
  whose authenticated idempotency namespace does not join the namespace the
  original request was admitted under (Rev 5: idempotency identity is
  ``(authenticated namespace, key)`` — two namespaces are NEVER the same
  command).
* **One vocabulary owner.**  The closed vocabularies below (and the delivery
  receipt vocabulary for
  :mod:`integrations.session_bridge.hermes_native_return`) live HERE, in
  Python, once.  The TypeScript mirror
  (``app/mastermind_os/src/hermes-native/execution-return-contract.ts``)
  asserts equality against the committed fixture
  ``integrations/mmos/fixtures/execution_return_v1/vocabularies.json``, which
  this module generates.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

#: Wire schema strings for the record and its delivery receipt.
EXECUTION_RETURN_SCHEMA = "mastermind.execution_return/v1"
EXECUTION_RETURN_DELIVERY_SCHEMA = "mastermind.execution_return_delivery/v1"

#: Closed ``stage`` vocabulary — the strongest delivery stage the evidence
#: PROVES, never a claim beyond it:
#:   result_only       only the sealed result exists; no GitHub evidence;
#:   branch_pushed     a branch is observed, no PR evidence;
#:   pr_open           a PR is observed, checks not all concluded;
#:   checks_green      every observed check concluded success/skipped;
#:   checks_failed     at least one observed check concluded failure;
#:   merged            merge observed, no installation claim in scope;
#:   installed_unknown merge observed AND an installation effect is claimed
#:                     but unproven — installed-ness is UNKNOWN, never green.
EXECUTION_RETURN_STAGES = (
    "result_only",
    "branch_pushed",
    "pr_open",
    "checks_green",
    "checks_failed",
    "merged",
    "installed_unknown",
)

#: ``acceptance`` is closed to exactly ``not_accepted`` in v1.  There is no
#: lawful producer of ``accepted`` in this schema generation; a future
#: acceptance owner must mint its own revision rather than widening this one.
EXECUTION_RETURN_ACCEPTANCE_STATES = ("not_accepted",)

#: Per-check conclusions as read from GitHub evidence.  ``skipped`` does not
#: block green (GitHub semantics); ``unknown`` always blocks green.
CHECK_CONCLUSIONS = ("success", "failure", "skipped", "unknown")

#: Merge evidence states.  ``not_merged`` is an observed negative; ``unknown``
#: is an unobserved fact and never means merged.
MERGE_STATES = ("merged", "not_merged", "unknown")

#: Derived overall check state.  ``unknown`` covers both "checks not read"
#: and "checks read but not all concluded" — neither may claim green.
CHECKS_STATES = ("green", "failed", "unknown")

#: Whether an installed/deployed effect is claimed by the sealed result.
#: A claim is never proof: ``claimed_unproven`` keeps installed-ness UNKNOWN.
INSTALLATION_STATES = ("none_claimed", "claimed_unproven")

#: Delivery receipt states for the return path (consumed by
#: :mod:`integrations.session_bridge.hermes_native_return`).  ``unknown`` is
#: an ambiguous send — honest terminal marker, never auto-retried.
EXECUTION_RETURN_DELIVERY_STATES = ("delivered", "unknown", "refused")

#: Closed typed refusal codes for this module.
EXECUTION_RETURN_ERROR_CODES = (
    "INPUT_INVALID",
    "ORIGINAL_BINDING_MISSING",
    "SEAL_MISSING",
    "NAMESPACE_MISMATCH",
    "GITHUB_EVIDENCE_INVALID",
)

#: Receipt refusal codes are transport-side and preserved VERBATIM (never
#: re-cased): the hermes_native seam emits lowercase guard codes
#: (``binding_unavailable``) while native refusal reasons are uppercase
#: (``SESSION_BUSY``); both grammars are admitted.
REFUSAL_CODE_PATTERN = r"[A-Za-z][A-Za-z0-9_]{0,63}"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER_MAX = 256
_RESULT_TEXT_MAX = 8192
_ARTIFACT_REFS_MAX = 16
_ARTIFACT_REF_MAX = 512
_CHECKS_MAX = 64
_PR_URL_MAX = 512
_RECORD_MAX_BYTES = 15 * 1024  # fits the native send seam's 16 KiB text budget

_TOP_LEVEL_KEYS = frozenset({
    "schema", "return_id", "digest", "stage", "acceptance",
    "acceptance_claim_refused", "attempt", "result", "github",
    "original_requester",
})
_ATTEMPT_KEYS = frozenset({
    "attempt_id", "root_id", "idempotency_key", "authenticated_namespace",
    "t3_thread_id", "t3_run_id", "seal_digest",
})
_RESULT_KEYS = frozenset({"text", "artifact_refs"})
_GITHUB_KEYS = frozenset({
    "branch", "pr_number", "pr_url", "checks", "checks_state",
    "merge_state", "installation",
})
_REQUESTER_KEYS = frozenset({
    "teammate_id", "conversation_id", "project_id", "authenticated_namespace",
})


class ExecutionReturnProjectionError(ValueError):
    """A typed closed refusal; ``code`` names the violated law."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in EXECUTION_RETURN_ERROR_CODES:
            raise ValueError(f"unknown execution-return error code {code!r}")
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _refuse(code: str, detail: str = "") -> None:
    raise ExecutionReturnProjectionError(code, detail)


def _identifier(value: Any, *, field: str, code: str = "INPUT_INVALID") -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _IDENTIFIER_MAX
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        _refuse(code, f"{field} is not a bounded non-empty identifier")
    return value


def _nullable_identifier(value: Any, *, field: str, code: str = "INPUT_INVALID") -> str | None:
    if value is None:
        return None
    return _identifier(value, field=field, code=code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _digest_of(record: dict[str, Any]) -> str:
    """Deterministic digest over the record content, excluding the two
    derived identity fields (``digest`` and ``return_id``, which is
    ``execret-`` + the first 32 hex of the digest)."""

    material = {
        key: value for key, value in record.items()
        if key not in ("digest", "return_id")
    }
    return hashlib.sha256(_canonical_bytes(material)).hexdigest()


def _return_id(digest: str) -> str:
    return "execret-" + digest[:32]


def canonical_record_bytes(value: Any) -> bytes:
    """Canonical UTF-8 JSON bytes — the single canonicalization law shared by
    the record digest and the native delivery text.  The TypeScript mirror
    reproduces it byte-for-byte (parity is proven on the committed fixture)."""

    return _canonical_bytes(value)


# ---------------------------------------------------------------------------
# input reduction
# ---------------------------------------------------------------------------


def _require_block(facts: Any, name: str) -> dict[str, Any]:
    if not isinstance(facts, dict):
        _refuse("INPUT_INVALID", "facts must be a dict")
    block = facts.get(name)
    if not isinstance(block, dict):
        _refuse("INPUT_INVALID", f"{name} block is missing or not a dict")
    return block


def _original_requester(facts: dict[str, Any]) -> dict[str, Any]:
    """The ORIGINAL Hermes teammate/project binding the evidence must return
    to.  All three identity fields plus the admission namespace are
    load-bearing: any gap refuses the whole projection."""

    requester = facts.get("original_requester")
    if not isinstance(requester, dict):
        _refuse("ORIGINAL_BINDING_MISSING", "original requester binding is absent")
    for field in ("teammate_id", "conversation_id", "project_id",
                  "authenticated_namespace"):
        if requester.get(field) in (None, ""):
            _refuse(
                "ORIGINAL_BINDING_MISSING",
                f"original requester binding is missing {field}",
            )
    return {
        "teammate_id": _identifier(
            requester["teammate_id"], field="original_requester.teammate_id",
            code="ORIGINAL_BINDING_MISSING"),
        "conversation_id": _identifier(
            requester["conversation_id"], field="original_requester.conversation_id",
            code="ORIGINAL_BINDING_MISSING"),
        "project_id": _identifier(
            requester["project_id"], field="original_requester.project_id",
            code="ORIGINAL_BINDING_MISSING"),
        "authenticated_namespace": _identifier(
            requester["authenticated_namespace"],
            field="original_requester.authenticated_namespace",
            code="ORIGINAL_BINDING_MISSING"),
    }


def _attempt(facts: dict[str, Any]) -> dict[str, Any]:
    """Sealed attempt facts + the authenticated idempotency identity."""

    attempt = _require_block(facts, "attempt")
    reduced = {
        "attempt_id": _identifier(attempt.get("attempt_id"), field="attempt.attempt_id"),
        "root_id": _identifier(attempt.get("root_id"), field="attempt.root_id"),
        "idempotency_key": _identifier(
            attempt.get("idempotency_key"), field="attempt.idempotency_key"),
        "authenticated_namespace": _identifier(
            attempt.get("authenticated_namespace"),
            field="attempt.authenticated_namespace"),
        "t3_thread_id": _nullable_identifier(
            attempt.get("t3_thread_id"), field="attempt.t3_thread_id"),
        "t3_run_id": _nullable_identifier(
            attempt.get("t3_run_id"), field="attempt.t3_run_id"),
    }
    seal = attempt.get("seal")
    if not isinstance(seal, dict) or type(seal.get("digest")) is not str \
            or _SHA256_RE.fullmatch(seal["digest"]) is None:
        _refuse(
            "SEAL_MISSING",
            "attempt carries no valid sealed terminal seal "
            "({schema: mastermind terminal seal, digest: 64-hex})",
        )
    reduced["seal_digest"] = seal["digest"]
    return reduced


def _result_block(facts: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
    """(reduced result block, acceptance claim refused?, installation claimed?)"""

    block = _require_block(facts, "result")
    text = block.get("text")
    if text is not None and (
            type(text) is not str or not text
            or len(text) > _RESULT_TEXT_MAX
            or any(ord(char) == 0 for char in text)):
        _refuse("INPUT_INVALID", "result.text must be null or bounded non-empty text")
    refs = block.get("artifact_refs", [])
    if refs is None:
        refs = []
    if type(refs) is not list or len(refs) > _ARTIFACT_REFS_MAX:
        _refuse("INPUT_INVALID", "result.artifact_refs must be a bounded list")
    seen: list[str] = []
    for ref in refs:
        if (type(ref) is not str or not ref or len(ref) > _ARTIFACT_REF_MAX
                or any(ord(char) < 32 or ord(char) == 127 for char in ref)
                or ref in seen):
            _refuse("INPUT_INVALID", "result.artifact_refs contains an invalid reference")
        seen.append(ref)
    # Acceptance forgery law: any input acceptance claim other than
    # "not_accepted" is refused-as-a-claim and never propagates.
    claimed = block.get("acceptance")
    acceptance_claim_refused = claimed is not None and claimed != "not_accepted"
    installation_claimed = block.get("installation_claimed") is True
    return (
        {"text": text, "artifact_refs": seen},
        acceptance_claim_refused,
        installation_claimed,
    )


def _github_block(facts: dict[str, Any], *, installation_claimed: bool) -> dict[str, Any]:
    """GitHub evidence, each field possibly unobserved; the derived stage
    inputs never turn an unobserved fact into a positive one."""

    block = _require_block(facts, "github")
    branch = _nullable_identifier(block.get("branch"), field="github.branch",
                                  code="GITHUB_EVIDENCE_INVALID")
    pr_number = block.get("pr_number")
    if pr_number is not None and (type(pr_number) is not int or pr_number < 1):
        _refuse("GITHUB_EVIDENCE_INVALID", "github.pr_number must be null or a positive int")
    pr_url = block.get("pr_url")
    if pr_url is not None and (
            type(pr_url) is not str or not pr_url.startswith("https://")
            or len(pr_url) > _PR_URL_MAX
            or any(ord(char) < 32 or ord(char) == 127 for char in pr_url)):
        _refuse("GITHUB_EVIDENCE_INVALID", "github.pr_url must be null or an https URL")
    checks = block.get("checks")
    if checks is not None:
        if type(checks) is not list or len(checks) > _CHECKS_MAX:
            _refuse("GITHUB_EVIDENCE_INVALID", "github.checks must be null or a bounded list")
        rows: list[dict[str, str]] = []
        names: list[str] = []
        for row in checks:
            if not isinstance(row, dict) or set(row) != {"name", "conclusion"}:
                _refuse("GITHUB_EVIDENCE_INVALID", "github.checks rows are {name, conclusion}")
            name = row["name"]
            if (type(name) is not str or not name or len(name) > 256
                    or any(ord(char) < 32 or ord(char) == 127 for char in name)
                    or name in names):
                _refuse("GITHUB_EVIDENCE_INVALID", "github.checks name is invalid or duplicated")
            if row["conclusion"] not in CHECK_CONCLUSIONS:
                _refuse("GITHUB_EVIDENCE_INVALID", "github.checks conclusion is outside the closed vocabulary")
            names.append(name)
            rows.append({"name": name, "conclusion": row["conclusion"]})
        checks = rows
    merge_state = block.get("merge_state")
    if merge_state is None:
        merge_state = "unknown"
    if merge_state not in MERGE_STATES:
        _refuse("GITHUB_EVIDENCE_INVALID", "github.merge_state is outside the closed vocabulary")

    conclusions = [row["conclusion"] for row in checks] if checks else []
    if conclusions and "failure" in conclusions:
        checks_state = "failed"
    elif conclusions and all(c in ("success", "skipped") for c in conclusions):
        checks_state = "green"
    else:
        checks_state = "unknown"
    installation = "claimed_unproven" if installation_claimed else "none_claimed"
    return {
        "branch": branch,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "checks": checks,
        "checks_state": checks_state,
        "merge_state": merge_state,
        "installation": installation,
    }


def _derive_stage(github: dict[str, Any]) -> str:
    """The strongest stage the reduced evidence PROVES.

    ``checks_green`` requires every observed check concluded success/skipped;
    any unconcluded check keeps the stage at ``pr_open`` (never green).
    ``merged`` requires observed merge; an installation claim on top of a
    proven merge is reported as ``installed_unknown`` — installed-ness is
    UNKNOWN, never green.
    """

    if github["merge_state"] == "merged":
        return "installed_unknown" if github["installation"] == "claimed_unproven" else "merged"
    if github["checks_state"] == "failed":
        return "checks_failed"
    if github["checks_state"] == "green":
        return "checks_green"
    if github["pr_number"] is not None or github["pr_url"] is not None:
        return "pr_open"
    if github["branch"] is not None:
        return "branch_pushed"
    return "result_only"


# ---------------------------------------------------------------------------
# public entry points
# ---------------------------------------------------------------------------


def project_execution_return(facts: Any) -> dict[str, Any]:
    """Project one sealed attempt fact set into ``mastermind.execution_return/v1``.

    Pure and closed.  Refuses with a typed code on: a missing original
    requester binding (``ORIGINAL_BINDING_MISSING``), a missing or malformed
    attempt seal (``SEAL_MISSING``), an authenticated-namespace mismatch
    between the attempt and the original request (``NAMESPACE_MISMATCH``),
    malformed input shapes (``INPUT_INVALID``) and malformed GitHub evidence
    (``GITHUB_EVIDENCE_INVALID``).
    """

    if not isinstance(facts, dict):
        _refuse("INPUT_INVALID", "facts must be a dict")
    requester = _original_requester(facts)
    attempt = _attempt(facts)
    if attempt["authenticated_namespace"] != requester["authenticated_namespace"]:
        _refuse(
            "NAMESPACE_MISMATCH",
            "attempt namespace does not join the original request namespace "
            "(Rev 5: (namespace, key) is the idempotency identity)",
        )
    result, acceptance_claim_refused, installation_claimed = _result_block(facts)
    github = _github_block(facts, installation_claimed=installation_claimed)
    record = {
        "schema": EXECUTION_RETURN_SCHEMA,
        "stage": _derive_stage(github),
        "acceptance": "not_accepted",
        "acceptance_claim_refused": acceptance_claim_refused,
        "attempt": attempt,
        "result": result,
        "github": github,
        "original_requester": requester,
    }
    digest = _digest_of(record)
    record["digest"] = digest
    record["return_id"] = _return_id(digest)
    if len(_canonical_bytes(record)) > _RECORD_MAX_BYTES:
        _refuse("INPUT_INVALID", "projected record exceeds the delivery text budget")
    return record


def validate_execution_return(value: Any) -> dict[str, Any]:
    """Fail-closed validation of one ``mastermind.execution_return/v1`` record.

    Checks the exact closed shape, every vocabulary, the deterministic digest
    and return id, and the internal honesty invariants: the stage must equal
    the stage the record's own GitHub evidence proves, and acceptance must be
    ``not_accepted``.  Returns an independent deep copy.
    """

    if not isinstance(value, dict) or set(value) != _TOP_LEVEL_KEYS:
        _refuse("INPUT_INVALID", "record is not the closed top-level shape")
    if value["schema"] != EXECUTION_RETURN_SCHEMA:
        _refuse("INPUT_INVALID", "record schema is not mastermind.execution_return/v1")
    if value["stage"] not in EXECUTION_RETURN_STAGES:
        _refuse("INPUT_INVALID", "stage is outside the closed vocabulary")
    if value["acceptance"] != "not_accepted":
        _refuse("INPUT_INVALID", "acceptance is closed to not_accepted in v1")
    if type(value["acceptance_claim_refused"]) is not bool:
        _refuse("INPUT_INVALID", "acceptance_claim_refused must be a bool")

    attempt = value["attempt"]
    if not isinstance(attempt, dict) or set(attempt) != _ATTEMPT_KEYS:
        _refuse("INPUT_INVALID", "attempt block is not the closed shape")
    _identifier(attempt["attempt_id"], field="attempt.attempt_id")
    _identifier(attempt["root_id"], field="attempt.root_id")
    _identifier(attempt["idempotency_key"], field="attempt.idempotency_key")
    _identifier(attempt["authenticated_namespace"], field="attempt.authenticated_namespace")
    _nullable_identifier(attempt["t3_thread_id"], field="attempt.t3_thread_id")
    _nullable_identifier(attempt["t3_run_id"], field="attempt.t3_run_id")
    if type(attempt["seal_digest"]) is not str or _SHA256_RE.fullmatch(attempt["seal_digest"]) is None:
        _refuse("INPUT_INVALID", "attempt.seal_digest is not 64-hex")

    result = value["result"]
    if not isinstance(result, dict) or set(result) != _RESULT_KEYS:
        _refuse("INPUT_INVALID", "result block is not the closed shape")
    if result["text"] is not None and (type(result["text"]) is not str or not result["text"]):
        _refuse("INPUT_INVALID", "result.text must be null or non-empty text")
    if type(result["artifact_refs"]) is not list:
        _refuse("INPUT_INVALID", "result.artifact_refs must be a list")
    for ref in result["artifact_refs"]:
        if type(ref) is not str or not ref:
            _refuse("INPUT_INVALID", "result.artifact_refs contains an invalid reference")

    github = value["github"]
    if not isinstance(github, dict) or set(github) != _GITHUB_KEYS:
        _refuse("INPUT_INVALID", "github block is not the closed shape")
    if github["branch"] is not None and (
            type(github["branch"]) is not str or not github["branch"]):
        _refuse("INPUT_INVALID", "github.branch must be null or non-empty text")
    if github["pr_number"] is not None and (type(github["pr_number"]) is not int
                                            or github["pr_number"] < 1):
        _refuse("INPUT_INVALID", "github.pr_number must be null or a positive int")
    if github["pr_url"] is not None and type(github["pr_url"]) is not str:
        _refuse("INPUT_INVALID", "github.pr_url must be null or text")
    if github["checks"] is not None:
        if type(github["checks"]) is not list:
            _refuse("INPUT_INVALID", "github.checks must be null or a list")
        for row in github["checks"]:
            if (not isinstance(row, dict) or set(row) != {"name", "conclusion"}
                    or type(row["name"]) is not str or not row["name"]
                    or row["conclusion"] not in CHECK_CONCLUSIONS):
                _refuse("INPUT_INVALID", "github.checks rows are not the closed shape")
    if github["checks_state"] not in CHECKS_STATES:
        _refuse("INPUT_INVALID", "github.checks_state is outside the closed vocabulary")
    if github["merge_state"] not in MERGE_STATES:
        _refuse("INPUT_INVALID", "github.merge_state is outside the closed vocabulary")
    if github["installation"] not in INSTALLATION_STATES:
        _refuse("INPUT_INVALID", "github.installation is outside the closed vocabulary")

    requester = value["original_requester"]
    if not isinstance(requester, dict) or set(requester) != _REQUESTER_KEYS:
        _refuse("INPUT_INVALID", "original_requester block is not the closed shape")
    for field in ("teammate_id", "conversation_id", "project_id", "authenticated_namespace"):
        if type(requester[field]) is not str or not requester[field]:
            _refuse("INPUT_INVALID", f"original_requester.{field} must be non-empty text")

    if type(value["digest"]) is not str or _SHA256_RE.fullmatch(value["digest"]) is None:
        _refuse("INPUT_INVALID", "digest is not 64-hex")
    if type(value["return_id"]) is not str or value["return_id"] != _return_id(value["digest"]):
        _refuse("INPUT_INVALID", "return_id does not derive from the digest")
    if _digest_of(value) != value["digest"]:
        _refuse("INPUT_INVALID", "digest does not match the record content")
    if _derive_stage(github) != value["stage"]:
        _refuse("INPUT_INVALID", "stage exceeds what the record's own evidence proves")
    try:
        encoded = _canonical_bytes(value)
    except (ValueError, TypeError) as exc:
        _refuse("INPUT_INVALID", f"record is not canonical JSON: {exc}")
    if len(encoded) > _RECORD_MAX_BYTES:
        _refuse("INPUT_INVALID", "record exceeds the delivery text budget")
    return json.loads(encoded)
