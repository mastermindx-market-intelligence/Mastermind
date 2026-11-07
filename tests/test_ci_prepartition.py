"""Exact selected work, terminal proof and custody for independent CI children."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

import pytest

from scripts import ci_pytest as ci
from scripts import ci_parallel_shard as fan
from scripts import ci_xdist_guard as guard


ROOT = Path(__file__).resolve().parents[1]


def test_inner_hash_is_independent_stable_and_preserves_outer_exact_cover():
    modules = tuple(f"tests/test_fixture_{index}.py" for index in range(960))
    outer = ci.partition_modules(modules, jobs=6)
    ci.verify_partition(modules, outer)
    for selected in outer:
        # Regression premise: the unchanged outer digest reaches two buckets.
        correlated = {int.from_bytes(hashlib.sha256(p.encode()).digest()[:8], "big") % 4
                      for p in selected}
        assert len(correlated) == 2
        children = ci.partition_modules(selected, jobs=4, inner=True)
        ci.verify_partition(selected, children)
        assert all(children)
        assert children == ci.partition_modules(selected, jobs=4, inner=True)
        before = {p: i for i, child in enumerate(children) for p in child}
        after = {p: i for i, child in enumerate(ci.partition_modules(
            (*selected, "tests/test_added.py"), jobs=4, inner=True)) for p in child}
        assert all(after[p] == index for p, index in before.items())
    assert ci.partition_modules(modules, jobs=6) == outer


@pytest.mark.parametrize("inner,jobs", [
    (False, 3), (False, 4), (False, 6), (True, 3), (True, 4), (True, 5),
])
def test_measured_child_pin_changes_only_four_child_placement(monkeypatch, inner, jobs):
    modules = tuple(f"tests/test_fixture_{index}.py" for index in range(160))
    baseline = ci.partition_modules(modules, jobs=jobs, inner=inner)
    before = {path: index for index, bucket in enumerate(baseline) for path in bucket}
    pinned = modules[0]
    destination = (before[pinned] + 1) % jobs
    monkeypatch.setattr(ci, "_MEASURED_FOUR_CHILD_PLACEMENT", {pinned: destination})

    candidate = ci.partition_modules(modules, jobs=jobs, inner=inner)
    ci.verify_partition(modules, candidate)
    after = {path: index for index, bucket in enumerate(candidate) for path in bucket}
    assert all(after[path] == before[path] for path in modules if path != pinned)
    if inner and jobs == 4:
        assert after[pinned] == destination != before[pinned]
    else:
        assert candidate == baseline


def test_four_process_entry_uses_exact_outer_membership_and_preserves_failure(tmp_path, monkeypatch):
    modules = tuple(f"tests/test_fixture_{index}.py" for index in range(240))
    workflow = tmp_path / ".github/workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("fixture")
    monkeypatch.setattr(fan, "validate_parallel_workflow", lambda _: None)
    monkeypatch.setattr(ci, "resolve_gate", lambda _: dict(included=modules,
        plan=dict(discovered=len(modules), excluded=0, running=len(modules))))
    calls = []
    def run(children, **kwargs):
        calls.append((children, kwargs))
        return 17
    monkeypatch.setattr(ci, "run_shards", run)
    args = ["--jobs", "6", "--index", "2", "--processes", "4", "--root", str(tmp_path)]
    assert fan.main(args) == 17
    expected = ci.partition_modules(ci.partition_modules(modules, jobs=6)[2], jobs=4, inner=True)
    assert calls == [(expected, dict(root=tmp_path.resolve(), completion_proof=True))]
    calls.clear()
    assert fan.main([*args, "--workers", "4"]) == 2 and not calls
    assert fan.main([*args[:-2], "--root", str(tmp_path), "--processes", "5"]) == 2 and not calls


def _fixture(tmp_path, files, *, conftest=None):
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "seen").mkdir()
    (scripts / "__init__.py").write_text("")
    for name in ("ci_pytest.py", "ci_xdist_guard.py", "ci_pytest_timing.py", "ci_fixed_diagnostics.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    for name, source in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(source)
    if conftest is not None:
        (root / "tests/conftest.py").write_text(conftest)
    for args in (["init", "-q"], ["add", "scripts", "tests", "pyproject.toml"],
                 ["-c", "user.name=CI fixture", "-c", "user.email=ci@example.invalid",
                  "commit", "-qm", "fixture"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    output = tmp_path / "diagnostics"
    output.mkdir(mode=0o700)
    env = dict(os.environ)
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTHONPATH"] = str(root)
    env["MMX_CI_FIXED_DIAGNOSTICS_DIR"] = str(output)
    return root, output, env


def _command(shards):
    code = ("from pathlib import Path; import sys; from scripts.ci_pytest import run_shards; "
            "sys.exit(run_shards(" + repr(shards) + ", root=Path.cwd(), completion_proof=True))")
    return [sys.executable, "-u", "-c", code]


def _run(root, env, shards):
    return subprocess.run(_command(shards), cwd=root, env=env, capture_output=True,
                          text=True, timeout=60)


def test_four_real_children_preserve_cases_skips_private_caches_and_diagnostics(tmp_path):
    files = {}
    for index in range(4):
        files[f"tests/test_unit_{index}.py"] = (
            "from pathlib import Path\nimport pytest\n"
            "@pytest.mark.parametrize('value', [1, 2])\n"
            f"def test_original(value): Path('seen/{index}-'+str(value)).write_text('once')\n"
            "def test_permitted_skip(): pytest.skip('fixture skip')\n"
        )
    files["tests/test_optional.py"] = "import pytest\npytest.importorskip('ci_fixture_absent_optional_sdk')\n"
    root, output, env = _fixture(tmp_path, files)
    shards = tuple((f"tests/test_unit_{index}.py",) for index in range(4))
    shards = (shards[0] + ("tests/test_optional.py",), *shards[1:])
    result = _run(root, env, shards)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(list((root / "seen").iterdir())) == 8
    assert result.stdout.count('"completion_valid": true') == 4
    pids, tokens = set(), set()
    for index in range(4):
        child = output / f"pytest-child-{index}"
        value = guard.read_child_receipt(child / guard.CHILD_RECEIPT_NAME)
        assert value["collected"] == value["finished"] == 3
        assert value["collection_completed"] is True
        assert value["assigned_modules_sha256"] == guard.item_digest(shards[index])
        pids.add(value["pid"]); tokens.add(value["token"])
        diagnostics = json.loads((child / "ci-fixed-diagnostics.json").read_text())
        assert diagnostics["head"] and not diagnostics["truncated"]
        summaries = [r for r in diagnostics["progress"] if r["event"] == "summary"]
        assert sum(r["cases_finished"] for r in summaries) == 3
        assert (child / "pytest-cache").is_dir()
    assert len(pids) == 4 and len(tokens) == 1
    assert not (root / ".pytest_cache").exists()
    assert not (output / "ci-fixed-diagnostics.json").exists()


@pytest.mark.parametrize("fault", ["assertion", "collection", "import_exit_zero",
    "body_exit_zero", "collection_exit_zero", "early_pytest_exit_zero", "killed"])
def test_real_incomplete_or_failed_child_never_makes_a_green_outer_job(tmp_path, fault):
    sources = {
        "assertion": "def test_bad(): assert False, 'original assertion'\n",
        "collection": "raise ValueError('original collection failure')\n",
        "import_exit_zero": "import os\nos._exit(0)\n",
        "body_exit_zero": "import os\ndef test_bad(): os._exit(0)\n",
        "collection_exit_zero": "import pytest\npytest.exit('early collection', returncode=0)\n",
        "early_pytest_exit_zero": "import pytest\ndef test_bad(): pytest.exit('early case', returncode=0)\ndef test_unfinished(): pass\n",
        "killed": "import os, signal\ndef test_bad(): os.kill(os.getpid(), signal.SIGKILL)\n",
    }
    root, output, env = _fixture(tmp_path, {
        "tests/test_bad.py": sources[fault],
        "tests/test_good.py": "from pathlib import Path\ndef test_good(): Path('seen/good').write_text('completed')\n",
    })
    result = _run(root, env, (("tests/test_bad.py",), ("tests/test_good.py",)))
    assert result.returncode != 0, result.stdout + result.stderr
    assert (root / "seen/good").read_text() == "completed"
    assert result.stdout.count("CI_CHILD_RESULT ") == 2
    if fault in ("import_exit_zero", "body_exit_zero", "collection_exit_zero", "early_pytest_exit_zero"):
        assert "CI_CHILD_GUARD missing or invalid terminal completion" in result.stdout


@pytest.mark.parametrize("fault", ["remove", "wrong_pid", "late_failure"])
def test_receipt_and_actual_exit_must_both_match_the_original_child(tmp_path, fault):
    conftest = ("import json\nfrom pathlib import Path\nimport pytest\n"
        "@pytest.hookimpl(hookwrapper=True, tryfirst=True)\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    yield\n"
        "    path = Path(session.config.option.ci_child_receipt)\n"
        + {"remove": "    path.unlink()\n",
           "wrong_pid": "    value=json.loads(path.read_text());value['pid']+=1;path.write_text(json.dumps(value))\n",
           "late_failure": "    session.exitstatus=1\n"}[fault])
    root, output, env = _fixture(tmp_path, {"tests/test_original.py": "def test_original(): pass\n"}, conftest=conftest)
    result = _run(root, env, (("tests/test_original.py",),))
    assert result.returncode != 0, result.stdout + result.stderr
    assert '"completion_valid": false' in result.stdout


def test_nested_pytest_does_not_inherit_the_outer_completion_target(tmp_path):
    source = ("from pathlib import Path\nimport subprocess, sys\n"
        "def test_nested():\n"
        "    child = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'nested/leaf.py'], capture_output=True, text=True)\n"
        "    assert child.returncode == 0, child.stdout + child.stderr\n")
    root, output, env = _fixture(tmp_path, {"tests/test_original.py": source})
    (root / "nested").mkdir()
    (root / "nested/leaf.py").write_text("def test_leaf(): pass\n")
    result = _run(root, env, (("tests/test_original.py",),))
    assert result.returncode == 0, result.stdout + result.stderr
    value = guard.read_child_receipt(output / "pytest-child-0" / guard.CHILD_RECEIPT_NAME)
    assert value["collected"] == value["finished"] == 1


@pytest.mark.parametrize("field,value", [("pid", 99), ("token", "b" * 32),
    ("assigned_modules_sha256", "b" * 64), ("collection_completed", False),
    ("collected", 0), ("finished", 1), ("finished", True),
    ("finished_sha256", "b" * 64), ("collection_errors", 1),
    ("deselected", 1), ("exitstatus", 1), ("unexpected", "private")])
def test_foreign_stale_partial_or_open_receipts_are_rejected(field, value):
    baseline = dict(schema=guard.CHILD_RECEIPT_SCHEMA, pid=7, token="a" * 32,
        assigned_modules_sha256="a" * 64, collected=2, finished=2,
        collected_sha256="a" * 64, finished_sha256="a" * 64,
        collection_completed=True, collection_errors=0, deselected=0, exitstatus=0)
    expected = dict(pid=7, token="a" * 32, assigned_digest="a" * 64, returncode=0)
    assert guard.valid_child_receipt(baseline, **expected)
    assert not guard.valid_child_receipt({**baseline, field: value}, **expected)


def test_private_completion_leaf_never_overwrites_or_adopts_foreign_files(tmp_path):
    child = tmp_path / "child"; child.mkdir(mode=0o700)
    path = child / guard.CHILD_RECEIPT_NAME
    foreign = tmp_path / "foreign"; foreign.write_text("PRIVATE"); foreign.chmod(0o600)
    path.symlink_to(foreign)
    with pytest.raises(OSError): guard.write_child_receipt(path, {"schema": "fixture"})
    with pytest.raises(OSError): guard.read_child_receipt(path)
    assert foreign.read_text() == "PRIVATE" and path.is_symlink()
    path.unlink(); os.link(foreign, path)
    with pytest.raises(ValueError): guard.read_child_receipt(path)
    path.unlink()
    guard.write_child_receipt(path, {"schema": "fixture"})
    with pytest.raises(FileExistsError): guard.write_child_receipt(path, {"schema": "replaced"})
    path.chmod(0o644)
    with pytest.raises(ValueError): guard.read_child_receipt(path)


def test_existing_child_directory_refuses_before_any_process(tmp_path):
    root, output, env = _fixture(tmp_path, {"tests/test_original.py": "def test_original(): pass\n"})
    foreign = output / "pytest-child-0"; foreign.mkdir(mode=0o700)
    (foreign / "owner").write_text("original")
    result = _run(root, env, (("tests/test_original.py",),))
    assert result.returncode != 0 and "CI_CHILD_RESULT " not in result.stdout
    assert (foreign / "owner").read_text() == "original"


def test_fifo_completion_leaf_is_rejected_without_waiting_for_a_writer(tmp_path):
    child = tmp_path / "child"; child.mkdir(mode=0o700)
    path = child / guard.CHILD_RECEIPT_NAME
    os.mkfifo(path, 0o600)
    code = ("from pathlib import Path; from scripts.ci_xdist_guard import read_child_receipt; "
            "read_child_receipt(Path(" + repr(str(path)) + "))")
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0 and "owned bounded file" in result.stderr
    assert path.exists()


def _running(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True)
    return result.returncode == 0 and bool(result.stdout.strip()) and not result.stdout.strip().startswith("Z")


@pytest.mark.parametrize("cancel_signal", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("parent_exits", [False, True], ids=["held-pipe", "parent-exits"])
def test_cancellation_terminates_owned_groups_and_reaps_every_child(tmp_path, cancel_signal, parent_exits):
    source = ("from pathlib import Path\nimport os, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen([sys.executable, '-c', \"import os,signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path('seen/grandchild-'+str(os.getpid())).write_text(str(os.getpid()));time.sleep(60)\"])\n"
        "Path('seen/child-'+str(os.getpid())).write_text(str(os.getpid()))\n"
        "def test_wait_for_controller(): time.sleep(60)\n")
    if parent_exits:
        source = source.replace("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n", "")
        source = source.replace("time.sleep(60)\"])", "time.sleep(60)\"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)")
    root, output, env = _fixture(tmp_path, {"tests/test_a.py": source, "tests/test_b.py": source})
    env["PYTEST_ADDOPTS"] = "-s"  # descendants hold the original output pipe
    process = subprocess.Popen(_command((("tests/test_a.py",), ("tests/test_b.py",))),
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    owned = []
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            children = list((root / "seen").glob("child-*"))
            grandchildren = list((root / "seen").glob("grandchild-*"))
            if len(children) == len(grandchildren) == 2:
                break
            assert process.poll() is None
            time.sleep(0.05)
        assert len(children) == len(grandchildren) == 2
        owned = [int(p.read_text()) for p in (*children, *grandchildren)]
        process.send_signal(cancel_signal)
        text, _ = process.communicate(timeout=15)
        assert process.returncode == 128 + cancel_signal, text
        assert text.count("CI_CHILD_RESULT ") == 2, text
        deadline = time.monotonic() + 2
        while any(_running(pid) for pid in owned) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert all(not _running(pid) for pid in owned)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                for path in (root / "seen").glob("child-*"):
                    try: os.killpg(int(path.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass
                process.kill(); process.communicate(timeout=5)


@pytest.mark.parametrize("replacement", ["${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/**",
    "${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/pytest-child-0/pytest-cache/**",
    "${{ env.MMX_CI_FIXED_DIAGNOSTICS_DIR }}/pytest-child-0/ci-pytest-completion.json"])
def test_workflow_upload_cannot_expand_to_raw_or_private_child_outputs(replacement):
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    upload = next(step for step in workflow["jobs"]["pytest_shards"]["steps"]
                  if step.get("name") == "Upload fixed test diagnostics")
    upload["with"]["path"] = replacement
    with pytest.raises(ci.PolicyError): fan.validate_parallel_workflow(yaml.safe_dump(workflow))


def test_broken_controller_output_drains_children_before_executor_join(tmp_path):
    files = {}
    for name in ("a", "b"):
        files[f"tests/test_{name}.py"] = (
            "from pathlib import Path\nimport os,time\n"
            f"Path('seen/child-{name}').write_text(str(os.getpid()))\n"
            f"while not Path('release-{name}').exists(): time.sleep(0.02)\n"
            "def test_wait(): time.sleep(60)\n"
        )
    root, output, env = _fixture(tmp_path, files)
    process = subprocess.Popen(_command((("tests/test_a.py",), ("tests/test_b.py",))),
        cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 20
        while len(list((root / "seen").glob("child-*"))) < 2 and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.02)
        children = [int(p.read_text()) for p in (root / "seen").glob("child-*")]
        assert len(children) == 2
        process.stdout.close()
        process.stdout = None
        (root / "release-a").touch()  # b remains in collection until controller cleanup
        _, error = process.communicate(timeout=15)
        assert process.returncode != 0 and "BrokenPipeError" in error
        assert all(not _running(pid) for pid in children)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: process.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                for path in (root / "seen").glob("child-*"):
                    try: os.killpg(int(path.read_text()), signal.SIGKILL)
                    except ProcessLookupError: pass
                process.kill(); process.communicate(timeout=5)


@pytest.mark.parametrize("refusal", ["permission", "absent"])
def test_one_group_signal_refusal_does_not_strand_other_owned_groups(tmp_path, refusal):
    slow = (
        "from pathlib import Path\nimport os,signal,subprocess,sys,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "child = subprocess.Popen([sys.executable, '-c', \"import os,signal,time;"
        "from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
        "Path('seen/grandchild').write_text(str(os.getpid()));time.sleep(60)\"])\n"
        "Path('seen/slow').write_text(str(os.getpid()))\n"
        "def test_wait(): time.sleep(60)\n"
    )
    fast = ("import os\nfrom pathlib import Path\n"
            "def test_completed(): Path('seen/fast').write_text(str(os.getpid()))\n")
    root, output, env = _fixture(tmp_path, {
        "tests/test_fast.py": fast, "tests/test_slow.py": slow,
    })
    env["PYTEST_ADDOPTS"] = "-s"
    controller = r'''
import json, os, signal, sys
from pathlib import Path
from scripts import ci_pytest as ci
original = os.killpg
refusal = sys.argv[1]
def observed(group, signum):
    fast = Path("seen/fast")
    refused = fast.exists() and int(fast.read_text()) == group
    with Path("seen/signals").open("a") as output:
        output.write(json.dumps({"group": group, "signal": signum, "refused": refused}) + "\n")
    if refused:
        if refusal == "permission":
            raise PermissionError(1, "fixture signal refusal")
        raise ProcessLookupError(3, "fixture group is absent")
    return original(group, signum)
ci.os.killpg = observed
raise SystemExit(ci.run_shards((("tests/test_fast.py",), ("tests/test_slow.py",)),
    root=Path.cwd(), completion_proof=True))
'''
    process = subprocess.Popen([sys.executable, "-u", "-c", controller, refusal],
                               cwd=root, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            ready = all((root / "seen" / name).exists() for name in ("fast", "slow", "grandchild"))
            if ready and not _running(int((root / "seen/fast").read_text())):
                break
            assert process.poll() is None
            time.sleep(0.02)
        assert ready
        fast_pid, slow_pid, descendant = (
            int((root / "seen" / name).read_text()) for name in ("fast", "slow", "grandchild")
        )
        assert not _running(fast_pid)
        process.send_signal(signal.SIGTERM)
        text, _ = process.communicate(timeout=12)
        assert process.returncode == (1 if refusal == "permission" else 128 + signal.SIGTERM), text
        assert ("CI_CHILD_CLEANUP signal failed; cleanup is unconfirmed" in text) is (refusal == "permission")
        records = [json.loads(line) for line in (root / "seen/signals").read_text().splitlines()]
        assert len([row for row in records if row["group"] == fast_pid]) == 1
        assert {row["signal"] for row in records if row["group"] == slow_pid} == {
            signal.SIGTERM, signal.SIGKILL,
        }
        assert not _running(slow_pid) and not _running(descendant)
    finally:
        for name in ("fast", "slow"):
            path = root / "seen" / name
            if path.exists():
                try:
                    os.killpg(int(path.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=3)
