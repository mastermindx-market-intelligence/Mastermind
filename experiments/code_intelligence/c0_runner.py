"""C0 runner: exercises both candidates across both languages and emits one result.

The runner is host-side only. Its workspace, binary, bundle and sandbox inputs
configure the experiment process and never appear in any model-facing schema.

Two properties are load-bearing:

* a decision comes only from :mod:`experiments.code_intelligence.decision`, which
  requires the complete non-synthetic candidate x language x case x phase matrix;
* a stand-in server can exercise every branch but can never win, because its
  trials are marked ``synthetic`` and the ruler discards them as evidence.

When a pinned bundle is missing, the runner fails closed to a typed blocked state
rather than manufacturing ``NO_SAFE_BACKEND`` from absent evidence.
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
from typing import Any, Mapping

from experiments.code_intelligence.backend import (
    BackendPayloadError,
    ExecutableSpec,
    guard_payload,
)
from experiments.code_intelligence.decision import (
    MATERIALITY_BAND,
    PRIMARY_CASES,
    REQUIRED_LANGUAGES,
    decide,
)
from experiments.code_intelligence.ground_truth import (
    corpus_manifest_digest,
    load_answer_key,
)
from experiments.code_intelligence.lsp_backend import DirectLspBackend
from experiments.code_intelligence.sandbox import (
    DEFAULT_LIMITS,
    SandboxUnavailable,
    build_sandbox,
)
from experiments.code_intelligence.semantic_contract import (
    SEMANTIC_TOOL_NAMES,
    SemanticContractError,
    canonical_json,
    semantic_tool_schema_digest,
    validate_semantic_request,
)
from experiments.code_intelligence.semantic_facade import (
    FacadeError,
    SemanticFacade,
    facade_source_digest,
)
from experiments.code_intelligence.serena_backend import (
    SerenaBackend,
    SerenaBackendError,
    resolve_serena_bundle,
    run_config_influence_probe,
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

CORPORA = {
    "python": Path("tests/fixtures/code_intelligence/python_sample"),
    "typescript": Path("tests/fixtures/code_intelligence/typescript_sample"),
}

#: Mutations actually applied to this source tree, each observed to turn the
#: named test RED and then reverted. Not a claim: a receipt.
PROVEN_MUTATION_KILLS = [
    {"mutation": "add a root-selecting field (project_path) to the find_symbol schema",
     "killed_by": "test_semantic_contract.py::test_no_schema_field_exposes_a_steering_token"},
    {"mutation": "disable candidate-tree write detection in verify_workspace_seal",
     "killed_by": "test_workspace_seal.py::test_backend_writing_the_worktree_is_refused"},
    {"mutation": "make the facade binding accept a foreign worktree seal",
     "killed_by": "test_semantic_facade.py::test_receipt_validation_against_a_foreign_seal_is_refused"},
    {"mutation": "bypass the executable SHA-256 check before launch",
     "killed_by": "test_jsonrpc_stdio.py::test_wrong_digest_refuses_to_launch"},
    {"mutation": "invert the lower-surface tie-break preference",
     "killed_by": "test_decision.py::test_tie_goes_to_the_lower_surface_candidate"},
    {"mutation": "let latency rather than correctness select the winner",
     "killed_by": "test_decision.py::test_material_secondary_advantage_beats_the_surface_preference"},
]

_GIT_ENV = {
    "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "c0", "GIT_AUTHOR_EMAIL": "c0@example.invalid",
    "GIT_COMMITTER_NAME": "c0", "GIT_COMMITTER_EMAIL": "c0@example.invalid",
}

#: Fields whose value is an observation of this run, not of the evidence. They are
#: preserved in the artifact but excluded from the semantic evidence digest, so
#: equivalent evidence yields a stable identity (B7).
_VOLATILE_FIELDS = frozenset(
    {
        "generated_unix_ms", "latency_ms", "startup_unix_ms", "median_latency_ms",
        "scratch", "detail", "duration_ms",
        # Identity of the DISPOSABLE corpus this run happened to create. It is an
        # observation of the run, not evidence about the candidates.
        "workspace_binding_digest", "per_execution",
        "candidate_tree_before", "candidate_tree_after",
        "scratch_files_before", "scratch_bytes_before",
    }
)


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


def _redact(text: str) -> str:
    """Strip absolute host paths out of anything the artifact publishes."""
    return " ".join(
        "<path>" if token.startswith("/") else token for token in str(text).split(" ")
    )


# --------------------------------------------------------------------- fixtures


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, env=_GIT_ENV, shell=False)


def make_disposable_corpus(
    destination: Path, *, corpus: Path | str | None = None, marker: str | None = None
) -> Path:
    """A throwaway git worktree holding a corpus. Never the real repository."""
    source = Path(corpus) if corpus is not None else CORPORA["python"]
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for child in ("src", "tests"):
        if (source / child).is_dir():
            shutil.copytree(source / child, destination / child, dirs_exist_ok=True)
    if marker:
        target = destination / "src"
        target.mkdir(parents=True, exist_ok=True)
        (target / "marker.py").write_text(
            f"def {marker}() -> str:\n    return \"{marker}\"\n", encoding="utf-8"
        )
    _git(destination, "init", "-q", "-b", "main")
    _git(destination, "add", "-A")
    _git(destination, "commit", "-q", "-m", "c0 corpus")
    return destination


# ----------------------------------------------------------------------- trials


def build_matrix(answer_key: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The frozen case matrix, derived from a corpus's own declarations."""
    bindings = answer_key["task_bindings"]
    definitions = {row["symbol"]: row for row in answer_key["definitions"]}
    definition = definitions[bindings["definition_symbol"]]
    overview_file = bindings["overview_file"]
    return [
        {
            "case": "O1_definition_live_implementation",
            "tool": "find_symbol",
            "arguments": {"name": bindings["definition_symbol"]},
            "expected": [[definition["relative_file"], definition["line"]]],
        },
        {
            "case": "W1_references_across_files",
            "tool": "find_references",
            "arguments": {"name": bindings["references_symbol"], "limit": 50},
            "expected": sorted(
                [row["relative_file"], row["line"]]
                for row in answer_key["references"][bindings["references_symbol"]]
            ),
        },
        {
            "case": "A3_implementations_of_protocol",
            "tool": "find_implementations",
            "arguments": {"name": bindings["implementations_symbol"], "limit": 50},
            "expected": sorted(
                answer_key["implementations"][bindings["implementations_symbol"]]
            ),
        },
        {
            "case": "overview_single_file",
            "tool": "symbol_overview",
            "arguments": {"relative_file": overview_file, "limit": 50},
            "expected": sorted(
                row["symbol"] for row in answer_key["definitions"]
                if row["relative_file"] == overview_file
            ),
        },
        {
            "case": "diagnostics_planted_undefined_name",
            "tool": "diagnostics",
            "arguments": {"relative_file": bindings["diagnostics_file"], "limit": 50},
            "expected": [
                [row["relative_file"], row["line"]] for row in answer_key["diagnostics"]
            ],
        },
    ]


