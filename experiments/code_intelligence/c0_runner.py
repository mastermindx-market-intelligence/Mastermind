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
from typing import Any, Mapping, Sequence

from experiments.code_intelligence.backend import (
    BackendIdentity,
    BackendPayloadError,
    ExecutableSpec,
    backend_identity_digest,
    guard_payload,
)
from experiments.code_intelligence.decision import (
    MATERIALITY_BAND,
    PRIMARY_CASES,
    REQUIRED_LANGUAGES,
    TERMINAL_CORPUS_ID,
    decide,
)
from experiments.code_intelligence.ground_truth import (
    GroundTruthError,
    TERMINAL_MIGRATE_LEGACY_PIN,
    corpus_manifest_digest,
    load_answer_key,
    materialize_terminal_case,
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

ARTIFACT_VERSION = "mastermind.codeintel_c0_result.v2"
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
    if not path.is_file():
        raise RunnerError("PATH_NOT_REGULAR_FILE", f"{label}: {path}")
    return path


def is_stand_in(spec: ExecutableSpec) -> bool:
    """A server shipped inside this experiment is a stand-in, never a candidate."""
    return spec.provenance == "stand_in"


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


def _make_terminal_corpus(destination: Path, case: Mapping[str, Any]) -> Path:
    """Materialize only the verified external blob into disposable scratch."""
    destination = Path(destination)
    relative = str(case["source"]["path"])
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(case["payload"])
    _git(destination, "init", "-q", "-b", "main")
    _git(destination, "add", "-A")
    _git(destination, "commit", "-q", "-m", "c0 terminal corpus")
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
    answer_key: Mapping[str, Any] | None,
    *,
    corpus_id: str,
    language: str,
    synthetic: bool,
    matrix: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for phase in ("cold", "warm"):
        specs = list(matrix) if matrix is not None else build_matrix(answer_key or {})
        for spec in specs:
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
                "case": spec["case"], "corpus_id": corpus_id,
                "language": language, "phase": phase,
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
        "launcher_name": identity.launcher_name,
        "canonical_argv": list(identity.canonical_argv),
        "argv_file_digests": [
            {"index": index, "name": name, "sha256": digest}
            for index, name, digest in identity.argv_file_digests
        ],
        "targets": [
            {
                "name": name,
                "sha256": digest,
                "ecosystem": ecosystem,
                "package": package,
                "version": version,
                "binding": binding,
            }
            for name, digest, ecosystem, package, version, binding in identity.targets
        ],
        "dependency_manifests": [
            {"ecosystem": ecosystem, "sha256": digest}
            for ecosystem, digest in identity.dependency_manifests
        ],
        "provenance": identity.provenance,
    }


def _exercise(
    backend_factory,
    *,
    corpus: Path,
    corpus_id: str,
    language: str,
    scratch_parent: Path,
    synthetic: bool,
    entry: dict[str, Any],
    receipts: list[dict[str, Any]],
    matrix: Sequence[Mapping[str, Any]] | None = None,
):
    """Run one candidate over one language corpus behind the sealed facade."""
    workspace_label = corpus_id.replace("/", "-").replace("_", "-")
    workspace = make_disposable_corpus(
        Path(scratch_parent) / f"ws-{entry['kind']}-{workspace_label}", corpus=corpus
    ) if matrix is None else corpus
    seal = capture_workspace_seal(workspace)
    scratch = create_external_scratch(parent=Path(scratch_parent) / "scratch", seal=seal)
    backend = backend_factory()
    facade = SemanticFacade(seal=seal, backend=backend, scratch=scratch)
    try:
        facade.start()
        receipt = dict(facade.binding_receipt())
        receipt["language"] = language
        receipt["candidate"] = entry["kind"]
        receipt["corpus_id"] = corpus_id
        receipts.append(receipt)
        entry["identity"] = entry.get("identity") or _identity_dict(backend)
        entry["trials"].extend(
            run_trials(
                facade,
                load_answer_key(corpus) if matrix is None else None,
                corpus_id=corpus_id,
                language=language,
                synthetic=synthetic,
                matrix=matrix,
            )
        )
        entry["status"] = "EXERCISED"
    except (FacadeError, WorkspaceSealError, SerenaBackendError) as exc:
        entry["hard_failures"].append(getattr(exc, "code", "BACKEND_FAILED"))
        entry["notes"] = _redact(str(exc))[:300]
    finally:
        facade.close()


def _argv_file_pins(argv: Sequence[str]) -> tuple[tuple[str, str], ...]:
    pins = []
    for item in argv:
        path = Path(item)
        if path.is_file():
            pins.append((str(path), _file_digest(path)))
    return tuple(pins)


