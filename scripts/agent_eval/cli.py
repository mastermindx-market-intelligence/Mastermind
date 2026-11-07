"""EVAL-R0 command-line surface (plan Task 7).

Every command prints exactly one canonical JSON object to stdout and bounded
diagnostics to stderr. Exit codes:

  0 = requested shape/graph/artifact operation succeeded cleanly
  1 = command completed with an invalid/degraded/unscored/insufficient result
  2 = usage/shape/graph-context/conflict/corruption/privacy/filesystem error

No command ever prints ``EVIDENCE_CONTENT_VERIFIED`` -- R0 implements only
``SHAPE_VALID`` and ``EVALUATION_GRAPH_VERIFIED``. ``summarize`` always
exits 1: R0's evidence grade is always ``INSUFFICIENT_EVIDENCE`` by design
(external content is never verified), and that is reported honestly rather
than as a clean success.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, localcontext
import json
import os
import sys
from pathlib import Path
from typing import Any

from scripts.agent_eval import MAX_CANONICAL_ARTIFACT_BYTES, contracts, corpus, scoring, store, validity, verification
from scripts.agent_eval.canonical import canonical_json_bytes, digest_value
from scripts.agent_eval.errors import ArtifactConflictError, ContractError, VerificationContextError

DEFAULT_ANALYSIS_VERSION = "mastermind.agent_evaluation_r0_analysis.v1"

_EXIT_OK = 0
_EXIT_INCOMPLETE = 1
_EXIT_ERROR = 2

_EXPECTED_EXCEPTIONS = (ContractError, VerificationContextError, ArtifactConflictError)


class CliUsageError(ValueError):
    """A usage-level error (bad argument combination, missing file, ...)."""


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        raise CliUsageError(f"no such file: {path}")
    if not path.is_file():
        raise CliUsageError(f"not a regular file: {path}")
    size = path.stat().st_size
    if size > MAX_CANONICAL_ARTIFACT_BYTES:
        raise CliUsageError(f"input file exceeds the canonical artifact size bound: {path}")
    with open(path, "rb") as handle:
        raw = handle.read(MAX_CANONICAL_ARTIFACT_BYTES + 1)
    if len(raw) > MAX_CANONICAL_ARTIFACT_BYTES:
        raise CliUsageError(f"input file exceeds the canonical artifact size bound: {path}")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliUsageError(f"input file is not valid JSON: {path} ({exc})") from exc


def _write_exclusive_json_file(path: Path, document: dict) -> None:
    canonical_bytes = canonical_json_bytes(document)
    if len(canonical_bytes) > MAX_CANONICAL_ARTIFACT_BYTES:
        raise CliUsageError("output document exceeds the canonical artifact size bound")
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise CliUsageError(f"output path already exists, refusing to overwrite: {path}") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(canonical_bytes)
        handle.flush()
        os.fsync(handle.fileno())


def _print_json(payload: dict) -> None:
    sys.stdout.write(canonical_json_bytes(payload).decode("utf-8"))
    sys.stdout.write("\n")


def _defect_payload(exc: Exception) -> list[dict]:
    defects = getattr(exc, "defects", ())
    return [{"path": d.path, "code": d.code, "message": d.message} for d in defects]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_validate_shape(args: argparse.Namespace) -> int:
    document = _load_json_file(Path(args.document))
    scope = contracts.validate_document_shape(document)
    _print_json({"scope": scope})
    return _EXIT_OK


def _cmd_verify_graph(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    target = Path(args.target)
    stored_candidate = artifact_store.root / target
    if not target.is_absolute() and stored_candidate.exists():
        result = artifact_store.verify_graph(target)
    else:
        document = _load_json_file(target)
        result = store._graph_verify_for(document, artifact_store)
    _print_json(
        {
            "scope": result.scope,
            "artifact_id": result.artifact_id,
            "artifact_digest": result.artifact_digest,
            "external_content_unverified_refs": list(result.external_content_unverified_refs),
        }
    )
    return _EXIT_OK


def _cmd_create(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    document = _load_json_file(Path(args.document))
    result = artifact_store.create(document)
    _print_json(
        {
            "disposition": result.disposition.value,
            "path": result.path,
            "artifact_id": result.artifact_id,
            "artifact_digest": result.artifact_digest,
        }
    )
    return _EXIT_OK


def _cmd_finalize_run(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    draft = _load_json_file(Path(args.draft))
    if draft.get("schema") != contracts.RUN_DRAFT_SCHEMA:
        raise CliUsageError("--draft must be a mastermind.agent_evaluation_run_draft.v1 document")

    scenario_ref = draft.get("scenario") or {}
    scenario = artifact_store.resolve_scenario(scenario_ref.get("scenario_id"), scenario_ref.get("scenario_version"))
    if scenario is None:
        raise CliUsageError("draft's scenario could not be resolved from --root")

    configuration = artifact_store.resolve_configuration((draft.get("configuration") or {}).get("configuration_id"))
    if configuration is None:
        raise CliUsageError("draft's configuration could not be resolved from --root")

    experiment_id = (draft.get("comparison") or {}).get("experiment_id")
    experiment = None
    if experiment_id is not None:
        experiment = artifact_store.resolve_experiment(experiment_id)
        if experiment is None:
            raise CliUsageError("draft's experiment_id could not be resolved from --root")

    run = validity.finalize_run_receipt(
        scenario,
        configuration,
        experiment,
        draft,
        validator_id=args.validator_id,
        validator_version=args.validator_version,
        validator_code_ref=args.validator_code_ref,
        validated_at=args.validated_at,
        created_at=args.created_at,
    )
    _write_exclusive_json_file(Path(args.output), run)
    _print_json(
        {
            "scope": "EVALUATION_GRAPH_VERIFIED",
            "run_id": run["run_id"],
            "run_digest": run["run_digest"],
            "validity_status": run["validity"]["status"],
            "reason_codes": list(run["validity"]["reason_codes"]),
            "output": str(args.output),
        }
    )
    return _EXIT_OK if run["validity"]["status"] == "VALID" else _EXIT_INCOMPLETE


def _cmd_score_integrity(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    run = artifact_store.resolve_run(args.run_id)
    if run is None:
        raise CliUsageError(f"run could not be resolved from --root: {args.run_id}")
    scorer_pass = scoring.build_technical_integrity_scorer_pass(
        run,
        scorer_pass_id=args.id,
        scorer_code_ref=args.scorer_code_ref,
        created_at=args.created_at,
    )
    result = artifact_store.create(scorer_pass)
    statuses = {item["dimension"]: item["status"] for item in scorer_pass["dimension_results"]}
    _print_json(
        {
            "scope": "EVALUATION_GRAPH_VERIFIED",
            "disposition": result.disposition.value,
            "scorer_pass_id": scorer_pass["scorer_pass_id"],
            "dimension_results": statuses,
        }
    )
    return _EXIT_OK if all(status == "PASS" for status in statuses.values()) else _EXIT_INCOMPLETE


def _cmd_summarize(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    experiment = artifact_store.resolve_experiment(args.experiment_id)
    if experiment is None:
        raise CliUsageError(f"experiment could not be resolved from --root: {args.experiment_id}")
    scenario_refs = sorted(experiment["scenario_refs"], key=lambda ref: (ref["scenario_id"], ref["scenario_version"]))

    # plan §5.6 complete-enumeration law: one deterministic, read-only,
    # sorted enumeration of the trusted root -- never a caller-selected
    # subset.
    runs = artifact_store.enumerate_runs()
    scorer_passes = artifact_store.enumerate_scorer_passes()

    if len(scenario_refs) <= 1:
        # UNCHANGED single-scenario path (byte-stable): scenario_refs[0] is
        # correct here because there is only ever one scenario to pick.
        primary_scenario_ref = scenario_refs[0]
        scenario = artifact_store.resolve_scenario(
            primary_scenario_ref["scenario_id"], primary_scenario_ref["scenario_version"]
        )
        if scenario is None:
            raise CliUsageError("experiment's scenario could not be resolved from --root")

        evidence = scoring.summarize_experiment(
            experiment,
            scenario,
            runs,
            scorer_passes,
            evidence_ref_id=args.id,
            intended_owner=args.owner,
            review_at=args.review_at,
            created_at=args.created_at,
            analysis_version=DEFAULT_ANALYSIS_VERSION,
        )
        result = artifact_store.create(evidence)
        _print_json(
            {
                "scope": "EVALUATION_GRAPH_VERIFIED",
                "disposition": result.disposition.value,
                "evidence_ref_id": evidence["evidence_ref_id"],
                "evidence_grade": evidence["evidence_grade"],
                "verification_scopes": list(evidence["verification_scopes"]),
                "counts": evidence["counts"],
                "external_content_unverified": True,
            }
        )
        # R0's evidence grade is always INSUFFICIENT_EVIDENCE (external
        # content is never verified) -- report that honestly rather than
        # as a clean 0.
        return _EXIT_INCOMPLETE

    # EVAL-S1: multi-scenario experiment. The R0 scenario_refs[0] shortcut
    # above would silently apply the WRONG scenario's required_dimensions
    # to every other scenario's runs -- see docs/superpowers/plans/2026-09-
    # 01-agent-evaluation-s1-scorers.md. This path resolves EVERY declared
    # scenario and groups runs by their OWN scenario. Store-integration
    # wave (same operation): published through the SAME governed create-
    # only ``ArtifactStore.create()`` path the single-scenario branch above
    # uses -- store.py now dispatches the multi-scenario schema too, with
    # the same enumeration-equality anti-laundering guarantee (a caller-
    # selected subset of scenarios/runs is refused at create, never
    # silently accepted).
    scenarios = []
    for ref in scenario_refs:
        scenario = artifact_store.resolve_scenario(ref["scenario_id"], ref["scenario_version"])
        if scenario is None:
            raise CliUsageError(
                f"experiment's scenario could not be resolved from --root: {ref['scenario_id']} v{ref['scenario_version']}"
            )
        scenarios.append(scenario)

    evidence = scoring.summarize_multi_scenario_experiment(
        experiment,
        tuple(scenarios),
        runs,
        scorer_passes,
        evidence_ref_id=args.id,
        intended_owner=args.owner,
        review_at=args.review_at,
        created_at=args.created_at,
        analysis_version=DEFAULT_ANALYSIS_VERSION,
    )
    result = artifact_store.create(evidence)
    _print_json(
        {
            "scope": "EVALUATION_GRAPH_VERIFIED",
            "disposition": result.disposition.value,
            "evidence_ref_id": evidence["evidence_ref_id"],
            "evidence_grade": evidence["evidence_grade"],
            "verification_scopes": list(evidence["verification_scopes"]),
            "counts": evidence["counts"],
            "scenario_groups": [
                {"scenario_id": group["scenario_id"], "scenario_version": group["scenario_version"], "counts": group["counts"]}
                for group in evidence["scenario_groups"]
            ],
            "external_content_unverified": True,
        }
    )
    # R0/S1's evidence grade is always INSUFFICIENT_EVIDENCE (external
    # content is never verified) -- report that honestly rather than as a
    # clean 0.
    return _EXIT_INCOMPLETE


def _resource_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Evidence coverage over all verified receipts, including failed/invalid ones.

    Missing observations remain null, not zero. Amounts of unlike currencies
    remain separate. None of these observations confers product acceptance.
    """
    count = len(rows)
    resources = [row["resources"] for row in rows]
    output: dict[str, Any] = {"run_count": count}
    for field in ("input_tokens", "output_tokens", "tool_calls", "elapsed_ms"):
        known: list[int] = []
        for resource in resources:
            value = resource[field]
            if value is not None:
                if type(value) is not int or value < 0:
                    raise ValueError("invalid resource count")
                known.append(value)
        total = sum(known)
        if total > (2 ** 63 - 1):
            raise ValueError("resource count exceeds signed 64-bit canonical range")
        output[field] = {
            "known_sum": total if known else None,
            "total": total if count and len(known) == count else None,
            "reported_runs": len(known),
            "missing_runs": count - len(known),
        }

    complete = [r for r in resources if r["input_tokens"] is not None and r["output_tokens"] is not None]
    complete_sum = sum(r["input_tokens"] + r["output_tokens"] for r in complete)
    if complete_sum > (2 ** 63 - 1):
        raise ValueError("combined tokens exceed signed 64-bit canonical range")
    output["total_tokens"] = {
        "known_sum_from_complete_runs": complete_sum if complete else None,
        "total": complete_sum if count and len(complete) == count else None,
        "reported_runs": len(complete),
        "missing_runs": count - len(complete),
    }

    currencies: dict[str, list[Decimal]] = {}
    cost_missing = 0
    for resource in resources:
        value, currency = resource["estimated_marginal_cost"], resource["cost_currency"]
        if value is None or currency is None:
            cost_missing += 1
            continue
        if type(value) is not str or type(currency) is not str or not currency:
            raise ValueError("invalid estimated cost evidence")
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError("estimated marginal cost must be finite and nonnegative")
        currencies.setdefault(currency, []).append(amount)
    groups: list[dict[str, Any]] = []
    for currency, amounts in sorted(currencies.items()):
        with localcontext() as ctx:
            integer_digits = max(max(amount.adjusted() + 1, 1) for amount in amounts)
            decimal_places = max(max(-amount.as_tuple().exponent, 0) for amount in amounts)
            ctx.prec = max(28, integer_digits + decimal_places + len(str(len(amounts))) + 3)
            exact_sum = sum(amounts, Decimal(0))
            groups.append({
                "currency": currency,
                "known_estimated_sum": str(exact_sum),
                "reported_runs": len(amounts),
            })
    output["estimated_cost"] = {
        "by_currency": groups,
        "missing_runs": cost_missing,
        "complete_single_currency": bool(count) and cost_missing == 0 and len(groups) == 1,
    }
    output["provider_usage_reference_runs"] = sum(bool(r["provider_usage_ref"]) for r in resources)
    output["completion_status_counts"] = dict(sorted(Counter(r["execution"]["completion_status"] for r in rows).items()))
    output["validity_status_counts"] = dict(sorted(Counter(r["validity"]["status"] for r in rows).items()))
    return output