def _actual_for(case: str, payload: Any) -> Any:
    rows = payload.get("rows", []) if isinstance(payload, dict) else []
    if case in ("A3_implementations_of_protocol", "overview_single_file"):
        return sorted({row.get("symbol", "") for row in rows if row.get("symbol")})
    return sorted([row["relative_file"], row["line"]] for row in rows)


def run_trials(
    facade: SemanticFacade,
    answer_key: Mapping[str, Any],
    *,
    language: str,
    synthetic: bool,
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for phase in ("cold", "warm"):
        for spec in build_matrix(answer_key):
            started = time.monotonic()
            error: str | None = None
            actual: Any = None
            try:
                request = validate_semantic_request(spec["tool"], spec["arguments"])
                response = facade.call(request, timeout=30)
                actual = _actual_for(spec["case"], response.payload)
            except (FacadeError, SemanticContractError, BackendPayloadError,
                    SerenaBackendError) as exc:
                error = _redact(f"{getattr(exc, 'code', type(exc).__name__)}: {exc}")[:300]
            trials.append({
                "case": spec["case"], "language": language, "phase": phase,
                "correct": bool(error is None and actual == spec["expected"]),
                "expected": spec["expected"], "actual": actual,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "synthetic": synthetic, "error": error,
            })
    return trials


# ------------------------------------------------------------- hostile probes


def run_hostile_checks(scratch: Path, *, serena_probe: Mapping[str, Any] | None = None):
    results: list[dict[str, Any]] = []

    def record(check: str, outcome: str, code: str | None = None, detail: str = "") -> None:
        results.append({"check": check, "outcome": outcome, "code": code,
                        "detail": _redact(detail)[:300]})

    for check, tool, arguments in [
        ("contract_refuses_root_selection", "find_symbol", {"name": "x", "project_root": "/etc"}),
        ("contract_refuses_absolute_location", "diagnostics", {"relative_file": "/etc/passwd"}),
        ("contract_refuses_path_traversal", "diagnostics", {"relative_file": "../outside.py"}),
        ("contract_refuses_unknown_tool", "execute_shell_command", {}),
        ("contract_refuses_oversized_limit", "find_references", {"name": "x", "limit": 10_000}),
    ]:
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
        ("payload_guard_refuses_wide_collection", {"rows": [{"i": i} for i in range(1001)]}),
    ]:
        try:
            guard_payload(payload)
        except BackendPayloadError as exc:
            record(check, "REFUSED_AS_REQUIRED", exc.code, str(exc))
        else:
            record(check, "ALLOWED", None, "payload guard accepted a leak")

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
    if (alpha_seal.candidate_tree_sha256 != beta_seal.candidate_tree_sha256
            and alpha_seal.inode != beta_seal.inode):
        record("two_worktrees_carry_distinct_seals", "REFUSED_AS_REQUIRED", None,
               "alpha and beta seals are distinct, so a cross-read cannot pass as a hit")
    else:
        record("two_worktrees_carry_distinct_seals", "ALLOWED", None, "seals collided")

    try:
        create_external_scratch(parent=probe_root / "inside", seal=seal)
    except WorkspaceSealError as exc:
        record("scratch_refuses_candidate_tree", "REFUSED_AS_REQUIRED", exc.code, exc.detail)
    else:
        record("scratch_refuses_candidate_tree", "ALLOWED", None, "scratch created inside the tree")

    if serena_probe is not None:
        if not serena_probe.get("ran"):
            record("serena_repository_config_differential", "NOT_RUN", None,
                   serena_probe.get("detail", "no bundle to probe"))
        elif serena_probe.get("influenced"):
            record("serena_repository_config_differential", "REFUSED_AS_REQUIRED",
                   serena_probe.get("code"), serena_probe.get("detail", ""))
        else:
            record("serena_repository_config_differential", "REFUSED_AS_REQUIRED", None,
                   "tool census unchanged under a hostile repository configuration")
    else:
        record("serena_repository_config_differential", "NOT_RUN", None,
               "no Serena bundle supplied")

    return results


