"""Real invocation evidence preserves case identity and phase association."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace

import pytest

from scripts import ci_pytest as ci
from scripts import ci_pytest_timing as timing
from scripts.ci_xdist_guard import item_digest

ROOT = Path(__file__).resolve().parents[1]


def _project(tmp_path, files):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/__init__.py").write_text("")
    for name in ("ci_pytest_timing.py", "ci_xdist_guard.py"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    (root / "pytest.ini").write_text("[pytest]\n")
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return root


def _invoke(root, targets, *, flag=True, extra=(), environment=None):
    private = Path(tempfile.mkdtemp(prefix="invocation-", dir=root.parent))
    (private / "child-tmp").mkdir()
    env = dict(os.environ, PYTHONPATH=str(root), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTEST_ADDOPTS="", TMPDIR=str(private / "child-tmp"))
    env.pop("PYTEST_PLUGINS", None)
    env.pop("MMX_CI_FIXED_DIAGNOSTICS_DIR", None)
    env.update(environment or {})
    argv = [sys.executable, "-m", "pytest", "-p", "scripts.ci_pytest_timing",
            "-p", "no:cacheprovider", "-q", "--basetemp", str(private / "pytest")]
    if flag:
        argv.append("--ci-case-evidence")
    result = subprocess.run([*argv, *extra, *targets], cwd=root, env=env,
                            capture_output=True, text=True, timeout=60)
    rows = [json.loads(line[len("CI_MODULE "):])
            for line in result.stdout.splitlines() if line.startswith("CI_MODULE ")]
    return result, rows


def _evidence(rows, module="tests/test_cases.py"):
    matches = [row for row in rows
               if row["event"] == "case_evidence" and row["module"] == module]
    assert len(matches) == 1, matches
    return matches[0]


def test_generic_progress_argv_never_activates_case_evidence():
    assert "--ci-case-evidence" not in ci.pytest_argv(["tests/test_cases.py"], progress=True)


def test_real_serial_preserves_skip_xfail_xpass_and_setup_teardown_failures(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py": """
import pytest
@pytest.mark.parametrize("value", [1, 2])
def test_param(value): pass
def test_skip(): pytest.skip("private reason must not enter evidence")
@pytest.mark.xfail
def test_xfail(): assert False
@pytest.mark.xfail
def test_xpass(): pass
@pytest.mark.xfail(strict=True)
def test_strict_xpass(): pass
@pytest.fixture
def bad_setup(): assert False, "setup failed"
def test_setup(bad_setup): pass
@pytest.fixture
def bad_teardown():
    yield
    assert False, "teardown failed"
