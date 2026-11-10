"""RWE uses the existing six-hosted cover; a shard cannot prove the full gate."""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from scripts import ci_parallel_shard, ci_pytest, rwe_env as rwe


ROOT = Path(__file__).resolve().parents[1]


def _arguments(tmp_path, monkeypatch, *, index=2):
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    monkeypatch.setattr(rwe, "_venv_python", lambda env: Path(sys.executable))
    monkeypatch.setattr(rwe, "require_supported_interpreter", lambda executable: None)
    monkeypatch.setattr(rwe, "vendor_present", lambda root: True)
    return argparse.Namespace(root=str(ROOT), env=str(env_dir), subset=None,
                              shard_index=index), env_dir


def test_real_canonical_shard_streams_and_records_only_its_scope(tmp_path, monkeypatch):
    project = tmp_path / "project"
    for directory in ("scripts", "tests", "ci", ".github/workflows"):
        (project / directory).mkdir(parents=True)
    for name in ("ci_parallel_shard.py", "ci_pytest.py", "ci_pytest_timing.py"):
        shutil.copyfile(ROOT / "scripts" / name, project / "scripts" / name)
    (project / "scripts/__init__.py").touch()
    (project / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (project / "ci/pytest_exclusions.toml").write_text("version = 1\nexclude = []\n")
    shutil.copyfile(ROOT / ".github/workflows/ci.yml", project / ".github/workflows/ci.yml")
    # Ask the incumbent planner for one path per bucket; do not copy its
    # placement function or create an alternative exclusion policy.
    candidates = tuple(f"tests/test_shadow_fixture_{i}.py" for i in range(60))
    paths = tuple(group[0] for group in ci_pytest.partition_modules(candidates, jobs=6))
    release = tmp_path / "release"
    for index, path in enumerate(paths):
        body = "def test_ok(): assert True\n"
        if index == 2:
            body = ("import pathlib, time\ndef test_original_shard():\n"
                    f"    while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.01)\n"
                    "    assert False, 'actual canonical shard failure'\n")
        (project / path).write_text(body)
    _, selected, digest = ci_parallel_shard.shard_plan(project, jobs=6, index=2)
    assert selected == (paths[2],)
    args, env_dir = _arguments(tmp_path, monkeypatch)
    args.root = str(project)
    monkeypatch.setenv("PYTHONPATH", str(project))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    progress = threading.Event()

    class Observed(io.StringIO):
        def write(self, text):
            count = super().write(text)
            if '"event": "start"' in self.getvalue() and paths[2] in self.getvalue():
                progress.set()
            return count

    output, errors = Observed(), io.StringIO()
    monkeypatch.setattr(rwe.sys, "stdout", output)
    monkeypatch.setattr(rwe.sys, "stderr", errors)
    codes, exceptions = [], []

    def run():
        try:
            codes.append(rwe.cmd_gate(args))
        except BaseException as exc:
            exceptions.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        live = progress.wait(8)
        no_early_receipt = not (env_dir / rwe.RECEIPT_FILENAME).exists()
    finally:
        release.write_text("finish")
        worker.join(8)
    assert not worker.is_alive()
    assert exceptions == []
    assert live and no_early_receipt
    assert codes == [1]
    assert "actual canonical shard failure" in output.getvalue()
    receipt = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())
    assert "gate" not in receipt["proof"]
    shard = receipt["proof"]["shard"]
    assert shard["exit"] == 1
    assert shard["scope"] == "canonical_shard"
    assert (shard["index"], shard["jobs"], shard["selected_modules"]) == (2, 6, 1)
    assert shard["discovered"] == 6
    assert shard["included_sha256"] == digest
    assert shard["plan_observation"] == "matched"
    assert shard["command"] == (
        "<env>/bin/python -u -m scripts.ci_parallel_shard --jobs 6 --index 2"
    )


RECORD = "parallel_shard=3/6 modules=1 included_sha256=" + "a" * 64


@pytest.mark.parametrize("record", [
    "", RECORD.replace("3/6", "2/6"), RECORD.replace("3/6", "3/5"),
    RECORD + "\n" + RECORD, RECORD.replace("a" * 64, "bad"),
    RECORD.replace("modules=1", "modules=0"), RECORD.replace("modules=1", "modules=7"),
])
def test_zero_child_exit_without_one_matching_plan_cannot_qualify(tmp_path, monkeypatch, record):
    args, env_dir = _arguments(tmp_path, monkeypatch)
    monkeypatch.setattr(rwe, "_stream_gate", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, "discovered=6 excluded=0 running=6\n" + record + "\n", "",
    ))
    assert rwe.cmd_gate(args) == 2
    proof = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())["proof"]
    assert "gate" not in proof
    assert proof["shard"]["exit"] == 0  # Preserve the original process observation.
    assert proof["shard"]["plan_observation"] == "invalid"
    assert proof["shard"]["included_sha256"] is None


@pytest.mark.parametrize("exit_code", [0, 7])
def test_completed_shard_preserves_exit_and_never_becomes_full_gate(tmp_path, monkeypatch, exit_code):
    args, env_dir = _arguments(tmp_path, monkeypatch)
    monkeypatch.setattr(rwe, "_stream_gate", lambda argv, **kw: subprocess.CompletedProcess(
        argv, exit_code, "discovered=6 excluded=0 running=6\n" + RECORD + "\n", "",
    ))
    assert rwe.cmd_gate(args) == exit_code
    proof = json.loads((env_dir / rwe.RECEIPT_FILENAME).read_text())["proof"]
    assert "gate" not in proof
    assert proof["shard"]["exit"] == exit_code
    assert proof["shard"]["plan_observation"] == "matched"