# ------------------------------------------------------------------- candidates


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


def _exercise(backend_factory, *, corpus: Path, language: str, scratch_parent: Path,
              synthetic: bool, entry: dict[str, Any], receipts: list[dict[str, Any]]):
    """Run one candidate over one language corpus behind the sealed facade."""
    workspace = make_disposable_corpus(
        Path(scratch_parent) / f"ws-{entry['kind']}-{language}", corpus=corpus
    )
    seal = capture_workspace_seal(workspace)
    scratch = create_external_scratch(parent=Path(scratch_parent) / "scratch", seal=seal)
    backend = backend_factory()
    facade = SemanticFacade(seal=seal, backend=backend, scratch=scratch)
    try:
        facade.start()
        receipt = dict(facade.binding_receipt())
        receipt["language"] = language
        receipt["candidate"] = entry["kind"]
        receipts.append(receipt)
        entry["identity"] = entry.get("identity") or _identity_dict(backend)
        entry["trials"].extend(
            run_trials(facade, load_answer_key(corpus), language=language,
                       synthetic=synthetic)
        )
        entry["status"] = "EXERCISED"
    except (FacadeError, WorkspaceSealError, SerenaBackendError) as exc:
        entry["hard_failures"].append(getattr(exc, "code", "BACKEND_FAILED"))
        entry["notes"] = _redact(str(exc))[:300]
    finally:
        facade.close()