def test_teardown(bad_teardown): pass
"""})
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == 1, result.stdout + result.stderr
    row = _evidence(rows)
    ids = ["tests/test_cases.py::" + case for case in (
        "test_param[1]", "test_param[2]", "test_skip", "test_xfail", "test_xpass",
        "test_strict_xpass", "test_setup", "test_teardown",
    )]
    assert row["complete"] and row["collection_complete"] and not row["errors"]
    assert row["collected"] == row["finished"] == row["case_invocations"] == 8
    assert row["phase_reports"] == 23
    assert row["collected_sha256"] == row["finished_sha256"] == item_digest(sorted(ids))
    assert row["deselected"] == 0
    assert row["schema"] == "ci.module-case-evidence.v1"
    assert type(row["pid"]) is int
    assert "private reason" not in json.dumps(row)
    expected = []
    for nodeid in ids:
        name = nodeid.split("::")[1]
        setup = ["setup", "failed" if name == "test_setup" else "passed", False]
        call = {
            "test_skip": ["call", "skipped", False],
            "test_xfail": ["call", "skipped", True],
            "test_xpass": ["call", "passed", True],
            "test_strict_xpass": ["call", "failed", False],
        }.get(name, ["call", "passed", False])
        teardown = ["teardown", "failed" if name == "test_teardown" else "passed", False]
        expected.append([nodeid, [setup, teardown] if name == "test_setup"
                         else [setup, call, teardown]])
    ordered = sorted(expected, key=lambda value: json.dumps(
        value, ensure_ascii=True, separators=(",", ":"),
    ))
    assert row["outcomes_sha256"] == item_digest(ordered)


def test_same_count_changed_identity_or_outcome_never_matches(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py": "def test_first(): pass\n"})
    _, one = _invoke(root, ["tests/test_cases.py"])
    (root / "tests/test_cases.py").write_text("def test_second(): pass\n")
    _, two = _invoke(root, ["tests/test_cases.py"])
    (root / "tests/test_cases.py").write_text("def test_second(): assert False\n")
    result, failed = _invoke(root, ["tests/test_cases.py"])
    first, second, last = map(_evidence, (one, two, failed))
    assert result.returncode == 1
    assert first["collected"] == second["collected"] == last["collected"] == 1
    assert first["collected_sha256"] != second["collected_sha256"]
    assert second["collected_sha256"] == last["collected_sha256"]
    assert second["outcomes_sha256"] != last["outcomes_sha256"]
    assert all(row["complete"] for row in (first, second, last))


@pytest.mark.parametrize("source,code,complete,collected", [
    ("# an honestly empty selected module\n", 5, True, 0),
    ("import pytest\npytest.skip('module gate', allow_module_level=True)\n", 5, True, 0),
    ("raise ValueError('collection failure')\n", 2, False, None),
    ("import pytest\npytest.exit('interrupted collection', returncode=0)\n", 2, False, None),
])
def test_empty_skipped_failed_and_unobserved_collection_are_distinct(
    tmp_path, source, code, complete, collected
):
    root = _project(tmp_path, {"tests/test_cases.py": source})
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == code, result.stdout + result.stderr
    row = _evidence(rows)
    assert row["complete"] is complete
    assert row["collected"] == collected
    assert row["collected_sha256"] == (item_digest([]) if collected == 0 else None)
    assert row["collection_reports"] >= (0 if "pytest.exit" in source else 1)


def test_deselection_and_interruption_cannot_claim_complete_work(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py":
        "def test_one(): pass\ndef test_two(): pass\n"})
    result, rows = _invoke(root, ["tests/test_cases.py"], extra=("-k", "one"))
    row = _evidence(rows)
    assert result.returncode == 0
    assert not row["complete"] and row["collection_complete"]
    assert row["collected"] == row["finished"] == row["deselected"] == 1
    assert row["deselected_sha256"] == item_digest(["tests/test_cases.py::test_two"])
    (root / "tests/test_cases.py").write_text(
        "import pytest\ndef test_one(): pytest.exit('early', returncode=0)\n"
        "def test_two(): pass\n"
    )
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == 0
    row = _evidence(rows)
    assert row["collected"] == 2 and not row["complete"]


@pytest.mark.parametrize("ambient", ["none", "env", "ini"])
def test_no_ambient_activation_and_legacy_timing_unchanged(tmp_path, ambient):
    root = _project(tmp_path, {"tests/test_cases.py": "def test_one(): pass\n"})
    environment = {}
    if ambient == "env":
        environment["PYTEST_ADDOPTS"] = "--ci-case-evidence"
    elif ambient == "ini":
        (root / "pytest.ini").write_text("[pytest]\naddopts = --ci-case-evidence\n")
    result, rows = _invoke(root, ["tests/test_cases.py"], flag=False, environment=environment)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [row["event"] for row in rows] == ["start", "summary"]


@pytest.mark.parametrize("distributed", [
    ("-n", "2"),
    ("--dist", "load", "--tx", "2*popen"),
])
def test_xdist_controllers_and_workers_never_emit_case_evidence(tmp_path, distributed):
    pytest.importorskip("xdist")
    root = _project(tmp_path, {"tests/test_cases.py": "def test_one(): pass\n"})
    result, rows = _invoke(root, ["tests/test_cases.py"],
                           extra=("-p", "xdist.plugin", *distributed))
    assert result.returncode == 0, result.stdout + result.stderr
    assert rows and all(row["event"] != "case_evidence" for row in rows)


def test_real_duplicate_ids_keep_multiplicity(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py": "def test_one(): pass\n"})
    result, rows = _invoke(root, ["tests/test_cases.py", "tests/test_cases.py"],
                           extra=("--keep-duplicates",))
    assert result.returncode == 0, result.stdout + result.stderr
    row = _evidence(rows)
    nodeid = "tests/test_cases.py::test_one"
    assert row["complete"] and row["collected"] == row["finished"] == 2
    assert row["collected_sha256"] == item_digest([nodeid, nodeid])
    assert row["collected_sha256"] != item_digest([nodeid])


def _observed(tmp_path, dispositions):
    lines = []
    module = "test_cases.py"
    config = SimpleNamespace(rootpath=tmp_path, args=[str(tmp_path / module)])
    observer = timing.ModuleCaseEvidence(SimpleNamespace(write_line=lines.append), config)
    observer.pytest_collectreport(SimpleNamespace(nodeid=module, outcome="passed", failed=False))
    nodeid = module + "::test_same"
    observer.pytest_collection_finish(SimpleNamespace(
        items=[SimpleNamespace(nodeid=nodeid) for _ in dispositions]
    ))
    for call, teardown in dispositions:
        observer.pytest_runtest_logstart(nodeid, None)
        for when, outcome in (("setup", "passed"), ("call", call), ("teardown", teardown)):
            observer.pytest_runtest_logreport(SimpleNamespace(
                nodeid=nodeid, when=when, outcome=outcome
            ))
        observer.pytest_runtest_logfinish(nodeid, None)
    observer.pytest_sessionfinish(None, 1)
    assert len(lines) == 1
    return json.loads(lines[0].removeprefix("\nCI_MODULE "))


def test_duplicate_phase_bags_cannot_hide_different_invocation_associations(tmp_path):
    left = [("passed", "failed"), ("failed", "passed")]
    right = [("passed", "passed"), ("failed", "failed")]
    assert Counter(value[0] for value in left) == Counter(value[0] for value in right)
    assert Counter(value[1] for value in left) == Counter(value[1] for value in right)
    first, second = (_observed(tmp_path, values) for values in (left, right))
    assert first["complete"] and second["complete"]
    assert first["collected_sha256"] == second["collected_sha256"]
    assert first["outcomes_sha256"] != second["outcomes_sha256"]
    repeated = _observed(tmp_path, [("passed", "passed")] * 2)
    assert repeated["case_invocations"] == 2


@pytest.mark.parametrize("limit,value", [
    ("_CASE_MAX_COUNT", 1), ("_CASE_MAX_PHASE_BYTES", 1),
    ("_CASE_MAX_TOTAL_BYTES", 1), ("_CASE_MAX_NODE_BYTES", 17),
])
def test_overflow_is_unavailable_and_never_hashes_a_truncated_subset(tmp_path, monkeypatch, limit, value):
    monkeypatch.setattr(timing, limit, value)
    row = _observed(tmp_path, [("passed", "passed"), ("passed", "passed")])
    assert not row["complete"] and "evidence_overflow" in row["errors"]
    for key in ("collected", "finished", "outcomes_sha256", "collected_sha256", "finished_sha256"):
        assert row[key] is None



def test_real_observer_keeps_invocation_primitives_during_test_patches(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py": """
import json
import pytest
from scripts import ci_pytest_timing as timing

