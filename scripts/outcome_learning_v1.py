#!/usr/bin/env python3
"""Outcome Learning V1 (OL-V1) — one sealed prospective episode, end to end.

Subcommands mirror the bounded learning sequence:

    compose              -> acquire current owners + trusted directive; preserve A1 frontier
    seal                 -> bind an exact accepted packet selection, expectation, and request
    preflight             -> prove committed prerequisite blobs and one exact carrier
    canary                -> run the two-call reversible effect or stop without retry
    outcome               -> derive the observed result from the canonical host journal
    evaluate              -> deterministic DESCRIPTIVE_ONLY evaluation + optional revision 1
    self-model            -> n=1 non-promoting self-model
    project               -> candidate-only Agent OS projection
    capture-publication   -> read exact remote branch/PR/commit/check evidence; never write
    mature-evaluation     -> append one delayed CI correction from exact owner evidence
    proof                 -> local candidate by default; production only with both remote receipts

Every GitHub call goes through an injectable :class:`GhTransport`; every git/subprocess
call goes through an injectable :class:`Runner`. The defaults shell out to ``gh``/``git``/
``python3``. This module is the only OL-V1 I/O shell; the contract and evaluator modules
remain pure. Publication and maturation commands have no GitHub write path. A production
proof is an external attestation about an immutable subject commit and is refused inside
the repository, preventing a self-referential proof commit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from control_plane.outcome_learning_contracts import (  # noqa: E402
    CANARY_TOKEN,
    OWNER_RENAME_EVENT_SCHEMA,
    PRIVACY_CLASS,
    OutcomeLearningContractError,
    build_canary_request,
    build_correction_revision,
    build_expectation,
    build_github_check_evidence,
    build_initial_artifact_revision,
    build_outcome,
    build_remote_publication_receipt,
    canonical_digest,
    scan_public_safe_text,
    validate_agentos_projection,
    validate_artifact_revision,
    validate_canary_request,
    validate_evaluation,
    validate_expectation,
    validate_effect_attempts,
    validate_effect_calls,
    validate_outcome,
    validate_owner_event_baseline,
    validate_preflight,
    validate_remote_publication_receipt,
    validate_revision_chain,
    validate_self_model,
)
from control_plane.outcome_learning_evaluator import (  # noqa: E402
    build_agentos_projection,
    build_self_model,
    evaluate_episode,
    mature_ci_evaluation,
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
_OPT_CANARY = "OPT-OLV1-PR-TITLE-CANARY"
_OPT_HOLD = "OPT-OLV1-PORTFOLIO-HOLD"
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WORKSTREAM_REF = "WS:AGENT-EVAL-FABRIC"
_CARRIER_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_CARRIER_BRANCH = "sol/outcome-learning-v1-complete-vertical-20260902"
_CARRIER_PR_NUMBER = 398
_CARRIER_REF = f"github:Mastermind:branch:{_CARRIER_BRANCH}"
_EXPECTATION_REPO_PATH = "research/outcome_learning/OLV1_EXPECTATION.json"
_REQUEST_REPO_PATH = "research/outcome_learning/OLV1_CANARY_REQUEST.json"
_PREFLIGHT_REPO_PATH = "research/outcome_learning/OLV1_PREFLIGHT.json"
_OUTCOME_REPO_PATH = "research/outcome_learning/OLV1_OUTCOME.json"
_EVALUATION_V1_REPO_PATH = "research/outcome_learning/OLV1_EVALUATION_V1.json"
_REVISION_V1_REPO_PATH = (
    "research/outcome_learning/OLV1_EVALUATION_REVISION_1.json"
)
_EVALUATION_V2_REPO_PATH = "research/outcome_learning/OLV1_EVALUATION_V2.json"
_REVISION_V2_REPO_PATH = (
    "research/outcome_learning/OLV1_EVALUATION_REVISION_2.json"
)
_SELF_MODEL_V2_REPO_PATH = "research/outcome_learning/OLV1_SELF_MODEL_V2.json"
_PROJECTION_V2_REPO_PATH = (
    "research/outcome_learning/OLV1_AGENTOS_PROJECTION_V2.json"
)
_DIRECTIVE_SCHEMA = "mastermind.olv1_directive.v1"
_SELECTION_SCHEMA = "mastermind.olv1_selection.v1"
_DIRECTIVE_AUTHORITY_CEILING = "COMPOSE_ONLY_NO_EFFECT_NO_PROMOTION"
_SELECTION_AUTHORITY_CEILING = "SEAL_ONLY_NO_EFFECT_NO_PROMOTION"
_EXECUTIVE_CONFIG_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/control.json"
)
_CANONICAL_JOURNAL_ROOT = Path(
    "/Library/Application Support/MastermindExecutive/state/"
    "outcome-learning-v1/journals"
)


class OutcomeLearningCliError(RuntimeError):
    """A CLI-level failure: bad input, refused write location, transport failure."""


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemUtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


_SYSTEM_CLOCK: Clock = SystemUtcClock()


def _parse_iso_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OutcomeLearningCliError(f"timestamp is not canonical UTC RFC3339: {value!r}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OutcomeLearningCliError(
            f"timestamp is not canonical UTC RFC3339: {value!r}"
        ) from exc
    if parsed.tzinfo != timezone.utc:
        raise OutcomeLearningCliError(f"timestamp is not UTC: {value!r}")
    return parsed


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise OutcomeLearningCliError("clock returned a naive datetime")
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _event_time(clock: Clock | None = None, *, after: str | None = None) -> str:
    value = (clock or _SYSTEM_CLOCK).now()
    if value.tzinfo is None:
        raise OutcomeLearningCliError("clock returned a naive datetime")
    value = value.astimezone(timezone.utc)
    if after is not None:
        floor = _parse_iso_utc(after)
        if value <= floor:
            value = floor + timedelta(microseconds=1)
    return _format_utc(value)


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


def _carrier_ref(repository: str, branch: str) -> str:
    return f"github:{repository.split('/')[-1]}:branch:{branch}"


def _episode_identity(
    expectation: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    validate_expectation(expectation)
    validate_canary_request(request)
    if request["operation_key"] != expectation["operation_key"]:
        raise OutcomeLearningCliError(
            "request operation_key does not match expectation"
        )
    if request["expectation_sealed_hash"] != expectation["sealed_hash"]:
        raise OutcomeLearningCliError(
            "request expectation_sealed_hash does not match expectation"
        )
    return {
        "operation_key": expectation["operation_key"],
        "carrier_ref": _carrier_ref(request["repository"], request["branch"]),
        "expectation_sealed_hash": expectation["sealed_hash"],
        "request_digest": canonical_digest(request),
    }


def _artifact_digest_at_commit(
    runner: Runner,
    mastermind_root: str | None,
    commit_sha: str,
    repo_path: str,
) -> dict[str, Any]:
    normalized = _normalize_repo_path(repo_path, where="publication artifact")
    if not normalized.startswith("research/outcome_learning/"):
        raise OutcomeLearningCliError(
            "publication artifacts must stay under research/outcome_learning/"
        )
    blob_sha, text = _resolve_committed_blob(
        runner,
        mastermind_root,
        commit_sha,
        normalized,
        where="publication artifact",
    )
    if _SHA40_RE.fullmatch(blob_sha) is None:
        raise OutcomeLearningCliError(
            f"publication artifact {normalized!r} resolved to invalid blob sha {blob_sha!r}"
        )
    return {
        "path": normalized,
        "blob_sha": blob_sha,
        "content_digest": f"sha256:{_sha256_hex_text(text)}",
    }


def _extract_remote_sha(doc: Any, *, where: str) -> str:
    try:
        if where == "branch":
            value = doc["object"]["sha"]
        else:
            value = doc["head"]["sha"]
    except (KeyError, TypeError) as exc:
        raise OutcomeLearningCliError(
            f"GitHub {where} readback did not contain a head sha"
        ) from exc
    if not isinstance(value, str) or _SHA40_RE.fullmatch(value) is None:
        raise OutcomeLearningCliError(f"GitHub {where} readback sha is invalid")
    return value


def _normalized_check_evidence(
    raw: Mapping[str, Any],
    *,
    repository: str,
    expected_commit_sha: str,
    observed_at: str,
) -> dict[str, Any]:
    if raw.get("head_sha") != expected_commit_sha:
        raise OutcomeLearningCliError(
            "GitHub check run is not bound to the exact evidence commit"
        )
    check_run_id = raw.get("id")
    check_name = raw.get("name")
    status = raw.get("status")
    conclusion = raw.get("conclusion")
    if type(check_run_id) is not int or check_run_id <= 0:
        raise OutcomeLearningCliError("GitHub check run id is invalid")
    if not isinstance(check_name, str) or not check_name:
        raise OutcomeLearningCliError("GitHub check run name is invalid")
    if status != "completed" or not isinstance(conclusion, str):
        raise OutcomeLearningCliError(
            "GitHub check run is not terminal and therefore cannot mature evidence"
        )
    return build_github_check_evidence(
        repository=repository,
        commit_sha=expected_commit_sha,
        check_run_id=check_run_id,
        check_name=check_name,
        status=status,
        conclusion=conclusion,
        observed_at=observed_at,
    )


def _check_runs_page(
    transport: GhTransport, repository: str, commit_sha: str
) -> list[Mapping[str, Any]]:
    _, doc = transport.get(
        f"repos/{repository}/commits/{commit_sha}/check-runs?filter=latest&per_page=100"
    )
    if not isinstance(doc, Mapping):
        raise OutcomeLearningCliError("GitHub check-runs response was not a mapping")
    total_count = doc.get("total_count")
    raw_checks = doc.get("check_runs")
    if type(total_count) is not int or total_count < 0 or not isinstance(raw_checks, list):
        raise OutcomeLearningCliError(
            "GitHub check-runs response lacks total_count/check_runs"
        )
    if total_count != len(raw_checks):
        raise OutcomeLearningCliError(
            "incomplete check-run page: GitHub reported "
            f"total_count={total_count} but returned {len(raw_checks)}; refusing partial evidence"
        )
    return raw_checks


def _require_commit_ancestor(
    runner: Runner,
    mastermind_root: str | None,
    ancestor_sha: str,
    descendant_sha: str,
) -> None:
    result = runner.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        cwd=mastermind_root,
    )
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"final commit {descendant_sha} must descend from the frozen evidence commit "
            f"{ancestor_sha}"
        )


def _json_artifact_content_digest(doc: Mapping[str, Any]) -> str:
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    return f"sha256:{_sha256_hex_text(text)}"


def _require_exact_artifact_contents(
    receipt: Mapping[str, Any],
    expected_docs: Mapping[str, Mapping[str, Any]],
    *,
    where: str,
) -> None:
    available = {
        artifact["path"]: artifact["content_digest"]
        for artifact in receipt["artifact_digests"]
    }
    missing_or_mismatched = {
        path: _json_artifact_content_digest(doc)
        for path, doc in expected_docs.items()
        if available.get(path) != _json_artifact_content_digest(doc)
    }
    if missing_or_mismatched:
        raise OutcomeLearningCliError(
            f"{where} receipt does not contain every exact committed artifact at its "
            f"canonical path: missing_or_mismatched={missing_or_mismatched}"
        )


def _verify_receipt_artifacts_at_commit(
    receipt: Mapping[str, Any],
    *,
    runner: Runner,
    mastermind_root: str | None,
) -> None:
    target = receipt["target_commit_sha"]
    for expected in receipt["artifact_digests"]:
        observed = _artifact_digest_at_commit(
            runner,
            mastermind_root,
            target,
            expected["path"],
        )
        if observed != expected:
            raise OutcomeLearningCliError(
                "remote publication receipt artifact does not match the exact committed "
                f"blob/content at {target}:{expected['path']}"
            )


def _check_identity(check: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        check["repository"],
        check["commit_sha"],
        check["check_run_id"],
        check["check_name"],
        check["status"],
        check["conclusion"],
    )


def _verify_live_final_receipt(
    receipt: Mapping[str, Any], *, transport: GhTransport
) -> None:
    repository = receipt["repository"]
    target = receipt["target_commit_sha"]
    _, branch_doc = transport.get(
        f"repos/{repository}/git/ref/heads/{receipt['branch']}"
    )
    branch_sha = _extract_remote_sha(branch_doc, where="branch")
    if branch_sha != target:
        raise OutcomeLearningCliError(
            f"remote branch head {branch_sha} does not equal final proof target {target}"
        )
    _, pr_doc = transport.get(f"repos/{repository}/pulls/{receipt['pr_number']}")
    pr_sha = _extract_remote_sha(pr_doc, where="PR")
    if pr_sha != target:
        raise OutcomeLearningCliError(
            f"remote PR head {pr_sha} does not equal final proof target {target}"
        )
    observed_at = receipt["observed_at"]
    live_checks = [
        _normalized_check_evidence(
            raw,
            repository=repository,
            expected_commit_sha=target,
            observed_at=observed_at,
        )
        for raw in _check_runs_page(transport, repository, target)
    ]
    if Counter(_check_identity(check) for check in live_checks) != Counter(
        _check_identity(check) for check in receipt["checks"]
    ):
        raise OutcomeLearningCliError(
            "live final check-run set does not equal the final publication receipt"
        )


def _verify_live_owner_check(
    owner_check: Mapping[str, Any], *, transport: GhTransport
) -> None:
    repository = owner_check["repository"]
    commit_sha = owner_check["commit_sha"]
    _, raw = transport.get(
        f"repos/{repository}/check-runs/{owner_check['check_run_id']}"
    )
    if not isinstance(raw, Mapping):
        raise OutcomeLearningCliError(
            "GitHub check-run-id response was not a mapping"
        )
    observed = _normalized_check_evidence(
        raw,
        repository=repository,
        expected_commit_sha=commit_sha,
        observed_at=owner_check["observed_at"],
    )
    if _check_identity(observed) != _check_identity(owner_check):
        raise OutcomeLearningCliError(
            "live frozen-commit owner check does not equal the evaluation revision receipt"
        )


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
    fields = [
        field
        for field in revision.split(";")
        if field and not field.startswith(prefix)
    ]
    fields.append(f"{label}:{digest}")
    return ";".join(fields)


def _add_binding_if_absent(revision: str, label: str, digest: str) -> str:
    """Accumulate-semantics: multiple distinct tokens for the same ``label`` may
    coexist (used for classification-sha256, one per option classified against this
    same chairman receipt) — mirrors ``_bind_bundle`` in
    ``tests/test_chairman_cognition_sources.py``."""
    token = f"{label}:{digest}"
    fields = [field for field in revision.split(";") if field]
    if token not in fields:
        fields.append(token)
    return ";".join(fields)


def _olv1_envelope(
    carrier_head: str, *, chairman_source_ref: str, expires_at: str
) -> dict[str, Any]:
    return {
        "schema": _ENVELOPE_SCHEMA,
        "envelope_id": f"ENV-OLV1-{carrier_head[:12]}",
        "authority_source_refs": [chairman_source_ref],
        "mode": "SUPERVISED_LIVE_CANARY",
        "allowed_actions": ["REVERSIBLE_RUNTIME_CANARY"],
        "allowed_reversibility": ["REVERSIBLE"],
        "allowed_repositories": ["mastermindx-market-intelligence/Mastermind"],
        "allowed_path_prefixes": {
            "mastermindx-market-intelligence/Mastermind": ["research/outcome_learning"]
        },
        "allowed_scope_prefixes": ["WS:OUTCOME-LEARNING-POLICY-CALIBRATION"],
        "allowed_carrier_prefixes": [_CARRIER_REF],
        "max_budget_units": 5,
        "max_active_children": 1,
        "require_exact_carrier": True,
        "expires_at": expires_at,
    }


def _olv1_options(
    operation_key: str, carrier_head: str, *, chairman_source_ref: str
) -> list[dict[str, Any]]:
    source_refs = [chairman_source_ref, _STRATEGIC_SOURCE_REF, _AGENT_OS_SOURCE_REF]
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
        "carrier_ref": _CARRIER_REF,
        "expected_head_sha": carrier_head,
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
            "carrying PR remains HOLD throughout the canary. Canary success alone "
            "authorizes neither a Ready transition nor merge; only the later, complete, "
            "independently accepted evidence chain may enter release review."
        ),
        "falsifier": (
            "Any second apply call, a non-identical restoration, or head movement "
            "during the effect falsifies this option's premise."
        ),
        "classification_source_ref": chairman_source_ref,
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
        "reversibility": "READ_ONLY",
        "source_refs": source_refs,
        "scope_refs": ["WS:OUTCOME-LEARNING-POLICY-CALIBRATION"],
        "effect_state": "NONE",
        "operation_key": operation_key,
        "carrier_state": "EXACT_EXISTING",
        "carrier_ref": _CARRIER_REF,
        "expected_head_sha": carrier_head,
        "repositories": ["mastermindx-market-intelligence/Mastermind"],
        "paths": [],
        "budget_units": 0,
        "active_children_after": 0,
        "creates_duplicate_control_plane": False,
        "stop_condition": "No effect; the vertical returns a typed blocker instead.",
        "rollback_plan": "No effect; the vertical returns a typed blocker instead.",
        "falsifier": "No effect; the vertical returns a typed blocker instead.",
        "classification_source_ref": chairman_source_ref,
        "change_classes": ["RESEARCH"],
        "affected_departments": ["executive"],
        "benefits": {
            "strategic_leverage": 5,
            "dependency_unlock": 0,
            "learning_value": 10,
            "chairman_load_reduction": 0,
            "user_or_machine_value": 0,
        },
        "costs": {
            "time_to_evidence": 90,
            "execution_cost": 0,
            "coordination_risk": 0,
            "irreversibility_risk": 0,
            "scarce_cognition_cost": 0,
        },
    }
    return [canary, hold]


def _canonical_objective(value: Any, *, where: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise OutcomeLearningCliError(f"{where}.objective must be canonical JSON text")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(f"{where}.objective is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise OutcomeLearningCliError(f"{where}.objective must decode to a mapping")
    canonical = json.dumps(
        parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    if canonical != value:
        raise OutcomeLearningCliError(f"{where}.objective is not canonical JSON")
    return parsed


def _closed_objective(
    value: Mapping[str, Any], *, required: set[str], where: str
) -> dict[str, Any]:
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing or extra:
        raise OutcomeLearningCliError(
            f"{where} objective has missing={sorted(missing)} extra={sorted(extra)}"
        )
    return dict(value)


def _intent_status(
    runner: Runner, mastermind_root: str, target: str
) -> dict[str, Any]:
    result = runner.run(
        [
            "python3",
            "scripts/ceo_intent.py",
            "--json",
            "--config",
            str(_EXECUTIVE_CONFIG_PATH),
            "status",
            target,
        ],
        cwd=mastermind_root,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unavailable"
        raise OutcomeLearningCliError(
            f"canonical ceo_intent status for {target!r} failed: {detail}"
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(
            f"canonical ceo_intent status for {target!r} was not JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise OutcomeLearningCliError(
            f"canonical ceo_intent status for {target!r} was not a mapping"
        )
    return payload


def _acquire_trusted_intent(
    runner: Runner,
    mastermind_root: str,
    intent_id: str,
    *,
    mastermind_sha: str,
    macro_sha: str,
    expected_schema: str,
) -> dict[str, Any]:
    receipt = _intent_status(runner, mastermind_root, intent_id)
    if receipt.get("schema") not in {
        "mastermind.ceo_intent_receipt.v1",
        "mastermind.ceo_intent_receipt.v2",
    }:
        raise OutcomeLearningCliError("canonical intent receipt schema is unsupported")
    fingerprint = receipt.get("fingerprint")
    job_id = receipt.get("job_id")
    if (
        receipt.get("intent_id") != intent_id
        or not isinstance(fingerprint, str)
        or _SHA256_RE.fullmatch(fingerprint) is None
        or not isinstance(job_id, str)
        or not job_id
        or receipt.get("accepted") is not True
        or receipt.get("dispatched") is not False
        or receipt.get("status") != "QUEUED"
    ):
        raise OutcomeLearningCliError(
            "canonical intent receipt is not one accepted, undispatched QUEUED intent"
        )
    authority = receipt.get("authority")
    if not isinstance(authority, dict) or authority.get("requested") != ["READ"]:
        raise OutcomeLearningCliError(
            "canonical intent receipt exceeds the READ-only OL-V1 authority ceiling"
        )
    grounding = receipt.get("grounding")
    if not isinstance(grounding, dict) or (
        grounding.get("mastermind_sha") != mastermind_sha
        or grounding.get("macro_sha") != macro_sha
    ):
        raise OutcomeLearningCliError(
            "canonical intent grounding does not match the exact Mastermind/Macro source"
        )
    created_at_ms = receipt.get("created_at_ms")
    if not isinstance(created_at_ms, int) or created_at_ms <= 0:
        raise OutcomeLearningCliError("canonical intent receipt has no valid created_at_ms")

    job = _intent_status(runner, mastermind_root, job_id)
    if (
        job.get("job_id") != job_id
        or job.get("status") != "QUEUED"
        or job.get("attempt_count") != 0
        or job.get("current_attempt_id") is not None
        or job.get("checkpoint") is not None
        or job.get("result") is not None
        or job.get("requested_authorities") != ["READ"]
        or job.get("authority_level") != "A0"
        or job.get("branch") is not None
        or job.get("worktree") is not None
        or job.get("allowed_write_paths") != []
        or job.get("validation_commands") != []
    ):
        raise OutcomeLearningCliError(
            "canonical intent Job is not an untouched READ-only admission"
        )
    objective = _canonical_objective(job.get("objective"), where=expected_schema)
    if objective.get("schema") != expected_schema:
        raise OutcomeLearningCliError(
            f"canonical intent objective schema is not {expected_schema}"
        )
    observed_at = _format_utc(
        datetime.fromtimestamp(created_at_ms / 1000, tz=timezone.utc)
    )
    source_ref = f"CEO_INTENT:{intent_id}:sha256:{fingerprint}"
    if len(source_ref) > 256:
        raise OutcomeLearningCliError("canonical intent source_ref exceeds 256 characters")
    return {
        "receipt": receipt,
        "job": job,
        "objective": objective,
        "observed_at": observed_at,
        "source_ref": source_ref,
        "receipt_digest": canonical_digest(receipt),
    }


def _validate_directive(
    acquired: Mapping[str, Any], *, operation_key: str, as_of: str
) -> dict[str, Any]:
    objective = _closed_objective(
        acquired["objective"],
        required={
            "schema",
            "workstream",
            "operation_key",
            "carrier_ref",
            "expires_at",
            "authority_ceiling",
        },
        where="directive",
    )
    expected = {
        "schema": _DIRECTIVE_SCHEMA,
        "workstream": _WORKSTREAM_REF,
        "operation_key": operation_key,
        "carrier_ref": _CARRIER_REF,
        "authority_ceiling": _DIRECTIVE_AUTHORITY_CEILING,
    }
    for field, value in expected.items():
        if objective.get(field) != value:
            raise OutcomeLearningCliError(
                f"directive objective {field}={objective.get(field)!r} does not equal {value!r}"
            )
    if _parse_iso_utc(acquired["observed_at"]) > _parse_iso_utc(as_of):
        raise OutcomeLearningCliError("directive receipt postdates composition as_of")
    if _parse_iso_utc(objective["expires_at"]) <= _parse_iso_utc(as_of):
        raise OutcomeLearningCliError("directive objective is expired at composition as_of")
    return objective


def _validate_selection(
    acquired: Mapping[str, Any],
    *,
    operation_key: str,
    packet_digest: str,
    chosen_option_id: str,
    carrier_ref: str,
    packet_as_of: str,
) -> dict[str, Any]:
    objective = _closed_objective(
        acquired["objective"],
        required={
            "schema",
            "workstream",
            "operation_key",
            "packet_digest",
            "chosen_option_id",
            "carrier_ref",
            "authority_ceiling",
        },
        where="selection",
    )
    expected = {
        "schema": _SELECTION_SCHEMA,
        "workstream": _WORKSTREAM_REF,
        "operation_key": operation_key,
        "packet_digest": packet_digest,
        "chosen_option_id": chosen_option_id,
        "carrier_ref": carrier_ref,
        "authority_ceiling": _SELECTION_AUTHORITY_CEILING,
    }
    for field, value in expected.items():
        if objective.get(field) != value:
            raise OutcomeLearningCliError(
                f"selection objective {field}={objective.get(field)!r} does not equal {value!r}"
            )
    if _parse_iso_utc(acquired["observed_at"]) <= _parse_iso_utc(packet_as_of):
        raise OutcomeLearningCliError(
            "selection intent must be accepted strictly after the packet source cutoff"
        )
    return objective


# Sol REQUEST_REPAIR (BLOCKER A, 2026-09-02): canonical identity is resolved against
# these exact GitHub remotes — never a local checkout's own branch name or working
# tree, which a dirty/detached/mutated local checkout could otherwise self-attest.
_CANONICAL_MASTERMIND_URL = "https://github.com/mastermindx-market-intelligence/Mastermind.git"
_CANONICAL_MASTERMIND_REPO = _CARRIER_REPOSITORY
# The canonical Macro remote is owned by data_layer/macro_refresh.py's authenticated
# seam (MACRO_GIT_REMOTE, DEC:B1-MACRO-PRIVATE-CUTOVER): Macro is flipping
# public -> private, and tests/test_no_anonymous_macro_reads.py forbids any other
# surface from carrying an anonymous Macro read literal. Reusing the seam's value
# (env override first, then its one allowlisted default) keeps a single owner of
# that identity — a narrowly justified cross-module reuse per review 5109215567's
# "reuse current protected source-continuity/owner primitives" instruction.
from data_layer.macro_refresh import _REMOTE as _CANONICAL_MACRO_URL  # noqa: E402
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


def _acquire_carrier_head(runner: Runner) -> str:
    """Acquire the exact action-time PR carrier independently from protected master.

    Protected ``master`` owns source law. The existing branch + open PR own the
    reversible effect carrier. Conflating those SHAs makes a multi-commit PR impossible
    to seal honestly, so both owner views are reacquired and must agree exactly.
    """
    branch_ref = f"refs/heads/{_CARRIER_BRANCH}"
    branch_sha = _ls_remote_sha(runner, _CANONICAL_MASTERMIND_URL, branch_ref)
    endpoint = f"repos/{_CARRIER_REPOSITORY}/pulls/{_CARRIER_PR_NUMBER}"
    result = runner.run(["gh", "api", endpoint])
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            f"carrier PR {_CARRIER_PR_NUMBER} could not be acquired: "
            f"{result.stderr.strip()}"
        )
    try:
        pr = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError("carrier PR payload is not valid JSON") from exc
    if not isinstance(pr, Mapping):
        raise OutcomeLearningCliError("carrier PR payload is not a mapping")

    head = pr.get("head")
    base = pr.get("base")
    if not isinstance(head, Mapping) or not isinstance(base, Mapping):
        raise OutcomeLearningCliError("carrier PR payload lacks closed head/base identity")
    head_repo = head.get("repo")
    base_repo = base.get("repo")
    if not isinstance(head_repo, Mapping) or not isinstance(base_repo, Mapping):
        raise OutcomeLearningCliError("carrier PR payload lacks repository ownership")

    if pr.get("number") != _CARRIER_PR_NUMBER:
        raise OutcomeLearningCliError("carrier PR number does not match the frozen carrier")
    if pr.get("state") != "open" or pr.get("merged") is True:
        raise OutcomeLearningCliError("carrier PR is not open and unmerged")
    if head_repo.get("full_name") != _CARRIER_REPOSITORY:
        raise OutcomeLearningCliError("carrier PR head repository is not the canonical owner")
    if base_repo.get("full_name") != _CARRIER_REPOSITORY or base.get("ref") != "master":
        raise OutcomeLearningCliError("carrier PR base is not canonical Mastermind master")
    if head.get("ref") != _CARRIER_BRANCH:
        raise OutcomeLearningCliError(
            f"carrier PR head branch {head.get('ref')!r} does not equal {_CARRIER_BRANCH!r}"
        )
    if head.get("sha") != branch_sha:
        raise OutcomeLearningCliError(
            f"carrier PR head {head.get('sha')!r} does not equal remote carrier branch "
            f"{branch_sha!r}"
        )
    return branch_sha


def _acquire_canonical_strategic_state(
    runner: Runner, protected_master_sha: str
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
            f"?ref={protected_master_sha}",
        ]
    )
    if result.returncode != 0:
        raise OutcomeLearningCliError(
            "gh api contents config/strategic_state.yml@"
            f"{protected_master_sha} failed: {result.stderr.strip()}"
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


def cmd_compose(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    clock: Clock | None = None,
) -> int:
    """Compose only from independently current repository, Agent OS, and Chairman sources.

    The Chairman source is an accepted, untouched, READ-only ``ceo_intent`` receipt.
    This command never creates that intent, never substitutes a fixture, and never
    infers authority from the local conversation. A multi-option actionable frontier is
    written as evidence and returns ``DECISION_REQUIRED``; it is not silently resolved.
    """
    runner = runner or SubprocessRunner()

    try:
        mastermind_sha = _ls_remote_sha(
            runner, _CANONICAL_MASTERMIND_URL, "refs/heads/master"
        )
        carrier_head_sha = _acquire_carrier_head(runner)
        strategic_blob_sha, canonical_strategic_state = (
            _acquire_canonical_strategic_state(runner, mastermind_sha)
        )
        macro_canonical_sha = _ls_remote_sha(
            runner, _CANONICAL_MACRO_URL, "refs/heads/main"
        )
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
        boot = _redact_boot_packet(
            _acquire_boot_packet(runner, args.mastermind_root, args.macro_root)
        )
    except (OutcomeLearningCliError, KeyError, json.JSONDecodeError) as exc:
        print(f"BLOCKER SOURCE_IDENTITY_UNVERIFIED {exc}")
        return 5

    boot_macro_sha = ((boot.get("macro") or {}).get("sha"))
    if boot_macro_sha != macro_local_sha:
        print(
            "BLOCKER SOURCE_IDENTITY_UNVERIFIED boot_packet.macro.sha "
            f"{boot_macro_sha!r} does not match the independently-verified local "
            f"macro checkout {macro_local_sha!r}"
        )
        return 5
    boot = {**boot, "strategic_state": canonical_strategic_state}

    try:
        directive = _acquire_trusted_intent(
            runner,
            args.mastermind_root,
            args.directive_intent_id,
            mastermind_sha=mastermind_sha,
            macro_sha=macro_local_sha,
            expected_schema=_DIRECTIVE_SCHEMA,
        )
    except OutcomeLearningCliError as exc:
        print(f"BLOCKER DIRECTIVE_SOURCE_UNVERIFIED {exc}")
        return 5

    agentos_override = getattr(args, "agentos_records_digest", None)
    try:
        agentos_reference_at = _event_time(clock)
        agentos_records_digest = _acquire_agentos_records_digest(
            runner,
            args.macro_root,
            agentos_reference_at,
            agentos_override,
        )
        as_of = _event_time(clock, after=agentos_reference_at)
        boot_generated_at = boot["generated_at"]
        for source_name, observed_at in (
            ("boot_packet.generated_at", boot_generated_at),
            ("directive.created_at", directive["observed_at"]),
        ):
            if _parse_iso_utc(observed_at) > _parse_iso_utc(as_of):
                raise OutcomeLearningCliError(
                    f"{source_name} {observed_at} postdates host acquisition completion "
                    f"{as_of}"
                )
        directive_objective = _validate_directive(
            directive, operation_key=args.operation_key, as_of=as_of
        )
    except OutcomeLearningCliError as exc:
        print(f"BLOCKER DIRECTIVE_SOURCE_UNVERIFIED {exc}")
        return 5

    strategic_state = boot.get("strategic_state") or {}
    brief = boot.get("brief") or {}
    strategic_payload_digest = canonical_digest(strategic_state)
    agentos_payload_digest = canonical_digest(brief) if brief else "UNRESOLVED"
    mastermind_revision_attestation = {
        "revision": mastermind_sha,
        "state": "CURRENT",
        "load_bearing": True,
        "observed_at": as_of,
        "source_blob_sha": strategic_blob_sha,
        "payload_digest": strategic_payload_digest,
    }
    agentos_revision_attestation = {
        "revision": macro_local_sha,
        "state": "UNKNOWN" if agentos_override is not None else "CURRENT",
        "load_bearing": True,
        "observed_at": as_of,
        "source_records_digest": agentos_records_digest,
        "payload_digest": agentos_payload_digest,
    }

    chairman_source_ref = directive["source_ref"]
    envelope = _olv1_envelope(
        carrier_head_sha,
        chairman_source_ref=chairman_source_ref,
        expires_at=directive_objective["expires_at"],
    )
    options = _olv1_options(
        args.operation_key,
        carrier_head_sha,
        chairman_source_ref=chairman_source_ref,
    )
    chairman_revision = _append_binding(
        "", "envelope-sha256", _digest_hex(_envelope_payload(envelope))
    )
    for option in options:
        chairman_revision = _add_binding_if_absent(
            chairman_revision,
            "classification-sha256",
            _digest_hex(_classification_payload(option)),
        )
    if len(chairman_revision) > 256:
        print(
            "BLOCKER COMPOSITION_INVALID trusted directive revision bindings exceed "
            "the canonical 256-character source receipt ceiling"
        )
        return 5
    chairman_directive = {
        "source_ref": chairman_source_ref,
        "revision": chairman_revision,
        "state": "CURRENT",
        "load_bearing": True,
        "observed_at": directive["observed_at"],
    }
    bundle = {
        "schema": _SOURCE_BUNDLE_SCHEMA,
        "as_of": as_of,
        "chairman_directive": chairman_directive,
        "mastermind_revision_attestation": mastermind_revision_attestation,
        "agentos_revision_attestation": agentos_revision_attestation,
        "boot_packet": boot,
        "additional_source_receipts": [],
        "delegation_envelope": envelope,
        "options": options,
    }

    try:
        composition = evaluate_bundle(bundle)
    except (ChairmanCognitionSourceError, ChairmanCognitionError) as exc:
        print(f"BLOCKER COMPOSITION_INVALID {exc}")
        return 5

    episode_dir = Path(args.episode_dir)
    episode_dir.mkdir(parents=True, exist_ok=True)
    _write_artifact(episode_dir / "bundle.json", bundle)
    _write_artifact(episode_dir / "composition.json", composition)

    print(f"as_of_mode=host_clock_after_acquisition as_of={as_of}")
    for summary in composition["source_summary"]:
        print(f"SOURCE {summary['source_ref']}={summary['state']}")
    for adjudication in composition["packet"]["adjudications"]:
        print(
            f"ADJUDICATION {adjudication['option_id']}="
            f"{adjudication['disposition']}/{adjudication['reason']}"
        )
    packet = composition["packet"]
    print(f"selection_state={packet['selection_state']}")
    print(f"recommended_option_id={packet['recommended_option_id']}")
    print(f"execution_authority_granted={composition['execution_authority_granted']}")
    print(f"source_bundle_digest=sha256:{composition['source_bundle_digest']}")
    print(f"composed_input_digest=sha256:{composition['composed_input_digest']}")
    print(f"packet_digest=sha256:{packet['packet_digest']}")
    print(f"composition_digest=sha256:{composition['composition_digest']}")

    canary_adjudication = next(
        item for item in packet["adjudications"] if item["option_id"] == _OPT_CANARY
    )
    disposition = canary_adjudication["disposition"]
    reason = canary_adjudication["reason"]
    if disposition == "ELIGIBLE_WITHIN_DELEGATION":
        if (
            packet["selection_state"] == "UNIQUE_ACTIONABLE_FRONTIER"
            and packet["recommended_option_id"] == _OPT_CANARY
        ):
            print("COMPOSE_OK unique canary recommendation is sealable without selection intent")
            return 0
        print(
            "BLOCKER DECISION_REQUIRED exact packet selection must be admitted through "
            "the canonical ceo_intent plane before seal"
        )
        return 7
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
        else:
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


def cmd_seal(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    clock: Clock | None = None,
) -> int:
    runner = runner or SubprocessRunner()
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
    chosen_option = next(item for item in options if item["option_id"] == chosen_action)
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

    selection: dict[str, Any] | None = None
    if (
        packet["selection_state"] == "UNIQUE_ACTIONABLE_FRONTIER"
        and packet["recommended_option_id"] == chosen_action
    ):
        if getattr(args, "selection_intent_id", None) is not None:
            raise OutcomeLearningCliError(
                "a selection intent is not accepted when A1 already produced one unique "
                "canary recommendation"
            )
        assignment_method = "deterministic_a1_unique_actionable_frontier"
    elif (
        packet["selection_state"] == "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
        and disposition == "ELIGIBLE_WITHIN_DELEGATION"
    ):
        selection_intent_id = getattr(args, "selection_intent_id", None)
        if not selection_intent_id:
            raise OutcomeLearningCliError(
                "refusing to seal an incomparable frontier without --selection-intent-id"
            )
        selection = _acquire_trusted_intent(
            runner,
            getattr(args, "mastermind_root", str(_ROOT)),
            selection_intent_id,
            mastermind_sha=bundle["mastermind_revision_attestation"]["revision"],
            macro_sha=bundle["agentos_revision_attestation"]["revision"],
            expected_schema=_SELECTION_SCHEMA,
        )
        _validate_selection(
            selection,
            operation_key=chosen_option["operation_key"],
            packet_digest=f"sha256:{packet['packet_digest']}",
            chosen_option_id=chosen_action,
            carrier_ref=chosen_option["carrier_ref"],
            packet_as_of=bundle["as_of"],
        )
        assignment_method = (
            "trusted_ceo_intent_selection_from_a1_incomparable_frontier"
        )
    else:
        raise OutcomeLearningCliError(
            f"refusing to seal chosen_action {chosen_action}: disposition={disposition} "
            f"does not map to a lawful selection path (selection_state="
            f"{packet['selection_state']}, recommended_option_id="
            f"{packet['recommended_option_id']})"
        )

    # Sol REQUEST_REPAIR (BLOCKER B, 2026-09-02): operation identity and ancestry are
    # DERIVED from the adjudicated A1 option, never freely supplied — a caller could
    # otherwise attach this packet's digest to an unrelated operation/parent/carrier.
    # --operation-key/--parent-head become optional cross-checks: if supplied, they
    # must exactly equal what the option already says, or sealing refuses outright.
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
    context_source_refs = [
        bundle["chairman_directive"]["source_ref"],
        _STRATEGIC_SOURCE_REF,
        _AGENT_OS_SOURCE_REF,
        "GITHUB:Mastermind:protected-master",
    ]
    source_cutoff = bundle["as_of"]
    selection_binding: dict[str, Any] | None = None
    if selection is not None:
        context_source_refs.append(selection["source_ref"])
        source_packet_digests.append(selection["receipt_digest"])
        source_cutoff = selection["observed_at"]
        selection_binding = {
            "source_ref": selection["source_ref"],
            "receipt_digest": selection["receipt_digest"],
        }
    expectation_recorded_at = _event_time(clock, after=source_cutoff)
    request_recorded_at = _event_time(clock, after=expectation_recorded_at)
    final_decision_binding = {
        "operation_key": operation_key,
        "packet_digest": f"sha256:{packet['packet_digest']}",
        "chosen_option_id": chosen_action,
        "carrier_ref": chosen_option["carrier_ref"],
        "selection": selection_binding,
    }

    expectation = build_expectation(
        decision_ref={
            "owner": "chairman_cognition",
            "type": "a1_decision_packet",
            "id": canonical_digest(packet),
        },
        operation_key=operation_key,
        decision_kind="organizational_learning_episode",
        recorded_at=expectation_recorded_at,
        context={
            "source_refs": context_source_refs,
            "task_kind": "organizational_learning_episode",
            "risk": "routine",
            "ambiguity": "low",
            "program": "organizational-learning",
            "repository": request_repository,
            "source_cutoff": source_cutoff,
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
                "metric_id": "ci_green_at_frozen_evidence_commit",
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
            "final_decision_digest": canonical_digest(final_decision_binding),
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
        recorded_at=request_recorded_at,
    )

    _write_artifact(args.out_expectation, expectation)
    _write_artifact(args.out_request, request)
    print(f"expectation_sealed_hash={expectation['sealed_hash']}")
    print(f"request_digest={canonical_digest(request)}")
    return 0


# --------------------------------------------------------------------------- preflight


def _verify_seal_commit_shape(
    runner: Runner,
    mastermind_root: str | None,
    sealed_commit: str,
    expectation_repo_path: str,
    request_repo_path: str,
) -> str:
    """Require one direct-child preregistration commit with exactly two changed paths."""
    expectation_path = _normalize_repo_path(
        expectation_repo_path, where="expectation repo-path"
    )
    request_path = _normalize_repo_path(
        request_repo_path, where="request repo-path"
    )
    if expectation_path == request_path:
        raise OutcomeLearningCliError(
            "expectation and request repo paths must be distinct preregistration paths"
        )

    parents_line = _git(
        runner,
        ["rev-list", "--parents", "-n", "1", sealed_commit],
        cwd=mastermind_root,
    )
    fields = parents_line.split()
    if len(fields) != 2 or fields[0] != sealed_commit:
        raise OutcomeLearningCliError(
            f"sealed_commit {sealed_commit} must have exactly one parent"
        )
    parent = fields[1]
    if _SHA40_RE.fullmatch(parent) is None:
        raise OutcomeLearningCliError("sealed_commit parent is not a 40-hex commit")

    changed = _git(
        runner,
        ["diff", "--name-only", parent, sealed_commit, "--"],
        cwd=mastermind_root,
    ).splitlines()
    observed_paths = sorted(path for path in changed if path)
    expected_paths = sorted([expectation_path, request_path])
    if observed_paths != expected_paths:
        raise OutcomeLearningCliError(
            "sealed_commit must change exactly the two preregistration paths: "
            f"expected={expected_paths!r} observed={observed_paths!r}"
        )
    return parent


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


def cmd_preflight(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    transport: GhTransport | None = None,
    clock: Clock | None = None,
) -> int:
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
    # runs BEFORE the first transport call. The seal is one direct-child commit whose
    # complete diff is exactly the expectation/request preregistration pair. Two
    # independent git calls PER artifact (blob-id resolution, then a separate content
    # read) then prove the supplied canonical content matches that exact commit.
    sealed_parent = _verify_seal_commit_shape(
        runner,
        args.mastermind_root,
        args.sealed_commit,
        args.expectation_repo_path,
        args.request_repo_path,
    )
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

    observed_at = _event_time(clock, after=request_obj["recorded_at"])
    preflight = {
        "observed_at": observed_at,
        "repository": args.repo,
        "branch": args.branch,
        "pr_number": pr["number"],
        "pr_url": pr["html_url"],
        "head_sha": head_sha,
        "base_ref": pr["base"]["ref"],
        "original_title_sha256": original_title_sha256,
        "original_title_length": len(original_title),
        "sealed_commit_sha": args.sealed_commit,
        "expectation_repo_path": _normalize_repo_path(
            args.expectation_repo_path, where="expectation repo-path"
        ),
        "request_repo_path": _normalize_repo_path(
            args.request_repo_path, where="request repo-path"
        ),
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


def _reacquire_sealed_episode(
    runner: Runner,
    mastermind_root: str | None,
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Re-prove the complete sealed episode from commit:path before owner I/O."""
    validate_preflight(preflight)
    sealed_commit = preflight["sealed_commit_sha"]
    parent = _verify_seal_commit_shape(
        runner,
        mastermind_root,
        sealed_commit,
        preflight["expectation_repo_path"],
        preflight["request_repo_path"],
    )
    expectation_blob_sha, expectation_text = _resolve_committed_blob(
        runner,
        mastermind_root,
        sealed_commit,
        preflight["expectation_repo_path"],
        where="effect-edge expectation",
    )
    request_blob_sha, request_text = _resolve_committed_blob(
        runner,
        mastermind_root,
        sealed_commit,
        preflight["request_repo_path"],
        where="effect-edge request",
    )
    if expectation_blob_sha != preflight["expectation_blob_sha"]:
        raise OutcomeLearningCliError(
            "effect-edge expectation blob does not match preflight"
        )
    if request_blob_sha != preflight["request_blob_sha"]:
        raise OutcomeLearningCliError(
            "effect-edge request blob does not match preflight"
        )
    try:
        expectation = json.loads(expectation_text)
        request = json.loads(request_text)
    except json.JSONDecodeError as exc:
        raise OutcomeLearningCliError(
            "effect-edge committed expectation/request is not valid JSON"
        ) from exc
    validate_expectation(expectation)
    validate_canary_request(request)
    expectation_digest = canonical_digest(expectation).removeprefix("sha256:")
    request_digest = canonical_digest(request).removeprefix("sha256:")
    if expectation_digest != preflight["expectation_content_sha256"]:
        raise OutcomeLearningCliError(
            "effect-edge expectation digest does not match preflight"
        )
    if request_digest != preflight["request_content_sha256"]:
        raise OutcomeLearningCliError(
            "effect-edge request digest does not match preflight"
        )
    if request["expectation_sealed_hash"] != expectation["sealed_hash"]:
        raise OutcomeLearningCliError(
            "effect-edge request does not bind the committed expectation"
        )
    if request["operation_key"] != expectation["operation_key"]:
        raise OutcomeLearningCliError(
            "effect-edge request/expectation operation_key mismatch"
        )
    if request["expected_parent_head"] != parent:
        raise OutcomeLearningCliError(
            "effect-edge sealed parent does not match the committed request"
        )
    if request["repository"] != preflight["repository"]:
        raise OutcomeLearningCliError(
            "effect-edge request repository does not match preflight"
        )
    if request["branch"] != preflight["branch"]:
        raise OutcomeLearningCliError(
            "effect-edge request branch does not match preflight"
        )
    if expectation["context"]["repository"] != request["repository"]:
        raise OutcomeLearningCliError(
            "effect-edge expectation repository does not match the request"
        )
    if expectation["chosen_action"] != _OPT_CANARY:
        raise OutcomeLearningCliError(
            "effect-edge expectation did not select the OL-V1 canary"
        )
    if (
        preflight["head_sha"] != sealed_commit
        or preflight["head_equals_sealed_commit"] is not True
    ):
        raise OutcomeLearningCliError(
            "effect-edge preflight head is not the exact sealed commit"
        )
    if preflight["base_ref"] != "master":
        raise OutcomeLearningCliError("effect-edge preflight base_ref must be master")
    return dict(expectation), dict(request), parent