def _target_pins(
    supplied: Mapping[str, Any],
    *,
    language: str,
    argv_pins: Sequence[tuple[str, str]],
    argv: Sequence[str],
    launcher_path: Path,
    launcher_digest: str,
) -> tuple[
    tuple[tuple[str, str, str, str, str, str], ...],
    tuple[tuple[str, Path], ...],
]:
    declared = supplied.get("targets")
    if declared:
        pins: list[tuple[str, str, str, str, str, str]] = []
        sources: list[tuple[str, Path]] = []
        pinned_by_argv_index = {
            index: (Path(item).resolve(), digest)
            for index, item in enumerate(argv, start=1)
            for pinned_path, digest in argv_pins
            if str(Path(item)) == pinned_path
        }
        for row in declared:
            required = {
                "name", "file", "sha256", "ecosystem", "package", "version", "binding"
            }
            if not isinstance(row, Mapping) or not required.issubset(row):
                raise RunnerError(
                    "TARGET_MANIFEST_INVALID",
                    "target rows need name, file, sha256, ecosystem, package, version and binding",
                )
            target = _require_real_path(Path(row["file"]), f"{language}-target")
            observed = _file_digest(target)
            if observed != row.get("sha256"):
                raise RunnerError(
                    "TARGET_DIGEST_MISMATCH", f"{language}:{row.get('name', 'unnamed')}"
                )
            name = str(row["name"])
            binding = str(row["binding"])
            if binding == "launcher":
                bound = (
                    target.resolve() == launcher_path.resolve()
                    and observed == launcher_digest
                )
            elif binding.startswith("argv_file:"):
                try:
                    index = int(binding.removeprefix("argv_file:"))
                except ValueError:
                    index = 0
                pinned = pinned_by_argv_index.get(index)
                bound = bool(
                    pinned
                    and target.resolve() == pinned[0]
                    and observed == pinned[1]
                )
            else:
                bound = False
            if not bound:
                raise RunnerError(
                    "TARGET_INVOCATION_MISMATCH",
                    f"{language}:{name}:{binding}",
                )
            pins.append((
                name,
                observed,
                str(row["ecosystem"]),
                str(row["package"]),
                str(row["version"]),
                binding,
            ))
            sources.append((name, target))
        return tuple(pins), tuple(sources)
    return (), ()


def _execution_view(receipt: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "candidate", "corpus_id", "language", "provenance", "launcher",
        "canonical_argv", "argv_file_digests", "targets", "backend_identity",
        "dependency_manifests", "backend_identity_digest",
    )
    return {key: receipt[key] for key in keys}


def _read_pinned_json(path: Path, expected_sha256: str, *, label: str) -> Any:
    source = _require_real_path(Path(path), label)
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise RunnerError("MANIFEST_DIGEST_INVALID", label)
    if _file_digest(source) != expected_sha256:
        raise RunnerError("MANIFEST_DIGEST_MISMATCH", label)
    try:
        return json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunnerError("MANIFEST_INVALID", label) from exc


def _python_package_tree_digest(files: Sequence[Mapping[str, Any]]) -> str:
    """Bind one package coordinate to the exact measured file-name/digest set."""
    return hashlib.sha256(
        b"".join(
            str(row["name"]).encode("utf-8") + b"\0"
            + str(row["sha256"]).encode("ascii") + b"\n"
            for row in sorted(files, key=lambda item: str(item["name"]))
        )
    ).hexdigest()


