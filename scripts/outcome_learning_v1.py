#!/usr/bin/env python3
"""Outcome Learning V1 (OL-V1) — one sealed prospective episode, end to end.

Subcommands mirror the episode's sequence exactly:

    compose      -> compose + evaluate one Chairman-cognition source bundle (read-only)
    seal         -> seal the decision-expectation receipt + canary request
    preflight    -> external, non-self-referential preflight receipt for the effect owner
    canary       -> apply the two-call GitHub PR-title canary, or stop EFFECT_UNKNOWN
    outcome      -> assemble + validate the OLV1_OUTCOME artifact from the journal
    evaluate     -> deterministic DESCRIPTIVE_ONLY evaluation
    self-model   -> n=1 non-promoting self-model
    project      -> candidate-only Agent OS projection
    proof        -> render the production-proof markdown from the six JSON artifacts

Every GitHub call goes through an injectable :class:`GhTransport`; every git/subprocess
call goes through an injectable :class:`Runner`. The defaults (`GhCliTransport`,
`SubprocessRunner`) shell out to ``gh``/``git``/``python3`` — this module is the only
place in the OL-V1 vertical allowed to perform I/O. ``control_plane.outcome_learning_*``
stay pure; this script is the impure shell around them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.outcome_learning_contracts import (  # noqa: E402
    CANARY_TOKEN,
    OutcomeLearningContractError,
    build_canary_request,
    build_expectation,
    build_outcome,
    canonical_digest,
    scan_public_safe_text,
    validate_agentos_projection,
    validate_canary_request,
    validate_evaluation,
    validate_expectation,
    validate_outcome,
    validate_preflight,
    validate_self_model,
)
from control_plane.outcome_learning_evaluator import (  # noqa: E402
    build_agentos_projection,
    build_self_model,
    evaluate_episode,
)
from control_plane.chairman_cognition import ChairmanCognitionError  # noqa: E402
from control_plane.chairman_cognition_sources import (  # noqa: E402
    ChairmanCognitionSourceError,
    evaluate_bundle,
)
from scripts.agent_eval.privacy import assert_public_safe_evidence  # noqa: E402
from scripts.agent_eval.errors import ContractError  # noqa: E402

_ENVELOPE_SCHEMA = "mastermind.chairman_delegation_envelope.v1"
_SOURCE_BUNDLE_SCHEMA = "mastermind.chairman_cognition_source_bundle.v1"
_STRATEGIC_SOURCE_REF = "STRATEGIC_STATE:config/strategic_state.yml"
_AGENT_OS_SOURCE_REF = "AGENT_OS:ceo_brief"
_CHAIRMAN_REF = "CHAIRMAN_DIRECTIVE:completion-drive-2026-09-02"
_OPT_CANARY = "OPT-OLV1-PR-TITLE-CANARY"
_OPT_HOLD = "OPT-OLV1-PORTFOLIO-HOLD"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


class OutcomeLearningCliError(RuntimeError):
    """A CLI-level failure: bad input, refused write location, transport failure."""


# --------------------------------------------------------------------------- transports


@dataclass(frozen=True)
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(
        self, args: Sequence[str], *, cwd: str | None = None, input: str | None = None
    ) -> RunResult: ...


class SubprocessRunner:
    """Default runner: real subprocess execution. Never used by the test suite."""

    def run(
        self, args: Sequence[str], *, cwd: str | None = None, input: str | None = None
    ) -> RunResult:
        import subprocess

        proc = subprocess.run(
            list(args), cwd=cwd, input=input, capture_output=True, text=True, check=False
        )
        return RunResult(proc.returncode, proc.stdout, proc.stderr)


class GhTransport(Protocol):
    def get(self, endpoint: str) -> tuple[int | str, Any]: ...

    def patch(self, endpoint: str, payload: Mapping[str, Any]) -> tuple[int | str, Any]: ...


class GhCliTransport:
    """Default transport: shells to ``gh api``. Never exercised by the test suite —
    OL-V1's live effect is exercised by the principal outside this build.

    ``gh api`` without ``-i`` prints only the response body, never the HTTP status
    line — there is genuinely no status to report, so both calls here return the
    literal "UNOBSERVED" rather than a fabricated 200 (MAJOR 7, principal review)."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or SubprocessRunner()

    def get(self, endpoint: str) -> tuple[int | str, Any]:
        result = self._runner.run(["gh", "api", endpoint])
        if result.returncode != 0:
            raise OutcomeLearningCliError(
                f"gh api GET {endpoint} failed: {result.stderr.strip()}"
            )
        return "UNOBSERVED", json.loads(result.stdout)

    def patch(self, endpoint: str, payload: Mapping[str, Any]) -> tuple[int | str, Any]:
        result = self._runner.run(
            ["gh", "api", endpoint, "-X", "PATCH", "--input", "-"],
            input=json.dumps(dict(payload)),
        )
        if result.returncode != 0:
            raise OutcomeLearningCliError(
                f"gh api PATCH {endpoint} failed: {result.stderr.strip()}"
            )
        return "UNOBSERVED", json.loads(result.stdout)


# --------------------------------------------------------------------------- io helpers


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_artifact(path: str | Path, doc: Any) -> None:
    """validate-where-applicable -> scan_public_safe_text -> assert_public_safe_evidence
    -> write, uniformly for EVERY JSON write this CLI performs (MAJOR 13) — the six
    OL-V1 schemas (already validated by the caller via contracts before this runs) AND
    the Chairman-cognition ``bundle.json``/``composition.json``, which have no
    OL-V1 contracts validator of their own but must never bypass the PUBLIC_SAFE scan
    on that account."""
    scan_public_safe_text(doc)
    try:
        assert_public_safe_evidence(doc)
    except ContractError as exc:
        raise OutcomeLearningCliError(f"refusing to write unsafe evidence: {exc}") from exc
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_text_artifact(path: str | Path, text: str) -> None:
    """Same scan -> assert -> write law as :func:`_write_artifact`, for the one
    non-JSON artifact this CLI produces (the proof markdown)."""
    scan_public_safe_text(text)
    try:
        assert_public_safe_evidence(text)
    except ContractError as exc:
        raise OutcomeLearningCliError(f"refusing to write unsafe evidence: {exc}") from exc
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _refuse_inside_repo(path: str | Path, *, where: str) -> Path:
    """External-receipt law: some artifacts must never land inside this checkout."""
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(_ROOT)
    except ValueError:
        return resolved
    raise OutcomeLearningCliError(
        f"{where} must be written outside the repository worktree, got {resolved}"
    )


def _sha256_hex_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- git helpers


def _git(runner: Runner, args: Sequence[str], *, cwd: str | None = None) -> str:
    result = runner.run(["git", *args], cwd=cwd)
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _normalize_repo_path(path: str, *, where: str) -> str:
    """Refuse an absolute path or any ".." segment, then collapse "." segments and
    redundant slashes. Sol REQUEST_REPAIR: a repo-path that could escape the sealed
    commit's own tree must never reach ``git rev-parse``."""
    if not isinstance(path, str) or not path:
        raise OutcomeLearningCliError(f"{where} must be a non-empty repo-relative path")
    if path.startswith("/"):
        raise OutcomeLearningCliError(
            f"{where} must be a repo-relative path, not absolute: {path!r}"
        )
    segments = path.split("/")
    if any(segment == ".." for segment in segments):
        raise OutcomeLearningCliError(
            f"{where} must not contain '..' path segments: {path!r}"
        )
    normalized = "/".join(segment for segment in segments if segment not in ("", "."))
    if not normalized:
        raise OutcomeLearningCliError(
            f"{where} must not be empty after normalization: {path!r}"
        )
    return normalized


def _resolve_committed_blob(
    runner: Runner,
    mastermind_root: str | None,
    sealed_commit: str,
    repo_path: str,
    *,
    where: str,
) -> tuple[str, str]:
    """Prove ``repo_path`` is an exact blob committed at ``sealed_commit`` — two
    INDEPENDENT git calls, never one: first resolve `<sealed_commit>:<repo_path>` to a
    blob id (``git rev-parse``), then separately read that blob's own bytes
    (``git cat-file -p``). Returns ``(blob_id, committed_text)``. Both calls run with
    an EXPLICIT cwd (``--mastermind-root``), never an implicit "wherever this process
    happens to be running"."""
    normalized = _normalize_repo_path(repo_path, where=f"{where} repo-path")
    rev_parse = runner.run(
        ["git", "rev-parse", f"{sealed_commit}:{normalized}"], cwd=mastermind_root
    )
    if rev_parse.returncode != 0 or not rev_parse.stdout.strip():
        raise OutcomeLearningCliError(
            f"{where}: sealed commit {sealed_commit} does not contain the exact "
            f"artifact path {normalized!r} — refusing (unresolvable blob)"
        )
    blob_id = rev_parse.stdout.strip()
    cat_file = runner.run(["git", "cat-file", "-p", blob_id], cwd=mastermind_root)
    if cat_file.returncode != 0:
        raise OutcomeLearningCliError(
            f"{where}: could not independently read committed blob {blob_id} for "
            f"{normalized!r}"
        )
    return blob_id, cat_file.stdout


# --------------------------------------------------------------------------- compose


def _envelope_payload(envelope: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": envelope["schema"],
        "envelope_id": envelope["envelope_id"],
        "authority_source_refs": sorted(envelope["authority_source_refs"]),
        "mode": envelope["mode"],
        "allowed_actions": sorted(envelope["allowed_actions"]),
        "allowed_reversibility": sorted(envelope["allowed_reversibility"]),
        "allowed_repositories": sorted(envelope["allowed_repositories"]),
        "allowed_path_prefixes": {
            repository: sorted(envelope["allowed_path_prefixes"][repository])
            for repository in sorted(envelope["allowed_path_prefixes"])
        },
        "allowed_scope_prefixes": sorted(envelope["allowed_scope_prefixes"]),
        "allowed_carrier_prefixes": sorted(envelope["allowed_carrier_prefixes"]),
        "max_budget_units": envelope["max_budget_units"],
        "max_active_children": envelope["max_active_children"],
        "require_exact_carrier": envelope["require_exact_carrier"],
        "expires_at": envelope["expires_at"],
    }


def _classification_payload(option: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "option_id": option["option_id"],
        "action": option["action"],
        "scope_refs": sorted(option["scope_refs"]),
        "repositories": sorted(option["repositories"]),
        "paths": sorted(option["paths"]),
        "creates_duplicate_control_plane": option["creates_duplicate_control_plane"],
        "change_classes": sorted(option["change_classes"]),
        "affected_departments": sorted(option["affected_departments"]),
    }


def _digest_hex(value: Any) -> str:
    from control_plane.wake_events import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _append_binding(revision: str, label: str, digest: str) -> str:
    """Replace-semantics: at most one token for ``label`` (used for envelope-sha256,
    which is a single value)."""
    prefix = f"{label}:"
    fields = [field for field in revision.split(";") if not field.startswith(prefix)]
    fields.append(f"{label}:{digest}")
    return ";".join(fields)


def _add_binding_if_absent(revision: str, label: str, digest: str) -> str:
    """Accumulate-semantics: multiple distinct tokens for the same ``label`` may
    coexist (used for classification-sha256, one per option classified against this
    same chairman receipt) — mirrors ``_bind_bundle`` in
    ``tests/test_chairman_cognition_sources.py``."""
    token = f"{label}:{digest}"
    fields = revision.split(";")
    if token not in fields:
        fields.append(token)
    return ";".join(fields)