# --------------------------------------------------------------------------- canary


def _make_call(
    seq: int,
    kind: str,
    endpoint: str,
    payload_sha: str,
    status: int | str,
    doc: Mapping[str, Any],
    *,
    requested_at: str,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "requested_at": requested_at,
        "method": "PATCH",
        "endpoint": endpoint,
        "payload_title_sha256": payload_sha,
        "response_status": status,
        "readback": {
            "observed_at": observed_at,
            "title_sha256": _sha256_hex_text(doc["title"]),
            "title_length": len(doc["title"]),
            "head_sha": doc["head"]["sha"],
        },
    }


def _reconcile(
    transport: GhTransport,
    endpoint: str,
    *,
    clock: Clock | None,
    after: str,
) -> dict[str, Any]:
    """Perform exactly one read-only reconciliation GET, never an effect retry."""
    try:
        _, doc = transport.get(endpoint)
        return {
            "attempted": True,
            "observed_title_sha256": _sha256_hex_text(doc["title"]),
            "observed_head_sha": doc["head"]["sha"],
            "observed_at": _event_time(clock, after=after),
        }
    except Exception:  # noqa: BLE001 - preserve EFFECT_UNKNOWN without a retry
        return {
            "attempted": True,
            "observed_title_sha256": None,
            "observed_head_sha": None,
            "observed_at": _event_time(clock, after=after),
        }


