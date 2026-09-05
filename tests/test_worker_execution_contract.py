"""Provider-neutral worker contract and dependency-boundary proofs."""
from __future__ import annotations

import ast
import dataclasses
from collections.abc import Mapping
from pathlib import Path

import pytest

from control_plane import codex_worker
from control_plane import executive_supervisor
from control_plane import executive_worker_broker
from control_plane import worker_adapter
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
