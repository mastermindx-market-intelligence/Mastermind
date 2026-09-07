"""Provider-neutral worker contract and dependency-boundary proofs."""
from __future__ import annotations

import ast
import dataclasses
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from control_plane import codex_worker
from control_plane import executive_supervisor
from control_plane import executive_worker_broker
from control_plane import worker_adapter
from control_plane import worker_execution_contract
from control_plane.worker_execution_contract import (
    WORKER_EXECUTION_CONTRACT_VERSION,
    ArtifactReceipt,
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ProcessInspector,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)


_LAUNCH_FIELDS = {
    "run_id",
    "job_id",
    "worker_id",
    "workspace_path",
    "run_dir",
    "prompt",
    "result_schema_path",
    "authorities",
    "authority",
    "model",
    "reasoning_effort",
    "timeout_seconds",
    "cancel_grace_seconds",
    "worker_user",
    "expected_base_sha",
    "allowed_artifact_paths",
    "isolation_roots",
    "isolation_denied_paths",
    "isolation_manifest",
    "isolation_manifest_sha256",
    "forbidden_paths",
    "max_artifacts",
    "max_artifact_bytes",
    "max_artifact_total_bytes",
    "expected_worker_uid",
    "expected_worker_gid",
    "shared_run_gid",
    "secret_canary_verdict",
    "require_secret_canary",
}
_MOVED_NAMES = {
    "ArtifactReceipt",
    "BinaryAttestation",
    "CancelReceipt",
    "CollectionReceipt",
    "LaunchSpec",
    "ProcessRef",
    "ValidationReceipt",
    "WorkerResult",
    "WorkerRunStatus",
}
_ARTIFACT_LIMITS = {
    "MAX_ARTIFACTS": 32,
    "MAX_ARTIFACT_BYTES": 8 * 1024 * 1024,
    "MAX_ARTIFACT_TOTAL_BYTES": 32 * 1024 * 1024,
}
_PROVIDER_OWNED_KEYWORDS = {
    "api_key",
    "claude_home",
    "codex_home",
    "credential_path",
    "provider_home",
    "provider_session_id",
    "token",
}
_TARGET_CONSTRUCTORS = {
    "control_plane.codex_worker.CodexWorkerAdapter": "adapter",
    "control_plane.executive_supervisor.ExecutiveSupervisor": "supervisor",
}
_EXPECTED_CONSTRUCTOR_SITES = {
    ("scripts/executive_os_phase1b.py", "_supervisor", "adapter", 1),
    ("scripts/executive_os_phase1b.py", "_supervisor", "supervisor", 1),
    ("scripts/executive_os_phase1b_proof.py", "_run", "adapter", 1),
    ("scripts/executive_os_phase1b_proof.py", "_run", "adapter", 2),
    ("scripts/executive_os_phase1b_proof.py", "_run", "supervisor", 1),
    ("scripts/executive_os_phase1b_proof.py", "_run", "supervisor", 2),
    ("scripts/executive_os_phase1b_proof.py", "_run", "supervisor", 3),
    (
        "scripts/executive_os_phase1c.py",
        "_service_from_config.supervisor_factory",
        "supervisor",
        1,
    ),
    ("scripts/executive_os_phase1c_worker.py", "_build_broker", "adapter", 1),
    (
        "scripts/executive_os_phase1fc_acceptance.py",
        "_ExactSupervisorFixtureDispatcher.__init__",
        "supervisor",
        1,
    ),
}
_ROOT = Path(__file__).resolve().parents[1]


@dataclasses.dataclass(frozen=True)
class _ConstructorSite:
    path: str
    scope: str
    kind: str
    ordinal: int
    lineno: int
    col_offset: int

    @property
    def identity(self) -> tuple[str, str, str, int]:
        return self.path, self.scope, self.kind, self.ordinal


@dataclasses.dataclass(frozen=True)
class _ConstructorCensus:
    sites: tuple[_ConstructorSite, ...]
    violations: tuple[str, ...]


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _dotted_name(node.value)
        if owner is not None:
            return f"{owner}.{node.attr}"
    return None