#: BLOCKER D journal state machine (CLI-internal artifact — not an OL-V1 contract
#: schema): PREPARED is the atomic reservation; APPLY_SENT/APPLIED_READBACK/
#: RESTORE_SENT are the only non-terminal in-flight states; the three terminal
#: states are RESTORED / EFFECT_UNKNOWN / INVALIDATED_BEFORE_EFFECT. Any other value
#: on disk — including a crash mid-sequence — is fail-closed non-terminal.
_JOURNAL_TERMINAL_STATES = frozenset(
    {"RESTORED", "EFFECT_UNKNOWN", "INVALIDATED_BEFORE_EFFECT"}
)


_JOURNAL_SCHEMA = "mastermind.olv1_canary_journal.v1"
_JOURNAL_STATES = frozenset(
    {
        "PREPARED",
        "APPLY_SENT",
        "APPLIED_READBACK",
        "RESTORE_SENT",
        "RESTORED",
        "EFFECT_UNKNOWN",
        "INVALIDATED_BEFORE_EFFECT",
    }
)
_JOURNAL_REQUIRED = {
    "schema",
    "state",
    "bound_identity",
    "selector_observation",
    "owner_event_baseline",
    "effect_attempts",
    "effect_calls",
    "reconciliation",
    "pre_effect_observation",
    "recorded_at",
}
_JOURNAL_IDENTITY_REQUIRED = {
    "repository",
    "branch",
    "operation_key",
    "expectation_sealed_hash",
    "sealed_commit_sha",
    "expected_parent_head",
    "preflight_pr_number",
    "canary_token",
    "request_digest",
}
_SELECTOR_OBSERVATION_REQUIRED = {
    "observed_at",
    "match_count",
    "matched_pr_number",
}
_RECONCILIATION_REQUIRED = {
    "attempted",
    "observed_title_sha256",
    "observed_head_sha",
    "observed_at",
}