def _olv1_envelope(parent_head: str) -> dict[str, Any]:
    return {
        "schema": _ENVELOPE_SCHEMA,
        "envelope_id": "ENV-OLV1-20260902",
        "authority_source_refs": [_CHAIRMAN_REF],
        "mode": "SUPERVISED_LIVE_CANARY",
        "allowed_actions": ["REVERSIBLE_RUNTIME_CANARY"],
        "allowed_reversibility": ["REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": ["research/outcome_learning"]
        },
        # Deviation from the frozen spec's literal "WS:OUTCOME-LEARNING" for the same
        # boundary-character reason documented below on allowed_carrier_prefixes: the
        # actual scope_ref "WS:OUTCOME-LEARNING-POLICY-CALIBRATION" is not preceded by a
        # boundary char after that truncated prefix, so it fails
        # control_plane.chairman_cognition._ref_matches_prefix. Using the exact scope_ref
        # is narrower, not broader, than the pinned literal. See this build's DEVIATIONS.
        "allowed_scope_prefixes": ["WS:OUTCOME-LEARNING-POLICY-CALIBRATION"],
        # Deviation from the frozen spec's literal
        # "github:Mastermind:branch:sol/outcome-learning" (no trailing boundary
        # character): control_plane.chairman_cognition._ref_matches_prefix requires
        # either an exact match or a boundary char (":", "/", "#") immediately after
        # the prefix. The truncated literal does not prefix-match the pinned carrier_ref
        # below (the next character is "-", not a boundary char), which drove the real
        # OPT-OLV1-PR-TITLE-CANARY option to CHAIRMAN_REQUIRED/SCOPE_OUTSIDE_ENVELOPE
        # instead of ELIGIBLE_WITHIN_DELEGATION — confirmed against a live compose run.
        # Using the exact carrier_ref as the sole allowed prefix scopes to precisely the
        # one branch this episode runs on (a strictly narrower, not broader, grant) and
        # is content-bound the same way. See this build's DEVIATIONS.
        "allowed_carrier_prefixes": [
            "github:Mastermind:branch:sol/outcome-learning-v1-complete-vertical-20260902"
        ],
        "max_budget_units": 5,
        "max_active_children": 1,
        "require_exact_carrier": True,
        "expires_at": "2026-09-09T00:00:00Z",
    }


_HOLD_CLASSIFICATION_SOURCE_REF = "OLV1:portfolio-hold-classification"
# Owner for the dedicated HOLD-option classification receipt. "STEWARD" was rejected on
# principal review — it collides with the real Executive Steward control-plane concept.
# The requested literal "OLV1_COMPOSER" is not a member of
# control_plane.chairman_cognition.ALLOWED_SOURCE_OWNERS / CLASSIFICATION_SOURCE_OWNERS
# (verified directly against that unmodifiable frozenset) and would make
# evaluate_document raise "unknown source owner" unconditionally. "OPERATION_ASSURANCE"
# is the closest already-allowed, non-colliding owner — this vertical IS an
# auditor-gated Operation Assurance episode. See this build's DEVIATIONS.
_HOLD_CLASSIFICATION_SOURCE_OWNER = "OPERATION_ASSURANCE"


def _olv1_options(operation_key: str, parent_head: str) -> list[dict[str, Any]]:
    source_refs = [_CHAIRMAN_REF, _STRATEGIC_SOURCE_REF, _AGENT_OS_SOURCE_REF]
    carrier_ref = "github:Mastermind:branch:sol/outcome-learning-v1-complete-vertical-20260902"
    canary = {
        "option_id": _OPT_CANARY,
        "title": "Run the OL-V1 supervised GitHub PR-title canary",
        "action": "REVERSIBLE_RUNTIME_CANARY",
        "reversibility": "REVERSIBLE",
        "source_refs": source_refs,
        "scope_refs": ["WS:OUTCOME-LEARNING-POLICY-CALIBRATION"],
        "effect_state": "NONE",
        "operation_key": operation_key,
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": carrier_ref,
        "expected_head_sha": parent_head,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": ["research/outcome_learning/"],
        "budget_units": 1,
        "active_children_after": 0,
        "creates_duplicate_control_plane": False,
        "stop_condition": (
            "Stop on EFFECT_UNKNOWN or any readback mismatch; no retry is ever issued."
        ),
        "rollback_plan": (
            "The single restore PATCH is already part of the two-call sequence; the "
            "carrying PR is a HOLD and is never merged."
        ),
        "falsifier": (
            "Any second apply call, a non-identical restoration, or head movement "
            "during the effect falsifies this option's premise."
        ),
        "classification_source_ref": _CHAIRMAN_REF,
        "change_classes": ["RUNTIME_CANARY"],
        "affected_departments": ["executive"],
        "benefits": {
            "strategic_leverage": 60,
            "dependency_unlock": 70,
            "learning_value": 85,
            "chairman_load_reduction": 40,
            "user_or_machine_value": 35,
        },
        "costs": {
            "time_to_evidence": 10,
            "execution_cost": 5,
            "coordination_risk": 10,
            "irreversibility_risk": 2,
            "scarce_cognition_cost": 15,
        },
    }
    hold = {
        "option_id": _OPT_HOLD,
        "title": "Hold the OL-V1 portfolio with no effect",
        "action": "PORTFOLIO_HOLD",
        # PORTFOLIO_HOLD is a READ_ONLY_ACTION; control_plane.chairman_cognition
        # hard-requires Reversibility.READ_ONLY for every READ_ONLY_ACTION
        # (_parse_options) — see this build's DEVIATIONS for the frozen-spec text
        # this corrects (it names "reversibility REVERSIBLE" for this option, which
        # evaluate_document unconditionally refuses).
        "reversibility": "READ_ONLY",
        "source_refs": [*source_refs, _HOLD_CLASSIFICATION_SOURCE_REF],
        "scope_refs": ["WS:OUTCOME-LEARNING-POLICY-CALIBRATION"],
        "effect_state": "NONE",
        "operation_key": operation_key,
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": carrier_ref,
        "expected_head_sha": parent_head,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": [],
        "budget_units": 0,
        "active_children_after": 0,
        "creates_duplicate_control_plane": False,
        "stop_condition": "No effect; the vertical returns a typed blocker instead.",
        "rollback_plan": "No effect; the vertical returns a typed blocker instead.",
        "falsifier": "No effect; the vertical returns a typed blocker instead.",
        # Deviation from the frozen spec's literal "classification_source_ref = chairman
        # ref" for BOTH options: binding two distinct classification-sha256 tokens plus
        # one envelope-sha256 token onto the single chairman receipt's `revision` field
        # overflows chairman_cognition_sources.py's unmodifiable 256-char bound on that
        # field (257+ chars, always). The canary option (the one actually executed) keeps
        # the literal pin; this read-only, never-executed fallback classifies against its
        # own dedicated receipt instead. See this build's DEVIATIONS.
        "classification_source_ref": _HOLD_CLASSIFICATION_SOURCE_REF,
        "change_classes": ["RESEARCH"],
        "affected_departments": ["executive"],
        "benefits": {
            "strategic_leverage": 5,
            "dependency_unlock": 0,
            "learning_value": 10,
            "chairman_load_reduction": 0,
            "user_or_machine_value": 0,
        },
        # Honest costs (principal review correction, 2026-09-02): a HOLD has genuinely
        # zero execution/coordination/irreversibility/scarce-cognition cost — it does
        # nothing. Its one real cost is that holding defers all evidence indefinitely
        # (time_to_evidence=90). Equalizing costs to the canary's to force Pareto
        # dominance (the prior draft's approach) was input-shaping, not honest
        # classification, and was reverted. Under strict Pareto dominance
        # (control_plane.chairman_cognition._dominates) this honest, near-zero-cost HOLD
        # is never dominated by the higher-benefit/higher-cost canary — both stay on the
        # actionable frontier (selection_state=MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS).
        # That is the A1 law working as designed, not a defect: compose's gate is
        # disposition-keyed on the canary option alone, not on selection_state or
        # recommended_option_id — see cmd_compose.
        "costs": {
            "time_to_evidence": 90,
            "execution_cost": 0,
            "coordination_risk": 0,
            "irreversibility_risk": 0,
            "scarce_cognition_cost": 0,
        },
    }
    return [canary, hold]


# Sol REQUEST_REPAIR (BLOCKER A, 2026-09-02): canonical identity is resolved against
# these exact GitHub remotes — never a local checkout's own branch name or working
# tree, which a dirty/detached/mutated local checkout could otherwise self-attest.
_CANONICAL_MASTERMIND_URL = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
_CANONICAL_MASTERMIND_REPO = "mastermindx-market-intelligence/Mastermind"
_CANONICAL_MACRO_URL = "https://github.com/mastermindx-market-intelligence/macro.git"
# Sparse-worktree omissions this repo's own CLAUDE.md documents as lawful (never
# "dirty"): a sparse worktree that never checked out these top-level dirs is not an
# uncommitted mutation of them.
_MACRO_SPARSE_OMITTED_PREFIXES = ("data/", "site/", "mockups/", "verify_shots/")


def _ls_remote_sha(runner: Runner, url: str, ref: str) -> str:
    """Resolve ``ref`` (e.g. ``refs/heads/master``) on the canonical remote ``url`` —
    never the local checkout's own idea of what that ref points to."""
    result = runner.run(["git", "ls-remote", url, ref])
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"git ls-remote {url} {ref} failed: {result.stderr.strip()}"
        )
    line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    sha = line.split()[0] if line.split() else ""
    if _SHA40_RE.fullmatch(sha) is None:
        raise OutcomeLearningCliError(
            f"git ls-remote {url} {ref} returned no resolvable 40-hex sha (got {line!r})"
        )
    return sha