def _constructor_bindings(path: str, tree: ast.AST) -> dict[str, str]:
    bindings: dict[str, str] = {}
    module_name = path.removesuffix(".py").replace("/", ".")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                if alias.name != "*":
                    bindings[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", 1)[0]
                bindings[local_name] = alias.name if alias.asname else local_name
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            bindings.setdefault(node.name, f"{module_name}.{node.name}")

    # Cover direct aliases such as ``Supervisor = ExecutiveSupervisor`` without
    # pretending to solve arbitrary runtime data flow.
    for _ in range(2):
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = _dotted_name(node.value) if node.value is not None else None
            if value is None:
                continue
            parts = value.split(".")
            canonical = ".".join((bindings.get(parts[0], parts[0]), *parts[1:]))
            if canonical not in _TARGET_CONSTRUCTORS:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = canonical
    return bindings


def _resolve_constructor(
    node: ast.expr,
    bindings: Mapping[str, str],
) -> tuple[str | None, bool, str | None]:
    raw = _dotted_name(node)
    if raw is None:
        return None, False, None
    parts = raw.split(".")
    is_bound = parts[0] in bindings
    canonical = ".".join((bindings.get(parts[0], parts[0]), *parts[1:]))
    return _TARGET_CONSTRUCTORS.get(canonical), is_bound, raw


def _constructor_census(sources: Mapping[str, str]) -> _ConstructorCensus:
    sites: list[_ConstructorSite] = []
    violations: list[str] = []
    for path in sorted(sources):
        tree = ast.parse(sources[path], filename=path)
        bindings = _constructor_bindings(path, tree)

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.scopes: list[str] = []
                self.ordinals: dict[tuple[str, str], int] = {}

            def _visit_scope(self, node: ast.AST, name: str) -> None:
                self.scopes.append(name)
                self.generic_visit(node)
                self.scopes.pop()

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self._visit_scope(node, node.name)

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                self._visit_scope(node, node.name)

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                self._visit_scope(node, node.name)

            def visit_Call(self, node: ast.Call) -> None:
                kind, is_bound, raw = _resolve_constructor(node.func, bindings)
                if kind is None:
                    if (
                        raw is not None
                        and raw.rsplit(".", 1)[-1]
                        in {"CodexWorkerAdapter", "ExecutiveSupervisor"}
                        and not is_bound
                    ):
                        violations.append(
                            f"{path}:{node.lineno}:unresolved_constructor:{raw}"
                        )
                    self.generic_visit(node)
                    return

                scope = ".".join(self.scopes) or "<module>"
                ordinal_key = (scope, kind)
                ordinal = self.ordinals.get(ordinal_key, 0) + 1
                self.ordinals[ordinal_key] = ordinal
                site = _ConstructorSite(
                    path=path,
                    scope=scope,
                    kind=kind,
                    ordinal=ordinal,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                )
                sites.append(site)

                keyword_names = [keyword.arg for keyword in node.keywords]
                if None in keyword_names:
                    violations.append(f"{path}:{node.lineno}:{kind}:opaque_kwargs")
                if kind == "supervisor":
                    forbidden = sorted(
                        name
                        for name in keyword_names
                        if name in _PROVIDER_OWNED_KEYWORDS
                    )
                    for name in forbidden:
                        violations.append(
                            f"{path}:{node.lineno}:supervisor:provider_keyword:{name}"
                        )
                else:
                    home_count = keyword_names.count("codex_home")
                    if home_count != 1:
                        violations.append(
                            f"{path}:{node.lineno}:adapter:codex_home_count:{home_count}"
                        )
                    forbidden = sorted(
                        name
                        for name in keyword_names
                        if name in _PROVIDER_OWNED_KEYWORDS - {"codex_home"}
                    )
                    for name in forbidden:
                        violations.append(
                            f"{path}:{node.lineno}:adapter:provider_keyword:{name}"
                        )
                self.generic_visit(node)

        Visitor().visit(tree)
    return _ConstructorCensus(tuple(sites), tuple(violations))


def _tracked_production_sources() -> dict[str, str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "control_plane", "scripts"],
        cwd=_ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8").split("\0")
    paths = sorted(path for path in tracked if path.endswith(".py"))
    return {path: (_ROOT / path).read_text(encoding="utf-8") for path in paths}


def _mutate_constructor_site(source: str, site: _ConstructorSite) -> str:
    tree = ast.parse(source, filename=site.path)
    matched = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and node.lineno == site.lineno
            and node.col_offset == site.col_offset
        ):
            matched += 1
            if site.kind == "supervisor":
                node.keywords.append(
                    ast.keyword(
                        arg="codex_home",
                        value=ast.Name(id="restored_provider_home", ctx=ast.Load()),
                    )
                )
            else:
                before = len(node.keywords)
                node.keywords = [
                    keyword for keyword in node.keywords if keyword.arg != "codex_home"
                ]
                assert len(node.keywords) == before - 1
    assert matched == 1
    ast.fix_missing_locations(tree)
    return ast.unparse(tree) + "\n"