def _closed_journal_mapping(
    value: Any, *, required: set[str], where: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OutcomeLearningCliError(f"{where} must be a mapping")
    keys = set(value)
    missing = required - keys
    extra = keys - required
    if missing or extra:
        raise OutcomeLearningCliError(
            f"{where} has invalid fields missing={sorted(missing)} unknown={sorted(extra)}"
        )
    return value


def _make_attempt(
    seq: int,
    kind: str,
    endpoint: str,
    payload_title: str,
    requested_at: str,
) -> dict[str, Any]:
    return {
        "seq": seq,
        "kind": kind,
        "requested_at": requested_at,
        "method": "PATCH",
        "endpoint": endpoint,
        "payload_title_sha256": _sha256_hex_text(payload_title),
        "payload_title_length": len(payload_title),
    }


def _journal_record(
    *,
    state: str,
    bound_identity: Mapping[str, Any],
    recorded_at: str,
    selector_observation: Mapping[str, Any] | None = None,
    owner_event_baseline: Mapping[str, Any] | None = None,
    effect_attempts: Sequence[Mapping[str, Any]] = (),
    effect_calls: Sequence[Mapping[str, Any]] = (),
    reconciliation: Mapping[str, Any] | None = None,
    pre_effect_observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "schema": _JOURNAL_SCHEMA,
        "state": state,
        "bound_identity": dict(bound_identity),
        "selector_observation": (
            dict(selector_observation) if selector_observation is not None else None
        ),
        "owner_event_baseline": (
            dict(owner_event_baseline) if owner_event_baseline is not None else None
        ),
        "effect_attempts": [dict(item) for item in effect_attempts],
        "effect_calls": [dict(item) for item in effect_calls],
        "reconciliation": dict(reconciliation) if reconciliation is not None else None,
        "pre_effect_observation": (
            dict(pre_effect_observation) if pre_effect_observation is not None else None
        ),
        "recorded_at": recorded_at,
    }
    _validate_journal_record(record)
    return record


def _validate_journal_record(record: Mapping[str, Any]) -> Mapping[str, Any]:
    item = _closed_journal_mapping(
        record, required=_JOURNAL_REQUIRED, where="journal"
    )
    if item["schema"] != _JOURNAL_SCHEMA:
        raise OutcomeLearningCliError("journal schema is unsupported")
    state = item["state"]
    if state not in _JOURNAL_STATES:
        raise OutcomeLearningCliError(f"unknown journal state {state!r}")
    identity = _closed_journal_mapping(
        item["bound_identity"],
        required=_JOURNAL_IDENTITY_REQUIRED,
        where="journal.bound_identity",
    )
    for field in ("repository", "branch", "operation_key", "canary_token"):
        if not isinstance(identity[field], str) or not identity[field]:
            raise OutcomeLearningCliError(
                f"journal.bound_identity.{field} must be non-empty text"
            )
    for field in ("sealed_commit_sha", "expected_parent_head"):
        if _SHA40_RE.fullmatch(str(identity[field])) is None:
            raise OutcomeLearningCliError(
                f"journal.bound_identity.{field} must be 40 lowercase hex"
            )
    if not isinstance(identity["preflight_pr_number"], int):
        raise OutcomeLearningCliError(
            "journal.bound_identity.preflight_pr_number must be an integer"
        )
    for field in ("expectation_sealed_hash", "request_digest"):
        value = str(identity[field])
        if not value.startswith("sha256:") and field == "expectation_sealed_hash":
            raise OutcomeLearningCliError(
                "journal expectation_sealed_hash must be a sha256 digest"
            )
    if _SHA256_RE.fullmatch(str(identity["request_digest"])) is None:
        raise OutcomeLearningCliError(
            "journal bound request_digest must be 64 lowercase hex"
        )
    recorded_time = _parse_iso_utc(str(item["recorded_at"]))
    selector = item["selector_observation"]
    if selector is not None:
        selector = _closed_journal_mapping(
            selector,
            required=_SELECTOR_OBSERVATION_REQUIRED,
            where="journal.selector_observation",
        )
        selector_time = _parse_iso_utc(str(selector["observed_at"]))
        if not isinstance(selector["match_count"], int) or selector["match_count"] < 0:
            raise OutcomeLearningCliError(
                "journal selector match_count must be a nonnegative integer"
            )
        matched = selector["matched_pr_number"]
        if matched is not None and (not isinstance(matched, int) or matched <= 0):
            raise OutcomeLearningCliError(
                "journal selector matched_pr_number must be null or positive"
            )
        if selector_time > recorded_time:
            raise OutcomeLearningCliError(
                "journal selector observation cannot postdate the journal record"
            )

    owner_event_baseline = validate_owner_event_baseline(
        item["owner_event_baseline"]
    )
    baseline_time = None
    if owner_event_baseline is not None:
        baseline_time = _parse_iso_utc(str(owner_event_baseline["observed_at"]))
        if baseline_time > recorded_time:
            raise OutcomeLearningCliError(
                "journal owner-event baseline cannot postdate the journal record"
            )

    attempts = validate_effect_attempts(item["effect_attempts"])
    calls = validate_effect_calls(item["effect_calls"])
    if len(calls) > len(attempts):
        raise OutcomeLearningCliError(
            "journal completed calls cannot exceed pre-PATCH attempts"
        )
    for index, call in enumerate(calls):
        attempt = attempts[index]
        for field in (
            "seq",
            "kind",
            "requested_at",
            "method",
            "endpoint",
            "payload_title_sha256",
        ):
            if call[field] != attempt[field]:
                raise OutcomeLearningCliError(
                    f"journal call {index + 1} does not match its pre-PATCH attempt"
                )
    pre_effect = item["pre_effect_observation"]
    if pre_effect is not None:
        pre_effect = _closed_journal_mapping(
            pre_effect,
            required={
                "observed_head_sha",
                "observed_title_sha256",
                "observed_title_length",
                "observed_at",
            },
            where="journal.pre_effect_observation",
        )
        if _SHA40_RE.fullmatch(str(pre_effect["observed_head_sha"])) is None:
            raise OutcomeLearningCliError(
                "journal pre-effect head must be 40 lowercase hex"
            )
        if _SHA256_RE.fullmatch(str(pre_effect["observed_title_sha256"])) is None:
            raise OutcomeLearningCliError(
                "journal pre-effect title hash must be 64 lowercase hex"
            )
        if (
            not isinstance(pre_effect["observed_title_length"], int)
            or pre_effect["observed_title_length"] < 0
        ):
            raise OutcomeLearningCliError(
                "journal pre-effect title length must be nonnegative"
            )
        pre_effect_time = _parse_iso_utc(str(pre_effect["observed_at"]))
        if pre_effect_time > recorded_time:
            raise OutcomeLearningCliError(
                "journal pre-effect observation cannot postdate the journal record"
            )

    if owner_event_baseline is not None:
        if pre_effect is None:
            raise OutcomeLearningCliError(
                "journal owner-event baseline requires a pre-effect observation"
            )
        if pre_effect_time >= baseline_time:
            raise OutcomeLearningCliError(
                "journal owner-event baseline must be observed after pre-effect freshness"
            )
        if attempts and baseline_time >= _parse_iso_utc(str(attempts[0]["requested_at"])):
            raise OutcomeLearningCliError(
                "journal owner-event baseline must precede the first PATCH attempt"
            )

    reconciliation = item["reconciliation"]
    if reconciliation is not None:
        reconciliation = _closed_journal_mapping(
            reconciliation,
            required=_RECONCILIATION_REQUIRED,
            where="journal.reconciliation",
        )
        if reconciliation["attempted"] is not True:
            raise OutcomeLearningCliError(
                "journal reconciliation.attempted must be True"
            )
        for field, pattern in (
            ("observed_title_sha256", _SHA256_RE),
            ("observed_head_sha", _SHA40_RE),
        ):
            value = reconciliation[field]
            if value is not None and pattern.fullmatch(str(value)) is None:
                raise OutcomeLearningCliError(
                    f"journal reconciliation.{field} has invalid shape"
                )
        if _parse_iso_utc(str(reconciliation["observed_at"])) > recorded_time:
            raise OutcomeLearningCliError(
                "journal reconciliation cannot postdate the journal record"
            )
    selector_single = bool(
        selector is not None
        and selector["match_count"] == 1
        and selector["matched_pr_number"] == identity["preflight_pr_number"]
    )
    if state == "PREPARED":
        valid = (
            selector is None
            and owner_event_baseline is None
            and not attempts
            and not calls
            and reconciliation is None
            and pre_effect is None
        )
    elif state == "INVALIDATED_BEFORE_EFFECT":
        valid = (
            selector is not None
            and owner_event_baseline is None
            and not attempts
            and not calls
            and reconciliation is None
            and (pre_effect is None or selector_single)
            and (pre_effect is not None or not selector_single)
        )
    elif state == "APPLY_SENT":
        valid = (
            selector_single
            and owner_event_baseline is not None
            and pre_effect is not None
            and len(attempts) == 1
            and not calls
            and reconciliation is None
        )
    elif state == "APPLIED_READBACK":
        valid = (
            selector_single
            and owner_event_baseline is not None
            and pre_effect is not None
            and len(attempts) == 1
            and len(calls) == 1
            and reconciliation is None
        )
    elif state == "RESTORE_SENT":
        valid = (
            selector_single
            and owner_event_baseline is not None
            and pre_effect is not None
            and len(attempts) == 2
            and len(calls) == 1
            and reconciliation is None
        )
    elif state == "RESTORED":
        valid = (
            selector_single
            and owner_event_baseline is not None
            and pre_effect is not None
            and len(attempts) == 2
            and len(calls) == 2
            and reconciliation is None
        )
    else:
        valid = (
            selector_single
            and owner_event_baseline is not None
            and pre_effect is not None
            and len(attempts) in {1, 2}
            and len(calls) <= len(attempts)
            and reconciliation is not None
        )
    if not valid:
        raise OutcomeLearningCliError(
            f"journal state {state} violates its closed required/forbidden shape"
        )
    return item


def _canonical_journal_identity(
    request: Mapping[str, Any], preflight: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "repository": request["repository"],
        "branch": request["branch"],
        "operation_key": request["operation_key"],
        "expectation_sealed_hash": request["expectation_sealed_hash"],
        "sealed_commit_sha": preflight["sealed_commit_sha"],
        "expected_parent_head": request["expected_parent_head"],
        "preflight_pr_number": preflight["pr_number"],
        "canary_token": request["canary_token"],
        "request_digest": canonical_digest(request).removeprefix("sha256:"),
    }


def _canonical_journal_path(
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    journal_root: Path | None = None,
) -> Path:
    """Derive the single host-owned journal identity; callers cannot select its path."""
    root = Path(journal_root) if journal_root is not None else _CANONICAL_JOURNAL_ROOT
    identity = _canonical_journal_identity(request, preflight)
    repository_key = _sha256_hex_text(str(identity["repository"]))[:24]
    branch_key = _sha256_hex_text(str(identity["branch"]))[:24]
    expectation_key = str(identity["expectation_sealed_hash"]).removeprefix("sha256:")
    return (
        root
        / repository_key
        / branch_key
        / str(identity["operation_key"])
        / expectation_key
        / str(identity["sealed_commit_sha"])
        / "journal.json"
    )


def _reserve_journal(journal_path: Path, record: dict[str, Any]) -> None:
    """Atomically reserve the single-shot journal (BLOCKER D). ``open(..., 'x')``
    (exclusive create) is the ENTIRE single-shot guard: whichever of two racing
    invocations wins this call proceeds, and the other sees ``FileExistsError``
    unconditionally — regardless of what state a pre-existing reservation is in."""
    _validate_journal_record(record)
    journal_path.parent.mkdir(parents=True, exist_ok=True, mode=stat.S_IRWXU)
    try:
        fd = os.open(str(journal_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise OutcomeLearningCliError(
            f"{journal_path} already exists — OL-V1 canary is single-shot for the "
            "host-owned repository + branch + operation + expectation + sealed-commit "
            "identity; every pre-existing reservation refuses, whatever its state"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")


def _advance_journal(journal_path: Path, record: dict[str, Any]) -> None:
    """Atomically advance a reservation already on disk: write a temp file in the
    SAME directory, then ``os.replace`` over the reservation — a concurrent reader
    (or a crash) never observes a partially-written state."""
    _validate_journal_record(record)
    tmp_path = journal_path.with_name(journal_path.name + f".tmp{os.getpid()}")
    tmp_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(str(tmp_path), str(journal_path))


_MAX_ISSUE_EVENT_PAGES = 10


def _fetch_issue_events(
    transport: GhTransport,
    repository: str,
    pr_number: int,
) -> list[Mapping[str, Any]]:
    """Read a complete, bounded GitHub issue-event history page by page."""
    events: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for page in range(1, _MAX_ISSUE_EVENT_PAGES + 1):
        endpoint = (
            f"repos/{repository}/issues/{pr_number}/events?per_page=100&page={page}"
        )
        _, payload = transport.get(endpoint)
        if not isinstance(payload, list):
            raise OutcomeLearningCliError(
                f"GitHub issue-events page {page} was not a list"
            )
        for index, raw in enumerate(payload):
            if not isinstance(raw, Mapping):
                raise OutcomeLearningCliError(
                    f"GitHub issue-events page {page} item {index} was not a mapping"
                )
            event_id = raw.get("id")
            if type(event_id) is not int or event_id <= 0:
                raise OutcomeLearningCliError(
                    f"GitHub issue-events page {page} item {index} has invalid id"
                )
            if event_id in seen_ids:
                raise OutcomeLearningCliError(
                    f"GitHub issue-events response repeats event id {event_id}"
                )
            seen_ids.add(event_id)
            events.append(raw)
        if len(payload) < 100:
            return events
    raise OutcomeLearningCliError(
        "GitHub issue-event pagination bound exceeded before a terminal short page"
    )


def _capture_owner_event_baseline(
    transport: GhTransport,
    preflight: Mapping[str, Any],
    *,
    clock: Clock | None,
    after: str,
) -> dict[str, Any]:
    events = _fetch_issue_events(
        transport,
        str(preflight["repository"]),
        int(preflight["pr_number"]),
    )
    rename_ids = sorted(
        int(event["id"])
        for event in events
        if event.get("event") == "renamed"
    )
    baseline = {
        "observed_at": _event_time(clock, after=after),
        "rename_event_ids": rename_ids,
    }
    validate_owner_event_baseline(baseline)
    return baseline


def cmd_canary(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    transport: GhTransport | None = None,
    clock: Clock | None = None,
    journal_root: Path | None = None,
) -> int:
    """Apply once, restore once, and persist a closed single-shot journal."""
    runner = runner or SubprocessRunner()
    transport = transport or GhCliTransport(runner)

    preflight = _read_json(args.preflight)
    validate_preflight(preflight)
    expectation, request, _sealed_parent = _reacquire_sealed_episode(
        runner, args.mastermind_root, preflight
    )
    if request["expectation_sealed_hash"] != expectation["sealed_hash"]:
        raise OutcomeLearningCliError(
            "effect-edge committed request/expectation binding mismatch"
        )
    reacquired_digest = canonical_digest(request).removeprefix("sha256:")

    journal_path = _canonical_journal_path(
        request, preflight, journal_root=journal_root
    )
    bound_identity = _canonical_journal_identity(request, preflight)
    if bound_identity["request_digest"] != reacquired_digest:
        raise OutcomeLearningCliError(
            "canonical journal request identity does not match the committed request blob"
        )
    prepared_at = _event_time(clock, after=preflight["observed_at"])
    _reserve_journal(
        journal_path,
        _journal_record(
            state="PREPARED",
            bound_identity=bound_identity,
            recorded_at=prepared_at,
        ),
    )

    endpoint = f"repos/{request['repository']}/pulls/{preflight['pr_number']}"
    original_sha = preflight["original_title_sha256"]
    sealed_head = preflight["sealed_commit_sha"]

    _, prs = transport.get(
        f"repos/{request['repository']}/pulls?head="
        f"{request['repository'].split('/')[0]}:{request['branch']}&state=open"
    )
    selector_at = _event_time(clock, after=prepared_at)
    selector_ok = (
        isinstance(prs, list)
        and len(prs) == 1
        and prs[0].get("number") == preflight["pr_number"]
    )
    selector_observation = {
        "observed_at": selector_at,
        "match_count": len(prs) if isinstance(prs, list) else 0,
        "matched_pr_number": (
            prs[0].get("number")
            if isinstance(prs, list) and len(prs) == 1
            else None
        ),
    }
    if not selector_ok:
        terminal_at = _event_time(clock, after=selector_at)
        _advance_journal(
            journal_path,
            _journal_record(
                state="INVALIDATED_BEFORE_EFFECT",
                bound_identity=bound_identity,
                selector_observation=selector_observation,
                recorded_at=terminal_at,
            ),
        )
        print(
            "effect_state=INVALIDATED_BEFORE_EFFECT (owner branch selector no longer "
            f"matches preflight: {prs!r})"
        )
        return 6

    _, current = transport.get(endpoint)
    freshness_at = _event_time(clock, after=selector_at)
    live_head = current["head"]["sha"]
    live_title = current["title"]
    live_title_sha = _sha256_hex_text(live_title)
    pre_effect_observation = {
        "observed_head_sha": live_head,
        "observed_title_sha256": live_title_sha,
        "observed_title_length": len(live_title),
        "observed_at": freshness_at,
    }
    if live_head != sealed_head or live_title_sha != original_sha:
        terminal_at = _event_time(clock, after=freshness_at)
        _advance_journal(
            journal_path,
            _journal_record(
                state="INVALIDATED_BEFORE_EFFECT",
                bound_identity=bound_identity,
                selector_observation=selector_observation,
                pre_effect_observation=pre_effect_observation,
                recorded_at=terminal_at,
            ),
        )
        print(
            "effect_state=INVALIDATED_BEFORE_EFFECT "
            f"(drift: {pre_effect_observation})"
        )
        return 6

    owner_event_baseline = _capture_owner_event_baseline(
        transport,
        preflight,
        clock=clock,
        after=freshness_at,
    )
    original_title = live_title
    applied_title = original_title + " " + request["canary_token"]
    apply_requested_at = _event_time(
        clock, after=owner_event_baseline["observed_at"]
    )
    apply_attempt = _make_attempt(
        1,
        "TITLE_APPLY",
        endpoint,
        applied_title,
        apply_requested_at,
    )
    _advance_journal(
        journal_path,
        _journal_record(
            state="APPLY_SENT",
            bound_identity=bound_identity,
            selector_observation=selector_observation,
            owner_event_baseline=owner_event_baseline,
            effect_attempts=[apply_attempt],
            pre_effect_observation=pre_effect_observation,
            recorded_at=apply_requested_at,
        ),
    )
    try:
        status1, applied_doc = transport.patch(endpoint, {"title": applied_title})
        apply_observed_at = _event_time(clock, after=apply_requested_at)
        call1 = _make_call(
            1,
            "TITLE_APPLY",
            endpoint,
            apply_attempt["payload_title_sha256"],
            status1,
            applied_doc,
            requested_at=apply_requested_at,
            observed_at=apply_observed_at,
        )
    except Exception:  # noqa: BLE001 - the apply may have crossed the effect boundary
        reconciliation = _reconcile(
            transport, endpoint, clock=clock, after=apply_requested_at
        )
        terminal_at = _event_time(clock, after=reconciliation["observed_at"])
        _advance_journal(
            journal_path,
            _journal_record(
                state="EFFECT_UNKNOWN",
                bound_identity=bound_identity,
                selector_observation=selector_observation,
                owner_event_baseline=owner_event_baseline,
                effect_attempts=[apply_attempt],
                reconciliation=reconciliation,
                pre_effect_observation=pre_effect_observation,
                recorded_at=terminal_at,
            ),
        )
        print("effect_state=EFFECT_UNKNOWN (apply raised)")
        return 3

    _advance_journal(
        journal_path,
        _journal_record(
            state="APPLIED_READBACK",
            bound_identity=bound_identity,
            selector_observation=selector_observation,
            owner_event_baseline=owner_event_baseline,
            effect_attempts=[apply_attempt],
            effect_calls=[call1],
            pre_effect_observation=pre_effect_observation,
            recorded_at=apply_observed_at,
        ),
    )
    restore_requested_at = _event_time(clock, after=apply_observed_at)
    restore_attempt = _make_attempt(
        2,
        "TITLE_RESTORE",
        endpoint,
        original_title,
        restore_requested_at,
    )
    attempts = [apply_attempt, restore_attempt]
    _advance_journal(
        journal_path,
        _journal_record(
            state="RESTORE_SENT",
            bound_identity=bound_identity,
            selector_observation=selector_observation,
            owner_event_baseline=owner_event_baseline,
            effect_attempts=attempts,
            effect_calls=[call1],
            pre_effect_observation=pre_effect_observation,
            recorded_at=restore_requested_at,
        ),
    )
    try:
        status2, restored_doc = transport.patch(endpoint, {"title": original_title})
        restore_observed_at = _event_time(clock, after=restore_requested_at)
        call2 = _make_call(
            2,
            "TITLE_RESTORE",
            endpoint,
            restore_attempt["payload_title_sha256"],
            status2,
            restored_doc,
            requested_at=restore_requested_at,
            observed_at=restore_observed_at,
        )
        effect_calls = [call1, call2]
        clean = (
            call1["readback"]["title_sha256"]
            == apply_attempt["payload_title_sha256"]
            and call1["readback"]["head_sha"] == sealed_head
            and call2["readback"]["title_sha256"] == original_sha
            and call2["readback"]["head_sha"] == sealed_head
        )
        if clean:
            state = "RESTORED"
            reconciliation = None
            evidence_at = restore_observed_at
        else:
            reconciliation = _reconcile(
                transport, endpoint, clock=clock, after=restore_observed_at
            )
            state = "EFFECT_UNKNOWN"
            evidence_at = reconciliation["observed_at"]
    except Exception:  # noqa: BLE001 - restore may have crossed the effect boundary
        reconciliation = _reconcile(
            transport, endpoint, clock=clock, after=restore_requested_at
        )
        effect_calls = [call1]
        state = "EFFECT_UNKNOWN"
        evidence_at = reconciliation["observed_at"]

    terminal_at = _event_time(clock, after=evidence_at)
    _advance_journal(
        journal_path,
        _journal_record(
            state=state,
            bound_identity=bound_identity,
            selector_observation=selector_observation,
            owner_event_baseline=owner_event_baseline,
            effect_attempts=attempts,
            effect_calls=effect_calls,
            reconciliation=reconciliation,
            pre_effect_observation=pre_effect_observation,
            recorded_at=terminal_at,
        ),
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


def _owner_rename_evidence(
    *,
    transport: GhTransport,
    preflight: Mapping[str, Any],
    owner_event_baseline: Mapping[str, Any],
    effect_attempts: Sequence[Mapping[str, Any]],
    effect_calls: Sequence[Mapping[str, Any]],
    observed_at: str,
) -> list[dict[str, Any]]:
    """Bind attempted title transitions to post-baseline GitHub owner evidence."""
    if not effect_attempts:
        return []
    validate_owner_event_baseline(owner_event_baseline)
    baseline_ids = set(owner_event_baseline["rename_event_ids"])
    payload = _fetch_issue_events(
        transport,
        str(preflight["repository"]),
        int(preflight["pr_number"]),
    )
    window_end = _parse_iso_utc(str(observed_at))
    candidates: list[dict[str, Any]] = []
    for raw in payload:
        if raw.get("event") != "renamed":
            continue
        event_id = raw.get("id")
        actor = raw.get("actor")
        rename = raw.get("rename")
        created_at = raw.get("created_at")
        if (
            type(event_id) is not int
            or event_id <= 0
            or not isinstance(actor, Mapping)
            or not isinstance(actor.get("login"), str)
            or not actor.get("login")
            or not isinstance(rename, Mapping)
            or not isinstance(rename.get("from"), str)
            or not isinstance(rename.get("to"), str)
            or not isinstance(created_at, str)
        ):
            raise OutcomeLearningCliError("GitHub rename event has an invalid shape")
        if event_id in baseline_ids:
            continue
        created = _parse_iso_utc(created_at)
        if created <= window_end:
            candidates.append(
                {
                    "id": event_id,
                    "actor_login": actor["login"],
                    "created_at": created_at,
                    "created": created,
                    "from": rename["from"],
                    "to": rename["to"],
                }
            )
    candidates.sort(key=lambda item: (item["created"], item["id"]))
    evidence: list[dict[str, Any]] = []
    previous_sha = preflight["original_title_sha256"]
    previous_length = preflight["original_title_length"]
    cursor = 0
    selected_ids: set[int] = set()
    for attempt in effect_attempts:
        matches: list[tuple[int, dict[str, Any]]] = []
        requested_floor = _parse_iso_utc(
            str(attempt["requested_at"])
        ).replace(microsecond=0)
        for index in range(cursor, len(candidates)):
            event = candidates[index]
            if event["created"] < requested_floor:
                continue
            if (
                _sha256_hex_text(event["from"]) == previous_sha
                and len(event["from"]) == previous_length
                and _sha256_hex_text(event["to"])
                == attempt["payload_title_sha256"]
                and len(event["to"]) == attempt["payload_title_length"]
            ):
                matches.append((index, event))
        if not matches:
            break
        if len(matches) != 1:
            raise OutcomeLearningCliError(
                f"GitHub owner evidence is ambiguous for {attempt['kind']}"
            )
        index, event = matches[0]
        selected_ids.add(event["id"])
        evidence.append(
            {
                "schema": OWNER_RENAME_EVENT_SCHEMA,
                "repository": preflight["repository"],
                "pr_number": preflight["pr_number"],
                "event_id": event["id"],
                "actor_login": event["actor_login"],
                "transition": attempt["kind"],
                "created_at": event["created_at"],
                "observed_at": observed_at,
                "from_title_sha256": _sha256_hex_text(event["from"]),
                "from_title_length": len(event["from"]),
                "to_title_sha256": _sha256_hex_text(event["to"]),
                "to_title_length": len(event["to"]),
                "privacy_class": PRIVACY_CLASS,
            }
        )
        previous_sha = attempt["payload_title_sha256"]
        previous_length = attempt["payload_title_length"]
        cursor = index + 1

    unbound = [item["id"] for item in candidates if item["id"] not in selected_ids]
    if unbound:
        raise OutcomeLearningCliError(
            f"unbound GitHub rename events occurred after the pre-effect baseline: {unbound}"
        )
    if len(evidence) < len(effect_calls):
        raise OutcomeLearningCliError(
            "GitHub owner rename-event evidence is missing for a completed effect call"
        )
    return evidence


def _derive_effect_edge(
    journal: Mapping[str, Any],
    owner_effect_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, bool]:
    selector = journal.get("selector_observation")
    selector_repeated_single_pr = bool(
        isinstance(selector, Mapping)
        and selector.get("match_count") == 1
        and selector.get("matched_pr_number")
        == journal["bound_identity"]["preflight_pr_number"]
    )
    owner_events_verified = len(owner_effect_evidence) >= len(
        journal.get("effect_calls", [])
    )
    checks = {
        "parent_proven": True,
        "expectation_reacquired_from_sealed_commit": True,
        "expectation_digest_matched": True,
        "request_reacquired_from_sealed_commit": True,
        "request_digest_matched": True,
        "selector_repeated_single_pr": selector_repeated_single_pr,
        "owner_rename_events_verified": owner_events_verified,
    }
    return {**checks, "bindings_verified": all(checks.values())}


def cmd_outcome(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    transport: GhTransport | None = None,
    clock: Clock | None = None,
    journal_root: Path | None = None,
) -> int:
    """Assemble an outcome from sealed bytes, a closed journal, and owner events."""
    runner = runner or SubprocessRunner()
    transport = transport or GhCliTransport(runner)
    preflight = _read_json(args.preflight)
    supplied_expectation = _read_json(args.expectation)
    supplied_request = _read_json(args.request)
    validate_preflight(preflight)
    validate_expectation(supplied_expectation)
    validate_canary_request(supplied_request)

    expectation, request, _sealed_parent = _reacquire_sealed_episode(
        runner, args.mastermind_root, preflight
    )
    if canonical_digest(expectation) != canonical_digest(supplied_expectation):
        raise OutcomeLearningCliError(
            "supplied expectation does not equal the exact committed expectation"
        )
    if canonical_digest(request) != canonical_digest(supplied_request):
        raise OutcomeLearningCliError(
            "supplied request does not equal the exact committed request"
        )
    if request["operation_key"] != expectation["operation_key"]:
        raise OutcomeLearningCliError(
            "request.operation_key does not match expectation.operation_key"
        )
    if request["expectation_sealed_hash"] != expectation["sealed_hash"]:
        raise OutcomeLearningCliError(
            "request.expectation_sealed_hash does not match expectation.sealed_hash"
        )

    request_digest = canonical_digest(request).removeprefix("sha256:")
    journal_path = _canonical_journal_path(
        request, preflight, journal_root=journal_root
    )
    journal = _read_json(journal_path)
    _validate_journal_record(journal)
    expected_identity = _canonical_journal_identity(request, preflight)
    if expected_identity["request_digest"] != request_digest:
        raise OutcomeLearningCliError(
            "canonical journal request identity does not match the supplied request"
        )
    if journal["bound_identity"] != expected_identity:
        raise OutcomeLearningCliError(
            "canonical journal bound_identity does not match the supplied episode"
        )

    journal_state = journal["state"]
    if journal_state not in _JOURNAL_TERMINAL_STATES:
        raise OutcomeLearningCliError(
            f"journal is in non-terminal state {journal_state!r} — refusing"
        )
    effect_state = _JOURNAL_STATE_TO_EFFECT_STATE[journal_state]
    effect_attempts = list(journal["effect_attempts"])
    effect_calls = list(journal["effect_calls"])
    owner_event_baseline = journal["owner_event_baseline"]
    reconciliation = journal["reconciliation"]
    pre_effect_observation = journal["pre_effect_observation"]
    original_sha = preflight["original_title_sha256"]
    sealed_head = preflight["sealed_commit_sha"]

    owner_observed_at = _event_time(clock, after=journal["recorded_at"])
    owner_effect_evidence = _owner_rename_evidence(
        transport=transport,
        preflight=preflight,
        owner_event_baseline=owner_event_baseline,
        effect_attempts=effect_attempts,
        effect_calls=effect_calls,
        observed_at=owner_observed_at,
    )

    if effect_state == "INVALIDATED_BEFORE_EFFECT":
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
    elif effect_state == "APPLIED_AND_RESTORED":
        restoration = {
            "byte_identical": True,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": original_sha,
            "head_unchanged": True,
        }
    elif (
        reconciliation is not None
        and reconciliation.get("observed_title_sha256") is not None
    ):
        observed_title = reconciliation["observed_title_sha256"]
        observed_head = reconciliation.get("observed_head_sha")
        restoration = {
            "byte_identical": observed_title == original_sha,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": observed_title,
            "head_unchanged": observed_head == sealed_head,
        }
    elif reconciliation is not None:
        restoration = {
            "byte_identical": None,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": "UNOBSERVED",
            "head_unchanged": False,
        }
    elif effect_calls:
        last = effect_calls[-1]
        restoration = {
            "byte_identical": last["readback"]["title_sha256"] == original_sha,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": last["readback"]["title_sha256"],
            "head_unchanged": last["readback"]["head_sha"] == sealed_head,
        }
    else:
        restoration = {
            "byte_identical": None,
            "prestate_title_sha256": original_sha,
            "poststate_title_sha256": "UNOBSERVED",
            "head_unchanged": False,
        }

    outcome_pre_effect_observation = (
        pre_effect_observation if effect_state == "INVALIDATED_BEFORE_EFFECT" else None
    )
    outcome_recorded_at = _event_time(clock, after=owner_observed_at)
    outcome = build_outcome(
        operation_key=expectation["operation_key"],
        expectation_sealed_hash=expectation["sealed_hash"],
        request=request,
        preflight=preflight,
        effect_attempts=effect_attempts,
        effect_calls=effect_calls,
        owner_event_baseline=owner_event_baseline,
        owner_effect_evidence=owner_effect_evidence,
        effect_state=effect_state,
        restoration=restoration,
        pre_effect_observation=outcome_pre_effect_observation,
        effect_edge=_derive_effect_edge(journal, owner_effect_evidence),
        recorded_at=outcome_recorded_at,
    )
    validate_outcome(outcome, expectation, request)
    _write_artifact(args.out, outcome)
    print(f"effect_state={outcome['effect_state']}")
    return 0


# --------------------------------------------------------------------------- evaluate / self-model / project


def cmd_evaluate(
    args: argparse.Namespace, *, clock: Clock | None = None
) -> int:
    expectation = _read_json(args.expectation)
    outcome = _read_json(args.outcome)
    request = _read_json(args.request)
    evaluation = evaluate_episode(
        expectation,
        outcome,
        request,
        recorded_at=_event_time(clock, after=outcome["recorded_at"]),
    )
    revision: dict[str, Any] | None = None
    out_revision = getattr(args, "out_revision", None)
    if out_revision is not None:
        revision = build_initial_artifact_revision(
            artifact_kind="EVALUATION",
            episode_identity=_episode_identity(expectation, request),
            payload=evaluation,
            owner_evidence=[],
            corrected_at=_event_time(clock, after=evaluation["recorded_at"]),
        )
    _write_artifact(args.out, evaluation)
    if revision is not None:
        _write_artifact(out_revision, revision)
    print(
        f"causal_grade={evaluation['causal_grade']} "
        f"promotion={evaluation['promotion']}"
    )
    return 0


def cmd_self_model(
    args: argparse.Namespace, *, clock: Clock | None = None
) -> int:
    evaluation = _read_json(args.evaluation)
    expectation = _read_json(args.expectation)
    self_model = build_self_model(
        evaluation,
        expectation,
        recorded_at=_event_time(clock, after=evaluation["recorded_at"]),
    )
    _write_artifact(args.out, self_model)
    print(
        f"sample_size={self_model['sample_size']} "
        f"promotion={self_model['promotion']}"
    )
    return 0


def cmd_project(
    args: argparse.Namespace, *, clock: Clock | None = None
) -> int:
    evaluation = _read_json(args.evaluation)
    expectation = _read_json(args.expectation)
    outcome = _read_json(args.outcome)
    recorded_at = _event_time(clock, after=evaluation["recorded_at"])
    key_hint = f"OLV1-EPISODE-CONSEQUENCE-{recorded_at[:10]}"
    projection = build_agentos_projection(
        evaluation,
        expectation,
        outcome,
        recorded_at=recorded_at,
        key_hint=key_hint,
    )
    _write_artifact(args.out, projection)
    print(f"candidates={len(projection['candidates'])}")
    return 0


# --------------------------------------------------------------------------- remote publication / maturation


def cmd_capture_publication(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    transport: GhTransport | None = None,
    clock: Clock | None = None,
) -> int:
    """Capture immutable git/GitHub readback; this command has no write transport."""
    runner = runner or SubprocessRunner()
    transport = transport or GhCliTransport(runner)
    expectation = _read_json(args.expectation)
    request = _read_json(args.request)
    identity = _episode_identity(expectation, request)
    if args.repo != request["repository"] or args.branch != request["branch"]:
        raise OutcomeLearningCliError(
            "publication repo/branch must exactly match the sealed canary request"
        )
    if _SHA40_RE.fullmatch(args.target_commit) is None:
        raise OutcomeLearningCliError("target commit must be 40 lowercase hex")
    if _SHA40_RE.fullmatch(args.frozen_evidence_commit) is None:
        raise OutcomeLearningCliError(
            "frozen evidence commit must be 40 lowercase hex"
        )

    _, branch_doc = transport.get(
        f"repos/{args.repo}/git/ref/heads/{args.branch}"
    )
    branch_sha = _extract_remote_sha(branch_doc, where="branch")
    if branch_sha != args.target_commit:
        raise OutcomeLearningCliError(
            f"remote branch head {branch_sha} does not equal target commit "
            f"{args.target_commit}"
        )
    _, pr_doc = transport.get(f"repos/{args.repo}/pulls/{args.pr_number}")
    pr_sha = _extract_remote_sha(pr_doc, where="PR")
    if pr_sha != args.target_commit:
        raise OutcomeLearningCliError(
            f"remote PR head {pr_sha} does not equal target commit {args.target_commit}"
        )

    if args.stage == "MATURATION_COMMIT":
        _require_commit_ancestor(
            runner,
            args.mastermind_root,
            args.frozen_evidence_commit,
            args.target_commit,
        )
    artifact_digests = [
        _artifact_digest_at_commit(
            runner,
            args.mastermind_root,
            args.target_commit,
            path,
        )
        for path in args.artifact
    ]
    checks: list[dict[str, Any]] = []
    observed_at = _event_time(clock)
    if args.stage == "MATURATION_COMMIT":
        raw_checks = _check_runs_page(transport, args.repo, args.target_commit)
        if not raw_checks:
            raise OutcomeLearningCliError(
                "MATURATION_COMMIT has no terminal hosted check runs"
            )
        checks = [
            _normalized_check_evidence(
                raw,
                repository=args.repo,
                expected_commit_sha=args.target_commit,
                observed_at=observed_at,
            )
            for raw in raw_checks
        ]
        observed_at = _event_time(clock, after=observed_at)

    receipt = build_remote_publication_receipt(
        stage=args.stage,
        repository=args.repo,
        branch=args.branch,
        pr_number=args.pr_number,
        episode_identity=identity,
        target_commit_sha=args.target_commit,
        frozen_evidence_commit_sha=args.frozen_evidence_commit,
        remote_branch_head_sha=branch_sha,
        remote_pr_head_sha=pr_sha,
        artifact_digests=artifact_digests,
        checks=checks,
        observed_at=observed_at,
    )
    out = _refuse_inside_repo(args.out, where="remote publication receipt")
    _write_artifact(out, receipt)
    print(
        f"publication_stage={receipt['stage']} "
        f"target_commit={receipt['target_commit_sha']}"
    )
    return 0


def cmd_mature_evaluation(
    args: argparse.Namespace,
    *,
    transport: GhTransport | None = None,
    clock: Clock | None = None,
) -> int:
    """Append one deterministic delayed-CI correction from exact GitHub evidence."""
    transport = transport or GhCliTransport()
    expectation = _read_json(args.expectation)
    request = _read_json(args.request)
    outcome = _read_json(args.outcome)
    initial_evaluation = _read_json(args.initial_evaluation)
    initial_revision = _read_json(args.initial_revision)
    evidence_receipt = _read_json(args.evidence_receipt)

    identity = _episode_identity(expectation, request)
    validate_outcome(outcome, expectation, request)
    validate_evaluation(initial_evaluation, expectation, outcome)
    validate_artifact_revision(initial_revision)
    validate_remote_publication_receipt(evidence_receipt)
    if initial_revision["artifact_kind"] != "EVALUATION":
        raise OutcomeLearningCliError("initial revision is not an EVALUATION revision")
    if initial_revision["payload"] != initial_evaluation:
        raise OutcomeLearningCliError(
            "initial revision payload does not equal the immutable initial evaluation"
        )
    if initial_revision["episode_identity"] != identity:
        raise OutcomeLearningCliError(
            "initial revision episode identity does not match expectation/request"
        )
    if evidence_receipt["stage"] != "EVIDENCE_COMMIT":
        raise OutcomeLearningCliError(
            "CI maturation requires an EVIDENCE_COMMIT publication receipt"
        )
    if evidence_receipt["episode_identity"] != identity:
        raise OutcomeLearningCliError(
            "evidence receipt episode identity does not match expectation/request"
        )
    frozen_sha = evidence_receipt["frozen_evidence_commit_sha"]
    repository = evidence_receipt["repository"]
    raw_checks = _check_runs_page(transport, repository, frozen_sha)
    matches = [raw for raw in raw_checks if raw.get("name") == args.check_name]
    if len(matches) != 1:
        raise OutcomeLearningCliError(
            f"expected exactly one GitHub check named {args.check_name!r}, got {len(matches)}"
        )
    check_observed_at = _event_time(clock, after=evidence_receipt["observed_at"])
    owner_check = _normalized_check_evidence(
        matches[0],
        repository=repository,
        expected_commit_sha=frozen_sha,
        observed_at=check_observed_at,
    )
    evaluation_recorded_at = _event_time(clock, after=check_observed_at)
    matured = mature_ci_evaluation(
        expectation,
        outcome,
        request,
        initial_evaluation,
        evidence_commit_sha=frozen_sha,
        owner_check=owner_check,
        expected_check_name=args.check_name,
        recorded_at=evaluation_recorded_at,
    )
    correction = build_correction_revision(
        initial_revision,
        payload=matured,
        correction_reason="DELAYED_OWNER_EVIDENCE_MATURATION",
        owner_evidence=[owner_check],
        corrected_at=_event_time(clock, after=evaluation_recorded_at),
    )
    validate_revision_chain([initial_revision, correction])
    _write_artifact(args.out_evaluation, matured)
    _write_artifact(args.out_revision, correction)
    print(
        f"matured_metric=ci_green_at_frozen_evidence_commit "
        f"evidence_commit={frozen_sha} revision={correction['revision']}"
    )
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


def _verify_remote_proof(
    *,
    expectation: Mapping[str, Any],
    request: Mapping[str, Any],
    outcome: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    self_model: Mapping[str, Any],
    projection: Mapping[str, Any],
    revisions: Sequence[Mapping[str, Any]],
    evidence_receipt: Mapping[str, Any],
    final_receipt: Mapping[str, Any],
    runner: Runner,
    transport: GhTransport,
    mastermind_root: str | None,
) -> None:
    chain = validate_revision_chain(revisions)
    identity = _episode_identity(expectation, request)
    if len(chain) < 2:
        raise OutcomeLearningCliError(
            "production proof requires an initial revision and a later correction"
        )
    if any(item["artifact_kind"] != "EVALUATION" for item in chain):
        raise OutcomeLearningCliError(
            "production proof revision chain must contain only EVALUATION revisions"
        )
    if any(item["episode_identity"] != identity for item in chain):
        raise OutcomeLearningCliError(
            "production proof revision chain does not match the sealed episode"
        )
    if chain[-1]["payload"] != evaluation:
        raise OutcomeLearningCliError(
            "proof evaluation is not the authoritative payload of the latest revision"
        )
    validate_remote_publication_receipt(evidence_receipt)
    validate_remote_publication_receipt(final_receipt)
    if evidence_receipt["stage"] != "EVIDENCE_COMMIT":
        raise OutcomeLearningCliError(
            "production proof requires one EVIDENCE_COMMIT receipt"
        )
    if final_receipt["stage"] != "MATURATION_COMMIT":
        raise OutcomeLearningCliError(
            "production proof requires one MATURATION_COMMIT receipt"
        )
    if (
        evidence_receipt["episode_identity"] != identity
        or final_receipt["episode_identity"] != identity
    ):
        raise OutcomeLearningCliError(
            "remote publication receipts do not match the sealed episode"
        )
    frozen_sha = evidence_receipt["target_commit_sha"]
    if evidence_receipt["frozen_evidence_commit_sha"] != frozen_sha:
        raise OutcomeLearningCliError(
            "evidence receipt does not freeze its own target commit"
        )
    if final_receipt["frozen_evidence_commit_sha"] != frozen_sha:
        raise OutcomeLearningCliError(
            "final receipt does not preserve the frozen evidence commit"
        )
    if final_receipt["target_commit_sha"] == frozen_sha:
        raise OutcomeLearningCliError(
            "final proof subject cannot recursively equal the frozen evidence commit"
        )
    owner_checks = [
        evidence
        for evidence in chain[-1]["owner_evidence"]
        if evidence.get("schema") == "mastermind.olv1_github_check_evidence.v1"
    ]
    if len(owner_checks) != 1 or owner_checks[0]["commit_sha"] != frozen_sha:
        raise OutcomeLearningCliError(
            "latest evaluation revision lacks one exact frozen-commit check receipt"
        )
    if _parse_iso_utc(chain[-1]["corrected_at"]) >= _parse_iso_utc(
        final_receipt["observed_at"]
    ):
        raise OutcomeLearningCliError(
            "final remote receipt must postdate the evaluation correction"
        )
    if _parse_iso_utc(projection["recorded_at"]) >= _parse_iso_utc(
        final_receipt["observed_at"]
    ):
        raise OutcomeLearningCliError(
            "final remote receipt must postdate the candidate projection"
        )

    final_sha = final_receipt["target_commit_sha"]
    _require_commit_ancestor(runner, mastermind_root, frozen_sha, final_sha)
    _verify_receipt_artifacts_at_commit(
        evidence_receipt,
        runner=runner,
        mastermind_root=mastermind_root,
    )
    _verify_receipt_artifacts_at_commit(
        final_receipt,
        runner=runner,
        mastermind_root=mastermind_root,
    )
    _require_exact_artifact_contents(
        evidence_receipt,
        {
            _EXPECTATION_REPO_PATH: expectation,
            _REQUEST_REPO_PATH: request,
            _PREFLIGHT_REPO_PATH: outcome["preflight"],
            _OUTCOME_REPO_PATH: outcome,
            _EVALUATION_V1_REPO_PATH: chain[0]["payload"],
            _REVISION_V1_REPO_PATH: chain[0],
        },
        where="evidence publication",
    )
    _require_exact_artifact_contents(
        final_receipt,
        {
            _EVALUATION_V2_REPO_PATH: evaluation,
            _REVISION_V2_REPO_PATH: chain[-1],
            _SELF_MODEL_V2_REPO_PATH: self_model,
            _PROJECTION_V2_REPO_PATH: projection,
        },
        where="final publication",
    )
    _verify_live_owner_check(owner_checks[0], transport=transport)
    _verify_live_final_receipt(final_receipt, transport=transport)


def cmd_proof(
    args: argparse.Namespace,
    *,
    runner: Runner | None = None,
    transport: GhTransport | None = None,
) -> int:
    expectation = _read_json(args.expectation)
    request = _read_json(args.request)
    outcome = _read_json(args.outcome)
    evaluation = _read_json(args.evaluation)
    self_model = _read_json(args.self_model)
    projection = _read_json(args.projection)

    _verify_proof_chain(expectation, request, outcome, evaluation, self_model, projection)

    revision_paths = list(getattr(args, "revision", None) or [])
    revisions = [_read_json(path) for path in revision_paths]
    evidence_path = getattr(args, "evidence_receipt", None)
    final_path = getattr(args, "final_publication_receipt", None)
    if bool(evidence_path) != bool(final_path):
        raise OutcomeLearningCliError(
            "remote proof requires both evidence and final publication receipts"
        )
    production = evidence_path is not None
    evidence_receipt: Mapping[str, Any] | None = None
    final_receipt: Mapping[str, Any] | None = None
    if revisions:
        chain = validate_revision_chain(revisions)
        if chain[-1]["payload"] != evaluation:
            raise OutcomeLearningCliError(
                "proof evaluation does not equal the latest supplied revision payload"
            )
    if production:
        runner = runner or SubprocessRunner()
        transport = transport or GhCliTransport(runner)
        evidence_receipt = _read_json(evidence_path)
        final_receipt = _read_json(final_path)
        _verify_remote_proof(
            expectation=expectation,
            request=request,
            outcome=outcome,
            evaluation=evaluation,
            self_model=self_model,
            projection=projection,
            revisions=revisions,
            evidence_receipt=evidence_receipt,
            final_receipt=final_receipt,
            runner=runner,
            transport=transport,
            mastermind_root=getattr(args, "mastermind_root", str(_ROOT)),
        )
        out_path = _refuse_inside_repo(args.out, where="production proof")
        title = "# OL-V1 Production Proof"
    else:
        out_path = Path(args.out)
        title = "# OL-V1 Local Candidate Proof"

    lines = [
        title,
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
    ]
    for index, revision in enumerate(revisions, start=1):
        lines.append(
            f"| R{index}. revision | evaluation revision {revision['revision']} | "
            f"`{revision['revision_id']}` |"
        )
    if production and evidence_receipt is not None and final_receipt is not None:
        lines.extend(
            [
                f"| remote 1 | frozen evidence commit | "
                f"`{evidence_receipt['target_commit_sha']}` |",
                f"| remote 2 | final subject commit | "
                f"`{final_receipt['target_commit_sha']}` |",
            ]
        )
    lines.extend(
        [
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
        ]
    )
    if production and evidence_receipt is not None and final_receipt is not None:
        lines.extend(
            [
                "- The delayed CI observation matured against the immutable frozen evidence commit "
                f"`{evidence_receipt['target_commit_sha']}`.",
                "- The final subject commit "
                f"`{final_receipt['target_commit_sha']}` was read back from both the remote branch "
                "and PR, and every captured terminal hosted check concluded success.",
                "- This production proof is an external attestation about that subject commit; "
                "it is intentionally not committed back onto the subject branch, avoiding a "
                "self-referential commit claim.",
            ]
        )
    else:
        lines.extend(
            [
                "- This is a local candidate proof only. It is not a production proof because "
                "the immutable remote evidence receipt, delayed owner observation, final remote "
                "readback, and terminal hosted checks have not all been supplied.",
            ]
        )
    lines.extend(
        [
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
    )
    _write_text_artifact(out_path, "\n".join(lines))
    print(f"wrote {out_path}")
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
        "--directive-intent-id",
        required=True,
        help=(
            "accepted, undispatched READ-only ceo_intent that binds the exact "
            "OL-V1 workstream, operation, carrier, expiry, and authority ceiling"
        ),
    )
    p_compose.add_argument("--operation-key", required=True)
    p_compose.add_argument("--agentos-records-digest", default=None)
    p_compose.set_defaults(func=cmd_compose)

    p_seal = sub.add_parser("seal", help="seal the expectation receipt + canary request")
    p_seal.add_argument("--composition", required=True)
    p_seal.add_argument("--episode-dir", required=True)
    p_seal.add_argument("--mastermind-root", default=str(_ROOT))
    p_seal.add_argument(
        "--selection-intent-id",
        default=None,
        help=(
            "required only when A1 returns multiple incomparable actionable options; "
            "must bind the exact packet, chosen option, carrier, operation, and "
            "no-effect authority ceiling"
        ),
    )
    p_seal.add_argument(
        "--parent-head",
        default=None,
        help="optional cross-check only (BLOCKER B): must exactly equal the adjudicated option's expected_head_sha, which is what is actually used",
    )
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
    p_preflight.add_argument("--out", required=True)
    p_preflight.set_defaults(func=cmd_preflight)

    p_canary = sub.add_parser("canary", help="apply the two-call PR-title canary")
    p_canary.add_argument("--preflight", required=True)
    p_canary.add_argument(
        "--request",
        required=True,
        help=(
            "kept for operator bookkeeping/consistency only — the effect edge "
            "reacquires expectation and request from their exact sealed-commit repo "
            "paths, cross-checks both blob ids/digests, and never trusts this file's bytes"
        ),
    )
    p_canary.add_argument(
        "--mastermind-root",
        default=None,
        help="explicit cwd for the committed-blob reacquisition git call (BLOCKER C)",
    )
    p_canary.set_defaults(func=cmd_canary)

    p_outcome = sub.add_parser("outcome", help="assemble + validate the outcome artifact")
    p_outcome.add_argument("--preflight", required=True)
    p_outcome.add_argument("--expectation", required=True)
    p_outcome.add_argument("--request", required=True)
    p_outcome.add_argument(
        "--mastermind-root",
        default=str(_ROOT),
        help="checkout used to reacquire exact committed expectation/request blobs",
    )
    p_outcome.add_argument("--out", required=True)
    p_outcome.set_defaults(func=cmd_outcome)

    p_evaluate = sub.add_parser("evaluate", help="deterministic DESCRIPTIVE_ONLY evaluation")
    p_evaluate.add_argument("--expectation", required=True)
    p_evaluate.add_argument("--outcome", required=True)
    p_evaluate.add_argument("--request", required=True)
    p_evaluate.add_argument("--out", required=True)
    p_evaluate.add_argument(
        "--out-revision",
        default=None,
        help="optional explicit revision-1 envelope with null predecessor",
    )
    p_evaluate.set_defaults(func=cmd_evaluate)

    p_self_model = sub.add_parser("self-model", help="n=1 non-promoting self-model")
    p_self_model.add_argument("--evaluation", required=True)
    p_self_model.add_argument("--expectation", required=True)
    p_self_model.add_argument("--out", required=True)
    p_self_model.set_defaults(func=cmd_self_model)

    p_project = sub.add_parser("project", help="candidate-only Agent OS projection")
    p_project.add_argument("--evaluation", required=True)
    p_project.add_argument("--expectation", required=True)
    p_project.add_argument("--outcome", required=True)
    p_project.add_argument("--out", required=True)
    p_project.set_defaults(func=cmd_project)

    p_publication = sub.add_parser(
        "capture-publication",
        help="capture exact remote branch/PR/blob/check readback without any write",
    )
    p_publication.add_argument(
        "--stage", choices=["EVIDENCE_COMMIT", "MATURATION_COMMIT"], required=True
    )
    p_publication.add_argument("--expectation", required=True)
    p_publication.add_argument("--request", required=True)
    p_publication.add_argument("--repo", required=True)
    p_publication.add_argument("--branch", required=True)
    p_publication.add_argument("--pr-number", type=int, required=True)
    p_publication.add_argument("--target-commit", required=True)
    p_publication.add_argument("--frozen-evidence-commit", required=True)
    p_publication.add_argument("--artifact", action="append", required=True)
    p_publication.add_argument("--mastermind-root", default=str(_ROOT))
    p_publication.add_argument("--out", required=True)
    p_publication.set_defaults(func=cmd_capture_publication)

    p_mature = sub.add_parser(
        "mature-evaluation",
        help="append one delayed CI evaluation correction from exact check-run evidence",
    )
    p_mature.add_argument("--expectation", required=True)
    p_mature.add_argument("--request", required=True)
    p_mature.add_argument("--outcome", required=True)
    p_mature.add_argument("--initial-evaluation", required=True)
    p_mature.add_argument("--initial-revision", required=True)
    p_mature.add_argument("--evidence-receipt", required=True)
    p_mature.add_argument("--check-name", required=True)
    p_mature.add_argument("--out-evaluation", required=True)
    p_mature.add_argument("--out-revision", required=True)
    p_mature.set_defaults(func=cmd_mature_evaluation)

    p_proof = sub.add_parser(
        "proof", help="render a local candidate or remote-gated production proof"
    )
    p_proof.add_argument("--expectation", required=True)
    p_proof.add_argument("--request", required=True)
    p_proof.add_argument("--outcome", required=True)
    p_proof.add_argument("--evaluation", required=True)
    p_proof.add_argument("--self-model", dest="self_model", required=True)
    p_proof.add_argument("--project", dest="projection", required=True)
    p_proof.add_argument(
        "--revision",
        action="append",
        default=[],
        help="ordered append-only evaluation revision (repeat from revision 1 onward)",
    )
    p_proof.add_argument("--evidence-receipt", default=None)
    p_proof.add_argument("--final-publication-receipt", default=None)
    p_proof.add_argument("--mastermind-root", default=str(_ROOT))
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