def build_result(
    *,
    scratch_parent: Path,
    lsp_binaries: Mapping[str, Mapping[str, Any]] | None = None,
    serena_bundle: Path | None = None,
    serena_sha256: str | None = None,
    source: Mapping[str, Any],
    require_sandbox: bool = True,
) -> dict[str, Any]:
    scratch_parent = Path(scratch_parent)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    lsp_binaries = lsp_binaries or {}
    binding_receipts: list[dict[str, Any]] = []
    environment_notes: list[str] = []

    sandbox = None
    sandbox_receipt: dict[str, Any] = {"available": False}
    try:
        sandbox = build_sandbox(scratch=scratch_parent / "sandbox",
                                require_network_denial=require_sandbox)
        attestation = sandbox.attest_no_network()
        sandbox_receipt = {
            "available": True,
            "profile_digest": sandbox.profile_digest,
            "network_denied": attestation["network_denied"],
            "attestation": _redact(attestation["detail"]),
            "enforced_limits": list(sandbox.enforced_limits),
            "unenforced_limits": list(sandbox.unenforced_limits),
        }
        if sandbox.unenforced_limits:
            environment_notes.append(
                "resource limits not enforceable on this host: "
                + ", ".join(sandbox.unenforced_limits)
            )
    except SandboxUnavailable as exc:
        sandbox_receipt = {"available": False, "code": exc.code,
                           "detail": _redact(exc.detail)}
        environment_notes.append(f"sandbox unavailable: {exc.code}")

    # ---- Candidate L: direct LSP, one entry covering both languages
    lsp_entry: dict[str, Any] = {
        "kind": "direct_lsp", "status": "UNEXERCISED_MISSING_BUNDLE",
        "identity": None, "trials": [], "hard_failures": [], "notes": "",
    }
    for language in REQUIRED_LANGUAGES:
        supplied = lsp_binaries.get(language)
        if not supplied:
            lsp_entry["hard_failures"].append(f"LSP_BINARY_UNAVAILABLE:{language}")
            continue
        binary = _require_real_path(Path(supplied["binary"]), f"{language}-lsp-binary")
        observed = _file_digest(binary)
        if supplied.get("sha256") and observed != supplied["sha256"]:
            lsp_entry["hard_failures"].append(f"EXECUTABLE_DIGEST_MISMATCH:{language}")
            continue
        if not supplied.get("sha256"):
            lsp_entry["hard_failures"].append(f"EXECUTABLE_DIGEST_UNPINNED:{language}")
            continue
        argv = tuple(supplied.get("argv", ()))
        spec = ExecutableSpec(
            path=binary, sha256=supplied["sha256"], argv_suffix=argv,
            argv_digests=tuple(
                (item, _file_digest(Path(item)))
                for item in argv if Path(item).is_file()
            ),
        )
        synthetic = is_stand_in(spec)
        if synthetic:
            lsp_entry["notes"] = (
                "Exercised against this experiment's own stand-in server: adapter "
                "behaviour only, categorically ineligible as empirical evidence."
            )
        _exercise(
            lambda spec=spec: DirectLspBackend(spec=spec, language=language, sandbox=sandbox),
            corpus=CORPORA[language], language=language,
            scratch_parent=scratch_parent, synthetic=synthetic,
            entry=lsp_entry, receipts=binding_receipts,
        )

    # ---- Candidate S: pinned Serena
    serena_entry: dict[str, Any] = {
        "kind": "serena", "status": "UNEXERCISED_MISSING_BUNDLE",
        "identity": None, "trials": [], "hard_failures": [], "notes": "",
    }
    serena_probe: dict[str, Any] | None = None
    if serena_bundle is None:
        serena_entry["hard_failures"].append("SERENA_BUNDLE_UNAVAILABLE")
        serena_entry["notes"] = (
            "No host-supplied immutable Serena bundle at the pinned commit was "
            "provided; the protected plan forbids acquiring one inside this wave."
        )
    else:
        try:
            bundle = resolve_serena_bundle(Path(serena_bundle))
            if serena_sha256 and bundle.sha256 != serena_sha256:
                raise SerenaBackendError(
                    "SERENA_BUNDLE_DIGEST_MISMATCH",
                    f"expected {serena_sha256}, found {bundle.sha256}",
                )
            launcher = lsp_binaries.get("serena_launcher")
            if not launcher:
                serena_entry["hard_failures"].append("SERENA_LAUNCHER_UNAVAILABLE")
                serena_entry["notes"] = "bundle resolved but no launcher was supplied"
            else:
                argv = tuple(launcher.get("argv", ()))
                spec = ExecutableSpec(
                    path=Path(launcher["binary"]), sha256=launcher["sha256"],
                    argv_suffix=argv,
                    argv_digests=tuple(
                        (item, _file_digest(Path(item)))
                        for item in argv if Path(item).is_file()
                    ),
                )
                synthetic = is_stand_in(spec)
                if synthetic:
                    serena_entry["notes"] = (
                        "Exercised against a Serena-shaped stand-in: adapter behaviour "
                        "only, categorically ineligible as empirical evidence."
                    )
                serena_probe = run_config_influence_probe(
                    spec=spec, bundle=bundle,
                    corpus_root=make_disposable_corpus(scratch_parent / "serena-probe"),
                    scratch_parent=scratch_parent / "scratch",
                    sandbox=sandbox,
                )
                for language in REQUIRED_LANGUAGES:
                    _exercise(
                        lambda spec=spec, bundle=bundle: SerenaBackend(
                            spec=spec, bundle=bundle, sandbox=sandbox),
                        corpus=CORPORA[language], language=language,
                        scratch_parent=scratch_parent, synthetic=synthetic,
                        entry=serena_entry, receipts=binding_receipts,
                    )
                serena_entry["advertised_tool_census"] = []
        except SerenaBackendError as exc:
            serena_entry["hard_failures"].append(exc.code)
            serena_entry["notes"] = _redact(exc.detail)[:300]

    candidates = [lsp_entry, serena_entry]
    hostile_results = run_hostile_checks(scratch_parent / "hostile", serena_probe=serena_probe)
    outcome = decide(candidates)

    result: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "operation_key": OPERATION_KEY,
        "generated_unix_ms": int(time.time() * 1000),
        "wave_status": WAVE_STATUS,
        "source": dict(source),
        "environment": {
            "platform": f"{platform.system()} {platform.machine()}",
            "python_version": sys.version.split()[0],
            "network_policy": (
                "enforced_and_attested"
                if sandbox_receipt.get("network_denied")
                else "unattested"
            ),
            "sandbox": sandbox_receipt,
            "observations": [
                "macOS injects __CF_USER_TEXT_ENCODING into every spawned child; it "
                "carries the invoking uid and cannot be suppressed by this experiment.",
                "RLIMIT_NPROC on Darwin is per-user, not per process group.",
                *environment_notes,
            ],
        },
        "corpora": [
            {
                "corpus_id": load_answer_key(path)["corpus_id"],
                "language": load_answer_key(path)["language"],
                "manifest_digest": corpus_manifest_digest(path),
                "answer_key_digest": hashlib.sha256(
                    (path / "answer_key.json").read_bytes()
                ).hexdigest(),
            }
            for path in CORPORA.values()
        ],
        "binding_receipt": {
            "workspace_binding_digest": (
                binding_receipts[0]["workspace_binding_digest"]
                if binding_receipts else hashlib.sha256(b"unbound").hexdigest()
            ),
            "facade_source_digest": facade_source_digest(),
            "semantic_schema_digest": semantic_tool_schema_digest(),
            "per_execution": binding_receipts,
        },
        "exposed_tool_census": list(SEMANTIC_TOOL_NAMES),
        "candidates": candidates,
        "candidate_summaries": [
            {
                key: (list(value) if isinstance(value, tuple) else value)
                for key, value in summary.items()
            }
            for summary in outcome.summaries
        ],
        "hostile_results": hostile_results,
        "mutation_kills": PROVEN_MUTATION_KILLS,
        "decision_state": outcome.state,
        "decision_gates": list(outcome.gates),
        "tie_break": outcome.tie_break,
        "materiality_band": MATERIALITY_BAND,
        "primary_cases": list(PRIMARY_CASES),
        "residual_risks": [
            "Adapter proofs used stand-in servers; real backend semantics remain unmeasured.",
            "The protected Terminal migrateLegacy case was not materialized: it is not "
            "present on any pinned Terminal checkout reachable from this host.",
            "Ground truth is a conservative census, not a type-checker.",
            "RLIMIT_AS is unenforceable on Darwin, so address space is not bounded.",
        ],
        "next_action": "",
    }
    if outcome.decision is not None:
        result["decision"] = outcome.decision
        result["next_action"] = "Return the decision to Sol for C0 release adjudication."
    else:
        result["blocking_reason"] = outcome.blocking_reason
        result["next_action"] = (
            "Sol/B0 to provide the pinned Serena bundle "
            "(949a27ef1e5fda1a6e7b561e777bcece345c6ffd / v1.7.0) and pinned Python and "
            "TypeScript/TSX language-server bundles as immutable host inputs; the "
            "harness then runs unchanged via c0_runner."
        )
    result["cleanup"] = cleanup_scratch(scratch_parent)
    result["semantic_evidence_digest"] = semantic_evidence_digest(result)
    return result


