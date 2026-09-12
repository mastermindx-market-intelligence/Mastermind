from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github/workflows/codeintel-experiment-bundle.yml"


def _source() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def _dispatch_input_names(source: str) -> set[str]:
    lines = source.splitlines()
    start = next(index for index, line in enumerate(lines) if line == "    inputs:")
    names: set[str] = set()
    for line in lines[start + 1 :]:
        if line and not line.startswith("      "):
            break
        match = re.fullmatch(r"      ([a-z_]+):", line)
        if match:
            names.add(match.group(1))
    return names


def test_workflow_is_manual_z0_only_with_exact_closed_inputs() -> None:
    source = _source()
    assert re.search(r"(?m)^on:\n  workflow_dispatch:\n    inputs:$", source)
    assert _dispatch_input_names(source) == {
        "consumer_sha",
        "consumer_tree_sha",
        "operation_key",
    }
    assert "pull_request:" not in source
    assert "push:" not in source
    assert "schedule:" not in source
    assert "mode:" not in source
    assert "C0" not in source
    assert "Z0" in source


def test_dispatch_values_enter_only_environment_not_shell_source() -> None:
    source = _source()
    in_run_block = False
    run_indent = 0
    for line in source.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if re.match(r"run:\s*[>|]?-?$", stripped):
            in_run_block = True
            run_indent = indent
            continue
        if in_run_block and stripped and indent <= run_indent:
            in_run_block = False
        if in_run_block:
            assert "${{ inputs." not in line

    assert "INPUT_CONSUMER_SHA: ${{ inputs.consumer_sha }}" in source
    assert "INPUT_CONSUMER_TREE_SHA: ${{ inputs.consumer_tree_sha }}" in source
    assert "INPUT_OPERATION_KEY: ${{ inputs.operation_key }}" in source
    assert "eval " not in source
    assert 'bash -c "${{' not in source


def test_workflow_pins_actions_and_runner_and_uses_no_cache() -> None:
    source = _source()
    uses = re.findall(r"(?m)^\s+- uses: ([^\s#]+)", source)
    assert uses
    assert set(uses) == {
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    }
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", value) for value in uses)
    assert "runs-on: ubuntu-24.04" in source
    assert "ubuntu-latest" not in source
    assert "actions/cache" not in source
    assert "setup-go" not in source
    assert "setup-python" not in source
    assert "persist-credentials: false" in source


def test_workflow_fails_closed_on_non_master_rerun_or_prior_ambiguous_effect() -> None:
    source = _source()
    assert "refs/heads/master" in source
    assert "GITHUB_RUN_ATTEMPT" in source
    assert "reconcile-prior-runs" in source
    assert "EFFECT_UNKNOWN" in source
    assert "cancel-in-progress: false" in source
    assert "continue-on-error" not in source
    assert "workflow_dispatch" not in "\n".join(
        line for line in source.splitlines() if "on:" not in line
    ).replace("  workflow_dispatch:", "")


def test_phase_p_is_the_only_acquisition_and_build_boundary() -> None:
    source = _source()
    assert "phase-p:" in source
    assert "phase-e:" in source
    assert "phase_e" not in source  # keep job and CLI spelling canonical
    assert "phase-p" in source
    assert "https://go.dev" not in source  # URLs come only from the validated lock
    assert "sourcegraph/zoekt" not in source  # repository comes only from the lock
    assert "GOTOOLCHAIN=local" in source
    assert "CGO_ENABLED=0" in source
    assert "GOPROXY=https://proxy.golang.org" in source
    assert "GOSUMDB=sum.golang.org" in source
    assert "npx " not in source
    assert "pip install" not in source
    assert "go install" not in source


def test_phase_p_entrypoints_scrub_ambient_environment() -> None:
    source = _source()
    phase_p = source[source.index("  phase-p:") : source.index("  phase-e:")]
    assert phase_p.count("/usr/bin/env -i") >= 3
    assert 'GH_TOKEN="$GH_TOKEN"' in phase_p
    assert "PATH=/usr/bin:/bin" in phase_p
    assert "LANG=C" in phase_p
    assert "LC_ALL=C" in phase_p
    assert phase_p.count('RUNNER_ENVIRONMENT="${RUNNER_ENVIRONMENT:-UNAVAILABLE}"') == 2
    assert phase_p.count('GITHUB_ACTIONS="${GITHUB_ACTIONS:-false}"') == 2