def _measure_python_closure(
    path: Path, expected_sha256: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    declared = _read_pinned_json(path, expected_sha256, label="python")
    if not isinstance(declared, list) or not declared:
        raise RunnerError("PYTHON_CLOSURE_INVALID", "expected a non-empty package array")
    packages: list[dict[str, Any]] = []
    for package in declared:
        if not isinstance(package, Mapping) or not {"name", "version", "files"}.issubset(package):
            raise RunnerError("PYTHON_CLOSURE_INVALID", "package row is incomplete")
        files = []
        for item in package["files"]:
            if not isinstance(item, Mapping) or not {"name", "source", "sha256"}.issubset(item):
                raise RunnerError("PYTHON_CLOSURE_INVALID", "file row is incomplete")
            name = str(item["name"])
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise RunnerError("PYTHON_CLOSURE_INVALID", "file name must be relative")
            source = _require_real_path(Path(item["source"]), "python-package-file")
            observed = _file_digest(source)
            if observed != item["sha256"]:
                raise RunnerError("PACKAGE_FILE_DIGEST_MISMATCH", name)
            files.append({"name": name, "sha256": observed})
        if not files:
            raise RunnerError("PYTHON_CLOSURE_INVALID", "package has no measured files")
        packages.append({
            "name": str(package["name"]),
            "version": str(package["version"]),
            "files": sorted(files, key=lambda row: row["name"]),
            "tree_sha256": _python_package_tree_digest(files),
        })
    packages.sort(key=lambda row: (row["name"].lower(), row["version"]))
    closure_sha = hashlib.sha256(canonical_json(packages).encode("utf-8")).hexdigest()
    return packages, {
        "ecosystem": "python",
        "sha256": expected_sha256,
        "closure_sha256": closure_sha,
        "provenance": "expected-digest manifest plus measured installed files",
    }


def _measure_npm_closure(
    path: Path, expected_sha256: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lock = _read_pinned_json(path, expected_sha256, label="npm")
    package_map = lock.get("packages") if isinstance(lock, Mapping) else None
    if not isinstance(package_map, Mapping):
        raise RunnerError("NPM_CLOSURE_INVALID", "package-lock packages map missing")
    packages = []
    for key, metadata in package_map.items():
        if not key or not isinstance(metadata, Mapping):
            continue
        required = (metadata.get("version"), metadata.get("resolved"), metadata.get("integrity"))
        if not all(isinstance(value, str) and value for value in required):
            raise RunnerError("NPM_CLOSURE_INVALID", f"package {key} lacks version/resolved/integrity")
        name = str(metadata.get("name") or str(key).split("node_modules/")[-1])
        packages.append({
            "name": name,
            "version": metadata["version"],
            "resolved": metadata["resolved"],
            "integrity": metadata["integrity"],
        })
    if not packages:
        raise RunnerError("NPM_CLOSURE_INVALID", "no locked packages")
    packages.sort(key=lambda row: (row["name"].lower(), row["version"], row["resolved"]))
    closure_sha = hashlib.sha256(canonical_json(packages).encode("utf-8")).hexdigest()
    return packages, {
        "ecosystem": "npm",
        "sha256": expected_sha256,
        "closure_sha256": closure_sha,
        "provenance": "expected-digest package-lock parsed by runner",
    }


def _identity_failures(
    *,
    executions: Sequence[Mapping[str, Any]],
    python_packages: Sequence[Mapping[str, Any]],
    npm_packages: Sequence[Mapping[str, Any]],
    resolution_manifests: Sequence[Mapping[str, Any]],
) -> list[str]:
    failures: list[str] = []
    if not executions:
        failures.append("EXECUTION_IDENTITY_MISSING")
    if any(not row.get("targets") for row in executions):
        failures.append("EXECUTABLE_TARGET_MISSING")
    if any(not row.get("canonical_argv") for row in executions):
        failures.append("CANONICAL_ARGV_MISSING")
    if any(
        any(str(token).startswith("<unbound-absolute-argv:") for token in row["canonical_argv"])
        for row in executions
    ):
        failures.append("ARGV_FILE_DIGEST_MISSING")
    valid_python = bool(python_packages) and all(
        row.get("name") and row.get("version") and row.get("files")
        and isinstance(row.get("tree_sha256"), str)
        and len(row["tree_sha256"]) == 64
        and row["tree_sha256"] == _python_package_tree_digest(row["files"])
        and all(
            item.get("name") and isinstance(item.get("sha256"), str)
            and len(item["sha256"]) == 64
            for item in row["files"]
        )
        for row in python_packages
    )
    if not valid_python:
        failures.append("PYTHON_PACKAGE_CLOSURE_MISSING")
    valid_npm = bool(npm_packages) and all(
        row.get("name") and row.get("version") and row.get("resolved")
        and row.get("integrity")
        for row in npm_packages
    )
    if not valid_npm:
        failures.append("NPM_PACKAGE_CLOSURE_MISSING")
    valid_manifests = [
        row for row in resolution_manifests
        if row.get("ecosystem") in {"python", "npm"}
        and isinstance(row.get("sha256"), str) and len(row["sha256"]) == 64
        and isinstance(row.get("closure_sha256"), str)
        and len(row["closure_sha256"]) == 64
        and row.get("provenance")
    ]
    ecosystems = {str(row.get("ecosystem")) for row in valid_manifests}
    if not {"python", "npm"}.issubset(ecosystems):
        failures.append("RESOLUTION_PROVENANCE_MANIFEST_MISSING")
    python_digests = {
        (str(row["name"]), str(row["version"])): {
            str(row.get("tree_sha256", "")),
            *(str(item.get("sha256", "")) for item in row.get("files", ())),
        }
        for row in python_packages
    }
    npm_coordinates = {
        (str(row["name"]), str(row["version"])) for row in npm_packages
    }
    for execution in executions:
        has_selected_launch_target = False
        for target in execution.get("targets", ()):
            coordinate = (str(target.get("package")), str(target.get("version")))
            ecosystem = target.get("ecosystem")
            binding = str(target.get("binding", ""))
            if binding == "launcher":
                invocation_bound = target.get("sha256") == execution["launcher"]["sha256"]
                has_selected_launch_target = has_selected_launch_target or invocation_bound
            elif binding.startswith("argv_file:"):
                try:
                    index = int(binding.removeprefix("argv_file:"))
                except ValueError:
                    index = 0
                invocation_bound = any(
                    row.get("index") == index
                    and row.get("sha256") == target.get("sha256")
                    for row in execution.get("argv_file_digests", ())
                )
                has_selected_launch_target = has_selected_launch_target or invocation_bound
            elif binding == "verified_bundle":
                invocation_bound = execution.get("candidate") == "serena"
            else:
                invocation_bound = False
            if not invocation_bound:
                failures.append("TARGET_INVOCATION_UNBOUND")
            if ecosystem == "python" and coordinate not in python_digests:
                failures.append("TARGET_PYTHON_PACKAGE_UNBOUND")
            elif (
                ecosystem == "python"
                and str(target.get("sha256")) not in python_digests[coordinate]
            ):
                failures.append("TARGET_PYTHON_DIGEST_UNBOUND")
            elif ecosystem == "npm" and coordinate not in npm_coordinates:
                failures.append("TARGET_NPM_PACKAGE_UNBOUND")
            elif ecosystem == "stand_in" and execution["provenance"]["kind"] != "stand_in":
                failures.append("TARGET_PROVENANCE_UNBOUND")
            elif ecosystem not in {"python", "npm", "stand_in"}:
                failures.append("TARGET_ECOSYSTEM_INVALID")
        if execution.get("targets") and not has_selected_launch_target:
            failures.append("TARGET_INVOCATION_UNBOUND")
    manifest_pins = sorted((row["ecosystem"], row["sha256"]) for row in valid_manifests)
    if any(
        sorted((row["ecosystem"], row["sha256"])
               for row in execution.get("dependency_manifests", ())) != manifest_pins
        for execution in executions
    ):
        failures.append("DEPENDENCY_MANIFEST_BINDING_MISSING")
    return list(dict.fromkeys(failures))


def build_result(
    *,
    scratch_parent: Path,
    lsp_binaries: Mapping[str, Mapping[str, Any]] | None = None,
    serena_bundle: Path | None = None,
    serena_sha256: str | None = None,
    terminal_repository: Path | None = None,
    python_closure_manifest: Path | None = None,
    python_closure_sha256: str | None = None,
    npm_lock_manifest: Path | None = None,
    npm_lock_sha256: str | None = None,
    source: Mapping[str, Any],
    require_sandbox: bool = True,
) -> dict[str, Any]:
    scratch_parent = Path(scratch_parent)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    lsp_binaries = lsp_binaries or {}
    python_packages: list[dict[str, Any]] = []
    npm_packages: list[dict[str, Any]] = []
    resolution_manifests: list[dict[str, Any]] = []
    if python_closure_manifest is not None or python_closure_sha256 is not None:
        if python_closure_manifest is None or python_closure_sha256 is None:
            raise RunnerError(
                "MANIFEST_DIGEST_UNPINNED", "python closure needs path and expected sha256"
            )
        python_packages, receipt = _measure_python_closure(
            python_closure_manifest, python_closure_sha256
        )
        resolution_manifests.append(receipt)
    if npm_lock_manifest is not None or npm_lock_sha256 is not None:
        if npm_lock_manifest is None or npm_lock_sha256 is None:
            raise RunnerError(
                "MANIFEST_DIGEST_UNPINNED", "npm lock needs path and expected sha256"
            )
        npm_packages, receipt = _measure_npm_closure(
            npm_lock_manifest, npm_lock_sha256
        )
        resolution_manifests.append(receipt)
    dependency_manifest_pins = tuple(
        (row["ecosystem"], row["sha256"]) for row in resolution_manifests
    )
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
        "identity": None, "identity_complete": False, "identity_failures": [],
        "trials": [], "hard_failures": [], "notes": "",
    }
    lsp_specs: dict[str, ExecutableSpec] = {}
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
        argv_pins = _argv_file_pins(argv)
        targets, target_sources = _target_pins(
            supplied,
            language=language,
            argv_pins=argv_pins,
            argv=argv,
            launcher_path=binary,
            launcher_digest=supplied["sha256"],
        )
        spec = ExecutableSpec(
            path=binary, sha256=supplied["sha256"], argv_suffix=argv,
            argv_digests=argv_pins,
            targets=targets,
            target_sources=target_sources,
            dependency_manifests=dependency_manifest_pins,
        )
        lsp_specs[language] = spec
        synthetic = is_stand_in(spec)
        if synthetic:
            lsp_entry["notes"] = (
                "Exercised against this experiment's own stand-in server: adapter "
                "behaviour only, categorically ineligible as empirical evidence."
            )
        _exercise(
            lambda spec=spec: DirectLspBackend(spec=spec, language=language, sandbox=sandbox),
            corpus=CORPORA[language],
            corpus_id=load_answer_key(CORPORA[language])["corpus_id"],
            language=language,
            scratch_parent=scratch_parent, synthetic=synthetic,
            entry=lsp_entry, receipts=binding_receipts,
        )

    # ---- Candidate S: pinned Serena
    serena_entry: dict[str, Any] = {
        "kind": "serena", "status": "UNEXERCISED_MISSING_BUNDLE",
        "identity": None, "identity_complete": False, "identity_failures": [],
        "trials": [], "hard_failures": [], "notes": "",
    }
    serena_probe: dict[str, Any] | None = None
    serena_spec: ExecutableSpec | None = None
    bundle = None
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
                launcher_binary = _require_real_path(
                    Path(launcher["binary"]), "serena-launcher-binary"
                )
                launcher_digest = launcher.get("sha256")
                if not launcher_digest:
                    raise SerenaBackendError(
                        "SERENA_LAUNCHER_DIGEST_UNPINNED", "launcher sha256 missing"
                    )
                if _file_digest(launcher_binary) != launcher_digest:
                    raise SerenaBackendError(
                        "SERENA_LAUNCHER_DIGEST_MISMATCH", "launcher bytes moved"
                    )
                argv = tuple(launcher.get("argv", ()))
                argv_pins = _argv_file_pins(argv)
                targets, target_sources = _target_pins(
                    launcher,
                    language="serena",
                    argv_pins=argv_pins,
                    argv=argv,
                    launcher_path=launcher_binary,
                    launcher_digest=launcher_digest,
                )
                spec = ExecutableSpec(
                    path=launcher_binary, sha256=launcher_digest,
                    argv_suffix=argv,
                    argv_digests=argv_pins,
                    targets=targets,
                    target_sources=target_sources,
                    dependency_manifests=dependency_manifest_pins,
                )
                serena_spec = spec
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
                        corpus=CORPORA[language],
                        corpus_id=load_answer_key(CORPORA[language])["corpus_id"],
                        language=language,
                        scratch_parent=scratch_parent, synthetic=synthetic,
                        entry=serena_entry, receipts=binding_receipts,
                    )
                serena_entry["advertised_tool_census"] = []
        except SerenaBackendError as exc:
            serena_entry["hard_failures"].append(exc.code)
            serena_entry["notes"] = _redact(exc.detail)[:300]

    terminal_case: dict[str, Any] | None = None
    terminal_failure: str | None = None
    if terminal_repository is None:
        terminal_failure = "TERMINAL_REPOSITORY_UNAVAILABLE"
    else:
        try:
            terminal_case = materialize_terminal_case(terminal_repository)
        except GroundTruthError as exc:
            terminal_failure = exc.code

    if terminal_case is not None:
        terminal_workspace = _make_terminal_corpus(
            scratch_parent / "terminal-source", terminal_case
        )
        trial_case = {
            key: value for key, value in terminal_case.items()
            if key in {"case", "tool", "arguments", "expected"}
        }
        ts_spec = lsp_specs.get("typescript")
        if ts_spec is not None:
            _exercise(
                lambda spec=ts_spec: DirectLspBackend(
                    spec=spec, language="typescript", sandbox=sandbox
                ),
                corpus=terminal_workspace,
                corpus_id=TERMINAL_CORPUS_ID,
                language="typescript",
                scratch_parent=scratch_parent,
                synthetic=is_stand_in(ts_spec),
                entry=lsp_entry,
                receipts=binding_receipts,
                matrix=[trial_case],
            )
        if serena_spec is not None and bundle is not None:
            serena_terminal_workspace = _make_terminal_corpus(
                scratch_parent / "terminal-source-serena", terminal_case
            )
            _exercise(
                lambda spec=serena_spec, bundle=bundle: SerenaBackend(
                    spec=spec, bundle=bundle, sandbox=sandbox
                ),
                corpus=serena_terminal_workspace,
                corpus_id=TERMINAL_CORPUS_ID,
                language="typescript",
                scratch_parent=scratch_parent,
                synthetic=is_stand_in(serena_spec),
                entry=serena_entry,
                receipts=binding_receipts,
                matrix=[trial_case],
            )
    else:
        for entry in (lsp_entry, serena_entry):
            entry["hard_failures"].append(terminal_failure or "TERMINAL_PIN_UNVERIFIED")

    executions = [_execution_view(receipt) for receipt in binding_receipts]
    for entry in (lsp_entry, serena_entry):
        candidate_executions = [
            row for row in executions if row["candidate"] == entry["kind"]
        ]
        entry["identity_failures"] = _identity_failures(
            executions=candidate_executions,
            python_packages=python_packages,
            npm_packages=npm_packages,
            resolution_manifests=resolution_manifests,
        )
        entry["identity_complete"] = not entry["identity_failures"]

    candidates = [lsp_entry, serena_entry]
    hostile_results = run_hostile_checks(scratch_parent / "hostile", serena_probe=serena_probe)
    outcome = decide(candidates)

    corpora = [
        {
            "corpus_id": load_answer_key(path)["corpus_id"],
            "language": load_answer_key(path)["language"],
            "manifest_digest": corpus_manifest_digest(path),
            "ground_truth": {
                "kind": "committed_answer_key",
                "sha256": hashlib.sha256((path / "answer_key.json").read_bytes()).hexdigest(),
            },
        }
        for path in CORPORA.values()
    ]
    if terminal_case is not None:
        corpora.append(
            {
                "corpus_id": TERMINAL_CORPUS_ID,
                "language": "typescript",
                "manifest_digest": hashlib.sha256(terminal_case["payload"]).hexdigest(),
                "ground_truth": {
                    "kind": "derived_external_git_source",
                    "source": dict(terminal_case["source"]),
                },
            }
        )

    residual_risks = [
        "Ground truth is a conservative census, not a type-checker.",
        "RLIMIT_AS is unenforceable on Darwin, so address space is not bounded.",
    ]
    if any(row["provenance"]["kind"] == "stand_in" for row in executions):
        residual_risks.insert(
            0,
            "Adapter proofs used stand-in servers; real backend semantics remain unmeasured.",
        )
    if terminal_case is None:
        residual_risks.insert(
            0,
            "The protected Terminal migrateLegacy case was not materialized from its exact pin.",
        )
    if any(not entry["identity_complete"] for entry in candidates):
        residual_risks.insert(
            0,
            "Executable identity is incomplete until Python and npm closures and immutable resolution manifests are supplied.",
        )

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
        "corpora": corpora,
        "toolchain": {
            "python_packages": list(python_packages),
            "npm_packages": list(npm_packages),
            "resolution_manifests": list(resolution_manifests),
            "executions": executions,
        },
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
        "residual_risks": residual_risks,
        "next_action": "",
    }
    if outcome.decision is not None:
        result["decision"] = outcome.decision
        result["next_action"] = "Return the decision to Sol for C0 release adjudication."
    else:
        result["blocking_reason"] = outcome.blocking_reason
        result["next_action"] = (
            "Sol/B0 to provide the exact Terminal checkout, pinned Serena bundle "
            "(949a27ef1e5fda1a6e7b561e777bcece345c6ffd / v1.7.0) and pinned Python and "
            "TypeScript/TSX language-server bundles plus Python/npm closure and "
            "immutable resolution manifests as host inputs; the "
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

    receipts = list(result["binding_receipt"].get("per_execution", ()))
    executions = list(result.get("toolchain", {}).get("executions", ()))
    required_identity_keys = {
        "candidate", "corpus_id", "language", "provenance", "launcher",
        "canonical_argv", "argv_file_digests", "targets", "backend_identity",
        "dependency_manifests", "backend_identity_digest",
    }
    if any(not required_identity_keys.issubset(row) for row in receipts + executions):
        raise RunnerError("RESULT_EXECUTION_IDENTITY_INCOMPLETE", "required identity row missing")

    def scope(row: Mapping[str, Any]) -> tuple[str, str, str]:
        return (str(row["candidate"]), str(row["corpus_id"]), str(row["language"]))

    receipt_scopes = [scope(row) for row in receipts]
    execution_scopes = [scope(row) for row in executions]
    trial_scopes = {
        (str(candidate["kind"]), str(trial.get("corpus_id")), str(trial["language"]))
        for candidate in result["candidates"]
        for trial in candidate["trials"]
    }
    if (
        len(receipt_scopes) != len(set(receipt_scopes))
        or len(execution_scopes) != len(set(execution_scopes))
        or set(receipt_scopes) != trial_scopes
        or set(execution_scopes) != trial_scopes
    ):
        raise RunnerError(
            "RESULT_EXECUTION_TRIAL_MISMATCH",
            "each candidate/corpus/language trial scope needs exactly one execution receipt",
        )
    receipt_views = sorted(
        canonical_json(_execution_view(row)) for row in receipts
    )
    execution_views = sorted(canonical_json(dict(row)) for row in executions)
    if receipt_views != execution_views:
        raise RunnerError(
            "RESULT_EXECUTION_IDENTITY_MISMATCH",
            "binding receipts and toolchain executions differ",
        )

    for row in executions:
        payload = row["backend_identity"]
        try:
            identity = BackendIdentity(
                kind=payload["kind"],
                source_version=payload["source_version"],
                source_commit=payload["source_commit"],
                executable_sha256=payload["executable_sha256"],
                language_servers=tuple(
                    (str(name), str(digest))
                    for name, digest in payload["language_servers"]
                ),
                configuration_digest=payload["configuration_digest"],
                launcher_name=payload["launcher_name"],
                canonical_argv=tuple(payload["canonical_argv"]),
                argv_file_digests=tuple(
                    (int(index), str(name), str(digest))
                    for index, name, digest in payload["argv_file_digests"]
                ),
                targets=tuple(
                    (
                        str(name), str(digest), str(ecosystem), str(package),
                        str(version), str(binding),
                    )
                    for name, digest, ecosystem, package, version, binding
                    in payload["targets"]
                ),
                dependency_manifests=tuple(
                    (str(ecosystem), str(digest))
                    for ecosystem, digest in payload["dependency_manifests"]
                ),
                provenance=payload["provenance"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RunnerError(
                "RESULT_EXECUTION_IDENTITY_INCOMPLETE", "invalid backend identity payload"
            ) from exc
        if backend_identity_digest(identity) != row["backend_identity_digest"]:
            raise RunnerError(
                "RESULT_BACKEND_IDENTITY_DIGEST_MISMATCH",
                "launcher, argv, target, provenance or source identity was substituted",
            )
        if (
            payload["canonical_argv"] != row["canonical_argv"]
            or payload["argv_file_digests"] != [
                [item["index"], item["name"], item["sha256"]]
                for item in row["argv_file_digests"]
            ]
            or payload["targets"] != [
                [
                    target["name"], target["sha256"], target["ecosystem"],
                    target["package"], target["version"], target["binding"],
                ]
                for target in row["targets"]
            ]
            or payload["dependency_manifests"] != [
                [manifest["ecosystem"], manifest["sha256"]]
                for manifest in row["dependency_manifests"]
            ]
            or payload["language_servers"] != [target[:2] for target in payload["targets"]]
            or payload["provenance"] != row["provenance"]["kind"]
            or payload["executable_sha256"] != row["launcher"]["sha256"]
            or payload["launcher_name"] != row["launcher"]["name"]
        ):
            raise RunnerError(
                "RESULT_EXECUTION_IDENTITY_MISMATCH",
                "execution projection disagrees with its canonical backend identity",
            )

    receipt_by_scope = {scope(row): row for row in receipts}
    for candidate in result["candidates"]:
        for trial in candidate["trials"]:
            row = receipt_by_scope[
                (candidate["kind"], trial["corpus_id"], trial["language"])
            ]
            expected_synthetic = row["provenance"]["kind"] == "stand_in"
            if bool(trial["synthetic"]) != expected_synthetic:
                raise RunnerError(
                    "RESULT_PROVENANCE_INCONSISTENT",
                    "trial synthetic marker disagrees with machine-derived execution provenance",
                )

    toolchain = result["toolchain"]
    for candidate in result["candidates"]:
        candidate_executions = [
            row for row in executions if row["candidate"] == candidate["kind"]
        ]
        failures = _identity_failures(
            executions=candidate_executions,
            python_packages=toolchain["python_packages"],
            npm_packages=toolchain["npm_packages"],
            resolution_manifests=toolchain["resolution_manifests"],
        )
        if failures != list(candidate.get("identity_failures", ())):
            raise RunnerError(
                "RESULT_IDENTITY_CLOSURE_INCONSISTENT",
                f"{candidate['kind']} identity failure rows do not match manifests",
            )
        if bool(candidate.get("identity_complete")) != (not failures):
            raise RunnerError(
                "RESULT_IDENTITY_CLOSURE_INCONSISTENT",
                f"{candidate['kind']} identity_complete is not machine-derived",
            )

    has_stand_in = any(
        row["provenance"]["kind"] == "stand_in" for row in executions
    )
    risk_mentions_stand_in = any(
        "stand-in" in risk.lower() for risk in result["residual_risks"]
    )
    if has_stand_in != risk_mentions_stand_in:
        raise RunnerError(
            "RESULT_PROVENANCE_RISK_INCONSISTENT",
            "residual risk does not match execution provenance",
        )

    terminal_trials = any(
        trial.get("corpus_id") == TERMINAL_CORPUS_ID
        for candidate in result["candidates"] for trial in candidate["trials"]
    )
    terminal_rows = [
        row for row in result["corpora"] if row["corpus_id"] == TERMINAL_CORPUS_ID
    ]
    terminal_risk = any("terminal migratelegacy" in risk.lower()
                        for risk in result["residual_risks"])
    if terminal_trials:
        if len(terminal_rows) != 1:
            raise RunnerError("RESULT_TERMINAL_PIN_MISMATCH", "Terminal corpus row missing")
        source = terminal_rows[0].get("ground_truth", {}).get("source")
        if source != TERMINAL_MIGRATE_LEGACY_PIN:
            raise RunnerError(
                "RESULT_TERMINAL_PIN_MISMATCH", "Terminal source identity is not the protected pin"
            )
    if terminal_trials == terminal_risk:
        raise RunnerError(
            "RESULT_TERMINAL_RISK_INCONSISTENT",
            "Terminal residual risk does not match materialized trial evidence",
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
    parser.add_argument("--python-lsp-target-name")
    parser.add_argument("--python-lsp-target-file")
    parser.add_argument("--python-lsp-target-sha256")
    parser.add_argument("--python-lsp-target-ecosystem")
    parser.add_argument("--python-lsp-target-package")
    parser.add_argument("--python-lsp-target-version")
    parser.add_argument("--python-lsp-target-binding")
    parser.add_argument("--typescript-lsp-binary")
    parser.add_argument("--typescript-lsp-sha256")
    parser.add_argument("--typescript-lsp-argv", nargs="*", default=[])
    parser.add_argument("--typescript-lsp-target-name")
    parser.add_argument("--typescript-lsp-target-file")
    parser.add_argument("--typescript-lsp-target-sha256")
    parser.add_argument("--typescript-lsp-target-ecosystem")
    parser.add_argument("--typescript-lsp-target-package")
    parser.add_argument("--typescript-lsp-target-version")
    parser.add_argument("--typescript-lsp-target-binding")
    parser.add_argument("--serena-bundle")
    parser.add_argument("--serena-sha256")
    parser.add_argument("--serena-launcher-binary")
    parser.add_argument("--serena-launcher-sha256")
    parser.add_argument("--serena-launcher-argv", nargs="*", default=[])
    parser.add_argument("--serena-target-name")
    parser.add_argument("--serena-target-file")
    parser.add_argument("--serena-target-sha256")
    parser.add_argument("--serena-target-ecosystem")
    parser.add_argument("--serena-target-package")
    parser.add_argument("--serena-target-version")
    parser.add_argument("--serena-target-binding")
    parser.add_argument("--terminal-repository")
    parser.add_argument("--python-package-closure")
    parser.add_argument("--python-package-closure-sha256")
    parser.add_argument("--npm-package-lock")
    parser.add_argument("--npm-package-lock-sha256")
    parser.add_argument("--no-sandbox", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    for label, values in (
        ("python LSP target", (
            args.python_lsp_target_name, args.python_lsp_target_file,
            args.python_lsp_target_sha256, args.python_lsp_target_ecosystem,
            args.python_lsp_target_package, args.python_lsp_target_version,
            args.python_lsp_target_binding,
        )),
        ("TypeScript LSP target", (
            args.typescript_lsp_target_name, args.typescript_lsp_target_file,
            args.typescript_lsp_target_sha256, args.typescript_lsp_target_ecosystem,
            args.typescript_lsp_target_package, args.typescript_lsp_target_version,
            args.typescript_lsp_target_binding,
        )),
        ("Serena target", (
            args.serena_target_name, args.serena_target_file,
            args.serena_target_sha256, args.serena_target_ecosystem,
            args.serena_target_package, args.serena_target_version,
            args.serena_target_binding,
        )),
    ):
        if any(values) and not all(values):
            parser.error(
                f"{label} requires name, file, sha256, ecosystem, package, version and binding together"
            )

    lsp_binaries: dict[str, dict[str, Any]] = {}
    if args.python_lsp_binary:
        lsp_binaries["python"] = {"binary": args.python_lsp_binary,
                                  "sha256": args.python_lsp_sha256,
                                  "argv": args.python_lsp_argv}
        if args.python_lsp_target_name:
            lsp_binaries["python"]["targets"] = [
                {"name": args.python_lsp_target_name,
                 "file": args.python_lsp_target_file,
                 "sha256": args.python_lsp_target_sha256,
                 "ecosystem": args.python_lsp_target_ecosystem,
                 "package": args.python_lsp_target_package,
                 "version": args.python_lsp_target_version,
                 "binding": args.python_lsp_target_binding}
            ]
    if args.typescript_lsp_binary:
        lsp_binaries["typescript"] = {"binary": args.typescript_lsp_binary,
                                      "sha256": args.typescript_lsp_sha256,
                                      "argv": args.typescript_lsp_argv}
        if args.typescript_lsp_target_name:
            lsp_binaries["typescript"]["targets"] = [
                {"name": args.typescript_lsp_target_name,
                 "file": args.typescript_lsp_target_file,
                 "sha256": args.typescript_lsp_target_sha256,
                 "ecosystem": args.typescript_lsp_target_ecosystem,
                 "package": args.typescript_lsp_target_package,
                 "version": args.typescript_lsp_target_version,
                 "binding": args.typescript_lsp_target_binding}
            ]
    if args.serena_launcher_binary:
        lsp_binaries["serena_launcher"] = {"binary": args.serena_launcher_binary,
                                           "sha256": args.serena_launcher_sha256,
                                           "argv": args.serena_launcher_argv}
        if args.serena_target_name:
            lsp_binaries["serena_launcher"]["targets"] = [
                {"name": args.serena_target_name,
                 "file": args.serena_target_file,
                 "sha256": args.serena_target_sha256,
                 "ecosystem": args.serena_target_ecosystem,
                 "package": args.serena_target_package,
                 "version": args.serena_target_version,
                 "binding": args.serena_target_binding}
            ]

    result = build_result(
        scratch_parent=Path(args.scratch_parent),
        lsp_binaries=lsp_binaries,
        serena_bundle=Path(args.serena_bundle) if args.serena_bundle else None,
        serena_sha256=args.serena_sha256,
        terminal_repository=(
            Path(args.terminal_repository) if args.terminal_repository else None
        ),
        python_closure_manifest=(
            Path(args.python_package_closure) if args.python_package_closure else None
        ),
        python_closure_sha256=args.python_package_closure_sha256,
        npm_lock_manifest=(Path(args.npm_package_lock) if args.npm_package_lock else None),
        npm_lock_sha256=args.npm_package_lock_sha256,
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
