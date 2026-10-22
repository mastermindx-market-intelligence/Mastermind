"""Remote process coordinates remain remote; only the prompt is Control-local."""
import dataclasses
from pathlib import Path

import pytest

from control_plane.worker_execution_contract import (
    WorkerLaunchSpec, WorkerProcessRef, WorkerRecoveryBinding,
    WorkerRecoveryContractError, WORKER_REMOTE_RECOVERY_BINDING_VERSION,
)
from test_worker_execution_contract import _binary


def fixture(tmp_path):
    local = tmp_path / "control" / "run-1" / "input"
    local.mkdir(parents=True)
    source = tmp_path / "source"
    source.mkdir()
    prompt = local / "worker-prompt.txt"
    prompt.write_text("bounded remote task")
    prompt.chmod(0o600)
    remote = Path("/srv/fabric/runs/run-1")
    spec = WorkerLaunchSpec(
        run_id="run-1", job_id="job-1", worker_id="worker-1",
        workspace_path=Path("/srv/fabric/workspaces/job-1"), run_dir=remote,
        prompt=prompt.read_text(), result_schema_path=remote / "input/result.schema.json",
        authorities=("READ",), expected_base_sha="c" * 40,
    )
    ref = WorkerProcessRef(
        run_id="run-1", pid=41, pgid=41, process_start_identity="start-41",
        boot_session_id="remote-boot", launch_nonce="nonce-fixture",
        provider_session_id=None, stdout_path=str(remote / "logs/stdout"),
        stderr_path=str(remote / "logs/stderr"), result_path=str(remote / "output/result.json"),
        started_at="2026-10-12T00:00:00Z", binary=_binary(), base_sha="c" * 40,
        session_id=41, effective_uid=1000, real_uid=1000, effective_gid=1000, real_gid=1000,
    )
    context = dict(input_root=str(local), source_workspace=str(source))
    return spec, ref, prompt, context


def bind(tmp_path):
    spec, ref, prompt, context = fixture(tmp_path)
    return WorkerRecoveryBinding.bind(adapter_id="attended-fabric", spec=spec,
        process_ref=ref, prompt_path=prompt, control_recovery=context), spec


def test_real_remote_output_paths_round_trip_without_local_remote_directory(tmp_path):
    binding, spec = bind(tmp_path)
    assert binding.schema_version == WORKER_REMOTE_RECOVERY_BINDING_VERSION
    restored = WorkerRecoveryBinding.from_dict(binding.to_dict()).validate_wire()
    assert restored.recover_launch_spec() == spec
    assert restored.process_ref.stdout_path.startswith("/srv/fabric/runs/")
    assert restored.control_recovery["input_root"].startswith(str(tmp_path))


@pytest.mark.parametrize("field", ["input_root", "source_workspace"])
def test_control_coordinates_cannot_change_without_original_context_digest(tmp_path, field):
    binding, _ = bind(tmp_path)
    value = binding.to_dict()
    value["launch_spec"]["control_recovery"][field] = "/foreign/control"
    with pytest.raises(WorkerRecoveryContractError, match="context digest"):
        WorkerRecoveryBinding.from_dict(value)


@pytest.mark.parametrize("field", ["stdout_path", "stderr_path", "result_path"])
def test_v2_keeps_remote_output_containment(tmp_path, field):
    binding, _ = bind(tmp_path)
    value = binding.to_dict()
    value["process_ref"][field] = str(tmp_path / "local-or-foreign-output")
    with pytest.raises(WorkerRecoveryContractError):
        WorkerRecoveryBinding.from_dict(value).validate_wire()


def test_v2_keeps_remote_schema_containment(tmp_path):
    spec, ref, prompt, context = fixture(tmp_path)
    spec = dataclasses.replace(spec, result_schema_path=prompt.parent / "schema.json")
    binding = WorkerRecoveryBinding.bind(adapter_id="attended-fabric", spec=spec,
        process_ref=ref, prompt_path=prompt, control_recovery=context)
    with pytest.raises(WorkerRecoveryContractError):
        binding.validate_wire()


def test_v1_cannot_relabel_remote_or_opt_in_implicitly(tmp_path):
    spec, ref, prompt, context = fixture(tmp_path)
    with pytest.raises(WorkerRecoveryContractError):
        WorkerRecoveryBinding.bind(adapter_id="attended-fabric", spec=spec,
                                  process_ref=ref, prompt_path=prompt)
    with pytest.raises(WorkerRecoveryContractError, match="Fabric owner"):
        WorkerRecoveryBinding.bind(adapter_id="codex-cli", spec=spec,
            process_ref=ref, prompt_path=prompt, control_recovery=context)


def test_private_prompt_and_original_bytes_still_required(tmp_path):
    binding, _ = bind(tmp_path)
    prompt = Path(binding.launch_spec["prompt_path"])
    prompt.write_text("changed")
    with pytest.raises(WorkerRecoveryContractError, match="digest"):
        binding.recover_launch_spec()
    prompt.chmod(0o644)
    with pytest.raises(WorkerRecoveryContractError, match="private"):
        binding.recover_launch_spec()


@pytest.mark.parametrize("bad", [
    {"input_root": "relative", "source_workspace": "/source"},
    {"input_root": "/a/../b", "source_workspace": "/source"},
    {"input_root": "/a", "source_workspace": "/source", "grant": "invented"},
])
def test_context_is_closed_and_canonical(tmp_path, bad):
    spec, ref, prompt, _ = fixture(tmp_path)
    with pytest.raises(WorkerRecoveryContractError):
        WorkerRecoveryBinding.bind(adapter_id="attended-fabric", spec=spec,
            process_ref=ref, prompt_path=prompt, control_recovery=bad)