def _cmd_resources(args: argparse.Namespace) -> int:
    """Existing-store-only EVAL query; requires non-creating ArtifactStore API."""
    root = Path(args.root)
    try:
        if root.is_symlink() or not root.is_dir():
            raise CliUsageError("resources requires an existing non-symlink store root")
    except OSError as exc:
        raise CliUsageError("cannot access evaluation store root") from exc
    contracts.parse_experiment_id(args.experiment_id)
    try:
        source = store.ArtifactStore(root, create_root=False)
        experiment = source.resolve_experiment(args.experiment_id)
        if experiment is None:
            raise CliUsageError("experiment not found in the existing store")
        verification.verify_experiment_graph(experiment, source)
        population = sorted(source.enumerate_runs(), key=lambda run: run["run_id"])
        seen: set[str] = set()
        selected = []
        for run in population:
            run_id = run["run_id"]
            if run_id in seen:
                raise ValueError("duplicate run identity in full population")
            seen.add(run_id)
            if run["comparison"]["experiment_id"] != args.experiment_id:
                continue
            if source.resolve_run(run_id) != run:
                raise ValueError("run cannot be resolved identically by canonical identity")
            verification.verify_run_graph(run, source)
            selected.append(run)
        selected.sort(key=lambda run: run["run_id"])
        groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for run in selected:
            key = (
                run["comparison"]["arm_id"],
                run["configuration"]["configuration_id"],
                run["scenario"]["scenario_id"],
                str(run["scenario"]["scenario_version"]),
            )
            groups.setdefault(key, []).append(run)
        overall_usage = _resource_usage(selected)
        all_fields_reported = bool(selected) and all(
            overall_usage[field]["missing_runs"] == 0
            for field in ("input_tokens", "output_tokens", "tool_calls", "elapsed_ms")
        ) and overall_usage["estimated_cost"]["missing_runs"] == 0
        payload = {
            "schema": "mastermind.agent_evaluation_resource_summary.v1",
            "experiment_id": args.experiment_id,
            "experiment_digest": experiment["experiment_digest"],
            "verification_scope": "EVALUATION_GRAPH_VERIFIED",
            "external_content_verified": False,
            "population_scope": "experiment receipts observed by one complete store enumeration",
            "observed_receipts_digest": digest_value([
                {"run_id": run["run_id"], "run_digest": run["run_digest"]}
                for run in selected
            ]),
            "all_expected_runs_observed": None,
            "summary": overall_usage,
            "observed_resource_field_coverage": "COMPLETE" if all_fields_reported else "INCOMPLETE",
            "groups": [
                {"arm_id": key[0], "configuration_id": key[1], "scenario_id": key[2],
                 "scenario_version": key[3], **_resource_usage(group)}
                for key, group in sorted(groups.items())
            ],
            "cost_per_accepted_outcome": None,
            "runtime_changed": False,
            "limitations": [
                "A verified receipt is not an independently accepted product outcome.",
                "Elapsed times are receipt totals, not critical-path or wall-clock latency.",
                "Parent/child usage may overlap; unique provider billing is unverified.",
                "Token units are recorded observations, not normalized billable tokens.",
                "Unrecorded attempts, framing, review and integration remain unknown.",
                "Estimated costs and usage refs do not prove actual billing or subscription consumption.",
                "Missing observations are unknown, never zero; no winner or routing policy is claimed.",
            ],
        }
    except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
        raise CliUsageError("resource evidence is malformed, incomplete or inaccessible") from exc
    _print_json(payload)
    return _EXIT_OK if all_fields_reported else _EXIT_INCOMPLETE

