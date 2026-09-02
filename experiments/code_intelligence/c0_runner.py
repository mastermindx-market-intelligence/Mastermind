"""C0 runner: exercises admitted candidates and emits one immutable result.

The runner is host-side only. Its ``--workspace``, ``--lsp-binary`` and
``--serena-bundle`` inputs configure the experiment process and never appear in
any model-facing schema.

The decisive property: a decision enum is emitted only when every candidate has
at least one NON-SYNTHETIC trial. A stand-in server can prove adapter behaviour;
it can never select a production backend. When a pinned bundle is missing, the
runner fails closed to ``BLOCKED_MISSING_PINNED_DEPENDENCY`` rather than
manufacturing ``NO_SAFE_BACKEND`` from absent evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from experiments.code_intelligence.backend import ExecutableSpec, guard_payload
from experiments.code_intelligence.backend import BackendPayloadError
from experiments.code_intelligence.ground_truth import (
    corpus_manifest_digest,
    load_answer_key,
)
from experiments.code_intelligence.lsp_backend import DirectLspBackend
from experiments.code_intelligence.semantic_contract import (
    SEMANTIC_TOOL_NAMES,
    SemanticContractError,
    semantic_tool_schema_digest,
    validate_semantic_request,
)
from experiments.code_intelligence.semantic_facade import (
    FacadeError,
    SemanticFacade,
    facade_source_digest,
)
from experiments.code_intelligence.serena_backend import (
    SerenaBackendError,
    resolve_serena_bundle,
)
from experiments.code_intelligence.workspace_seal import (
    WorkspaceSealError,
    capture_workspace_seal,
    create_external_scratch,
    verify_workspace_seal,
    workspace_binding_digest,
)

ARTIFACT_VERSION = "mastermind.codeintel_c0_result.v1"
OPERATION_KEY = "mastermind-codeintel-c0-semantic-falsifier-20260830-sol-001"
WAVE_STATUS = "DISPOSABLE FALSIFIER / PRODUCTION_INERT"
SCHEMA_PATH = Path("research/code_intelligence_fabric/c0-result.schema.json")
CORPUS_PATH = Path("tests/fixtures/code_intelligence/python_sample")

#: Mutations actually applied to this source tree, each observed to turn the
#: named test RED and then reverted. Not a claim: a receipt.
PROVEN_MUTATION_KILLS = [
    {
        "mutation": "add a root-selecting field (project_path) to the find_symbol schema",
        "killed_by": "tests/code_intelligence/test_semantic_contract.py::TestClosedSchemas::test_no_schema_field_exposes_a_steering_token[find_symbol]",
    },
    {
        "mutation": "disable candidate-tree write detection in verify_workspace_seal",
        "killed_by": "tests/code_intelligence/test_workspace_seal.py::TestZeroWriteProof::test_backend_writing_the_worktree_is_refused",
    },
    {
        "mutation": "make the facade binding accept a foreign worktree seal",
        "killed_by": "tests/code_intelligence/test_semantic_facade.py::TestBindingReceipt::test_receipt_validation_against_a_foreign_seal_is_refused",
    },
    {
        "mutation": "bypass the executable SHA-256 check before launch",
        "killed_by": "tests/code_intelligence/test_jsonrpc_stdio.py::TestDigestPinning::test_wrong_digest_refuses_to_launch",
    },
]

_GIT_ENV = {
    "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "c0",
    "GIT_AUTHOR_EMAIL": "c0@example.invalid",
    "GIT_COMMITTER_NAME": "c0",
    "GIT_COMMITTER_EMAIL": "c0@example.invalid",
}


class RunnerError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_real_path(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise RunnerError("SYMLINK_REFUSED", f"{label}: {path}")
    if not path.exists():
        raise RunnerError("PATH_UNAVAILABLE", f"{label}: {path}")
    return path


def is_stand_in(spec: ExecutableSpec) -> bool:
    """A server shipped inside this experiment is a stand-in, never a candidate."""
    marker = str(Path("tests") / "code_intelligence" / "servers")
    return any(marker in str(item) for item in spec.argv_suffix)


# --------------------------------------------------------------------- fixtures


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, capture_output=True, env=_GIT_ENV, shell=False,
    )


def make_disposable_corpus(destination: Path, marker: str | None = None) -> Path:
    """A throwaway git worktree holding the corpus. Never the real repository."""
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(CORPUS_PATH / "src", destination / "src", dirs_exist_ok=True)
    shutil.copytree(CORPUS_PATH / "tests", destination / "tests", dirs_exist_ok=True)
    if marker:
        (destination / "src" / "sample" / "marker.py").write_text(
            f"def {marker}() -> str:\n    return \"{marker}\"\n", encoding="utf-8"
        )
    _git(destination, "init", "-q", "-b", "main")
    _git(destination, "add", "-A")
    _git(destination, "commit", "-q", "-m", "c0 corpus")
    return destination


# ----------------------------------------------------------------------- trials


def _matrix(answer_key: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = {row["symbol"]: row for row in answer_key["definitions"]}
    return [
        {
            "case": "O1_definition_live_implementation",
            "tool": "find_symbol",
            "arguments": {"name": "LiveProducer"},
            "expected": [
                [definitions["LiveProducer"]["relative_file"], definitions["LiveProducer"]["line"]]
            ],
        },
        {
            "case": "W1_references_across_files",
            "tool": "find_references",
            "arguments": {"name": "consume", "limit": 50},
            "expected": sorted(
                [row["relative_file"], row["line"]]
                for row in answer_key["references"]["consume"]
            ),
        },
        {
            "case": "A3_implementations_of_protocol",
            "tool": "find_implementations",
            "arguments": {"name": "Producer", "limit": 50},
            "expected": sorted(answer_key["implementations"]["Producer"]),
        },
        {
            "case": "overview_single_file",
            "tool": "symbol_overview",
            "arguments": {"relative_file": "src/sample/producer.py", "limit": 50},
            "expected": sorted(
                row["symbol"]
                for row in answer_key["definitions"]
                if row["relative_file"] == "src/sample/producer.py"
            ),
        },
        {
            "case": "diagnostics_planted_undefined_name",
            "tool": "diagnostics",
            "arguments": {"relative_file": "src/sample/consumer.py", "limit": 50},
            "expected": [
                [row["relative_file"], row["line"]] for row in answer_key["diagnostics"]
            ],
        },
    ]


def _actual_for(case: str, payload: Any) -> Any:
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    if case == "A3_implementations_of_protocol":
        return sorted({row.get("symbol", "") for row in rows if row.get("symbol")})
    if case == "overview_single_file":
        return sorted({row.get("symbol", "") for row in rows if row.get("symbol")})
    return sorted([row["relative_file"], row["line"]] for row in rows)


def run_trials(
    facade: SemanticFacade, answer_key: dict[str, Any], *, synthetic: bool
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for phase in ("cold", "warm"):
        for spec in _matrix(answer_key):
            started = time.monotonic()
            error: str | None = None
            actual: Any = None
            try:
                request = validate_semantic_request(spec["tool"], spec["arguments"])
                response = facade.call(request, timeout=30)
                actual = _actual_for(spec["case"], response.payload)
            except (FacadeError, SemanticContractError, BackendPayloadError) as exc:
                error = f"{getattr(exc, 'code', type(exc).__name__)}: {exc}"[:300]
            latency_ms = int((time.monotonic() - started) * 1000)
            trials.append(
                {
                    "case": spec["case"],
                    "language": "python",
                    "phase": phase,
                    "correct": bool(error is None and actual == spec["expected"]),
                    "expected": spec["expected"],
                    "actual": actual,
                    "latency_ms": latency_ms,
                    "synthetic": synthetic,
                    "error": error,
                }
            )
    return trials


# ------------------------------------------------------------- hostile probes


def _redact(text: str) -> str:
    """Strip absolute host paths out of anything the artifact publishes.

    The experiment refuses absolute paths in backend payloads; the result
    artifact must hold itself to the same standard, and this is also what makes
    two runs of the same sealed workspace byte-identical.
    """
    return " ".join(
        "<path>" if token.startswith("/") else token for token in text.split(" ")
    )


def run_hostile_checks(scratch: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def record(check: str, outcome: str, code: str | None = None, detail: str = "") -> None:
        results.append(
            {"check": check, "outcome": outcome, "code": code, "detail": _redact(detail)[:300]}
        )

    hostile_arguments = [
        ("contract_refuses_root_selection", "find_symbol", {"name": "x", "project_root": "/etc"}),
        ("contract_refuses_absolute_location", "diagnostics", {"relative_file": "/etc/passwd"}),
        ("contract_refuses_path_traversal", "diagnostics", {"relative_file": "../outside.py"}),
        ("contract_refuses_unknown_tool", "execute_shell_command", {}),
        ("contract_refuses_oversized_limit", "find_references", {"name": "x", "limit": 10_000}),
    ]
    for check, tool, arguments in hostile_arguments:
        try:
            validate_semantic_request(tool, arguments)
        except SemanticContractError as exc:
            record(check, "REFUSED_AS_REQUIRED", "SemanticContractError", str(exc))
        else:
            record(check, "ALLOWED", None, "contract accepted a hostile argument")

    for check, payload in [
        ("payload_guard_refuses_absolute_path", {"rows": [{"relative_file": "/etc/passwd", "line": 1}]}),
        ("payload_guard_refuses_host_key", {"executable": "/usr/bin/python3"}),
        ("payload_guard_refuses_secret", {"rows": [{"relative_file": "a.py", "line": 1, "note": "ghp_" + "x" * 36}]}),
        ("payload_guard_refuses_unbounded_rows", {"rows": [{"relative_file": "a.py", "line": i} for i in range(101)]}),
    ]:
        try:
            guard_payload(payload)
        except BackendPayloadError as exc:
            record(check, "REFUSED_AS_REQUIRED", exc.code, str(exc))
        else:
            record(check, "ALLOWED", None, "payload guard accepted a leak")

    # Seal-level probes run against disposable corpora, never the real workspace.
    probe_root = make_disposable_corpus(scratch / "hostile-probe")
    seal = capture_workspace_seal(probe_root)
    (probe_root / ".semantic-cache").write_text("planted\n", encoding="utf-8")
    try:
        verify_workspace_seal(seal)
    except WorkspaceSealError as exc:
        record("seal_detects_candidate_tree_write", "REFUSED_AS_REQUIRED", exc.code, exc.detail)
    else:
        record("seal_detects_candidate_tree_write", "ALLOWED", None, "write went unnoticed")

    symlink_root = scratch / "hostile-symlink"
    symlink_root.symlink_to(probe_root, target_is_directory=True)
    try:
        capture_workspace_seal(symlink_root)
    except WorkspaceSealError as exc:
        record("seal_refuses_symlink_root", "REFUSED_AS_REQUIRED", exc.code, exc.detail)
    else:
        record("seal_refuses_symlink_root", "ALLOWED", None, "symlink root accepted")

    alpha = make_disposable_corpus(scratch / "alpha", marker="WORKTREE_ALPHA_ONLY")
    beta = make_disposable_corpus(scratch / "beta", marker="WORKTREE_BETA_ONLY")
    alpha_seal = capture_workspace_seal(alpha)
    beta_seal = capture_workspace_seal(beta)
    if (
        alpha_seal.candidate_tree_sha256 != beta_seal.candidate_tree_sha256
        and alpha_seal.inode != beta_seal.inode
    ):
        record(
            "two_worktrees_carry_distinct_seals",
            "REFUSED_AS_REQUIRED",
            None,
            "alpha and beta seals are distinct, so a cross-read cannot be mistaken for a hit",
        )
    else:
        record("two_worktrees_carry_distinct_seals", "ALLOWED", None, "seals collided")

    try:
        create_external_scratch(parent=probe_root / "inside", seal=seal)
    except WorkspaceSealError as exc:
        record("scratch_refuses_candidate_tree", "REFUSED_AS_REQUIRED", exc.code, exc.detail)
    else:
        record("scratch_refuses_candidate_tree", "ALLOWED", None, "scratch created inside the tree")

    return results


# ------------------------------------------------------------------- assembly


def _identity_dict(backend: Any) -> dict[str, Any] | None:
    try:
        identity = backend.identity
    except Exception:  # pragma: no cover - defensive
        return None
    return {
        "kind": identity.kind,
        "source_version": identity.source_version,
        "source_commit": identity.source_commit,
        "executable_sha256": identity.executable_sha256,
        "configuration_digest": identity.configuration_digest,
    }


def build_result(
    *,
    workspace: Path,
    scratch_parent: Path,
    lsp_binary: Path | None,
    lsp_sha256: str | None,
    lsp_argv: tuple[str, ...],
    serena_bundle: Path | None,
    source: dict[str, Any],
    mutation_kills: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    workspace = _require_real_path(Path(workspace), "workspace")
    seal = capture_workspace_seal(workspace)
    scratch = create_external_scratch(parent=Path(scratch_parent), seal=seal)
    answer_key = load_answer_key(CORPUS_PATH)

    candidates: list[dict[str, Any]] = []
    # The workspace and facade halves of the receipt are properties of the
    # sealed tree and of this experiment's own source; neither needs a backend.
    binding_receipt: dict[str, Any] = {
        "workspace_binding_digest": workspace_binding_digest(seal),
        "facade_source_digest": facade_source_digest(),
        "semantic_schema_digest": semantic_tool_schema_digest(),
    }

    # ---- Candidate L: direct LSP
    lsp_entry: dict[str, Any] = {
        "kind": "direct_lsp",
        "status": "UNEXERCISED_MISSING_BUNDLE",
        "identity": None,
        "trials": [],
        "hard_failures": [],
        "notes": "",
    }
    if lsp_binary is None:
        lsp_entry["hard_failures"].append("LSP_BINARY_UNAVAILABLE")
        lsp_entry["notes"] = (
            "No host-supplied pinned Python language server was provided. The protected "
            "plan forbids downloading one and requires an immutable installed bundle."
        )
    else:
        binary = _require_real_path(Path(lsp_binary), "lsp-binary")
        actual_digest = _file_digest(binary)
        if lsp_sha256 and actual_digest != lsp_sha256:
            lsp_entry["hard_failures"].append("EXECUTABLE_DIGEST_MISMATCH")
            lsp_entry["notes"] = f"expected {lsp_sha256}, found {actual_digest}"
        else:
            spec = ExecutableSpec(
                path=binary, sha256=actual_digest, argv_suffix=tuple(lsp_argv)
            )
            synthetic = is_stand_in(spec)
            backend = DirectLspBackend(spec=spec, language="python")
            facade = SemanticFacade(seal=seal, backend=backend, scratch=scratch)
            try:
                facade.start()
                binding_receipt = dict(facade.binding_receipt())
                lsp_entry["identity"] = _identity_dict(backend)
                lsp_entry["trials"] = run_trials(facade, answer_key, synthetic=synthetic)
                lsp_entry["status"] = "EXERCISED"
                if synthetic:
                    lsp_entry["notes"] = (
                        "Exercised against the experiment's own stand-in server. Adapter "
                        "behaviour only; this can never select a production backend."
                    )
            except (FacadeError, WorkspaceSealError) as exc:
                lsp_entry["hard_failures"].append(getattr(exc, "code", "BACKEND_FAILED"))
                lsp_entry["notes"] = str(exc)[:300]
            finally:
                facade.close()
    candidates.append(lsp_entry)

    # ---- Candidate S: pinned Serena
    serena_entry: dict[str, Any] = {
        "kind": "serena",
        "status": "UNEXERCISED_MISSING_BUNDLE",
        "identity": None,
        "trials": [],
        "hard_failures": [],
        "notes": "",
    }
    if serena_bundle is None:
        serena_entry["hard_failures"].append("SERENA_BUNDLE_UNAVAILABLE")
        serena_entry["notes"] = (
            "No host-supplied immutable Serena bundle at the pinned commit was provided; "
            "the protected plan forbids acquiring one inside this wave."
        )
    else:
        try:
            bundle = resolve_serena_bundle(Path(serena_bundle))
            serena_entry["notes"] = f"bundle resolved at {bundle.source_commit}"
            serena_entry["hard_failures"].append("SERENA_RUNTIME_NOT_EXERCISED")
        except SerenaBackendError as exc:
            serena_entry["hard_failures"].append(exc.code)
            serena_entry["notes"] = exc.detail[:300]
    candidates.append(serena_entry)

    hostile_results = run_hostile_checks(scratch)

    exercised_real = [
        entry
        for entry in candidates
        if entry["status"] == "EXERCISED"
        and any(not trial["synthetic"] for trial in entry["trials"])
    ]

    result: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "operation_key": OPERATION_KEY,
        "generated_unix_ms": int(time.time() * 1000),
        "wave_status": WAVE_STATUS,
        "source": source,
        "environment": {
            "platform": f"{platform.system()} {platform.machine()}",
            "python_version": sys.version.split()[0],
            "network_policy": "disabled",
            "observations": [
                "macOS injects __CF_USER_TEXT_ENCODING into every spawned child; it "
                "carries the invoking uid and cannot be suppressed by this experiment.",
            ],
        },
        "corpora": [
            {
                "corpus_id": answer_key["corpus_id"],
                "language": answer_key["language"],
                "manifest_digest": corpus_manifest_digest(CORPUS_PATH),
                "answer_key_digest": hashlib.sha256(
                    (CORPUS_PATH / "answer_key.json").read_bytes()
                ).hexdigest(),
            }
        ],
        "binding_receipt": binding_receipt,
        "exposed_tool_census": list(SEMANTIC_TOOL_NAMES),
        "candidates": candidates,
        "hostile_results": hostile_results,
        "mutation_kills": mutation_kills or [],
        "residual_risks": [],
        "next_action": "",
    }

    if len(exercised_real) == len(candidates):
        result["decision_state"] = "DECIDED"
        result["decision"] = "NO_SAFE_BACKEND"
        result["next_action"] = "Return the decision to Sol for architecture revision."
    else:
        missing = [
            entry["kind"]
            for entry in candidates
            if entry not in exercised_real
        ]
        result["decision_state"] = "BLOCKED_MISSING_PINNED_DEPENDENCY"
        result["blocking_reason"] = (
            "No decision may be published: candidate(s) "
            f"{sorted(missing)} have no non-synthetic trial. The protected plan sets "
            "network_policy=disabled and requires host-supplied immutable bundles, and "
            "no such bundle exists on this host. Emitting NO_SAFE_BACKEND here would "
            "assert an empirical result that was never obtained."
        )
        result["next_action"] = (
            "Sol to provision, or authorise acquisition of, the pinned Serena bundle "
            "(949a27ef1e5fda1a6e7b561e777bcece345c6ffd / v1.7.0) and pinned Python and "
            "TypeScript language-server bundles as immutable host-side inputs; the "
            "harness then runs unchanged via c0_runner."
        )
    result["residual_risks"] = [
        "Adapter proofs used stand-in servers; real backend semantics remain unmeasured.",
        "The TypeScript/TSX corpus and the protected Terminal migrateLegacy case were "
        "not exercised: no TypeScript language server bundle exists on this host.",
        "macOS injects __CF_USER_TEXT_ENCODING (uid-bearing) into child processes.",
        "Ground truth is a conservative AST census, not a full type-checker.",
    ]
    return result


def validate_result(result: dict[str, Any]) -> None:
    """Validate against the shipped JSON Schema; fail closed if unavailable."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RunnerError("SCHEMA_VALIDATOR_UNAVAILABLE", str(exc)) from exc
    jsonschema.Draft202012Validator(schema).validate(result)