def test_shared_serializer_patch(monkeypatch):
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError("test subject must reject before serialization")
    monkeypatch.setattr(json, "dumps", forbidden)
    assert calls == []

@pytest.mark.parametrize("limit", [
    "_CASE_MAX_COUNT", "_CASE_MAX_NODE_BYTES",
    "_CASE_MAX_PHASE_BYTES", "_CASE_MAX_TOTAL_BYTES",
])
def test_shared_limit_patch(monkeypatch, limit):
    monkeypatch.setattr(timing, limit, 1)

def test_after_patches():
    assert json.dumps(["ordinary"]) == '["ordinary"]'
"""})
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == 0, result.stdout + result.stderr
    row = _evidence(rows)
    assert row["complete"] and row["errors"] == [], row
    assert row["collected"] == row["finished"] == row["case_invocations"] == 6
    assert row["phase_reports"] == 18
    assert row["collected_sha256"] == row["finished_sha256"]


def test_real_subtest_reports_remain_attached_to_their_invocation(tmp_path):
    root = _project(tmp_path, {"tests/test_cases.py": """
import unittest
class TestSubcases(unittest.TestCase):
    def test_subcases(self):
        for value in (1, 2, 3):
            with self.subTest(value=value):
                self.assertGreater(value, 0)
"""})
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == 0, result.stdout + result.stderr
    row = _evidence(rows)
    assert row["complete"] and row["collected"] == row["finished"] == 1
    assert row["phase_reports"] >= 3


def test_same_path_nested_timing_cannot_add_canonical_evidence(tmp_path):
    from tests.test_ci_prepartition import _fixture, _run

    source = """import subprocess, sys
from pathlib import Path
def test_outer(capsys):
    nested = Path.cwd() / 'nested'
    result = subprocess.run([sys.executable, '-m', 'pytest', '-p',
        'scripts.ci_pytest_timing', '-q', 'tests/test_same.py'],
        cwd=nested, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    with capsys.disabled():
        print(result.stdout, end='', flush=True)
"""
    root, output, env = _fixture(tmp_path, {"tests/test_same.py": source})
    nested = root / "nested"
    (nested / "tests").mkdir(parents=True)
    (nested / "pytest.ini").write_text("[pytest]\n")
    (nested / "tests/test_same.py").write_text(
        "def test_nested_one(): pass\ndef test_nested_two(): pass\n"
    )
    result = _run(root, env, (("tests/test_same.py",),))
    assert result.returncode == 0, result.stdout + result.stderr
    rows = [json.loads(line[len("CI_MODULE "):])
            for line in result.stdout.splitlines() if line.startswith("CI_MODULE ")]
    legacy = [row for row in rows if row["event"] == "summary"]
    assert sorted(row["cases_finished"] for row in legacy) == [1, 2]
    row = _evidence(rows, "tests/test_same.py")
    assert row["complete"] and row["collected"] == row["finished"] == 1
    from scripts import ci_xdist_guard as guard
    receipt = guard.read_child_receipt(output / "pytest-child-0" / guard.CHILD_RECEIPT_NAME)
    assert receipt["collected"] == receipt["finished"] == 1
    assert row["pid"] == receipt["pid"]
    assert row["collected_sha256"] == receipt["collected_sha256"]


def test_collection_hook_exit_keeps_unobserved_inventory_unavailable(tmp_path):
    root = _project(tmp_path, {
        "tests/test_cases.py": "def test_one(): pass\n",
        "conftest.py": "import pytest\ndef pytest_collection(session):\n    pytest.exit('before collection', returncode=0)\n",
    })
    result, rows = _invoke(root, ["tests/test_cases.py"])
    assert result.returncode == 0, result.stdout + result.stderr
    row = _evidence(rows)
    assert not row["complete"] and not row["collection_complete"]
    assert row["collected"] is None and row["collected_sha256"] is None
    assert row["collection_sha256"] is None
    assert "collection_unobserved" in row["errors"]