def test_host_userns_policy_window_is_exact_and_precedes_each_boundary() -> None:
    source = _source()
    assert source.count("RUNNER_ENVIRONMENT: ${{ runner.environment }}") == 3
    assert source.count('GITHUB_ACTIONS: "true"') == 3
    assert source.count('RUNNER_TEMP="$RUNNER_TEMP"') == 4
    assert source.count('ImageOS="${ImageOS:-UNAVAILABLE}"') == 4
    assert "probe-phase-e-hosted" in source
    assert "run-phase-e-hosted" in source
    assert source.index("reconcile-prior-runs") < source.index(
        "\n              phase-p \\"
    )
    assert source.index("probe-phase-e-hosted") < source.index("run-phase-e-hosted")
    assert "/usr/bin/sudo" not in source
    assert "/usr/sbin/sysctl" not in source


def test_phase_e_mechanically_seals_network_before_fixed_consumer() -> None:
    source = _source()
    probe = source.index("probe-phase-e-hosted")
    consumer = source.index("run-phase-e-hosted")
    assert probe < consumer
    assert "NETWORK_SEAL_UNAVAILABLE" in source
    assert "ref: ${{ inputs.consumer_sha }}" in source
    assert "refs/pull/" not in source
    assert "switch -C" not in source
    assert "serena" not in source.lower()
    assert "pyright" not in source.lower()
    assert "typescript" not in source.lower()
    assert "ctags" not in source.lower()


def test_consumer_receives_no_actions_credentials_or_arbitrary_argv() -> None:
    source = _source()
    assert "env -i" in source
    assert "GITHUB_TOKEN" not in source[source.index("probe-phase-e-hosted") :]
    assert "ACTIONS_RUNTIME_TOKEN" not in source
    assert "--command" not in source
    assert "--module" not in source
    assert "--repository" not in source
    assert "--url" not in source
    assert "--runner" not in _dispatch_input_names(source)


def test_artifacts_are_content_addressed_and_receipt_upload_is_not_a_retry() -> None:
    source = _source()
    assert "bundle_sha256" in source
    assert "codeintel-z0-${{ steps.prepare.outputs.bundle_sha256 }}" in source
    assert "semantic-receipt.json" in source
    assert "if: always()" in source
    assert "compression-level: 0" in source
    assert "overwrite: true" not in source
    assert "retry" not in source.lower()


def test_semantic_receipt_artifact_has_exactly_one_member() -> None:
    source = _source()
    fixed_name = (
        "name: codeintel-z0-operation-"
        "9aae1af9ef430044fbba77ae0f87cf12d4425c75f577b4427c09ae66cec11bf4"
    )
    starts = [match.start() for match in re.finditer(re.escape(fixed_name), source)]
    assert len(starts) == 3
    for start in starts:
        end = source.find("\n      - ", start)
        block = source[start:] if end == -1 else source[start:end]
        assert "semantic-receipt.json" in block
        assert "z0-result.json" not in block
        assert "z0-report.md" not in block
    assert (
        "name: codeintel-z0-result-${{ needs.phase-p.outputs.bundle_sha256 }}" in source
    )
    result_start = source.index("name: Upload bounded Z0 result files")
    result_block = source[result_start:]
    assert "if: steps.sealed.outcome == 'success'" in result_block
    assert "id: sealed" in source


def test_workflow_permissions_and_timeouts_are_bounded() -> None:
    source = _source()
    assert re.search(r"permissions:\n  actions: read\n  contents: read", source)
    assert "timeout-minutes: 45" in source
    assert "timeout-minutes: 20" in source
    assert "max-parallel: 1" not in source  # there is no matrix/fan-out lane
    assert "cancel-in-progress: false" in source


def test_every_workflow_shell_block_parses_as_bash() -> None:
    document = yaml.load(_source(), Loader=yaml.BaseLoader)
    runs = [
        step["run"]
        for job in document["jobs"].values()
        for step in job["steps"]
        if "run" in step
    ]
    assert runs
    for script in runs:
        completed = subprocess.run(
            ["/bin/bash", "-n"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