@pytest.mark.parametrize("index,subset", [(True, None), (-1, None), (6, None), ("2", None), (2, "case.py")])
def test_invalid_shard_scope_refuses_before_interpreter_or_child(tmp_path, monkeypatch, index, subset):
    args = argparse.Namespace(root=str(ROOT), env=str(tmp_path), subset=subset, shard_index=index)
    monkeypatch.setattr(rwe, "_venv_python", lambda env: pytest.fail("unexpected interpreter probe"))
    monkeypatch.setattr(rwe, "_stream_gate", lambda *a, **k: pytest.fail("unexpected gate child"))
    assert rwe.cmd_gate(args) == 2


def _workflow():
    return yaml.load((ROOT / ".github/workflows/rwe-shadow.yml").read_text(),
                     Loader=ci_pytest._WorkflowYAMLLoader)


def test_shadow_uses_six_hosted_indices_and_one_common_lock_owner():
    document = _workflow()
    assert document["permissions"] == {"contents": "read"}
    jobs = document["jobs"]
    assert set(jobs) == {"prepare-lock", "shadow-shards", "shadow-gate"}
    prepare, shards, final = (jobs[name] for name in ("prepare-lock", "shadow-shards", "shadow-gate"))
    assert shards["needs"] == ["prepare-lock"]
    assert shards["strategy"] == {"fail-fast": False, "max-parallel": 6,
                                   "matrix": {"index": list(range(6))}}
    assert shards["runs-on"] == "ubuntu-24.04"
    assert prepare["runs-on"] == final["runs-on"] == "ubuntu-latest"
    macro_checkout = next(step["with"] for step in shards["steps"]
                          if step.get("with", {}).get("repository") ==
                          "mastermindx-market-intelligence/macro")
    ordinary = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(),
                         Loader=ci_pytest._WorkflowYAMLLoader)
    ordinary_checkout = next(
        step["with"] for step in ordinary["jobs"]["pytest_shards"]["steps"]
        if step.get("with", {}).get("repository") ==
        "mastermindx-market-intelligence/macro"
    )
    assert macro_checkout["sparse-checkout"] == ordinary_checkout["sparse-checkout"]
    assert macro_checkout["sparse-checkout"].splitlines() == ["engine", "lib", "config"]
    assert macro_checkout["persist-credentials"] is False
    assert macro_checkout["token"] == ordinary_checkout["token"]
    assert shards["timeout-minutes"] == 45
    minting = [(name, step) for name, job in jobs.items() for step in job["steps"]
               if "pip-compile " in step.get("run", "")]
    assert len(minting) == 1 and minting[0][0] == "prepare-lock"
    assert minting[0][1]["if"] == "hashFiles('requirements/gate-linux-x86_64-py312.lock') == ''"
    uploads = [s for s in prepare["steps"] if s.get("uses") == "actions/upload-artifact@v4"]
    downloads = [s for s in shards["steps"] if s.get("uses") == "actions/download-artifact@v4"]
    assert len(uploads) == len(downloads) == 1
    assert uploads[0]["with"]["name"] == downloads[0]["with"]["name"] == "rwe-linux-lock"
    assert uploads[0]["with"]["if-no-files-found"] == "error"
    assert downloads[0]["with"]["path"] == "requirements"
    runners = [s for s in shards["steps"] if "--shard-index" in s.get("run", "")]
    assert len(runners) == 1
    assert runners[0]["run"] == (
        'python scripts/rwe_env.py gate --env "$RUNNER_TEMP/rwe-env" --shard-index ${{ matrix.index }}'
    )
    receipts = [s for s in shards["steps"] if s.get("uses") == "actions/upload-artifact@v4"
                and s.get("name") == "Upload receipt"]
    assert len(receipts) == 1
    assert receipts[0]["if"] == "always()"
    assert receipts[0]["with"]["name"] == "rwe-receipt-linux-${{ matrix.index }}"
    # Per-job environment: a fixed /tmp path survives between jobs on a
    # persistent runner, and the always() receipt upload would then publish
    # an earlier job's receipt as this job's evidence.
    assert receipts[0]["with"]["path"] == "${{ runner.temp }}/rwe-env/rwe_receipt.json"
    realize = [s for s in shards["steps"] if s.get("name") == "Realize hash-locked environment"]
    assert len(realize) == 1
    assert realize[0]["run"] == 'python scripts/rwe_env.py realize --dest "$RUNNER_TEMP/rwe-env"'
    assert not any("/tmp/" in str(step) for step in shards["steps"])
    assert final["needs"] == ["prepare-lock", "shadow-shards"]
    assert final["if"] == "${{ always() }}"
    assert all("continue-on-error" not in job and all("continue-on-error" not in step
               for step in job["steps"]) for job in jobs.values())


@pytest.mark.parametrize("lock_result", ["success", "failure", "cancelled", "skipped"])
@pytest.mark.parametrize("shards_result", ["success", "failure", "cancelled", "skipped"])
def test_actual_shadow_fan_in_accepts_only_complete_success(lock_result, shards_result):
    steps = _workflow()["jobs"]["shadow-gate"]["steps"]
    assert len(steps) == 1
    assert steps[0]["env"] == {"LOCK_RESULT": "${{ needs.prepare-lock.result }}",
                              "SHARDS_RESULT": "${{ needs.shadow-shards.result }}"}
    result = subprocess.run(["bash", "-c", steps[0]["run"]],
                            env={"LOCK_RESULT": lock_result, "SHARDS_RESULT": shards_result},
                            capture_output=True, text=True)
    assert (result.returncode == 0) is (lock_result == shards_result == "success")