def _cmd_corpus_verify(args: argparse.Namespace) -> int:
    """EVAL-C0: scenario-vs-corpus consistency check over a committed public
    corpus tree (never one of R0's three verification scopes -- this is a
    narrower, additive governance check; see scripts/agent_eval/corpus.py)."""
    corpus_root = Path(args.corpus_root)
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    if not corpus_root.is_dir():
        raise CliUsageError(f"no such corpus directory: {corpus_root}")
    report = corpus.verify_corpus_tree_consistency(corpus_root, repo_root)
    _print_json(
        {
            "result": report.result,
            "corpus_revision": report.corpus_revision,
            "corpus_tree_digest": report.corpus_tree_digest,
            "scenario_count": report.scenario_count,
            "holdout_count": report.holdout_count,
            "defect_count": len(report.defects),
            "defects": [{"path": d.path, "code": d.code, "message": d.message} for d in report.defects],
        }
    )
    return _EXIT_OK if report.result == "CONSISTENT" else _EXIT_ERROR


def _cmd_verify_tree_graph(args: argparse.Namespace) -> int:
    artifact_store = store.ArtifactStore(args.root)
    defects = artifact_store.verify_tree_graph()
    _print_json(
        {
            "scope": "EVALUATION_GRAPH_VERIFIED",
            "defect_count": len(defects),
            "defects": [{"path": d.path, "code": d.code, "message": d.message} for d in defects],
        }
    )
    return _EXIT_OK if not defects else _EXIT_ERROR


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent_evaluation",
        description=(
            "EVAL-R0: Mastermind-native agent-evaluation evidence core. "
            "Implements SHAPE_VALID and EVALUATION_GRAPH_VERIFIED only -- "
            "EVIDENCE_CONTENT_VERIFIED is never claimed. No runner pass/fail, "
            "winner, route, policy, approval, acceptance, or production "
            "action is ever produced."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_shape = subparsers.add_parser("validate-shape", help="shape-validate one document; prints SHAPE_VALID only")
    validate_shape.add_argument("document")
    validate_shape.set_defaults(func=_cmd_validate_shape)

    verify_graph = subparsers.add_parser(
        "verify-graph", help="graph-verify a stored artifact or a standalone document; prints EVALUATION_GRAPH_VERIFIED only"
    )
    verify_graph.add_argument("--root", required=True)
    verify_graph.add_argument("target", help="path relative to --root of a stored artifact, or a standalone document file")
    verify_graph.set_defaults(func=_cmd_verify_graph)

    create = subparsers.add_parser("create", help="publish one finalized document to the create-only artifact store")
    create.add_argument("--root", required=True)
    create.add_argument("document")
    create.set_defaults(func=_cmd_create)

    finalize_run = subparsers.add_parser("finalize-run", help="finalize a closed runner draft into an immutable run receipt")
    finalize_run.add_argument("--root", required=True)
    finalize_run.add_argument("--draft", required=True)
    finalize_run.add_argument("--validator-id", required=True)
    finalize_run.add_argument("--validator-version", required=True)
    finalize_run.add_argument("--validator-code-ref", required=True)
    finalize_run.add_argument("--validated-at", required=True)
    finalize_run.add_argument("--created-at", required=True)
    finalize_run.add_argument("--output", required=True)
    finalize_run.set_defaults(func=_cmd_finalize_run)

    score_integrity = subparsers.add_parser("score-integrity", help="append a technical-integrity scorer pass for one run")
    score_integrity.add_argument("--root", required=True)
    score_integrity.add_argument("--run-id", required=True)
    score_integrity.add_argument("--scorer-code-ref", required=True)
    score_integrity.add_argument("--created-at", required=True)
    score_integrity.add_argument("--id", required=True)
    score_integrity.set_defaults(func=_cmd_score_integrity)

    summarize = subparsers.add_parser("summarize", help="build one sanitized evidence reference for an experiment")
    summarize.add_argument("--root", required=True)
    summarize.add_argument("--experiment-id", required=True)
    summarize.add_argument("--owner", required=True)
    summarize.add_argument("--review-at", required=True)
    summarize.add_argument("--created-at", required=True)
    summarize.add_argument("--id", required=True)
    summarize.set_defaults(func=_cmd_summarize)

    resources = subparsers.add_parser("resources", help="read-only coverage over all graph-verified experiment receipts")
    resources.add_argument("--root", required=True)
    resources.add_argument("--experiment-id", required=True)
    resources.set_defaults(func=_cmd_resources)

    verify_tree_graph = subparsers.add_parser(
        "verify-tree-graph", help="graph-verify every artifact under --root; never repairs"
    )
    verify_tree_graph.add_argument("--root", required=True)
    verify_tree_graph.set_defaults(func=_cmd_verify_tree_graph)

    corpus_verify = subparsers.add_parser(
        "corpus-verify",
        help="EVAL-C0: scenario-vs-corpus consistency check over a committed public corpus tree; never repairs",
    )
    corpus_verify.add_argument("--corpus-root", required=True, help="path to the corpus/agent_eval directory")
    corpus_verify.add_argument(
        "--repo-root", required=False, help="repository root fixture artifact_refs resolve against (default: cwd)"
    )
    corpus_verify.set_defaults(func=_cmd_corpus_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already printed its own usage message to stderr
        return exc.code if isinstance(exc.code, int) else _EXIT_ERROR

    try:
        return args.func(args)
    except CliUsageError as exc:
        sys.stderr.write(f"usage error: {exc}\n")
        return _EXIT_ERROR
    except _EXPECTED_EXCEPTIONS as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        for defect in _defect_payload(exc):
            sys.stderr.write(f"  {defect['path']} {defect['code']}: {defect['message']}\n")
        return _EXIT_ERROR
    except FileNotFoundError as exc:
        sys.stderr.write(f"file not found: {exc}\n")
        return _EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