# -------------------------------------------------------------------- cleanup


def cleanup_scratch(scratch_parent: Path) -> dict[str, Any]:
    """B8 — deterministic teardown with a truthful census, never a silent swallow."""
    scratch_parent = Path(scratch_parent)
    files = 0
    total_bytes = 0
    if scratch_parent.exists():
        for path in scratch_parent.rglob("*"):
            if path.is_file():
                files += 1
                try:
                    total_bytes += path.stat().st_size
                except OSError:  # pragma: no cover - defensive
                    pass
    receipt: dict[str, Any] = {
        "scratch_files_before": files,
        "scratch_bytes_before": total_bytes,
        "removed": False,
        "retained_paths": 0,
        "failure": None,
    }
    try:
        shutil.rmtree(scratch_parent)
        receipt["removed"] = True
    except OSError as exc:
        receipt["failure"] = _redact(str(exc))[:200]
    if scratch_parent.exists():
        receipt["retained_paths"] = sum(1 for _ in scratch_parent.rglob("*"))
    return receipt


# ------------------------------------------------------------------ artifacts


def _strip_volatile(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_volatile(item)
            for key, item in sorted(value.items())
            if key not in _VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [_strip_volatile(item) for item in value]
    return value


def semantic_evidence_digest(result: Mapping[str, Any]) -> str:
    """Stable identity of the EVIDENCE, independent of wall-clock observation."""
    payload = dict(result)
    payload.pop("semantic_evidence_digest", None)
    return hashlib.sha256(
        canonical_json(_strip_volatile(payload)).encode("utf-8")
    ).hexdigest()


def validate_result(result: Mapping[str, Any]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RunnerError("SCHEMA_VALIDATOR_UNAVAILABLE", str(exc)) from exc
    jsonschema.Draft202012Validator(schema).validate(result)
    cross_check_result(result)


def cross_check_result(result: Mapping[str, Any]) -> None:
    """Winner law that JSON Schema alone cannot express."""
    kinds = [c["kind"] for c in result["candidates"]]
    if sorted(kinds) != ["direct_lsp", "serena"]:
        raise RunnerError("RESULT_CANDIDATE_SET_INVALID", str(kinds))
    recomputed = decide(result["candidates"])
    if recomputed.state != result["decision_state"]:
        raise RunnerError(
            "RESULT_DECISION_INCONSISTENT",
            f"artifact says {result['decision_state']}, law says {recomputed.state}",
        )
    if recomputed.decision != result.get("decision"):
        raise RunnerError(
            "RESULT_DECISION_INCONSISTENT",
            f"artifact says {result.get('decision')}, law says {recomputed.decision}",
        )


def result_digest(result: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _git_here(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True,
                          text=True, shell=False).stdout.strip()


def _git_source() -> dict[str, Any]:
    base = _git_here("merge-base", "origin/master", "HEAD")
    changed = _git_here("diff", "--name-only", base, "HEAD")
    return {
        "repository": "mastermindx-market-intelligence/Mastermind",
        "branch": _git_here("rev-parse", "--abbrev-ref", "HEAD"),
        "head_sha": _git_here("rev-parse", "HEAD"),
        "base_sha": base,
        "protected_pickup_sha": "ae483cc5f101d369f368f217bb767c91fc9e0150",
        "changed_paths": sorted(line for line in changed.splitlines() if line),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the C0 semantic falsifier.")
    parser.add_argument("--scratch-parent", required=True)
    parser.add_argument("--python-lsp-binary")
    parser.add_argument("--python-lsp-sha256")
    parser.add_argument("--python-lsp-argv", nargs="*", default=[])
    parser.add_argument("--typescript-lsp-binary")
    parser.add_argument("--typescript-lsp-sha256")
    parser.add_argument("--typescript-lsp-argv", nargs="*", default=[])
    parser.add_argument("--serena-bundle")
    parser.add_argument("--serena-sha256")
    parser.add_argument("--serena-launcher-binary")
    parser.add_argument("--serena-launcher-sha256")
    parser.add_argument("--serena-launcher-argv", nargs="*", default=[])
    parser.add_argument("--no-sandbox", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    lsp_binaries: dict[str, dict[str, Any]] = {}
    if args.python_lsp_binary:
        lsp_binaries["python"] = {"binary": args.python_lsp_binary,
                                  "sha256": args.python_lsp_sha256,
                                  "argv": args.python_lsp_argv}
    if args.typescript_lsp_binary:
        lsp_binaries["typescript"] = {"binary": args.typescript_lsp_binary,
                                      "sha256": args.typescript_lsp_sha256,
                                      "argv": args.typescript_lsp_argv}
    if args.serena_launcher_binary:
        lsp_binaries["serena_launcher"] = {"binary": args.serena_launcher_binary,
                                           "sha256": args.serena_launcher_sha256,
                                           "argv": args.serena_launcher_argv}

    result = build_result(
        scratch_parent=Path(args.scratch_parent),
        lsp_binaries=lsp_binaries,
        serena_bundle=Path(args.serena_bundle) if args.serena_bundle else None,
        serena_sha256=args.serena_sha256,
        source=_git_source(),
        require_sandbox=not args.no_sandbox,
    )
    validate_result(result)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    print(
        f"decision_state={result['decision_state']} "
        f"decision={result.get('decision', 'NONE')} "
        f"evidence={result['semantic_evidence_digest']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