def _acquire_canonical_strategic_state(
    runner: Runner, canonical_mastermind_sha: str
) -> tuple[str, dict[str, Any]]:
    """Fetch ``config/strategic_state.yml`` — its exact committed BLOB sha and
    content — at the canonical Mastermind commit via the GitHub Contents API, never
    from any local working tree. Returns ``(blob_sha, strategic_state_summary)``.

    Narrowly-justified import (six-path ceiling, documented): reuses the
    already-protected :mod:`control_plane.strategic_state` parser/validator instead
    of reimplementing YAML strategic-state validation here. The projection into the
    ``mastermind.strategic_state.v1`` boot-packet summary shape mirrors
    ``control_plane.ceo_boot_packet.load_strategic_summary`` (a five-line, obviously
    equivalent transcription — not a second competing implementation)."""
    result = runner.run(
        [
            "gh",
            "api",
            f"repos/{_CANONICAL_MASTERMIND_REPO}/contents/config/strategic_state.yml"
            f"?ref={canonical_mastermind_sha}",
        ]
    )
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            "gh api contents config/strategic_state.yml@"
            f"{canonical_mastermind_sha} failed: {result.stderr.strip()}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(
            "canonical strategic_state.yml contents payload is not valid JSON"
        ) from exc
    blob_sha = payload.get("sha")
    encoded_content = payload.get("content")
    encoding = payload.get("encoding")
    if (
        not isinstance(blob_sha, str)
        or _SHA40_RE.fullmatch(blob_sha) is None
        or encoding != "base64"
        or not isinstance(encoded_content, str)
    ):
        raise OutcomeLearningCliError(
            "canonical strategic_state.yml contents payload is malformed (missing "
            "blob sha or base64 content)"
        )

    import base64
    import tempfile

    from control_plane.strategic_state import StrategicStateError, load_strategic_state

    try:
        yaml_bytes = base64.b64decode(encoded_content, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # noqa: BLE001
        raise OutcomeLearningCliError(
            "canonical strategic_state.yml content is not valid base64"
        ) from exc

    fd, tmp_path = tempfile.mkstemp(suffix=".yml")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(yaml_bytes)
        state = load_strategic_state(tmp_path)
    except StrategicStateError as exc:
        raise OutcomeLearningCliError(
            f"canonical strategic_state.yml failed validation: {exc}"
        ) from exc
    finally:
        os.unlink(tmp_path)

    summary = {
        "schema": state["schema"],
        "company_phase": state["company_phase"],
        "north_star": list(state["north_star"]),
        "p0": [
            {
                "id": obj["id"],
                "department": obj["department"],
                "objective": " ".join(str(obj["objective"]).split()),
                "status": obj["status"],
            }
            for obj in state["p0"]
        ],
        "constraints": {name: str(level) for name, level in state["constraints"].items()},
    }
    return blob_sha, summary


def _macro_checkout_matches_canonical_and_is_clean(
    runner: Runner, macro_root: str, canonical_macro_sha: str
) -> tuple[str, bool, list[str]]:
    """Return ``(local_sha, is_clean, dirty_lines)`` for the LOCAL macro checkout used
    for this compose run. ``is_clean`` ignores porcelain lines under a known
    sparse-worktree omission prefix (this repo's own CLAUDE.md: ``data/``, ``site/``,
    ``mockups/``, ``verify_shots/``) — a sparse tree that never checked those out is
    not an uncommitted mutation of them."""
    local_sha = _git(runner, ["rev-parse", "HEAD"], cwd=macro_root)
    result = runner.run(["git", "status", "--porcelain"], cwd=macro_root)
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"git status --porcelain failed in the macro checkout: {result.stderr.strip()}"
        )
    dirty_lines = []
    for raw_line in result.stdout.splitlines():
        if not raw_line.strip():
            continue
        path = raw_line[3:] if len(raw_line) > 3 else raw_line.strip()
        if any(path.startswith(prefix) for prefix in _MACRO_SPARSE_OMITTED_PREFIXES):
            continue
        dirty_lines.append(raw_line)
    return local_sha, not dirty_lines, dirty_lines


def _acquire_boot_packet(runner: Runner, mastermind_root: str, macro_root: str) -> dict[str, Any]:
    result = runner.run(
        [
            "python3",
            "scripts/ceo_boot_packet.py",
            "--json",
            "--macro-root",
            macro_root,
            # The Agent OS brief legitimately takes minutes on a large estate; the
            # producer's 60s default would time out and mislabel the owner UNKNOWN.
            "--timeout",
            "900",
        ],
        cwd=mastermind_root,
    )
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"ceo_boot_packet.py failed: {result.stderr.strip()}"
        )
    return json.loads(result.stdout)


_REDACTED_LOCAL_PATH = "REDACTED_LOCAL_PATH"


def _redact_boot_packet(boot: Mapping[str, Any]) -> dict[str, Any]:
    """Strip local filesystem locators before the boot packet is bundled or digested
    (MAJOR 13). Digests embedded in the two attestations are computed over
    ``boot["strategic_state"]``/``boot["brief"]`` alone, never over ``mastermind``/
    ``macro``, so redacting these fields here changes no digest downstream — it is
    purely a privacy cut applied once, before the (already-redacted) ``boot`` is used
    for anything else."""
    redacted = dict(boot)
    redacted["mastermind"] = {**boot["mastermind"], "root": _REDACTED_LOCAL_PATH}
    redacted["macro"] = {
        **boot["macro"],
        "root": _REDACTED_LOCAL_PATH,
        "candidates_tried": _REDACTED_LOCAL_PATH,
    }
    return redacted


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_utc(value: str):
    from datetime import datetime, timezone

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _acquire_agentos_records_digest(
    runner: Runner, macro_root: str, as_of: str, override: str | None
) -> str:
    """Read-only real producer: ``scripts/agentos.py status --dry-run`` prints
    ``agentos.source_records_digest.v1``'s value at top-level ``source_records_digest``
    without writing any file. ``override`` lets an operator supply the value directly
    when the producer is genuinely unavailable (documented in the runbook)."""
    if override is not None:
        return override
    agentos_root = os.path.join(macro_root, "agentos")
    result = runner.run(
        [
            "python3",
            "scripts/agentos.py",
            "status",
            "--root",
            agentos_root,
            "--dry-run",
            "--now",
            as_of,
        ],
        cwd=macro_root,
    )
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"agentos.py status --dry-run failed: {result.stderr.strip()}"
        )
    # --dry-run writes the JSON document first, then ::warning diagnostics and a
    # human summary on the same stream; decode the leading document only.
    start = result.stdout.find("{")
    if start < 0:
        raise OutcomeLearningCliError(
            "agentos.py status --dry-run emitted no JSON document"
        )
    payload, _ = json.JSONDecoder().raw_decode(result.stdout[start:])
    digest = payload.get("source_records_digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise OutcomeLearningCliError(
            "agentos.py status --dry-run did not emit a source_records_digest"
        )
    return digest


def cmd_compose(args: argparse.Namespace, *, runner: Runner | None = None) -> int:
    """Sol REQUEST_REPAIR (BLOCKER A, 2026-09-02): every identity claim this function
    embeds is now acquired from a source it cannot itself author. Mastermind's
    revision and its strategic-state blob come from the canonical GitHub remote (via
    ``git ls-remote`` + the Contents API), never local ``git rev-parse``/working-tree
    bytes. Macro's identity is proven by requiring the LOCAL macro checkout used for
    the boot-packet/brief run to exactly equal, and be clean at, the canonical
    ``main`` ls-remote sha — a dirty or divergent local checkout can no longer
    self-attest CURRENT. Any acquisition failure (unreachable remote, missing blob,
    checkout mismatch, dirty tree) is a typed, named refusal before any bundle is
    even constructed — see the ``BLOCKER SOURCE_IDENTITY_UNVERIFIED`` handling below.
    """
    runner = runner or SubprocessRunner()

    try:
        mastermind_sha = _ls_remote_sha(
            runner, _CANONICAL_MASTERMIND_URL, "refs/heads/master"
        )
        strategic_blob_sha, canonical_strategic_state = _acquire_canonical_strategic_state(
            runner, mastermind_sha
        )
        macro_canonical_sha = _ls_remote_sha(runner, _CANONICAL_MACRO_URL, "refs/heads/main")
        macro_local_sha, macro_clean, macro_dirty_lines = (
            _macro_checkout_matches_canonical_and_is_clean(
                runner, args.macro_root, macro_canonical_sha
            )
        )
        if macro_local_sha != macro_canonical_sha:
            raise OutcomeLearningCliError(
                "local macro checkout HEAD "
                f"{macro_local_sha} does not match canonical macro main "
                f"{macro_canonical_sha}"
            )
        if not macro_clean:
            raise OutcomeLearningCliError(
                "local macro checkout is not clean (git status --porcelain, "
                f"excluding known sparse omissions): {macro_dirty_lines[:5]}"
            )
    except OutcomeLearningCliError as exc:
        print(f"BLOCKER SOURCE_IDENTITY_UNVERIFIED {exc}")
        return 5

    boot = _redact_boot_packet(
        _acquire_boot_packet(runner, args.mastermind_root, args.macro_root)
    )
    # Cross-check: the boot packet's own (independently git-derived) macro sha must
    # agree with the identity we just proved — a boot packet pointed at a different
    # macro checkout than --macro-root would otherwise silently smuggle in an
    # unverified Macro state.
    boot_macro_sha = ((boot.get("macro") or {}).get("sha"))
    if boot_macro_sha != macro_local_sha:
        print(
            "BLOCKER SOURCE_IDENTITY_UNVERIFIED boot_packet.macro.sha "
            f"{boot_macro_sha!r} does not match the independently-verified local "
            f"macro checkout {macro_local_sha!r}"
        )
        return 5
    # The canonical, GitHub-content-API-fetched strategic state REPLACES whatever the
    # boot packet's own local-working-tree read produced — the whole point of this
    # repair is that only the canonical read may promote to CURRENT.
    boot = {**boot, "strategic_state": canonical_strategic_state}

    # as_of (principal correction, addendum A, 2026-09-02): a caller-fixed --as-of
    # captured BEFORE acquisition can end up earlier than the receipts' own
    # observed_at once a slow acquisition (the Agent OS brief can take minutes) has
    # finished — A1 then rightly refuses ("source receipt cannot postdate
    # document.as_of"). Default: compute as_of AFTER acquisition, as the later of
    # "now" and the boot packet's own generated_at, so it can never be postdated by
    # anything this command is about to embed. An explicitly supplied --as-of is
    # honored, but refused up front if the boot packet's generated_at already
    # postdates it — the same defect, caught before composing instead of inside A1.
    agentos_records_digest = _acquire_agentos_records_digest(
        runner, args.macro_root, args.as_of or _utc_now_iso(), args.agentos_records_digest
    )
    if args.as_of is not None:
        as_of = args.as_of
        as_of_mode = "explicit"
        if _parse_iso_utc(boot["generated_at"]) > _parse_iso_utc(as_of):
            raise OutcomeLearningCliError(
                f"--as-of {as_of} predates boot_packet.generated_at "
                f"{boot['generated_at']} — refusing (A1 would reject this receipt as "
                "postdating document.as_of); omit --as-of to compute it automatically"
            )
    else:
        acquisition_completed_at = _utc_now_iso()
        as_of = max(
            (boot["generated_at"], acquisition_completed_at), key=_parse_iso_utc
        )
        as_of_mode = "auto(max_observed_at)"

    strategic_state = boot.get("strategic_state") or {}
    brief = boot.get("brief") or {}
    strategic_payload_digest = canonical_digest(strategic_state)
    agentos_payload_digest = canonical_digest(brief) if brief else "UNRESOLVED"

    # Sol REQUEST_REPAIR: the two attestations are no longer the SAME copied boolean.
    # Mastermind's state is CURRENT because we are already past every acquisition
    # check above (ls-remote + Contents API both succeeded and validated). Agent OS's
    # state is CURRENT only when the macro identity was independently proven AND no
    # unverifiable operator override was supplied for its records digest — an
    # override can never itself participate in a CURRENT claim (BLOCKER A, item 3).
    mastermind_state = "CURRENT"
    agentos_state = "UNKNOWN" if args.agentos_records_digest is not None else "CURRENT"

    mastermind_revision_attestation = {
        "revision": mastermind_sha,
        "state": mastermind_state,
        "load_bearing": True,
        "observed_at": as_of,
        # The real committed BLOB sha for config/strategic_state.yml — never the
        # commit sha (BLOCKER A's named defect).
        "source_blob_sha": strategic_blob_sha,
        "payload_digest": strategic_payload_digest,
    }
    agentos_revision_attestation = {
        "revision": macro_local_sha,
        "state": agentos_state,
        "load_bearing": True,
        "observed_at": as_of,
        "source_records_digest": agentos_records_digest,
        "payload_digest": agentos_payload_digest,
    }

    envelope = _olv1_envelope(mastermind_sha)
    options = _olv1_options(args.operation_key, mastermind_sha)
    envelope_digest = _digest_hex(_envelope_payload(envelope))

    chairman_revision = _append_binding(
        args.chairman_revision, "envelope-sha256", envelope_digest
    )
    additional_source_receipts: list[dict[str, Any]] = []
    for option in options:
        classification_digest = _digest_hex(_classification_payload(option))
        if option["classification_source_ref"] == _CHAIRMAN_REF:
            chairman_revision = _add_binding_if_absent(
                chairman_revision, "classification-sha256", classification_digest
            )
        else:
            additional_source_receipts.append(
                {
                    "source_ref": option["classification_source_ref"],
                    "owner": _HOLD_CLASSIFICATION_SOURCE_OWNER,
                    "revision": f"classification-sha256:{classification_digest}",
                    "state": "CURRENT",
                    "load_bearing": True,
                    "observed_at": as_of,
                }
            )
    chairman_directive = {
        "source_ref": _CHAIRMAN_REF,
        "revision": chairman_revision,
        "state": "CURRENT",
        "load_bearing": True,
        "observed_at": as_of,
    }

    bundle = {
        "schema": _SOURCE_BUNDLE_SCHEMA,
        "as_of": as_of,
        "chairman_directive": chairman_directive,
        "mastermind_revision_attestation": mastermind_revision_attestation,
        "agentos_revision_attestation": agentos_revision_attestation,
        "boot_packet": boot,
        "additional_source_receipts": additional_source_receipts,
        "delegation_envelope": envelope,
        "options": options,
    }

    # Error-channel honesty (principal correction, addendum B, 2026-09-02): an
    # exception here is a COMPOSITION defect (a malformed bundle, an unbindable
    # envelope, a stale as_of that slipped past the check above) — never an owner
    # SOURCE state, and it must never be rendered through the
    # "BLOCKER OWNER_SOURCE_NOT_CURRENT <ref>=<state>" template, which presumes a
    # successfully-composed packet with a real ref/state pair. Exit 4 /
    # OWNER_SOURCE_NOT_CURRENT is reserved strictly for that successful-packet case,
    # below.
    try:
        composition = evaluate_bundle(bundle)
    except (ChairmanCognitionSourceError, ChairmanCognitionError) as exc:
        print(f"BLOCKER COMPOSITION_INVALID {exc}")
        return 5

    episode_dir = Path(args.episode_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)
    _write_artifact(episode_dir / "bundle.json", bundle)
    _write_artifact(episode_dir / "composition.json", composition)

    print(f"as_of_mode={as_of_mode} as_of={as_of}")
    for summary in composition["source_summary"]:
        print(f"SOURCE {summary['source_ref']}={summary['state']}")
    for adjudication in composition["packet"]["adjudications"]:
        print(
            f"ADJUDICATION {adjudication['option_id']}="
            f"{adjudication['disposition']}/{adjudication['reason']}"
        )
    print(f"selection_state={composition['packet']['selection_state']}")
    print(f"recommended_option_id={composition['packet']['recommended_option_id']}")
    print(f"execution_authority_granted={composition['execution_authority_granted']}")
    print(f"source_bundle_digest=sha256:{composition['source_bundle_digest']}")
    print(f"composed_input_digest=sha256:{composition['composed_input_digest']}")
    print(f"packet_digest=sha256:{composition['packet']['packet_digest']}")
    print(f"composition_digest=sha256:{composition['composition_digest']}")

    # Disposition-keyed gate (principal correction, 2026-09-02): compose does NOT require
    # selection_state == UNIQUE_ACTIONABLE_FRONTIER or recommended_option_id == the
    # canary. control_plane.chairman_cognition's A1 law lets an honest, near-zero-cost
    # READ_ONLY HOLD join the actionable frontier alongside a higher-benefit/higher-cost
    # canary under strict Pareto dominance — MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS is
    # an expected, lawful outcome, not a fault. What actually gates this episode is
    # whether the CANARY option itself is ELIGIBLE_WITHIN_DELEGATION — the principal (or
    # a human reading this output) makes the final selection among an incomparable
    # frontier; compose never manufactures uniqueness by input-shaping the HOLD option.
    canary_adjudication = next(
        item
        for item in composition["packet"]["adjudications"]
        if item["option_id"] == _OPT_CANARY
    )
    disposition = canary_adjudication["disposition"]
    reason = canary_adjudication["reason"]

    if disposition == "ELIGIBLE_WITHIN_DELEGATION":
        print(
            "COMPOSE_OK canary_disposition=ELIGIBLE_WITHIN_DELEGATION "
            f"selection_state={composition['packet']['selection_state']} "
            f"recommended_option_id={composition['packet']['recommended_option_id']}"
        )
        return 0
    if disposition == "REFUSED" and reason == "SOURCE_NOT_CURRENT":
        blocker_ref = next(
            (
                summary["source_ref"]
                for summary in composition["source_summary"]
                if summary["load_bearing"] and summary["state"] != "CURRENT"
            ),
            None,
        )
        if blocker_ref is not None:
            state = next(
                summary["state"]
                for summary in composition["source_summary"]
                if summary["source_ref"] == blocker_ref
            )
            print(f"BLOCKER OWNER_SOURCE_NOT_CURRENT {blocker_ref}={state}")
        else:  # pragma: no cover - defensive: reason implies a non-CURRENT source exists
            print("BLOCKER OWNER_SOURCE_NOT_CURRENT unknown=SOURCE_NOT_CURRENT")
        return 4
    print(f"BLOCKER CANARY_NOT_ELIGIBLE {disposition}/{reason}")
    return 5