def result_digest(result: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _git_here(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, shell=False
    ).stdout.strip()


def _git_source() -> dict[str, Any]:
    changed = _git_here(
        "diff", "--name-only", f"{_git_here('merge-base', 'origin/master', 'HEAD')}", "HEAD"
    )
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "branch": _git_here("rev-parse", "--abbrev-ref", "HEAD"),
        "head_sha": _git_here("rev-parse", "HEAD"),
        "base_sha": _git_here("merge-base", "origin/master", "HEAD"),
        "protected_pickup_sha": "ae483cc5f101d369f368f217bb767c91fc9e0150",
        "changed_paths": sorted(line for line in changed.splitlines() if line),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C0 semantic falsifier.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--scratch-parent", required=True)
    parser.add_argument("--lsp-binary", default=None)
    parser.add_argument("--lsp-sha256", default=None)
    parser.add_argument("--lsp-argv", nargs="*", default=[])
    parser.add_argument("--serena-bundle", default=None)
    parser.add_argument("--serena-sha256", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    result = build_result(
        workspace=Path(args.workspace),
        scratch_parent=Path(args.scratch_parent),
        lsp_binary=Path(args.lsp_binary) if args.lsp_binary else None,
        lsp_sha256=args.lsp_sha256,
        lsp_argv=tuple(args.lsp_argv),
        serena_bundle=Path(args.serena_bundle) if args.serena_bundle else None,
        source=_git_source(),
        mutation_kills=PROVEN_MUTATION_KILLS,
    )
    validate_result(result)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    print(f"decision_state={result['decision_state']} digest={result_digest(result)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
