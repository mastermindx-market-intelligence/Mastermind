"""Actual canonical Git/parser through incumbent sealed source acquisition."""
import base64
import json
from pathlib import Path
import subprocess
import zlib

import pytest

from control_plane import agentos_project_plan as owner
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from tests.test_agentos_project_plan_source import RECORD
from tests.test_installed_product_acceptance_context import fixture


def bound(tmp_path, monkeypatch, mutation=None):
    collector, _, seen = fixture(tmp_path)
    macro = seen["macro"]
    record = macro / "agentos/workstreams/WS-ONE.md"
    record.write_text(RECORD)
    parser = macro / "scripts/agentos.py"
    parser.parent.mkdir()
    data = json.loads((Path(__file__).parent / "fixtures/agentos-project-plan-parser-ed12006d.json").read_bytes())
    parser.write_bytes(zlib.decompress(base64.b64decode(data["zlib_base64"], validate=True)))
    subprocess.run(["git", "-C", str(macro), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(macro), "commit", "-qm", "authored plan fixture"], check=True, capture_output=True)
    seen["sha"] = subprocess.check_output(["git", "-C", str(macro), "rev-parse", "HEAD"], text=True).strip()
    seen["record"] = record
    monkeypatch.setattr(owner, "_SOURCE_ROOT", seen["code"])
    def runner(argv, **limits):
        seen["calls"].append((list(argv), dict(limits)))
        if argv[0] == "git":
            return _default_packet_runner(argv, **limits)
        child = Path(argv[argv.index("--macro-root") + 1])
        seen["child_macro"] = child
        value = owner.read_from_macro_owner(macro_root=child,
            expected_macro_sha=argv[argv.index("--expected-macro-sha") + 1],
            work_ref=argv[argv.index("--work-ref") + 1], timeout=float(argv[-1]))
        if mutation: mutation(value, child, seen)
        return dict(code=0, stdout=json.dumps(value), timed_out=False, limit_exceeded=False, invalid_utf8=False)
    collector._runner = runner
    return collector, seen


def test_actual_parser_and_git_source_through_full_sealed_collector(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_plan_reader(macro_root=seen["macro"])
    value = reader.read(work_ref="WS:ONE")
    assert value["availability"] == "AVAILABLE"
    assert value["source"]["commit"] == seen["sha"]
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert value["plan"]["version_history"]["revisions"][0]["commit"] == seen["sha"]
    child_calls = [(argv, limits) for argv, limits in seen["calls"] if argv[0] != "git"]
    assert len(child_calls) == 1
    argv, limits = child_calls[0]
    assert argv[:4] == [str(seen["python"]), "-I", "-B", str(seen["code"] / "scripts/agentos_project_plan_entry.py")]
    assert limits["max_bytes"] == 262144 and 0 < limits["timeout"] <= 15
    assert seen["child_macro"] != seen["macro"] and not seen["child_macro"].exists()
    assert not collector._collections


@pytest.mark.parametrize("target", ["live", "materialized", "body", "commit"])
def test_source_mutation_or_conflicting_child_output_refuses(tmp_path, monkeypatch, target):
    def mutate(value, child, seen):
        if target == "body": value["plan"]["private"] = "unpublished"
        elif target == "commit": value["source"]["commit"] = "f" * 40
        else:
            record = seen["record"] if target == "live" else child / "agentos/workstreams/WS-ONE.md"
            raw = record.read_bytes()
            record.write_bytes(b"transient change\n"); record.write_bytes(raw)
    collector, seen = bound(tmp_path, monkeypatch, mutate)
    reader = collector.project_plan_reader(macro_root=seen["macro"])
    with pytest.raises(GatewayError): reader.read(work_ref="WS:ONE")
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("field,value", [("_python", Path("/foreign/python")), ("_expected_source_sha", "f" * 40), ("_allow_synthetic_fixture", True)])
def test_issued_reader_rejects_retargeted_owner_before_source(tmp_path, monkeypatch, field, value):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_plan_reader(macro_root=seen["macro"])
    setattr(collector, field, value)
    with pytest.raises(owner.ProjectPlanSourceUnavailable): reader.read(work_ref="WS:ONE")
    assert seen["calls"] == []


def test_fixed_child_entry_missing_dependency_is_closed_unavailability(tmp_path, monkeypatch):
    import os
    import sys
    collector, seen = bound(tmp_path, monkeypatch)
    entry = Path(__file__).resolve().parents[1] / "scripts/agentos_project_plan_entry.py"
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(entry),
        "--macro-root", str(seen["macro"]), "--expected-macro-sha", seen["sha"],
        "--work-ref", "WS:ONE", "--timeout", "10"],
        capture_output=True, timeout=15, env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert len(result.stdout) <= 131072
    value = json.loads(result.stdout)
    assert value["availability"] == "UNAVAILABLE"
    assert value["reason_codes"] == ["SOURCE_UNAVAILABLE"]
    assert value["plan"] is None and value["source"] is None
    assert "PyYAML" not in result.stdout.decode() and result.stderr == b""


def test_fixed_child_entry_executes_actual_dependency_complete_isolated_python(tmp_path, monkeypatch):
    import os
    import sys
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    # macOS reuses the incumbent qualified capacity boot environment. Hosted
    # source CI uses its dependency-complete project environment; neither path
    # installs dependencies or enables ambient user-site packages.
    python = PYTHON_BINARY if PYTHON_BINARY.is_file() else Path(sys.executable)
    _, seen = bound(tmp_path, monkeypatch)
    entry = Path(__file__).resolve().parents[1] / "scripts/agentos_project_plan_entry.py"
    result = subprocess.run([str(python), "-I", "-B", str(entry),
        "--macro-root", str(seen["macro"]), "--expected-macro-sha", seen["sha"],
        "--work-ref", "WS:ONE", "--timeout", "10"],
        capture_output=True, timeout=15, env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert len(result.stdout) <= 131072
    value = json.loads(result.stdout)
    assert value["availability"] == "AVAILABLE", value["reason_codes"]
    assert value["source"]["commit"] == seen["sha"]
    assert value["plan"]["objective"] == "Deliver the real owner content."
    assert value["plan"]["waves"][1]["depends_on"] == ["first"]
    assert result.stderr == b"" and "Private body" not in result.stdout.decode()
