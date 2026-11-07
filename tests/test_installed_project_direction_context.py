"""Actual Git/parser/Direction helper through the incumbent sealed collector.

These inert temporary repositories do not establish an installed host namespace.
"""
import base64
import copy
import json
from pathlib import Path
import subprocess
import zlib

import pytest

from control_plane import agentos_project_direction as source
from integrations.executive_mcp.installed import InstalledBootPacketCollector, _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from tests.test_agentos_project_direction_source import WS, decision, WORK
from tests.test_installed_product_acceptance_context import fixture


def bound(tmp_path, monkeypatch, mutation=None):
    collector, _, seen = fixture(tmp_path)
    macro = seen["macro"]
    data = json.loads((Path(__file__).parent / "fixtures/agentos-direction-owner.json").read_bytes())
    for path, item in data["files"].items():
        target = macro / path; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True)))
    current = macro / "agentos/decisions/DEC-CURRENT.md"
    current.parent.mkdir(exist_ok=True)
    current.write_text(decision("CURRENT", "DEC:PREVIOUS"))
    (current.parent / "DEC-PREVIOUS.md").write_text(decision("PREVIOUS", None, "DEC:CURRENT"))
    (macro / "agentos/workstreams/WS-DIRECTION-TEST.md").write_text(WS)
    subprocess.run(["git", "-C", str(macro), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(macro), "commit", "-qm", "inert Direction source"], check=True, capture_output=True)
    seen["sha"] = subprocess.check_output(["git", "-C", str(macro), "rev-parse", "HEAD"], text=True).strip()
    seen["record"] = current
    monkeypatch.setattr(source, "_SOURCE_ROOT", seen["code"])
    def runner(argv, **limits):
        seen["calls"].append((list(argv), dict(limits)))
        if argv[0] == "git":
            return _default_packet_runner(argv, **limits)
        child = Path(argv[argv.index("--macro-root") + 1]); seen["child_macro"] = child
        value = source.read_from_macro_owner(macro_root=child,
            expected_macro_sha=argv[argv.index("--expected-macro-sha") + 1],
            work_ref=argv[argv.index("--work-ref") + 1], timeout=float(argv[-1]))
        if mutation:
            mutation(value, child, seen)
        return {"code": 0, "stdout": json.dumps(value), "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}
    collector._runner = runner
    return collector, seen


def test_actual_direction_owner_is_materialized_and_bound_by_the_installed_factory(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_direction_reader(macro_root=seen["macro"])
    value = reader.read(work_ref=WORK)
    assert value["availability"] == "AVAILABLE", value
    assert value["source"]["commit"] == seen["sha"]
    assert value["direction"]["current"]["decision_ref"] == "DEC:CURRENT"
    assert value["direction"]["history"]["total_count"] == 2
    calls = [(argv, limits) for argv, limits in seen["calls"] if argv[0] != "git"]
    assert len(calls) == 1
    argv, limits = calls[0]
    assert argv[:4] == [str(seen["python"]), "-I", "-B", str(seen["code"] / "scripts/agentos_project_direction_entry.py")]
    assert limits["max_bytes"] == 65536 and 0 < limits["timeout"] <= 15
    assert seen["child_macro"] != seen["macro"] and not seen["child_macro"].exists()
    assert not collector._collections


@pytest.mark.parametrize("kind", ["live", "materialized", "body", "commit"])
def test_source_drift_or_malformed_child_result_cannot_publish_direction(tmp_path, monkeypatch, kind):
    def mutate(value, child, seen):
        if kind == "body": value["direction"]["private"] = "not public"
        elif kind == "commit": value["source"]["commit"] = "f" * 40
        else:
            path = seen["record"] if kind == "live" else child / "agentos/decisions/DEC-CURRENT.md"
            raw = path.read_bytes(); path.write_bytes(b"transient change\n"); path.write_bytes(raw)
    collector, seen = bound(tmp_path, monkeypatch, mutate)
    reader = collector.project_direction_reader(macro_root=seen["macro"])
    with pytest.raises(GatewayError):
        reader.read(work_ref=WORK)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("kind", ["bare", "forged", "copied", "other_owner", "callback", "context"])
def test_lower_core_binding_stays_exact_to_this_facade_owner_and_callback(tmp_path, monkeypatch, kind):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_direction_reader(macro_root=seen["macro"])
    candidate = source.AgentOsProjectDirectionReader(macro_root=seen["macro"])
    candidate._installed_context_owner = collector
    candidate._installed_context_binding = reader._installed_context_binding
    if kind == "forged": candidate._installed_reader_binding = {"issued": True, "owner": collector}
    elif kind == "copied": candidate._installed_reader_binding = reader._installed_reader_binding
    elif kind == "other_owner":
        candidate = reader; candidate._installed_context_owner = copy.copy(collector)
    elif kind == "callback":
        candidate = reader
        monkeypatch.setattr(InstalledBootPacketCollector, "read_project_direction", lambda *a, **k: pytest.fail("changed callback invoked"))
    elif kind == "context":
        candidate = reader; collector._expected_source_sha = "f" * 40
    with pytest.raises(source.DirectionSourceUnavailable, match="^SOURCE_UNAVAILABLE$"):
        candidate.read(work_ref=WORK)
    assert seen["calls"] == []


def test_lower_core_direction_facade_has_no_reverse_integration_import():
    import ast
    tree = ast.parse(Path(source.__file__).read_text())
    assert not any(isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "integrations" for node in ast.walk(tree))