# --------------------------------------------------------------------------- seal


def _alternative_from_adjudication(
    packet: Mapping[str, Any], option_id: str
) -> dict[str, Any]:
    adjudication = next(
        item for item in packet["adjudications"] if item["option_id"] == option_id
    )
    if adjudication["disposition"] in {"ELIGIBLE_WITHIN_DELEGATION", "READ_ONLY_ELIGIBLE"}:
        return {"action_id": option_id, "eligible": True, "exclusion_reason": None}
    return {
        "action_id": option_id,
        "eligible": False,
        "exclusion_reason": f"{adjudication['disposition']}/{adjudication['reason']}",
    }


def cmd_seal(args: argparse.Namespace) -> int:
    composition = _read_json(args.composition)
    bundle = _read_json(Path(args.episode_dir) / "bundle.json")

    # BLOCKER 3 (principal correction, 2026-09-02): composition.json is an editable
    # file sitting on disk between compose and seal — trusting it verbatim would let a
    # hand edit (e.g. REFUSED -> ELIGIBLE_WITHIN_DELEGATION) sail straight through.
    # evaluate_bundle is pure and deterministic, so re-running it over the
    # ALSO-on-disk bundle.json must reproduce composition.json byte-for-byte; any
    # mismatch means one of the two files was tampered with or has drifted, and
    # sealing refuses outright.
    try:
        recomposed = evaluate_bundle(bundle)
    except (ChairmanCognitionSourceError, ChairmanCognitionError) as exc:
        raise OutcomeLearningCliError(
            f"refusing to seal: bundle.json no longer composes cleanly: {exc}"
        ) from exc
    if canonical_digest(recomposed) != canonical_digest(composition):
        raise OutcomeLearningCliError(
            "refusing to seal: composition.json does not match a fresh "
            "evaluate_bundle(bundle.json) recomputation — one of the two files was "
            "edited or has drifted since compose"
        )
    if composition["execution_authority_granted"] is not False:
        raise OutcomeLearningCliError(
            "refusing to seal: composition.execution_authority_granted is not False"
        )

    packet = composition["packet"]
    options = bundle["options"]
    chosen_action = _OPT_CANARY

    # Truthful assignment.method from the packet's own adjudication (principal
    # correction, 2026-09-02) — never a hardcoded "DETERMINISTIC" label. A1's frontier
    # may legitimately be MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS (an honest
    # near-zero-cost HOLD is never Pareto-dominated); that is not grounds to refuse
    # sealing the canary, only grounds to say plainly that a human selected it from an
    # incomparable frontier rather than A1 having uniquely recommended it.
    canary_adjudication = next(
        item for item in packet["adjudications"] if item["option_id"] == chosen_action
    )
    disposition = canary_adjudication["disposition"]
    reason = canary_adjudication["reason"]
    if disposition in {"REFUSED", "CHAIRMAN_REQUIRED"}:
        raise OutcomeLearningCliError(
            f"refusing to seal chosen_action {chosen_action}: adjudication "
            f"disposition={disposition} reason={reason}"
        )
    if packet["recommended_option_id"] == chosen_action:
        assignment_method = "deterministic_a1_unique_actionable_frontier"
    elif (
        packet["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
        and disposition == "ELIGIBLE_WITHIN_DELEGATION"
    ):
        assignment_method = "principal_selection_from_a1_incomparable_frontier"
    else:  # pragma: no cover - defensive: not reachable for this vertical's fixed options
        raise OutcomeLearningCliError(
            f"refusing to seal chosen_action {chosen_action}: disposition={disposition} "
            f"does not map to a known assignment.method (selection_state="
            f"{packet['selection_state']}, recommended_option_id="
            f"{packet['recommended_option_id']})"
        )

    # Sol REQUEST_REPAIR (BLOCKER B, 2026-09-02): operation identity and ancestry are
    # DERIVED from the adjudicated A1 option, never freely supplied — a caller could
    # otherwise attach this packet's digest to an unrelated operation/parent/carrier.
    # --operation-key/--parent-head become optional cross-checks: if supplied, they
    # must exactly equal what the option already says, or sealing refuses outright.
    chosen_option = next(item for item in options if item["option_id"] == chosen_action)
    operation_key = chosen_option["operation_key"]
    expected_parent_head = chosen_option["expected_head_sha"]
    option_repositories = chosen_option["repositories"]
    if len(option_repositories) != 1:
        raise OutcomeLearningCliError(
            "refusing to seal: the adjudicated option does not name exactly one "
            f"repository ({option_repositories!r})"
        )
    request_repository = option_repositories[0]
    carrier_ref = chosen_option["carrier_ref"] or ""
    carrier_branch_prefix = "github:Mastermind:branch:"
    if not carrier_ref.startswith(carrier_branch_prefix):
        raise OutcomeLearningCliError(
            f"refusing to seal: cannot derive a branch from carrier_ref {carrier_ref!r}"
        )
    request_branch = carrier_ref[len(carrier_branch_prefix):]

    if args.operation_key is not None and args.operation_key != operation_key:
        raise OutcomeLearningCliError(
            f"--operation-key {args.operation_key!r} does not match the adjudicated "
            f"option's operation_key {operation_key!r} — refusing"
        )
    if args.parent_head is not None and args.parent_head != expected_parent_head:
        raise OutcomeLearningCliError(
            f"--parent-head {args.parent_head!r} does not match the adjudicated "
            f"option's expected_head_sha {expected_parent_head!r} — refusing"
        )

    option_set_digest = canonical_digest(options)
    source_packet_digests = [
        f"sha256:{composition['source_bundle_digest']}",
        f"sha256:{composition['composed_input_digest']}",
        f"sha256:{packet['packet_digest']}",
        f"sha256:{composition['composition_digest']}",
    ]

    expectation = build_expectation(
        decision_ref={
            "owner": "chairman_cognition",
            "type": "a1_decision_packet",
            "id": canonical_digest(packet),
        },
        operation_key=operation_key,
        decision_kind="organizational_learning_episode",
        recorded_at=args.recorded_at,
        context={
            "source_refs": [
                bundle["chairman_directive"]["source_ref"],
                _STRATEGIC_SOURCE_REF,
                _AGENT_OS_SOURCE_REF,
                "GITHUB:Mastermind:protected-master",
            ],
            "task_kind": "organizational_learning_episode",
            "risk": "routine",
            "ambiguity": "low",
            "program": "organizational-learning",
            "repository": request_repository,
            "source_cutoff": bundle["as_of"],
            "applicability_cohort": (
                "supervised reversible GitHub metadata canary, repository-owner PR, "
                "single episode"
            ),
        },
        alternatives=[
            _alternative_from_adjudication(packet, _OPT_CANARY),
            _alternative_from_adjudication(packet, _OPT_HOLD),
        ],
        chosen_action=chosen_action,
        assignment={
            "method": assignment_method,
            "probability": None,
            "probability_null_reason": "DETERMINISTIC_NO_COUNTERFACTUAL_SUPPORT",
            "policy_version": "olv1-v1",
            "randomization_unit": "N/A",
        },
        expectations=[
            {
                "metric_id": "effect_applied_and_restored",
                "horizon": "terminal",
                "estimate": 0.90,
                "lower": 0.70,
                "upper": 0.97,
                "kind": "probability",
            },
            {
                "metric_id": "head_unchanged_through_effect",
                "horizon": "terminal",
                "estimate": 0.97,
                "lower": 0.85,
                "upper": 0.995,
                "kind": "probability",
            },
            {
                "metric_id": "byte_identical_restoration",
                "horizon": "terminal",
                "estimate": 0.95,
                "lower": 0.80,
                "upper": 0.99,
                "kind": "probability",
            },
            {
                "metric_id": "effect_calls_exactly_two",
                "horizon": "terminal",
                "estimate": 0.90,
                "lower": 0.75,
                "upper": 0.98,
                "kind": "probability",
            },
            {
                "metric_id": "ci_green_at_final_head",
                "horizon": "delayed",
                "estimate": 0.80,
                "lower": 0.55,
                "upper": 0.95,
                "kind": "probability",
            },
        ],
        guardrails=[
            {"guardrail_id": "G1", "statement": "Two-call max: exactly apply then restore."},
            {"guardrail_id": "G2", "statement": "No retry of any effect call, ever."},
            {
                "guardrail_id": "G3",
                "statement": "EFFECT_UNKNOWN stops the episode; no failover path exists.",
            },
            {
                "guardrail_id": "G4",
                "statement": "The episode is supervised by the principal at every step.",
            },
            {
                "guardrail_id": "G5",
                "statement": "Restore before any further push to the carrying branch.",
            },
        ],
        causal_question=(
            "Does one supervised, sealed GitHub PR-title canary apply and restore "
            "byte-identically within a two-call, no-retry contract?"
        ),
        known_confounders=[
            "a concurrent editor of the same PR title during the episode window",
            "transient GitHub API instability producing an ambiguous PATCH response",
        ],
        assumptions=[
            {
                "assumption_id": "OLV1-A1",
                "role": "LOAD_BEARING",
                "statement": "Exactly one open PR exists for the branch and its head "
                "matches the sealed commit.",
                "evidence_refs": ["preflight.head_equals_sealed_commit"],
                "ex_ante_confidence": 0.90,
                "confidence_null_reason": None,
                "falsifier": "Preflight finds zero, multiple, or a head-mismatched PR.",
            },
            {
                "assumption_id": "OLV1-A2",
                "role": "LOAD_BEARING",
                "statement": "The apply PATCH's effect is observable via read-back and "
                "the head stays stable through the call.",
                "evidence_refs": ["effect_calls[0].readback"],
                "ex_ante_confidence": 0.90,
                "confidence_null_reason": None,
                "falsifier": "The readback title or head does not match the apply payload.",
            },
            {
                "assumption_id": "OLV1-A3",
                "role": "LOAD_BEARING",
                "statement": "The restore PATCH returns the title to a byte-identical "
                "original.",
                "evidence_refs": ["outcome.restoration.byte_identical"],
                "ex_ante_confidence": 0.90,
                "confidence_null_reason": None,
                "falsifier": "The restored title hash differs from the original.",
            },
            {
                "assumption_id": "OLV1-A4",
                "role": "CONTEXTUAL",
                "statement": "No concurrent mutator changes the PR title during the "
                "episode window.",
                "evidence_refs": ["effect_calls[*].readback.title_sha256"],
                "ex_ante_confidence": 0.80,
                "confidence_null_reason": None,
                "falsifier": "A readback shows a title hash neither party expected.",
            },
            {
                "assumption_id": "OLV1-A5",
                "role": "CONTEXTUAL",
                "statement": "A direct PATCH readback, not a reconciliation read, "
                "confirms each effect call.",
                "evidence_refs": [],
                "ex_ante_confidence": None,
                "confidence_null_reason": (
                    "V1's outcome schema does not record whether a readback came from "
                    "a direct PATCH response or a reconciliation GET — see the runbook."
                ),
                "falsifier": "N/A in v1 — never independently assessable this cycle.",
            },
            {
                "assumption_id": "OLV1-A6",
                "role": "CONTEXTUAL",
                "statement": "The composed source states stay stable through the "
                "episode window.",
                "evidence_refs": [],
                "ex_ante_confidence": None,
                "confidence_null_reason": (
                    "V1 performs no post-episode re-composition — an honest ceiling, "
                    "not a defect."
                ),
                "falsifier": "N/A in v1 — no re-composition is ever attempted.",
            },
        ],
        memory_exposure={
            "pre_memory_option_set_digest": option_set_digest,
            "final_option_set_digest": option_set_digest,
            "final_decision_digest": canonical_digest(
                {
                    "operation_key": operation_key,
                    "recommended_option_id": packet["recommended_option_id"],
                }
            ),
            "consulted": [
                {
                    "record_ref": "DEC:OUTCOME-LEARNING-POLICY-CALIBRATION-ARCHITECTURE",
                    "influence": "MATERIALLY_CHANGED",
                    "why": (
                        "Set the sealed-receipt / two-call-canary / DESCRIPTIVE_ONLY "
                        "shape this episode follows."
                    ),
                },
                {
                    "record_ref": "DEC:OUTCOME-LEARNING-TWO-DECISION-CANARY-GATE",
                    "influence": "CONSULTED_NO_CHANGE",
                    "why": (
                        "Confirmed this supervised n=1 episode sits outside the "
                        "randomized-gate's scope without altering this episode's design."
                    ),
                },
                {
                    "record_ref": "DSC:HISTORICAL-ROUTING-COUNTERFACTUALS-NOT-IDENTIFIED",
                    "influence": "CONSULTED_NO_CHANGE",
                    "why": (
                        "Confirmed no prior routing counterfactual exists for this "
                        "exact episode shape; nothing to reconcile against."
                    ),
                },
            ],
            "source_packet_digests": source_packet_digests,
        },
    )

    request = build_canary_request(
        operation_key=operation_key,
        expectation_sealed_hash=expectation["sealed_hash"],
        repository=request_repository,
        branch=request_branch,
        expected_parent_head=expected_parent_head,
        recorded_at=args.recorded_at,
    )

    _write_artifact(args.out_expectation, expectation)
    _write_artifact(args.out_request, request)
    print(f"expectation_sealed_hash={expectation['sealed_hash']}")
    print(f"request_digest={canonical_digest(request)}")
    return 0


# --------------------------------------------------------------------------- preflight


def _committed_blob_content_sha256(
    runner: Runner,
    mastermind_root: str | None,
    sealed_commit: str,
    repo_path: str,
    local_path: str,
    *,
    where: str,
) -> tuple[str, str]:
    """Sol REQUEST_REPAIR (committed-seal-before-effect): prove the SUPPLIED artifact
    file is byte-identical, after canonicalization, to the blob actually committed at
    ``sealed_commit:repo_path`` — never trust a local file's own fingerprint as if it
    were a claim about what the sealed commit contains. Returns
    ``(blob_id, committed_content_sha256)``; raises on any unresolvable path, escape
    attempt, unreadable blob, non-JSON committed content, or digest mismatch against
    the supplied file."""
    blob_id, committed_text = _resolve_committed_blob(
        runner, mastermind_root, sealed_commit, repo_path, where=where
    )
    try:
        committed_obj = json.loads(committed_text)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(
            f"{where}: committed blob {blob_id} is not valid JSON"
        ) from exc
    committed_content_sha256 = canonical_digest(committed_obj).removeprefix("sha256:")

    supplied_obj = json.loads(Path(local_path).read_text(encoding="utf-8"))
    supplied_content_sha256 = canonical_digest(supplied_obj).removeprefix("sha256:")

    if committed_content_sha256 != supplied_content_sha256:
        raise OutcomeLearningCliError(
            f"{where}: committed blob {blob_id} at {sealed_commit}:{repo_path} does "
            "not match the supplied artifact file — refusing (committed-vs-supplied "
            f"digest mismatch: committed={committed_content_sha256} "
            f"supplied={supplied_content_sha256})"
        )
    return blob_id, committed_content_sha256


def cmd_preflight(args: argparse.Namespace, *, runner: Runner | None = None, transport: GhTransport | None = None) -> int:
    """Sol REQUEST_REPAIR, 2026-09-02: preflight proves ``head_equals_sealed_commit``
    together with an independently-verified claim that the expectation/request
    artifacts are the EXACT bytes committed at ``sealed_commit`` — never a local
    uncommitted fingerprint standing in for that claim. There is no local-file
    fallback; both ``--expectation-repo-path``/``--request-repo-path`` are required."""
    runner = runner or SubprocessRunner()
    transport = transport or GhCliTransport(runner)
    out_path = _refuse_inside_repo(args.out, where="preflight --out")

    if not args.expectation_repo_path or not args.request_repo_path:
        raise OutcomeLearningCliError(
            "preflight requires both --expectation-repo-path and --request-repo-path "
            "— there is no local-uncommitted-file fallback (Sol REQUEST_REPAIR: a "
            "local hash-object fingerprint cannot prove the artifact is part of the "
            "sealed commit)"
        )

    # Sol REQUEST_REPAIR (BLOCKER B, 2026-09-02): every local-identity check below
    # runs BEFORE the first transport call. Two independent git calls PER artifact
    # (blob-id resolution, then a separate content read) — see
    # _committed_blob_content_sha256 — prove the supplied file's canonical content
    # matches what the sealed commit actually contains; only THEN is the sealed
    # request's own content trusted for the repo/branch/ancestry cross-checks.
    expectation_blob_sha, expectation_content_sha256 = _committed_blob_content_sha256(
        runner,
        args.mastermind_root,
        args.sealed_commit,
        args.expectation_repo_path,
        args.expectation,
        where="expectation",
    )
    request_blob_sha, request_content_sha256 = _committed_blob_content_sha256(
        runner,
        args.mastermind_root,
        args.sealed_commit,
        args.request_repo_path,
        args.request,
        where="request",
    )
    request_obj = json.loads(Path(args.request).read_text(encoding="utf-8"))

    if args.repo != request_obj["repository"]:
        raise OutcomeLearningCliError(
            f"--repo {args.repo!r} does not match the sealed request's repository "
            f"{request_obj['repository']!r} — refusing before any transport call"
        )
    if args.branch != request_obj["branch"]:
        raise OutcomeLearningCliError(
            f"--branch {args.branch!r} does not match the sealed request's branch "
            f"{request_obj['branch']!r} — refusing before any transport call"
        )

    sealed_parent = _git(
        runner, ["rev-parse", f"{args.sealed_commit}^"], cwd=args.mastermind_root
    )
    if sealed_parent != request_obj["expected_parent_head"]:
        raise OutcomeLearningCliError(
            f"sealed_commit {args.sealed_commit}'s parent {sealed_parent} does not "
            "equal request.expected_parent_head "
            f"{request_obj['expected_parent_head']!r} — refusing before any transport call"
        )

    status, prs = transport.get(
        f"repos/{args.repo}/pulls?head={args.repo.split('/')[0]}:{args.branch}&state=open"
    )
    if not isinstance(prs, list) or len(prs) != 1:
        raise OutcomeLearningCliError(
            f"expected exactly one open PR for branch {args.branch!r}, found "
            f"{len(prs) if isinstance(prs, list) else 'a non-list response'}"
        )
    pr_summary = prs[0]
    _, pr = transport.get(f"repos/{args.repo}/pulls/{pr_summary['number']}")

    original_title = pr["title"]
    original_title_sha256 = _sha256_hex_text(original_title)
    head_sha = pr["head"]["sha"]

    preflight = {
        "observed_at": args.observed_at,
        "repository": args.repo,
        "pr_number": pr["number"],
        "pr_url": pr["html_url"],
        "head_sha": head_sha,
        "base_ref": pr["base"]["ref"],
        "original_title_sha256": original_title_sha256,
        "original_title_length": len(original_title),
        "sealed_commit_sha": args.sealed_commit,
        "expectation_blob_sha": expectation_blob_sha,
        "request_blob_sha": request_blob_sha,
        "expectation_content_sha256": expectation_content_sha256,
        "request_content_sha256": request_content_sha256,
        "head_equals_sealed_commit": head_sha == args.sealed_commit,
        "seal_provenance": "COMMITTED_BLOBS_VERIFIED",
    }
    validate_preflight(preflight)
    _write_artifact(out_path, preflight)
    print(f"head_equals_sealed_commit={preflight['head_equals_sealed_commit']}")
    print(f"seal_provenance={preflight['seal_provenance']}")
    return 0


# --------------------------------------------------------------------------- canary


def _make_call(
    seq: int,
    kind: str,
    endpoint: str,
    payload_sha: str,
    status: int | str,
    doc: Mapping[str, Any],
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "requested_at": recorded_at,
        "method": "PATCH",
        "endpoint": endpoint,
        "payload_title_sha256": payload_sha,
        "response_status": status,
        "readback": {
            "observed_at": recorded_at,
            "title_sha256": _sha256_hex_text(doc["title"]),
            "title_length": len(doc["title"]),
            "head_sha": doc["head"]["sha"],
        },
    }


def _reconcile(
    transport: GhTransport, endpoint: str
) -> dict[str, Any]:
    """EXACTLY one read-only reconciliation GET — never a retry of any PATCH. Returns
    the actually-observed post-effect state, or nulls when even the reconciliation
    itself failed (BLOCKER 1: the caller must then report "UNOBSERVED", never guess)."""
    try:
        _, doc = transport.get(endpoint)
        return {
            "attempted": True,
            "observed_title_sha256": _sha256_hex_text(doc["title"]),
            "observed_head_sha": doc["head"]["sha"],
        }
    except Exception:  # noqa: BLE001 - preserve EFFECT_UNKNOWN without a retry
        return {"attempted": True, "observed_title_sha256": None, "observed_head_sha": None}


#: BLOCKER D journal state machine (CLI-internal artifact — not an OL-V1 contract
#: schema): PREPARED is the atomic reservation; APPLY_SENT/APPLIED_READBACK/
#: RESTORE_SENT are the only non-terminal in-flight states; the three terminal
#: states are RESTORED / EFFECT_UNKNOWN / INVALIDATED_BEFORE_EFFECT. Any other value
#: on disk — including a crash mid-sequence — is fail-closed non-terminal.
_JOURNAL_TERMINAL_STATES = frozenset(
    {"RESTORED", "EFFECT_UNKNOWN", "INVALIDATED_BEFORE_EFFECT"}
)


def _reserve_journal(journal_path: Path, record: dict[str, Any]) -> None:
    """Atomically reserve the single-shot journal (BLOCKER D). ``open(..., 'x')``
    (exclusive create) is the ENTIRE single-shot guard: whichever of two racing
    invocations wins this call proceeds, and the other sees ``FileExistsError``
    unconditionally — regardless of what state a pre-existing reservation is in."""
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(journal_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        raise OutcomeLearningCliError(
            f"{journal_path} already exists — OL-V1 canary is single-shot per "
            "operation_key + expectation_sealed_hash within one --episode-dir "
            "(BLOCKER D: ANY pre-existing reservation, whatever its state, refuses; "
            "a different --episode-dir can only be stopped operationally by the "
            "supervised single-operator law — see the runbook)"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")


def _advance_journal(journal_path: Path, record: dict[str, Any]) -> None:
    """Atomically advance a reservation already on disk: write a temp file in the
    SAME directory, then ``os.replace`` over the reservation — a concurrent reader
    (or a crash) never observes a partially-written state."""
    tmp_path = journal_path.with_name(journal_path.name + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(tmp_path), str(journal_path))


def cmd_canary(
    args: argparse.Namespace, *, runner: Runner | None = None, transport: GhTransport | None = None
) -> int:
    """Apply-then-restore, no retry, ever.

    Sol REQUEST_REPAIR (BLOCKERS C + D, 2026-09-02): the canary request is REACQUIRED
    from its committed git blob (never trusted from the local ``--request`` file
    beyond locating that blob) and independently re-validated before anything else
    happens; the owner's exact branch selector is re-run to reprove there is still
    exactly one open PR whose number matches preflight, before the pre-effect
    freshness read. The derived journal is reserved via an atomic exclusive-create
    BEFORE any transport call at all — read or write — and advanced through an
    explicit state machine (PREPARED -> APPLY_SENT -> APPLIED_READBACK ->
    RESTORE_SENT -> a terminal state) so a crash after APPLY leaves a non-terminal
    reservation on disk that the next invocation refuses outright rather than
    replays. Any exception mid-sequence gets EXACTLY one read-only reconciliation GET
    (best effort) and the episode reports EFFECT_UNKNOWN; a completed apply call is
    always journaled honestly (BLOCKER 1's poststate law).
    """
    transport = transport or GhCliTransport()
    runner = runner or SubprocessRunner()
    episode_dir = _refuse_inside_repo(args.episode_dir, where="canary --episode-dir")

    preflight = _read_json(args.preflight)
    # Sol REQUEST_REPAIR: validate_preflight (including its seal_provenance ==
    # "COMMITTED_BLOBS_VERIFIED" check) runs BEFORE any transport call — a tampered
    # or absent seal_provenance raises here, so the episode never issues a single GET
    # or PATCH against a preflight this CLI cannot prove is committed-seal-verified.
    validate_preflight(preflight)

    # BLOCKER C: reacquire the canary request from its committed blob — a git-only
    # read, zero transport — and independently re-validate it. The local --request
    # file is never trusted beyond having pointed us at this preflight/blob in the
    # first place; every field used from here on is the REACQUIRED document.
    cat_file = runner.run(
        ["git", "cat-file", "-p", preflight["request_blob_sha"]], cwd=args.mastermind_root
    )
    if cat_file.returncode != 0:
        raise OutcomeLearningCliError(
            f"could not reacquire the committed request blob {preflight['request_blob_sha']}: "
            f"{cat_file.stderr.strip()}"
        )
    try:
        request = json.loads(cat_file.stdout)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(
            "reacquired committed request blob is not valid JSON"
        ) from exc
    validate_canary_request(request)
    reacquired_digest = canonical_digest(request).removeprefix("sha256:")
    if reacquired_digest != preflight["request_content_sha256"]:
        raise OutcomeLearningCliError(
            "reacquired committed request content does not match "
            f"preflight.request_content_sha256 (reacquired={reacquired_digest}, "
            f"preflight={preflight['request_content_sha256']})"
        )
    if request["repository"] != preflight["repository"]:
        raise OutcomeLearningCliError(
            f"reacquired request.repository {request['repository']!r} does not match "
            f"preflight.repository {preflight['repository']!r}"
        )

    if preflight["head_equals_sealed_commit"] is not True:
        raise OutcomeLearningCliError(
            "refusing to canary: preflight.head_equals_sealed_commit is not True"
        )

    journal_name = (
        f"canary_journal.{request['operation_key']}."
        f"{request['expectation_sealed_hash'][7:19]}.json"
    )
    journal_path = episode_dir / journal_name
    bound_identity = {
        "repository": request["repository"],
        "branch": request["branch"],
        "operation_key": request["operation_key"],
        "expectation_sealed_hash": request["expectation_sealed_hash"],
        "sealed_commit_sha": preflight["sealed_commit_sha"],
        "expected_parent_head": request["expected_parent_head"],
        "preflight_pr_number": preflight["pr_number"],
        "canary_token": request["canary_token"],
        "request_digest": reacquired_digest,
    }

    # BLOCKER D: the atomic reservation — before ANY transport call, read or write.
    _reserve_journal(
        journal_path,
        {"state": "PREPARED", "bound_identity": bound_identity, "recorded_at": args.recorded_at},
    )

    endpoint = f"repos/{request['repository']}/pulls/{preflight['pr_number']}"
    original_sha = preflight["original_title_sha256"]
    sealed_head = preflight["sealed_commit_sha"]

    # BLOCKER C: re-run the EXACT owner branch selector (never merely re-GET the
    # already-known PR number) — reproving there is still exactly one open PR for
    # this branch AND that its number agrees with preflight, before trusting
    # anything else the owner reports.
    _, prs = transport.get(
        f"repos/{request['repository']}/pulls?head="
        f"{request['repository'].split('/')[0]}:{request['branch']}&state=open"
    )
    selector_ok = (
        isinstance(prs, list)
        and len(prs) == 1
        and prs[0].get("number") == preflight["pr_number"]
    )
    if not selector_ok:
        _advance_journal(
            journal_path,
            {
                "state": "INVALIDATED_BEFORE_EFFECT",
                "bound_identity": bound_identity,
                "effect_calls": [],
                "reconciliation": None,
                "pre_effect_observation": None,
                "recorded_at": args.recorded_at,
            },
        )
        print(
            "effect_state=INVALIDATED_BEFORE_EFFECT (owner branch selector no longer "
            f"matches preflight: {prs!r})"
        )
        return 6

    # Pre-effect freshness gate (MAJOR 5 + BLOCKER E): read the live PR once, before
    # issuing any PATCH, and refuse outright — zero PATCHes — if it has drifted from
    # preflight. The exact observation is journaled honestly either way (BLOCKER E).
    _, current = transport.get(endpoint)
    live_head = current["head"]["sha"]
    live_title = current["title"]
    live_title_sha = _sha256_hex_text(live_title)
    pre_effect_observation = {
        "observed_head_sha": live_head,
        "observed_title_sha256": live_title_sha,
        "observed_title_length": len(live_title),
        "observed_at": args.recorded_at,
    }
    if live_head != sealed_head or live_title_sha != original_sha:
        _advance_journal(
            journal_path,
            {
                "state": "INVALIDATED_BEFORE_EFFECT",
                "bound_identity": bound_identity,
                "effect_calls": [],
                "reconciliation": None,
                "pre_effect_observation": pre_effect_observation,
                "recorded_at": args.recorded_at,
            },
        )
        print(f"effect_state=INVALIDATED_BEFORE_EFFECT (drift: {pre_effect_observation})")
        return 6

    original_title = live_title
    applied_title = original_title + " " + request["canary_token"]
    applied_sha = _sha256_hex_text(applied_title)

    _advance_journal(
        journal_path,
        {
            "state": "APPLY_SENT",
            "bound_identity": bound_identity,
            "pre_effect_observation": pre_effect_observation,
            "recorded_at": args.recorded_at,
        },
    )
    try:
        status1, applied_doc = transport.patch(endpoint, {"title": applied_title})
        call1 = _make_call(1, "TITLE_APPLY", endpoint, applied_sha, status1, applied_doc, args.recorded_at)
    except Exception:  # noqa: BLE001 - the apply may have crossed the effect boundary
        reconciliation = _reconcile(transport, endpoint)
        _advance_journal(
            journal_path,
            {
                "state": "EFFECT_UNKNOWN",
                "bound_identity": bound_identity,
                "effect_calls": [],
                "reconciliation": reconciliation,
                "pre_effect_observation": pre_effect_observation,
                "recorded_at": args.recorded_at,
            },
        )
        print("effect_state=EFFECT_UNKNOWN (apply raised)")
        return 3

    _advance_journal(
        journal_path,
        {
            "state": "APPLIED_READBACK",
            "bound_identity": bound_identity,
            "effect_calls": [call1],
            "pre_effect_observation": pre_effect_observation,
            "recorded_at": args.recorded_at,
        },
    )
    _advance_journal(
        journal_path,
        {
            "state": "RESTORE_SENT",
            "bound_identity": bound_identity,
            "effect_calls": [call1],
            "pre_effect_observation": pre_effect_observation,
            "recorded_at": args.recorded_at,
        },
    )
    try:
        # MAJOR 6: the restore payload's digest is computed from the title text
        # ACTUALLY SENT in this PATCH, never fetched indirectly from preflight.
        restore_payload_sha = _sha256_hex_text(original_title)
        status2, restored_doc = transport.patch(endpoint, {"title": original_title})
        call2 = _make_call(
            2, "TITLE_RESTORE", endpoint, restore_payload_sha, status2, restored_doc, args.recorded_at
        )
        clean = (
            call1["readback"]["title_sha256"] == applied_sha
            and call1["readback"]["head_sha"] == sealed_head
            and call2["readback"]["title_sha256"] == original_sha
            and call2["readback"]["head_sha"] == sealed_head
        )
        effect_calls = [call1, call2]
        state = "RESTORED" if clean else "EFFECT_UNKNOWN"
        reconciliation = None
    except Exception:  # noqa: BLE001 - the restore may have crossed the effect boundary
        # BLOCKER 1: the apply DID complete — call1 is real evidence and is journaled,
        # never discarded. The reconciliation GET's observed title (or UNOBSERVED, if
        # even that fails) becomes cmd_outcome's poststate — never a guessed "nothing
        # changed" over a PR that may still carry the mutated, unrestored title.
        reconciliation = _reconcile(transport, endpoint)
        effect_calls = [call1]
        state = "EFFECT_UNKNOWN"

    _advance_journal(
        journal_path,
        {
            "state": state,
            "bound_identity": bound_identity,
            "effect_calls": effect_calls,
            "reconciliation": reconciliation,
            "pre_effect_observation": pre_effect_observation,
            "recorded_at": args.recorded_at,
        },
    )
    if state == "EFFECT_UNKNOWN":
        print("effect_state=EFFECT_UNKNOWN")
        return 3
    print("effect_state=APPLIED_AND_RESTORED")
    return 0


# --------------------------------------------------------------------------- outcome


#: Journal state-machine terminal state -> outcome.effect_state (contracts) mapping.
_JOURNAL_STATE_TO_EFFECT_STATE = {
    "RESTORED": "APPLIED_AND_RESTORED",
    "EFFECT_UNKNOWN": "EFFECT_UNKNOWN",
    "INVALIDATED_BEFORE_EFFECT": "INVALIDATED_BEFORE_EFFECT",
}


def _derive_effect_edge(journal: Mapping[str, Any]) -> dict[str, bool]:
    """BLOCKER F: which Blocker B/C revalidations actually happened for this
    episode, honestly derived from the journal's own recorded control flow —
    ``cmd_canary`` raises BEFORE ever reserving a journal if request reacquisition,
    its digest check, or the repository cross-check fail, so any journal that exists
    at all proves those three; the owner-selector re-run is the first step that can
    leave a journal in INVALIDATED_BEFORE_EFFECT with no pre-effect observation."""
    state = journal["state"]
    selector_repeated_single_pr = not (
        state == "INVALIDATED_BEFORE_EFFECT" and journal.get("pre_effect_observation") is None
    )
    parent_proven = True
    request_reacquired_from_sealed_commit = True
    request_digest_matched = True
    bindings_verified = (
        parent_proven
        and request_reacquired_from_sealed_commit
        and request_digest_matched
        and selector_repeated_single_pr
    )
    return {
        "parent_proven": parent_proven,
        "request_reacquired_from_sealed_commit": request_reacquired_from_sealed_commit,
        "request_digest_matched": request_digest_matched,
        "selector_repeated_single_pr": selector_repeated_single_pr,
        "bindings_verified": bindings_verified,
    }


def cmd_outcome(args: argparse.Namespace) -> int:
    """Restoration is derived in strict priority order, honest evidence first
    (BLOCKER 1): a reconciliation GET that actually observed the live title is ground
    truth over anything else, including the calls' own readbacks — the reconciliation
    runs precisely because the calls could not be trusted. Only when there is truly no
    observation at all does poststate become the literal "UNOBSERVED".

    Sol REQUEST_REPAIR (BLOCKER D): a journal whose ``state`` is not one of the three
    terminal states (a crash mid-sequence) is refused outright — never replayed,
    never silently interpreted as any particular outcome.
    """
    journal = _read_json(args.journal)
    preflight = _read_json(args.preflight)
    expectation = _read_json(args.expectation)
    request = _read_json(args.request)

    journal_state = journal["state"]
    if journal_state not in _JOURNAL_TERMINAL_STATES:
        raise OutcomeLearningCliError(
            f"journal is in non-terminal state {journal_state!r} — refusing "
            "(BLOCKER D: a crash mid-sequence is never replayed and never "
            "interpreted as any particular outcome)"
        )
    effect_state = _JOURNAL_STATE_TO_EFFECT_STATE[journal_state]
    effect_calls = journal.get("effect_calls", [])
    reconciliation = journal.get("reconciliation")
    pre_effect_observation = journal.get("pre_effect_observation")
    original_sha = preflight["original_title_sha256"]
    sealed_head = preflight["sealed_commit_sha"]

    if effect_state == "INVALIDATED_BEFORE_EFFECT":
        # BLOCKER E: derive restoration HONESTLY from the exact pre-effect
        # observation that caused the refusal — never assume "zero PATCHes" means
        # "unchanged state". A selector-stage refusal (no freshness read reached)
        # has no observation at all, so poststate is the literal UNOBSERVED.
        if pre_effect_observation is None:
            restoration = {
                "byte_identical": None,
                "prestate_title_sha256": original_sha,
                "poststate_title_sha256": "UNOBSERVED",
                "head_unchanged": False,
            }
        else:
            observed_title = pre_effect_observation["observed_title_sha256"]
            observed_head = pre_effect_observation["observed_head_sha"]
            restoration = {
                "byte_identical": observed_title == original_sha,
                "prestate_title_sha256": original_sha,
                "poststate_title_sha256": observed_title,
                "head_unchanged": observed_head == sealed_head,
            }
    elif effect_state in {"APPLIED_AND_RESTORED", "NOT_ATTEMPTED"}:
        restoration = {
            "byte_identical": True,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": original_sha,
            "head_unchanged": True,
        }
    elif reconciliation is not None and reconciliation.get("observed_title_sha256") is not None:
        # EFFECT_UNKNOWN with a reconciliation GET that actually observed the live
        # title — the ground truth for "what state is the PR in right now".
        observed_title = reconciliation["observed_title_sha256"]
        observed_head = reconciliation.get("observed_head_sha")
        restoration = {
            "byte_identical": observed_title == original_sha,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": observed_title,
            "head_unchanged": observed_head == sealed_head,
        }
    elif reconciliation is not None:
        # Reconciliation was attempted but itself failed — genuinely no observed
        # post-effect state, so poststate is the literal UNOBSERVED, never a guess.
        restoration = {
            "byte_identical": None,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": "UNOBSERVED",
            "head_unchanged": False,
        }
    elif effect_calls:
        # No reconciliation was attempted (both calls completed without raising, but
        # their readbacks did not match expectations) — the calls' own evidence is
        # definitive; report what the last observed readback actually showed.
        last = effect_calls[-1]
        restoration = {
            "byte_identical": last["readback"]["title_sha256"] == original_sha,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": last["readback"]["title_sha256"],
            "head_unchanged": last["readback"]["head_sha"] == sealed_head,
        }
    else:
        # No calls and no reconciliation at all: genuinely no basis to claim anything.
        restoration = {
            "byte_identical": None,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": "UNOBSERVED",
            "head_unchanged": False,
        }

    # The journal keeps pre_effect_observation for every state once the freshness
    # GET has run (audit trail for cmd_canary's own control flow), but the outcome
    # contract permits it ONLY on the INVALIDATED_BEFORE_EFFECT terminal state — carry
    # it into the outcome exactly there, never on APPLIED_AND_RESTORED/EFFECT_UNKNOWN.
    outcome_pre_effect_observation = (
        pre_effect_observation if effect_state == "INVALIDATED_BEFORE_EFFECT" else None
    )
    outcome = build_outcome(
        operation_key=expectation["operation_key"],
        expectation_sealed_hash=expectation["sealed_hash"],
        request=request,
        preflight=preflight,
        effect_calls=effect_calls,
        effect_state=effect_state,
        restoration=restoration,
        pre_effect_observation=outcome_pre_effect_observation,
        effect_edge=_derive_effect_edge(journal),
        recorded_at=args.recorded_at,
    )
    _write_artifact(args.out, outcome)
    print(f"effect_state={outcome['effect_state']}")
    return 0


# --------------------------------------------------------------------------- evaluate / self-model / project


def cmd_evaluate(args: argparse.Namespace) -> int:
    expectation = _read_json(args.expectation)
    outcome = _read_json(args.outcome)
    request = _read_json(args.request)
    evaluation = evaluate_episode(expectation, outcome, request, recorded_at=args.recorded_at)
    _write_artifact(args.out, evaluation)
    print(f"causal_grade={evaluation['causal_grade']} promotion={evaluation['promotion']}")
    return 0


def cmd_self_model(args: argparse.Namespace) -> int:
    evaluation = _read_json(args.evaluation)
    expectation = _read_json(args.expectation)
    self_model = build_self_model(evaluation, expectation, recorded_at=args.recorded_at)
    _write_artifact(args.out, self_model)
    print(f"sample_size={self_model['sample_size']} promotion={self_model['promotion']}")
    return 0


def cmd_project(args: argparse.Namespace) -> int:
    evaluation = _read_json(args.evaluation)
    expectation = _read_json(args.expectation)
    outcome = _read_json(args.outcome)
    # key_hint is derived from recorded_at's own date, never hardcoded — the CLI
    # supplies it (evaluator.build_agentos_projection never invents its own "today").
    key_hint = f"OLV1-EPISODE-CONSEQUENCE-{args.recorded_at[:10]}"
    projection = build_agentos_projection(
        evaluation, expectation, outcome, recorded_at=args.recorded_at, key_hint=key_hint
    )
    _write_artifact(args.out, projection)
    print(f"candidates={len(projection['candidates'])}")
    return 0


# --------------------------------------------------------------------------- proof


def _proof_effect_state_bullets(outcome: Mapping[str, Any]) -> list[str]:
    """MAJOR 12 (principal review): the summary must never assert "applied, bounded
    to two calls with no retry" for an episode that did not actually apply anything —
    every bullet here is conditional on the outcome's REAL effect_state."""
    effect_state = outcome["effect_state"]
    restoration = outcome["restoration"]
    poststate = restoration["poststate_title_sha256"]
    byte_identical = restoration["byte_identical"]
    head_unchanged = restoration["head_unchanged"]

    if effect_state == "APPLIED_AND_RESTORED":
        return [
            "- Exactly one reversible GitHub PR-title canary effect was attempted, "
            "applied, and restored — bounded to two calls with no retry.",
            f"- Restoration was confirmed byte-identical: byte_identical=`{byte_identical}`, "
            f"head_unchanged=`{head_unchanged}`.",
        ]
    if effect_state == "EFFECT_UNKNOWN":
        bullets = [
            "- The episode attempted the canary effect and stopped on ambiguity "
            "rather than guessing or retrying — no second PATCH of either kind was "
            "ever issued.",
            f"- restoration.poststate_title_sha256=`{poststate}`, "
            f"byte_identical=`{byte_identical}`, head_unchanged=`{head_unchanged}`.",
        ]
        if poststate == "UNOBSERVED" or byte_identical is not True:
            bullets.append(
                "- **MANUAL RESTORATION MAY BE OWED** — the carrying PR's title was "
                "never confirmed restored to its original value. A human must check "
                "the PR directly before treating it as clean."
            )
        return bullets
    if effect_state == "INVALIDATED_BEFORE_EFFECT":
        return [
            "- The pre-effect freshness gate refused before any PATCH was issued — "
            "the live PR had already drifted from what preflight observed. Zero "
            "PATCHes were sent.",
        ]
    return ["- No effect was attempted this episode."]  # NOT_ATTEMPTED


def _verify_proof_chain(
    expectation: Mapping[str, Any],
    request: Mapping[str, Any],
    outcome: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    self_model: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> None:
    """Sol REQUEST_REPAIR (BLOCKER F, 2026-09-02): run every artifact's OWN validator,
    cross-bound against its neighbors, BEFORE a single proof line is rendered — never
    render a claim this CLI has not just mechanically re-checked. Each validator
    raises its own specific, named mismatch (digest mismatch, forbidden key, frozen
    value violated, ...); nothing here invents a new error message, it only refuses
    to skip the check."""
    validate_expectation(expectation)
    validate_canary_request(request)
    validate_outcome(outcome, expectation, request)
    validate_evaluation(evaluation, expectation, outcome)
    validate_self_model(self_model, evaluation)
    validate_agentos_projection(projection, evaluation)


def cmd_proof(args: argparse.Namespace) -> int:
    expectation = _read_json(args.expectation)
    request = _read_json(args.request)
    outcome = _read_json(args.outcome)
    evaluation = _read_json(args.evaluation)
    self_model = _read_json(args.self_model)
    projection = _read_json(args.projection)

    _verify_proof_chain(expectation, request, outcome, evaluation, self_model, projection)

    lines = [
        "# OL-V1 Production Proof",
        "",
        f"operation_key: `{expectation['operation_key']}`",
        "",
        "## Chronology",
        "",
        "| Step | Artifact | Digest |",
        "|---|---|---|",
        f"| 1. seal | expectation | `{expectation['sealed_hash']}` |",
        f"| 2. seal | canary request | `{canonical_digest(request)}` |",
        f"| 3. preflight | preflight receipt | `{canonical_digest(outcome['preflight'])}` |",
        f"| 4. canary+outcome | outcome | `{canonical_digest(outcome)}` |",
        f"| 5. evaluate | evaluation | `{canonical_digest(evaluation)}` |",
        f"| 6. self-model | self-model | `{canonical_digest(self_model)}` |",
        f"| 7. project | agentos projection | `{canonical_digest(projection)}` |",
        "",
        "## Preflight (embedded verbatim)",
        "",
        "```json",
        json.dumps(outcome["preflight"], indent=2, sort_keys=True),
        "```",
        "",
        "## Authority",
        "",
        f"- expectation_sealed_hash: `{expectation['sealed_hash']}`",
        f"- request_digest (A2): `{canonical_digest(request)}`",
        f"- decision_ref.id (A1 packet digest): `{expectation['decision_ref']['id']}`",
        f"- execution_authority_granted: `{request['execution_authority_granted']}`",
        "",
        "## What this proves",
        "",
        "- One sealed, prospective decision-expectation receipt existed before any effect.",
        *_proof_effect_state_bullets(outcome),
        "- The evaluation is DESCRIPTIVE_ONLY with promotion=NONE; the self-model is n=1, "
        "sample_state=INSUFFICIENT_SAMPLE, promotion=NONE, authority=NONE, "
        "universal_score=None.",
        "- The Agent OS projection carries candidate-only entries: automatic_writes=False, "
        "grants_authority=False, every candidate status=CANDIDATE_ONLY.",
        "",
        "## What this does NOT prove",
        "",
        "- Not broad memory efficacy — this is one episode, n=1.",
        "- Not executive competence — this exercises one narrow, supervised, reversible "
        "effect class.",
        "- Not route superiority — no alternative route was executed for comparison.",
        "- Not policy — nothing here changes any standing rule; the self-model and "
        "projection are non-promoting by construction.",
        "",
    ]
    _write_text_artifact(args.out, "\n".join(lines))
    print(f"wrote {args.out}")
    return 0


# --------------------------------------------------------------------------- argparse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_compose = sub.add_parser("compose", help="compose + evaluate one source bundle")
    p_compose.add_argument("--mastermind-root", required=True)
    p_compose.add_argument("--macro-root", required=True)
    p_compose.add_argument("--episode-dir", required=True)
    p_compose.add_argument(
        "--as-of",
        default=None,
        help=(
            "optional; when omitted, computed AFTER acquisition as the later of "
            "'now' and boot_packet.generated_at, so it can never postdate a receipt"
        ),
    )
    p_compose.add_argument(
        "--chairman-revision", default="conversation:chairman-completion-drive-20260902"
    )
    p_compose.add_argument("--operation-key", required=True)
    p_compose.add_argument("--agentos-records-digest", default=None)
    p_compose.set_defaults(func=cmd_compose)

    p_seal = sub.add_parser("seal", help="seal the expectation receipt + canary request")
    p_seal.add_argument("--composition", required=True)
    p_seal.add_argument("--episode-dir", required=True)
    p_seal.add_argument(
        "--parent-head",
        default=None,
        help="optional cross-check only (BLOCKER B): must exactly equal the adjudicated option's expected_head_sha, which is what is actually used",
    )
    p_seal.add_argument("--recorded-at", required=True)
    p_seal.add_argument(
        "--operation-key",
        default=None,
        help="optional cross-check only (BLOCKER B): must exactly equal the adjudicated option's operation_key, which is what is actually used",
    )
    p_seal.add_argument("--out-expectation", required=True)
    p_seal.add_argument("--out-request", required=True)
    p_seal.set_defaults(func=cmd_seal)

    p_preflight = sub.add_parser("preflight", help="build the external preflight receipt")
    p_preflight.add_argument("--repo", required=True)
    p_preflight.add_argument("--branch", required=True)
    p_preflight.add_argument("--sealed-commit", required=True)
    p_preflight.add_argument("--expectation", required=True)
    p_preflight.add_argument("--request", required=True)
    p_preflight.add_argument(
        "--expectation-repo-path",
        required=True,
        help="repo-relative path proving the expectation is committed at --sealed-commit (no local fallback)",
    )
    p_preflight.add_argument(
        "--request-repo-path",
        required=True,
        help="repo-relative path proving the canary request is committed at --sealed-commit (no local fallback)",
    )
    p_preflight.add_argument(
        "--mastermind-root",
        default=None,
        help="explicit cwd for the git blob-provenance calls (default: this process's cwd)",
    )
    p_preflight.add_argument("--observed-at", required=True)
    p_preflight.add_argument("--out", required=True)
    p_preflight.set_defaults(func=cmd_preflight)

    p_canary = sub.add_parser("canary", help="apply the two-call PR-title canary")
    p_canary.add_argument("--preflight", required=True)
    p_canary.add_argument(
        "--request",
        required=True,
        help=(
            "kept for operator bookkeeping/consistency only — Sol REQUEST_REPAIR "
            "(BLOCKER C) reacquires the actual request content from its committed "
            "blob (preflight.request_blob_sha) and never reads this file's bytes"
        ),
    )
    p_canary.add_argument(
        "--mastermind-root",
        default=None,
        help="explicit cwd for the committed-blob reacquisition git call (BLOCKER C)",
    )
    p_canary.add_argument("--recorded-at", required=True)
    p_canary.add_argument(
        "--episode-dir",
        required=True,
        help=(
            "outside the repo; the journal filename is DERIVED from operation_key + "
            "expectation_sealed_hash (BLOCKER 2) — there is no --out-journal override"
        ),
    )
    p_canary.set_defaults(func=cmd_canary)

    p_outcome = sub.add_parser("outcome", help="assemble + validate the outcome artifact")
    p_outcome.add_argument("--journal", required=True)
    p_outcome.add_argument("--preflight", required=True)
    p_outcome.add_argument("--expectation", required=True)
    p_outcome.add_argument("--request", required=True)
    p_outcome.add_argument("--recorded-at", required=True)
    p_outcome.add_argument("--out", required=True)
    p_outcome.set_defaults(func=cmd_outcome)

    p_evaluate = sub.add_parser("evaluate", help="deterministic DESCRIPTIVE_ONLY evaluation")
    p_evaluate.add_argument("--expectation", required=True)
    p_evaluate.add_argument("--outcome", required=True)
    p_evaluate.add_argument("--request", required=True)
    p_evaluate.add_argument("--recorded-at", required=True)
    p_evaluate.add_argument("--out", required=True)
    p_evaluate.set_defaults(func=cmd_evaluate)

    p_self_model = sub.add_parser("self-model", help="n=1 non-promoting self-model")
    p_self_model.add_argument("--evaluation", required=True)
    p_self_model.add_argument("--expectation", required=True)
    p_self_model.add_argument("--recorded-at", required=True)
    p_self_model.add_argument("--out", required=True)
    p_self_model.set_defaults(func=cmd_self_model)

    p_project = sub.add_parser("project", help="candidate-only Agent OS projection")
    p_project.add_argument("--evaluation", required=True)
    p_project.add_argument("--expectation", required=True)
    p_project.add_argument("--outcome", required=True)
    p_project.add_argument("--recorded-at", required=True)
    p_project.add_argument("--out", required=True)
    p_project.set_defaults(func=cmd_project)

    p_proof = sub.add_parser("proof", help="render the production-proof markdown")
    p_proof.add_argument("--expectation", required=True)
    p_proof.add_argument("--request", required=True)
    p_proof.add_argument("--outcome", required=True)
    p_proof.add_argument("--evaluation", required=True)
    p_proof.add_argument("--self-model", dest="self_model", required=True)
    p_proof.add_argument("--project", dest="projection", required=True)
    p_proof.add_argument("--out", required=True)
    p_proof.set_defaults(func=cmd_proof)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        OutcomeLearningCliError,
        OutcomeLearningContractError,
        ChairmanCognitionSourceError,
        ChairmanCognitionError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
