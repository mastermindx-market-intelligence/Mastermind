"""Qualification of a proposal-only OMH donor integration, never live admission."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from control_plane.executive_orchestration_result import (
    PLAN_SCHEMA_V4, _validate_plan, canonical_digest,
)

ROOT = Path(__file__).resolve().parents[1]


def node(ident, parents=(), scope=(), role="build"):
    return dict(id=ident, label=ident, category="quick", prompt="Implement the bounded change.",
                depends_on=list(parents), write_scope=list(scope), role=role)


def policy(scope=()):
    return dict(business_impact="routine", review_required=False,
                requested_authorities=["READ"], allowed_write_paths=list(scope),
                validation_ids=[], attempt_limit=1, cost_class="small")


def sample():
    nodes = [node("verify", ("build-a", "build-b"), role="verify"),
             node("build-b", scope=("src/b.py",)), node("build-a", scope=("src/a.py",))]
    policies = {n["id"]: policy(("src",) if n["write_scope"] else ()) for n in nodes}
    for name in ("build-a", "build-b"):
        policies[name]["requested_authorities"] = ["READ", "WRITE"]
    return dict(nodes=nodes, policies=policies, root_job_id="ROOT-OMH", plan_attempt_id="ATT-PLAN")


@pytest.fixture
def api():
    try:
        return importlib.import_module("integrations.hermes_omh.adapter")
    except ModuleNotFoundError:
        pytest.fail("OMH proposal adapter has not been implemented")


def test_real_canonical_consumer_and_stable_topological_order():
    try:
        api = importlib.import_module("integrations.hermes_omh.adapter")
    except ModuleNotFoundError:
        pytest.fail("OMH proposal adapter has not been implemented")
    request = sample()
    original = copy.deepcopy(request)
    out = api.prepare_execution_plan(**request)
    assert out["state"] == "PREPARED_NOT_ADMITTED"
    assert out["admitted"] is False and out["dispatched"] is False
    plan = out["plan"]
    assert plan["schema_version"] == PLAN_SCHEMA_V4
    assert [s["step_id"] for s in plan["steps"]] == ["build-b", "build-a", "verify"]
    assert plan["steps"][2]["prerequisite_step_ids"] == ["build-a", "build-b"]
    assert plan == _validate_plan(plan, outer=dict(run_id="ATT-PLAN", expected_root_job_id="ROOT-OMH"))
    assert out["plan_sha256"] == canonical_digest(plan)
    assert all("placement" not in s for s in plan["steps"])
    assert out["topology"]["layers"] == [["build-b", "build-a"], ["verify"]]
    assert out["topology"]["critical_path_measure"] == "node_count"
    assert out["topology"]["critical_path"] == ["build-a", "verify"]
    assert request == original
    plan["steps"][0]["requested_authorities"].append("ADMIN")
    assert request == original


@pytest.mark.parametrize("change", ["unknown", "self", "cycle", "duplicate-id", "duplicate-edge"])
def test_rejects_invalid_graph_before_donor_simplification(api, change):
    r = sample()
    if change == "unknown": r["nodes"][0]["depends_on"] = ["ghost"]
    if change == "self": r["nodes"][0]["depends_on"] = ["verify"]
    if change == "cycle": r["nodes"][1]["depends_on"] = ["verify"]
    if change == "duplicate-id": r["nodes"][1]["id"] = "build-a"
    if change == "duplicate-edge": r["nodes"][0]["depends_on"] = ["build-a", "build-a"]
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("count", [0, 9])
def test_refuses_graph_outside_canonical_v4_bound(api, count):
    ns = [node(f"n-{i}") for i in range(count)]
    with pytest.raises(api.ProposalError):
        api.prepare_execution_plan(ns, policies={n["id"]: policy() for n in ns},
                                   root_job_id="ROOT", plan_attempt_id="ATT")


@pytest.mark.parametrize("bad", [None, True, {}, "nodes", (node("a"),)])
def test_plain_bounded_node_array_only(api, bad):
    r = sample(); r["nodes"] = bad
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("field,value", [
    ("prompt", "x"*3001), ("prompt", "\ud800"), ("prompt", " bad"),
    ("label", "x"*81), ("category", []), ("role", "admin"),
    ("id", "UPPER"), ("id", "a"*33), ("depends_on", "build-a"),
    ("write_scope", "src/a.py"), ("prompt", "bad\x00value"),
])
def test_node_field_validation(api, field, value):
    r = sample(); r["nodes"][0][field] = value
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("field", ["status", "accepted", "placement", "root_id", "unknown"])
def test_refuses_persisted_status_and_authority_fields(api, field):
    r = sample(); r["nodes"][0][field] = "SENSITIVE_SENTINEL"
    with pytest.raises(api.ProposalError) as exc: api.prepare_execution_plan(**r)
    assert "SENSITIVE_SENTINEL" not in str(exc.value)


@pytest.mark.parametrize("field,value", [
    ("attempt_limit", True), ("attempt_limit", 3), ("review_required", 1),
    ("business_impact", "unknown"), ("cost_class", "expensive"),
    ("requested_authorities", []), ("requested_authorities", ["admin"]),
    ("validation_ids", ["not-a-digest"]), ("allowed_write_paths", ["."]),
])
def test_policy_is_not_inferred_or_coerced(api, field, value):
    r = sample(); r["policies"]["verify"][field] = value
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("change", ["missing", "extra", "extra-field", "no-policy"])
def test_policy_keys_must_exactly_cover_graph(api, change):
    r = sample()
    if change == "missing": del r["policies"]["verify"]
    if change == "extra": r["policies"]["foreign"] = policy()
    if change == "extra-field": r["policies"]["verify"]["placement"] = {"provider": "any"}
    if change == "no-policy": r["policies"] = None
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("path", ["/etc/passwd", "../x", "src/../x", "./src", "src//x",
    "src/", "src\\x", "src/*", "src/?.py", "src/[x]", "C:/x", "~/.hermes", "src/\x00x",
    "src/ bad", "src/bad ", "src/a\nb", "src/\u202eb.py"])
def test_unsafe_scope_refuses(api, path):
    r = sample(); r["nodes"][1]["write_scope"] = [path]
    r["policies"]["build-b"]["allowed_write_paths"] = [path]
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


@pytest.mark.parametrize("left,right", [("src", "src/a.py"), ("src/A.py", "src/a.py"),
    ("src/caf\u00e9.py", "src/cafe\u0301.py"), ("src/a.py", "src/a.py")])
def test_unordered_scope_overlap_including_aliases_refuses(api, left, right):
    r = sample()
    r["nodes"][1]["write_scope"] = [left]
    r["nodes"][2]["write_scope"] = [right]
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def test_transitively_ordered_overlapping_writers_are_allowed(api):
    r = sample()
    r["nodes"] = [node("a", scope=("src/a.py",)), node("b", ("a",)),
                  node("c", ("b",), ("src/a.py",))]
    r["policies"] = {n["id"]: policy(("src",)) for n in r["nodes"]}
    out = api.prepare_execution_plan(**r)
    assert out["topology"]["layers"] == [["a"], ["b"], ["c"]]


@pytest.mark.parametrize("scope,allowed", [("src2/a.py", "src"), ("Src/a.py", "src"),
                                          ("src/cafe\u0301.py", "src/caf\u00e9.py")])
def test_scope_containment_does_not_widen_by_prefix_or_alias(api, scope, allowed):
    r = sample(); r["nodes"][1]["write_scope"] = [scope]
    r["policies"]["build-b"]["allowed_write_paths"] = [allowed]
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def test_metadata_does_not_select_provider_review_or_privilege(api):
    r = sample(); r["nodes"][0]["category"] = "ultrabrain"; r["nodes"][0]["role"] = "review"
    out = api.prepare_execution_plan(**r)
    step = out["plan"]["steps"][-1]
    assert step["review_required"] is False
    assert step["requested_authorities"] == ["READ"]
    assert "placement" not in step


@pytest.mark.parametrize("field,value", [("root_job_id", None), ("root_job_id", ""),
    ("root_job_id", "root with spaces"), ("plan_attempt_id", True), ("plan_attempt_id", "a"*129)])
def test_identity_is_required_data_not_guessed(api, field, value):
    r = sample(); r[field] = value
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def test_vendor_bytes_match_pinned_git_blob():
    path = ROOT / "integrations/hermes_omh/vendor/dag_core.py"
    assert path.exists(), "Pinned donor has not been vendored"
    raw = path.read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == "e4bdf90bb03206b0eed806396196762cb5daa091"
    manifest = json.loads(path.with_name("PROVENANCE.json").read_text())
    assert manifest["commit"] == "5ead1032360edadd4b3a749f234f3830324de3b2"
    assert manifest["files"]["dag_core.py"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert "MIT License" in path.with_name("LICENSE").read_text()


def test_pure_api_has_no_io(api, monkeypatch):
    def forbidden(*args, **kwargs): pytest.fail("Pure proposal attempted IO")
    import builtins, socket, os
    for owner, name in [(builtins, "open"), (socket, "socket"), (os, "open"),
                        (subprocess, "Popen"), (Path, "read_text"), (Path, "read_bytes")]:
        monkeypatch.setattr(owner, name, forbidden)
    assert api.prepare_execution_plan(**sample())["state"] == "PREPARED_NOT_ADMITTED"


def test_plain_object_graph_is_bounded_before_encoding(api):
    r = sample(); deep = []
    for _ in range(100): deep = [deep]
    r["nodes"][0]["prompt"] = deep
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)
    r = sample(); r["nodes"].append(r)
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def cli(raw, *args):
    return subprocess.run([sys.executable, "-m", "integrations.hermes_omh", *args],
                          input=raw, capture_output=True, cwd=ROOT, timeout=10)


def test_cli_roundtrip_uses_actual_canonical_consumer():
    proc = cli(json.dumps(sample()).encode())
    assert proc.returncode == 0, proc.stderr.decode()
    out = json.loads(proc.stdout)
    assert out["state"] == "PREPARED_NOT_ADMITTED"
    assert out["plan"] == _validate_plan(out["plan"], outer=dict(run_id="ATT-PLAN", expected_root_job_id="ROOT-OMH"))
    assert proc.stderr == b""


@pytest.mark.parametrize("raw", [b'{"nodes":[],"nodes":[]}', b'{"a":NaN}', b'{"a":Infinity}',
    b'\xff', b'', b'{}', b'[]', b'['*10000+b']'*10000, pytest.param(b' '*131073, id='oversized-whitespace'),
    b'{"SENSITIVE_SENTINEL": "secret"}', b'{"a":"\\ud800"}'], ids=["duplicate-keys", "nan", "infinity", "invalid-utf8", "empty",
    "empty-object", "array", "deep-nesting", "oversize", "sensitive-key", "unpaired-surrogate"])
def test_cli_refuses_bad_input_without_echo_or_traceback(raw):
    proc = cli(raw)
    assert proc.returncode == 2
    out = json.loads(proc.stdout)
    assert set(out) == {"state", "reason"} and out["state"] == "REFUSED"
    assert "plan" not in out
    assert b"SENSITIVE_SENTINEL" not in proc.stdout + proc.stderr
    assert b"Traceback" not in proc.stdout + proc.stderr
    assert proc.stderr == b""


def test_cli_file_and_help(tmp_path):
    p = tmp_path / "graph.json"; p.write_text(json.dumps(sample()))
    assert cli(b"", "--input", str(p)).returncode == 0
    assert b"proposal" in cli(b"", "--help").stdout.lower()
    link = tmp_path / "link.json"; link.symlink_to(p)
    assert cli(b"", "--input", str(link)).returncode == 2
    assert cli(b"", "--input", str(tmp_path)).returncode == 2
    assert cli(b"", "--input", str(tmp_path / "absent")).returncode == 2


@pytest.mark.parametrize("path", ["src/name.", "src/CON", "src/AUX.py", "src/NUL.txt", "src/COM1"])
def test_cross_platform_ambiguous_path_refuses(api, path):
    r = sample(); r["nodes"][1]["write_scope"] = [path]
    r["policies"]["build-b"]["allowed_write_paths"] = [path]
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def test_bad_cli_arguments_have_value_free_json_diagnostics():
    proc = cli(b"", "--SENSITIVE_SENTINEL")
    assert proc.returncode == 2 and proc.stderr == b""
    assert json.loads(proc.stdout) == {"state": "REFUSED", "reason": "INVALID_INPUT"}
    assert b"SENSITIVE_SENTINEL" not in proc.stdout


def test_eight_nodes_and_every_small_dag_preserve_all_dependencies(api):
    import itertools
    r = sample()
    r["nodes"] = [node(f"n-{i}", [f"n-{i-1}"] if i else []) for i in range(8)]
    r["policies"] = {n["id"]: policy() for n in r["nodes"]}
    assert len(api.prepare_execution_plan(**r)["plan"]["steps"]) == 8
    edges = [(i, j) for i in range(4) for j in range(i)]
    for mask in range(1 << len(edges)):
        parents = {f"n-{i}": [] for i in range(4)}
        for bit, (i, j) in enumerate(edges):
            if mask & (1 << bit): parents[f"n-{i}"].append(f"n-{j}")
        for order in itertools.permutations(range(4)):
            r["nodes"] = [node(f"n-{i}", parents[f"n-{i}"]) for i in order]
            r["policies"] = {n["id"]: policy() for n in r["nodes"]}
            out = api.prepare_execution_plan(**r)
            steps = out["plan"]["steps"]
            ranks = {s["step_id"]: s["ordinal"] for s in steps}
            for s in steps:
                assert s["prerequisite_step_ids"] == parents[s["step_id"]]
                assert all(ranks[p] < s["ordinal"] for p in parents[s["step_id"]])


def test_tests_are_in_incumbent_ci_discovery():
    from scripts.ci_pytest import discover_test_modules
    assert "tests/test_hermes_omh.py" in discover_test_modules(ROOT)


def test_nonplain_object_is_not_coerced_or_inspected(api):
    class Hostile(dict):
        def items(self): raise AssertionError("untrusted mapping was inspected")
    r = sample(); r["policies"] = Hostile(r["policies"])
    with pytest.raises(api.ProposalError): api.prepare_execution_plan(**r)


def test_cli_strings_do_not_confuse_depth_scanner():
    r = sample(); r["nodes"][0]["prompt"] = 'Inspect these literal delimiters: ' + '['*100 + '\\ "quoted"'
    assert cli(json.dumps(r).encode()).returncode == 0