class _SyntheticInspector:
    def boot_session_id(self) -> str:
        return "boot-fixture"

    def identity(self, pid: int) -> tuple[str, int]:
        return f"start-{pid}", pid

    def inspect(self, pid: int) -> object:
        return object()


def _binary() -> BinaryAttestation:
    return BinaryAttestation(
        path="/fixture/provider",
        real_path="/fixture/provider",
        version="fixture-1",
        sha256="a" * 64,
        team_identifier=None,
        size=1,
        device=2,
        inode=3,
        mode=0o500,
        uid=501,
        gid=20,
        mtime_ns=4,
    )


def _spec(tmp_path: Path, **changes: object) -> WorkerLaunchSpec:
    values: dict[str, object] = {
        "run_id": "run-1",
        "job_id": "job-1",
        "worker_id": "worker-1",
        "workspace_path": tmp_path / "workspace",
        "run_dir": tmp_path / "run",
        "prompt": "bounded task",
        "result_schema_path": tmp_path / "result.schema.json",
    }
    values.update(changes)
    return WorkerLaunchSpec(**values)  # type: ignore[arg-type]


def test_artifact_limits_have_one_exported_common_policy_source(tmp_path: Path) -> None:
    assert Path(worker_execution_contract.__file__).resolve() == (
        _ROOT / "control_plane" / "worker_execution_contract.py"
    )
    assert Path(codex_worker.__file__).resolve() == (
        _ROOT / "control_plane" / "codex_worker.py"
    )
    defaults = {field.name: field.default for field in dataclasses.fields(WorkerLaunchSpec)}
    contract_tree = ast.parse(
        Path(worker_execution_contract.__file__).read_text(encoding="utf-8")
    )
    codex_tree = ast.parse(Path(codex_worker.__file__).read_text(encoding="utf-8"))

    contract_assignments = {
        target.id
        for node in ast.walk(contract_tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    codex_assignments = {
        target.id
        for node in ast.walk(codex_tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    codex_common_imports = {
        alias.name
        for node in ast.walk(codex_tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "control_plane.worker_execution_contract"
        for alias in node.names
    }

    for name, expected in _ARTIFACT_LIMITS.items():
        assert getattr(worker_execution_contract, name) == expected
        assert name in worker_execution_contract.__all__
        assert name in contract_assignments
        assert defaults[name.lower()] == expected
    assert _ARTIFACT_LIMITS.keys() <= codex_common_imports
    assert _ARTIFACT_LIMITS.keys().isdisjoint(codex_assignments)
    assert {f"_{name}" for name in _ARTIFACT_LIMITS}.isdisjoint(codex_assignments)
    assert _spec(tmp_path).max_artifacts == _ARTIFACT_LIMITS["MAX_ARTIFACTS"]


def test_common_artifact_limit_source_mutation_reaches_defaults_and_adapter_validation(
    tmp_path: Path,
) -> None:
    mutated_root = tmp_path / "mutated-source"
    shutil.copytree(
        _ROOT / "control_plane",
        mutated_root / "control_plane",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    contract_path = mutated_root / "control_plane" / "worker_execution_contract.py"
    tree = ast.parse(contract_path.read_text(encoding="utf-8"))
    replacements = {
        "MAX_ARTIFACTS": 2,
        "MAX_ARTIFACT_BYTES": 64,
        "MAX_ARTIFACT_TOTAL_BYTES": 128,
    }
    changed: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in replacements:
            node.value = ast.Constant(replacements[target.id])
            changed.add(target.id)
    assert changed == set(replacements)
    ast.fix_missing_locations(tree)
    contract_path.write_text(ast.unparse(tree) + "\n", encoding="utf-8")

    runtime_root = tmp_path / "runtime"
    script = r"""
import dataclasses
import sys
from pathlib import Path

source_root = Path(sys.argv[1]).resolve()
runtime_root = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(source_root))

from control_plane import codex_worker as cw
from control_plane import worker_execution_contract as contract

assert Path(contract.__file__).is_relative_to(source_root)
assert Path(cw.__file__).is_relative_to(source_root)
expected = (2, 64, 128)
assert (
    contract.MAX_ARTIFACTS,
    contract.MAX_ARTIFACT_BYTES,
    contract.MAX_ARTIFACT_TOTAL_BYTES,
) == expected

workspace = runtime_root / "workspace"
workspace.mkdir(parents=True, mode=0o700)
cw._validate_project_configuration = lambda _workspace: None
cw._git_snapshot = lambda _workspace, require_clean: cw._GitSnapshot("a" * 40, b"")
adapter = object.__new__(cw.CodexWorkerAdapter)
adapter._runs = {}
adapter._validate_isolation_manifest = lambda *args, **kwargs: None

def spec(label, **changes):
    run_dir = runtime_root / f"run-{label}"
    run_dir.mkdir(parents=True, mode=0o700)
    schema = run_dir / "result.schema.json"
    schema.write_text("{}", encoding="utf-8")
    values = {
        "run_id": f"run-{label}",
        "job_id": f"job-{label}",
        "worker_id": "worker-1",
        "workspace_path": workspace,
        "run_dir": run_dir,
        "prompt": "bounded task",
        "result_schema_path": schema,
    }
    values.update(changes)
    return contract.WorkerLaunchSpec(**values)

default = spec("default")
assert (default.max_artifacts, default.max_artifact_bytes, default.max_artifact_total_bytes) == expected
adapter._validate_spec(default, codex_home=runtime_root / "provider-home")

for label, field, value, message in (
    ("count", "max_artifacts", 3, "max_artifacts exceeds adapter ceiling"),
    ("single", "max_artifact_bytes", 65, "max_artifact_bytes exceeds adapter ceiling"),
    ("total", "max_artifact_total_bytes", 129, "max_artifact_total_bytes exceeds adapter ceiling"),
):
    candidate = spec(label, **{field: value})
    try:
        adapter._validate_spec(candidate, codex_home=runtime_root / "provider-home")
    except cw.LaunchValidationError as exc:
        assert str(exc) == message
    else:
        raise AssertionError(f"mutated common {field} did not reach Codex validation")
"""
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-c",
            script,
            os.fspath(mutated_root),
            os.fspath(runtime_root),
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_common_contract_instantiates_every_execution_type(tmp_path: Path) -> None:
    artifact = ArtifactReceipt(path="proof.json", sha256="b" * 64, size=7)
    spec = _spec(tmp_path)
    process = WorkerProcessRef(
        run_id=spec.run_id,
        pid=41,
        pgid=41,
        process_start_identity="start-41",
        boot_session_id="boot-fixture",
        launch_nonce="nonce-fixture",
        provider_session_id=None,
        stdout_path=str(tmp_path / "stdout.jsonl"),
        stderr_path=str(tmp_path / "stderr.log"),
        result_path=str(tmp_path / "result.json"),
        started_at="2026-09-03T00:00:00+00:00",
        binary=_binary(),
        base_sha="c" * 40,
    )
    result = WorkerResult(
        job_id=spec.job_id,
        run_id=spec.run_id,
        worker_id=spec.worker_id,
        status=WorkerRunStatus.SUCCEEDED,
        structured_output={"status": "COMPLETED"},
        artifact_manifest=(artifact,),
        git_manifest={"base_sha": "c" * 40, "paths": ["proof.json"]},
        usage={"input_tokens": 1, "output_tokens": 2},
        provider_session_id="provider-observation",
        exit_code=0,
        started_at=process.started_at,
        finished_at="2026-09-03T00:00:01+00:00",
        error=None,
    )
    collection = CollectionReceipt(
        process_ref=process,
        result=result,
        stdout_sha256="d" * 64,
        stderr_sha256="e" * 64,
        result_sha256="f" * 64,
    )
    cancel = CancelReceipt(
        run_id=spec.run_id,
        reason="operator requested",
        signal_sent=True,
        escalated_to_sigkill=False,
        already_exited=False,
        finished_at="2026-09-03T00:00:02+00:00",
    )
    validation = ValidationReceipt(
        argv=("/usr/bin/true",),
        exit_code=0,
        stdout_sha256="0" * 64,
        stdout_size=0,
        stderr_sha256="0" * 64,
        stderr_size=0,
        timed_out=False,
        error=None,
    )

    assert WORKER_EXECUTION_CONTRACT_VERSION == "mastermind.worker_execution_contract/v1"
    assert collection.result.artifact_manifest == (artifact,)
    assert cancel.run_id == spec.run_id
    assert validation.argv == ("/usr/bin/true",)
    assert isinstance(_SyntheticInspector(), ProcessInspector)


def test_launch_contract_has_exact_provider_neutral_fields(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    fields = {item.name for item in dataclasses.fields(spec)}

    assert fields == _LAUNCH_FIELDS
    for forbidden in (
        "codex_home",
        "provider_home",
        "claude_home",
        "api_key",
        "credential_path",
        "token",
        "provider_session_id",
    ):
        assert forbidden not in fields
        assert not hasattr(spec, forbidden)


def test_common_mapping_inputs_are_copied_and_deeply_immutable(tmp_path: Path) -> None:
    isolation = {"roots": {"allowed": ["workspace"]}}
    canary = {"passed": True, "checks": ["no-secret"]}
    spec = _spec(
        tmp_path,
        isolation_manifest=isolation,
        secret_canary_verdict=canary,
    )
    result = WorkerResult(
        job_id="job-1",
        run_id="run-1",
        worker_id="worker-1",
        status=WorkerRunStatus.SUCCEEDED,
        structured_output={"nested": {"values": [1, 2]}},
        artifact_manifest=(),
        git_manifest={"paths": ["proof.json"]},
        usage={"tokens": {"input": 1}},
        provider_session_id=None,
        exit_code=0,
        started_at="2026-09-03T00:00:00+00:00",
        finished_at="2026-09-03T00:00:01+00:00",
        error=None,
    )

    isolation["roots"]["allowed"].append("mutated")
    canary["checks"].append("mutated")
    assert spec.isolation_manifest["roots"]["allowed"] == ("workspace",)
    assert spec.secret_canary_verdict["checks"] == ("no-secret",)
    assert result.structured_output is not None
    assert result.structured_output["nested"]["values"] == (1, 2)
    assert result.git_manifest["paths"] == ("proof.json",)

    with pytest.raises(TypeError):
        spec.isolation_manifest["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        spec.isolation_manifest["roots"]["new"] = "value"  # type: ignore[index]
    with pytest.raises((AttributeError, TypeError)):
        result.git_manifest["paths"].append("other.json")

    isolation_snapshot = spec.isolation_manifest
    with pytest.raises(TypeError):
        isolation_snapshot |= {"new": "value"}
    assert "new" not in spec.isolation_manifest

    with pytest.raises(TypeError):
        dict.__setitem__(  # type: ignore[arg-type]
            spec.secret_canary_verdict,
            "passed",
            False,
        )
    assert spec.secret_canary_verdict["passed"] is True


def test_validation_receipt_copies_mutable_argv_input() -> None:
    argv = ["/usr/bin/true"]
    receipt = ValidationReceipt(
        argv=argv,  # type: ignore[arg-type]
        exit_code=0,
        stdout_sha256="0" * 64,
        stdout_size=0,
        stderr_sha256="0" * 64,
        stderr_size=0,
        timed_out=False,
        error=None,
    )

    argv.append("--mutated")

    assert receipt.argv == ("/usr/bin/true",)


def test_codex_compatibility_names_are_the_common_types() -> None:
    aliases = {
        "ArtifactReceipt": ArtifactReceipt,
        "BinaryAttestation": BinaryAttestation,
        "CancelReceipt": CancelReceipt,
        "CollectionReceipt": CollectionReceipt,
        "LaunchSpec": WorkerLaunchSpec,
        "ProcessRef": WorkerProcessRef,
        "ValidationReceipt": ValidationReceipt,
        "WorkerResult": WorkerResult,
        "WorkerRunStatus": WorkerRunStatus,
    }

    for name, common_type in aliases.items():
        exported = getattr(codex_worker, name)
        assert exported is common_type
        assert exported.__module__ == "control_plane.worker_execution_contract"


def test_common_consumers_do_not_import_moved_types_from_codex() -> None:
    for module in (worker_adapter, executive_supervisor, executive_worker_broker):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_from_codex = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module == "control_plane.codex_worker"
            for alias in node.names
        }
        assert not imported_from_codex.intersection(_MOVED_NAMES)


def test_supervisor_never_owns_or_injects_a_provider_home() -> None:
    tree = ast.parse(Path(executive_supervisor.__file__).read_text(encoding="utf-8"))
    owned_home = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr in {"codex_home", "claude_home", "provider_home"}
    ]
    injected_home = [
        keyword
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg in {"codex_home", "claude_home", "provider_home"}
    ]

    assert owned_home == []
    assert injected_home == []


def test_serialized_common_launch_request_has_no_provider_owned_fields(
    tmp_path: Path,
) -> None:
    serialized = executive_worker_broker._launch_spec_to_json(_spec(tmp_path))

    assert {
        "codex_home",
        "provider_home",
        "claude_home",
        "credential_path",
        "api_key",
        "token",
        "provider_session_id",
    }.isdisjoint(serialized)


def test_phase1c_worker_composes_exactly_one_policy_owned_codex_home() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "executive_os_phase1c_worker.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "CodexWorkerAdapter")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "CodexWorkerAdapter"
            )
        )
    ]

    assert len(calls) == 1
    home_keywords = [
        keyword
        for keyword in calls[0].keywords
        if keyword.arg in {"codex_home", "provider_home", "claude_home"}
    ]
    assert len(home_keywords) == 1
    assert home_keywords[0].arg == "codex_home"
    assert ast.dump(home_keywords[0].value, include_attributes=False) == (
        "Attribute(value=Name(id='policy', ctx=Load()), "
        "attr='provider_home', ctx=Load())"
    )


def test_constructor_source_law_covers_calibrated_sites_and_kills_each_mutant() -> None:
    sources = _tracked_production_sources()
    census = _constructor_census(sources)

    assert census.violations == ()
    assert {site.identity for site in census.sites} == _EXPECTED_CONSTRUCTOR_SITES
    assert sum(site.kind == "supervisor" for site in census.sites) == 6
    assert sum(site.kind == "adapter" for site in census.sites) == 4

    killed: list[tuple[str, str, str, int]] = []
    for site in census.sites:
        mutant = _constructor_census(
            {site.path: _mutate_constructor_site(sources[site.path], site)}
        )
        if site.kind == "supervisor":
            expected = ":supervisor:provider_keyword:codex_home"
        else:
            expected = ":adapter:codex_home_count:0"
        assert len(mutant.violations) == 1
        assert expected in mutant.violations[0]
        killed.append(site.identity)
    assert len(killed) == 10


def test_constructor_source_law_preserves_alias_qualified_opaque_and_foreign_controls(
) -> None:
    controls = {
        "aliased-supervisor": (
            "from control_plane.executive_supervisor import ExecutiveSupervisor as Sup\n"
            "Sup(runtime, adapter, codex_home=home)\n",
            ":supervisor:provider_keyword:codex_home",
        ),
        "qualified-missing-home-adapter": (
            "import control_plane.codex_worker as cw\n"
            "cw.CodexWorkerAdapter('/provider')\n",
            ":adapter:codex_home_count:0",
        ),
        "opaque-supervisor": (
            "from control_plane.executive_supervisor import ExecutiveSupervisor\n"
            "ExecutiveSupervisor(runtime, adapter, **options)\n",
            ":supervisor:opaque_kwargs",
        ),
        "opaque-adapter": (
            "from control_plane.codex_worker import CodexWorkerAdapter\n"
            "CodexWorkerAdapter('/provider', **options)\n",
            ":adapter:opaque_kwargs",
        ),
    }
    observed: list[str] = []
    for label, (source, expected) in controls.items():
        census = _constructor_census({f"scripts/{label}.py": source})
        assert len(census.sites) == 1
        assert any(expected in violation for violation in census.violations)
        observed.append(label)

    foreign = _constructor_census(
        {
            "scripts/foreign-adapter-home.py": (
                "from foreign_workers import CodexWorkerAdapter\n"
                "CodexWorkerAdapter('/provider', codex_home=foreign_home)\n"
            )
        }
    )
    assert foreign.sites == ()
    assert foreign.violations == ()
    observed.append("foreign-adapter-home")
    assert len(observed) == 5
