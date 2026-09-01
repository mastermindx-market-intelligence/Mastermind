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
import json
import os
import sys
from pathlib import Path

from scripts.agent_eval import MAX_CANONICAL_ARTIFACT_BYTES, contracts, corpus, scoring, store, validity
from scripts.agent_eval.canonical import canonical_json_bytes
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
    primary_scenario_ref = scenario_refs[0]
    scenario = artifact_store.resolve_scenario(primary_scenario_ref["scenario_id"], primary_scenario_ref["scenario_version"])
    if scenario is None:
        raise CliUsageError("experiment's scenario could not be resolved from --root")

    # plan §5.6 complete-enumeration law: one deterministic, read-only,
    # sorted enumeration of the trusted root -- never a caller-selected
    # subset.
    runs = artifact_store.enumerate_runs()
    scorer_passes = artifact_store.enumerate_scorer_passes()

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
    # R0's evidence grade is always INSUFFICIENT_EVIDENCE (external content
    # is never verified) -- report that honestly rather than as a clean 0.
    return _EXIT_INCOMPLETE


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
