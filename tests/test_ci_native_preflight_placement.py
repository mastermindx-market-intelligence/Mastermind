"""Native admission F4 placement: unchanged gate, independent required runner."""
import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard as fan
from scripts import ci_pytest as cip

ROOT = Path(__file__).resolve().parents[1]
NAME = "Verify native application admission and dispatch custody"
JOB_NAME = "Native application admission gates"


def workflow():
    return yaml.load((ROOT / ".github/workflows/ci.yml").read_text(),
                     Loader=cip._WorkflowYAMLLoader)


def step(job, name):
    matches = [s for s in job["steps"] if s.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def contract(value):
    fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))
    shards = value["jobs"]["pytest_shards"]
    job = value["jobs"]["native_admission"]
    native = step(job, NAME)
    assert shards["strategy"]["matrix"]["index"] == list(range(6))
    assert shards["strategy"]["max-parallel"] == 6
    assert shards["strategy"]["fail-fast"] is False
    assert job["name"] == JOB_NAME
    assert job["if"] == fan._REQUIRED_SHARDS_IF
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    assert native.get("if") is None
    assert not [s for s in shards["steps"] if s.get("name") == NAME]
    prerequisites = [s for s in job["steps"]
                     if s.get("uses") in ("actions/setup-node@v4", "actions/setup-python@v5")]
    prerequisites += [step(job, "Install project"),
                      step(job, "Prepare fixed test diagnostics")]
    assert len(prerequisites) == 4
    assert all(s.get("if") is None and job["steps"].index(s) < job["steps"].index(native)
               for s in prerequisites)
    evidence = json.loads((ROOT / "ci/shard_timings/42545600621-native-forward.json").read_text())
    assert hashlib.sha256(native["run"].encode()).hexdigest() == evidence["unchanged_step_body_sha256"]
    assert "$GITHUB_ENV" not in native["run"] and "$GITHUB_OUTPUT" not in native["run"]
    assert 'NATIVE_ROLLOUT_TEST_ROOT="$native_rollout_test_root" python -m pytest' in native["run"]
    assert "trap 'rm -rf \"$native_rollout_test_root\"' EXIT" in native["run"]
    upload = step(job, "Upload native admission diagnostics")
    assert job["steps"].index(upload) > job["steps"].index(native)
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "native-admission-fixed-diagnostics"
    assert upload["with"]["path"].splitlines() == [
        "${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-unit/ci-fixed-diagnostics.json",
        "${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/native-admission-rollout/ci-fixed-diagnostics.json",
    ]
    assert job["timeout-minutes"] == 45
    assert step(shards, "Run repository test shard")["timeout-minutes"] == 45


def test_native_admission_is_required_once_in_parallel_with_all_shards():
    contract(workflow())


@pytest.mark.parametrize("condition", [
    None, True, False, "matrix.index == 5", "matrix.index == 0",
    "always()", "${{ steps.previous_ci.outputs.reuse != 'true' }}",
])
def test_native_job_cannot_be_omitted_rerouted_or_reuse_gated(condition):
    value = workflow()
    if condition is None:
        value["jobs"]["native_admission"].pop("if")
    else:
        value["jobs"]["native_admission"]["if"] = condition
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "after-upload", "skip", "no-fail"])
def test_native_body_must_execute_once_with_no_bypass(mutation):
    value = workflow()
    job = value["jobs"]["native_admission"]
    native = step(job, NAME)
    if mutation == "missing":
        job["steps"].remove(native)
    elif mutation == "duplicate":
        job["steps"].append(copy.deepcopy(native))
    elif mutation == "after-upload":
        job["steps"].remove(native)
        job["steps"].append(native)
    elif mutation == "skip":
        native["if"] = "false"
    else:
        native["continue-on-error"] = True
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))


def test_native_cannot_be_duplicated_on_shard_five():
    value = workflow()
    value["jobs"]["pytest_shards"]["steps"].append(
        copy.deepcopy(step(value["jobs"]["native_admission"], NAME)))
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))


def test_native_body_and_diagnostic_artifacts_cannot_shrink():
    value = workflow()
    native = step(value["jobs"]["native_admission"], NAME)
    native["run"] = native["run"].replace("test_qwen_account_eligibility.py", "test_omitted.py")
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))
    value = workflow()
    upload = step(value["jobs"]["native_admission"], "Upload native admission diagnostics")
    upload["with"]["path"] = "missing.json"
    with pytest.raises(cip.PolicyError):
        fan.validate_parallel_workflow(yaml.safe_dump(value, sort_keys=False))


def test_measured_placement_does_not_claim_whole_run_speedup():
    value = json.loads((ROOT / "ci/shard_timings/42545600621-native-forward.json").read_text())
    assert value["observed_native_step_seconds"] == 754
    assert value["observed_unit_envelope_seconds"] == 38.937942
    assert value["observed_rollout_envelope_seconds"] == 713.602082
    assert value["target_worker"] == 5
    assert value["whole_run_speedup_measured"] is False
