"""Actual captured Macro CLI through the installed source/materialization owner.

Records and CF2 attestation are explicit fixtures. The compiler, helper, isolated
child, Git observations and process runner are real; this is not host enrollment.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import zlib

import pytest
import yaml

from control_plane import agentos_context_bundle as context
from control_plane import ceo_boot_packet
from integrations.executive_mcp import installed
from integrations.executive_mcp.schemas import GatewayError
from tests.test_agentos_project_plan_source import RECORD
from tests.test_installed_product_acceptance_context import fixture

ROOT = Path(__file__).resolve().parents[1]
WORK = "WS:ONE"
ENTRY = ROOT / "scripts/agentos_context_bundle_entry.py"


def commit(root):
    subprocess.run(["git", "-C", str(root), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "captured owner and authored context"],
                   check=True, capture_output=True)
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def write_record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("---\n" + yaml.safe_dump(value, sort_keys=False) + "---\nAuthored fixture body.\n")


def bound(tmp_path, monkeypatch, *, mutate_result=None, source_changes=None, attest_change=None):
    collector, _, seen = fixture(tmp_path)
    seen["record"].unlink()
    macro = seen["macro"]
    captured = json.loads((ROOT / "tests/fixtures/agentos-project-plan-owner-contract.json").read_bytes())
    for item in captured["files"]:
        raw = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        assert installed._git_blob_oid(raw) == item["blob"]
        target = macro / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    record = macro / "agentos/workstreams/WS-ONE.md"
    record.write_text(RECORD.replace("next_action:", "do_not_redo: [DNR:KEEP-OWNER]\nnext_action:"))
    config = macro / "config"
    config.mkdir()
    (config / "mastermind_programs.yml").write_text("programs:\n  executive-os:\n    title: Executive OS\n")
    (config / "context_index.yml").write_text("projects: {}\n")
    (config / "compiled_kill_registry.yml").write_text(
        "entries:\n  - key: KEEP-OWNER\n    topic: Preserve the canonical context owner\n"
        "    verdict: reject\n    source: fixture\n    section_name: source ownership\n")
    # A typed DEC forces the captured compiler to execute its real sibling
    # helper during load_store/check_decision, not only list its digest.
    write_record(macro / "agentos/decisions/DEC-PLAN.md", {
        "key": "PLAN", "question": "Which plan?", "answer": "The declared source.",
        "rationale": "Fixture adoption.", "alternatives": [{"option": "Infer", "why_not": "No."}],
        "evidence": ["Fixture"], "affects": [WORK], "confidence": "high",
        "reversibility": "easy", "decided_by": "fixture-owner", "decided_at": "2026-11-04",
        "project_plan_adoption": {"schema": "agentos.project_plan_adoption.v1", "work_ref": WORK,
            "adopted_source": {"repository": "mastermindx-market-intelligence/macro",
                "path": "planning/base.md", "commit": "b" * 40, "content_sha256": "c" * 64},
            "predecessor": None, "proposal_source": None, "display_revision": None},
    })
    seen.update(record=record, code=ROOT, python=Path(sys.executable).absolute(), attests=[], results=[])
    if source_changes:
        source_changes(macro, seen)
    seen["sha"] = commit(macro)
    collector._code_root = ROOT
    collector._python = seen["python"]
    site = Path(yaml.__file__).resolve().parent.parent
    # Test-only stand-in for the separately tested CF2 host custody owner.
    # These fake RECORD/tree commitments must never be called production proof.
    contract = SimpleNamespace(site_packages=site, python_binary=seen["python"],
        python_version=sys.version.split()[0], python_binary_sha256="a" * 64,
        pyyaml_version=yaml.__version__, pyyaml_record_sha256="b" * 64,
        runtime_tree_sha256="c" * 64)
    monkeypatch.setattr(ceo_boot_packet, "_capacity_runtime_contract", lambda: contract)

    def attestor(python, *, runner):
        assert python == seen["python"]
        seen["attests"].append(python)
        if attest_change:
            return attest_change(contract, runner, seen)
        return site

    monkeypatch.setattr(ceo_boot_packet, "attest_capacity_boot_runtime", attestor)

    def runner(argv, **limits):
        seen["calls"].append((list(argv), dict(limits)))
        if argv[0] == "git":
            return installed._default_packet_runner(argv, **limits)
        assert Path(argv[4]) == ENTRY
        child = Path(argv[argv.index("--macro-root") + 1])
        seen["child_macro"] = child
        seen["materialized_files"] = sorted(str(path.relative_to(child)) for path in child.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(child).parts)
        result = installed._default_packet_runner(argv, **limits)
        seen["results"].append(copy.deepcopy(result))
        if mutate_result:
            mutate_result(result, child, seen)
        return result

    collector._runner = runner
    return collector, seen


def test_actual_compiler_helper_and_exact_bytes_through_incumbent_owner(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.agentos_context_reader(macro_root=seen["macro"])
    raw, receipt = reader.read(work_ref=WORK)
    assert raw == seen["results"][0]["stdout"].encode("utf-8")
    bundle = json.loads(raw)
    assert bundle["schema"] == "context_bundle.v1"
    assert bundle["target"]["workstream"] == WORK
    assert bundle["repo_sha"] == seen["sha"]
    assert b"DNR:KEEP-OWNER" in raw and b"Preserve the canonical context owner" in raw
    assert b"DEC:PLAN" in raw
    assert not any("PLAN_CONTRACT" in str(x) or "DEC-PLAN" in str(x) for x in bundle["degraded"])
    assert receipt["compiler_code_commit"] == receipt["data_commit"] == seen["sha"]
    assert receipt["bundle_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["source_mode"] == "ADOPTED_SNAPSHOT" and receipt["execution_authority"] is False
    assert receipt["compiler_sources_scope"] == "fixed_macro_entry_and_helper"
    assert {x["path"] for x in receipt["compiler_sources"]} == context.REQUIRED_COMPILER_PATHS
    assert receipt["source_inventory_files"] == len(seen["materialized_files"])
    assert context.validate_context_read(raw, receipt, work_ref=WORK) == (raw, receipt)
    assert len(seen["attests"]) == 2
    child_calls = [(a, k) for a, k in seen["calls"] if a[0] != "git"]
    assert len(child_calls) == 1
    argv, limits = child_calls[0]
    assert argv[:5] == [str(seen["python"]), "-I", "-S", "-B", str(ENTRY)]
    assert limits["max_bytes"] == context.MAX_BUNDLE_BYTES and 0 < limits["timeout"] <= 25
    assert seen["child_macro"] != seen["macro"] and not seen["child_macro"].exists()
    assert not collector._collections


@pytest.mark.parametrize("target", ["live_record", "child_record", "live_helper", "child_helper", "context_config"])
def test_original_and_materialized_mutate_restore_refuse(tmp_path, monkeypatch, target):
    def mutate(result, child, seen):
        path = {"live_record": seen["record"], "child_record": child / "agentos/workstreams/WS-ONE.md",
            "live_helper": seen["macro"] / "scripts/agentos_project_plan_contract.py",
            "child_helper": child / "scripts/agentos_project_plan_contract.py",
            "context_config": child / "config/context_index.yml"}[target]
        raw = path.read_bytes()
        path.write_bytes(raw + b"\n# transient mutation\n")
        path.write_bytes(raw)
    collector, seen = bound(tmp_path, monkeypatch, mutate_result=mutate)
    with pytest.raises(GatewayError):
        collector.read_agentos_context(work_ref=WORK)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("bad", ["commit", "budget", "target", "duplicate", "nonfinite", "oversize", "utf8", "timeout", "limit", "code_bool", "stderr_type", "flag_type"])
def test_malformed_or_conflicting_original_child_result_refuses(tmp_path, monkeypatch, bad):
    def mutate(result, child, seen):
        bundle = json.loads(result["stdout"])
        if bad == "commit": bundle["repo_sha"] = "f" * 40
        elif bad == "budget": bundle["token_budget"] = 3999
        elif bad == "target": bundle["target"]["workstream"] = "WS:FOREIGN"
        elif bad == "duplicate": result["stdout"] = '{"schema":"context_bundle.v1",' + result["stdout"][1:]; return
        elif bad == "nonfinite": bundle["token_budget"] = float("nan")
        elif bad == "oversize": result["stdout"] += " " * context.MAX_BUNDLE_BYTES; return
        elif bad == "utf8": result["stdout"] += "\ud800"; return
        elif bad == "timeout": result["timed_out"] = True; return
        elif bad == "limit": result["limit_exceeded"] = True; return
        elif bad == "code_bool": result["code"] = False; return
        elif bad == "stderr_type": result["stderr"] = None; return
        elif bad == "flag_type": result["invalid_utf8"] = 0; return
        result["stdout"] = json.dumps(bundle)
    collector, seen = bound(tmp_path, monkeypatch, mutate_result=mutate)
    with pytest.raises(GatewayError): collector.read_agentos_context(work_ref=WORK)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("kind", ["bare", "copied", "retarget", "callback"])
def test_nominal_reader_cannot_be_forged_copied_or_retargeted(tmp_path, monkeypatch, kind):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.agentos_context_reader(macro_root=seen["macro"])
    if kind == "bare": reader = context.AgentOsContextBundleReader(macro_root=seen["macro"])
    elif kind == "copied": reader = copy.copy(reader)
    elif kind == "retarget": collector._python = Path("/foreign/python")
    else: collector.read_agentos_context = lambda **kw: (b"{}", {})
    with pytest.raises(context.AgentOsContextUnavailable): reader.read(work_ref=WORK)
    assert seen["calls"] == []


@pytest.mark.parametrize("scope", [installed._CANONICAL_PROJECT_DATA, installed._CANONICAL_PROJECT_COMPILATION])
def test_adopted_read_never_inherits_latest_data_scope(tmp_path, monkeypatch, scope):
    collector, seen = bound(tmp_path, monkeypatch)
    token = scope.set(object())
    try:
        with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE"):
            collector.read_agentos_context(work_ref=WORK)
    finally: scope.reset(token)
    assert seen["calls"] == []


@pytest.mark.parametrize("timeout", [True, 0, -1, 25.1, float("nan"), float("inf")])
def test_invalid_deadline_refuses_before_acquisition(tmp_path, monkeypatch, timeout):
    collector, seen = bound(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="SOURCE_UNAVAILABLE"):
        collector.read_agentos_context(work_ref=WORK, timeout=timeout)
    assert seen["calls"] == []


def _add_artifacts(seen, paths):
    record = seen["record"]
    record.write_text(record.read_text().replace("repos: [macro]",
        "repos: [macro]\nartifacts: " + json.dumps(["macro:" + path for path in paths])))


def test_materialized_shadows_cannot_replace_runtime_or_dependencies(tmp_path, monkeypatch):
    marker = tmp_path / "shadow-executed"
    paths = ["yaml.py", "_yaml.py", "_strptime.py", "context_artifact.py"]
    def sources(macro, seen):
        for path in paths:
            (macro / path).write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n")
        _add_artifacts(seen, paths)
    collector, seen = bound(tmp_path, monkeypatch, source_changes=sources)
    raw, receipt = collector.read_agentos_context(work_ref=WORK)
    assert all(path in seen["materialized_files"] for path in paths)
    assert not marker.exists()
    assert receipt["source_inventory_files"] > len(receipt["compiler_sources"])
    assert not any(x["path"] in paths for x in receipt["compiler_sources"])
    assert b"context_artifact.py" in raw


@pytest.mark.parametrize("mode", ["lazy_stdlib", "artifact", "absent_optional"])
def test_import_policy_with_actual_owner_function_and_no_live_path_fallback(tmp_path, monkeypatch, mode):
    marker = tmp_path / "import-executed"
    def sources(macro, seen):
        payload = "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n"
        for path in ("_strptime.py", "context_artifact.py"):
            (macro / path).write_text(payload)
        _add_artifacts(seen, ["_strptime.py", "context_artifact.py"])
    _, seen = bound(tmp_path, monkeypatch, source_changes=sources)
    # This separately tests the child import policy against the real owner
    # function. The fixed CLI does not pass --now, so this is not a claim that
    # its ordinary context path exercised _parse_moment's fallback.
    program = """
import importlib.util, pathlib, runpy, sys
spec=importlib.util.spec_from_file_location('fixed_context_child',sys.argv[1])
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
clean=entry._qualify_import_paths(pathlib.Path(sys.argv[3]))
owner=runpy.run_path(str(pathlib.Path(sys.argv[2])/'scripts/agentos.py'))
mode=sys.argv[4]
if mode=='lazy_stdlib':
    value=owner['_parse_moment']('2026-1-2')
    assert value.year==2026 and value.month==1 and value.day==2
elif mode=='artifact':
    try: __import__('context_artifact')
    except ImportError: pass
else:
    try: __import__('this_optional_module_is_absent')
    except ImportError: pass
try: clean()
except ValueError: print('REFUSED')
else: print('CLEAN')
"""
    result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c", program, str(ENTRY),
        str(seen["macro"]), str(Path(yaml.__file__).resolve().parent.parent), mode],
        capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == (b"REFUSED\n" if mode == "artifact" else b"CLEAN\n")
    assert not marker.exists()


def test_matching_helper_bytecode_artifact_is_refused_before_execution(tmp_path, monkeypatch):
    from importlib._bootstrap_external import _code_to_hash_pyc
    marker = tmp_path / "helper-cache-executed"
    def sources(macro, seen):
        helper = macro / "scripts/agentos_project_plan_contract.py"
        cache = Path(importlib.util.cache_from_source(str(helper)))
        cache.parent.mkdir()
        malicious = compile("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n",
                            str(helper), "exec")
        cache.write_bytes(_code_to_hash_pyc(malicious, importlib.util.source_hash(helper.read_bytes()), checked=True))
        _add_artifacts(seen, [str(cache.relative_to(macro))])
        # Establish that this is a valid source-matching pyc for the unmodified
        # standard loader, rather than an irrelevant or corrupt cache file.
        control = subprocess.run([sys.executable, "-I", "-S", "-B", "-c",
            "import importlib.util,sys;s=importlib.util.spec_from_file_location('helper',sys.argv[1]);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)", str(helper)],
            capture_output=True, timeout=10)
        assert control.returncode == 0 and marker.read_text() == "executed"
        marker.unlink()
    collector, seen = bound(tmp_path, monkeypatch, source_changes=sources)
    with pytest.raises(GatewayError): collector.read_agentos_context(work_ref=WORK)
    assert not marker.exists() and not seen["child_macro"].exists()
    assert seen["results"][0]["stdout"] == "" and seen["results"][0]["stderr"] == ""


@pytest.mark.parametrize("stage", [1, 2])
def test_attestor_overrun_refuses_late_result_without_renewing_budget(tmp_path, monkeypatch, stage):
    expired = False
    original = installed._remaining_deadline_seconds
    def remaining(*args, **kwargs):
        if expired: raise TimeoutError("fixture synchronous attestor overrun")
        return original(*args, **kwargs)
    def attest(contract, runner, seen):
        nonlocal expired
        if len(seen["attests"]) == stage: expired = True
        return contract.site_packages
    collector, seen = bound(tmp_path, monkeypatch, attest_change=attest)
    monkeypatch.setattr(installed, "_remaining_deadline_seconds", remaining)
    with pytest.raises(GatewayError, match="cumulative deadline"):
        collector.read_agentos_context(work_ref=WORK)
    assert len(seen["results"]) == (0 if stage == 1 else 1)
    assert len(seen["attests"]) == stage
    assert not seen.get("child_macro", tmp_path / "absent").exists()


def test_runtime_probe_uses_original_remaining_budget_and_commitment(tmp_path, monkeypatch):
    seen = []
    contract = SimpleNamespace(site_packages=tmp_path / "dependencies", python_binary=tmp_path / "python",
        python_version="3.12.14", python_binary_sha256="a" * 64, pyyaml_version="6.0.3",
        pyyaml_record_sha256="b" * 64, runtime_tree_sha256="c" * 64)
    monkeypatch.setattr(ceo_boot_packet, "_capacity_runtime_contract", lambda: contract)
    def attest(python, *, runner):
        runner([str(python), "fixture probe"], timeout=10.0, max_bytes=64)
        return contract.site_packages
    monkeypatch.setattr(ceo_boot_packet, "attest_capacity_boot_runtime", attest)
    budgets = iter([4.0, 3.0, 2.0])
    site, receipt = installed._agentos_context_runtime(contract.python_binary,
        runner=lambda argv, **kw: seen.append((argv, kw)), remaining=lambda: next(budgets))
    assert site == contract.site_packages and seen[0][1]["timeout"] == 3.0
    assert receipt["owner"] == "cf2_capacity_runtime" and receipt["runtime_tree_sha256"] == "c" * 64


def test_runtime_change_after_compilation_withholds_original_bytes(tmp_path, monkeypatch):
    def attest(contract, runner, seen):
        if len(seen["attests"]) == 2: contract.runtime_tree_sha256 = "d" * 64
        return contract.site_packages
    collector, seen = bound(tmp_path, monkeypatch, attest_change=attest)
    with pytest.raises(GatewayError, match="runtime changed"):
        collector.read_agentos_context(work_ref=WORK)
    assert len(seen["results"]) == 1 and not seen["child_macro"].exists()


def test_cleanup_uncertainty_has_no_retry_or_partial_return(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    original = collector._runner
    def runner(argv, **limits):
        result = original(argv, **limits)
        if argv[0] != "git": raise RuntimeError("fixture process-group settlement uncertain")
        return result
    collector._runner = runner
    with pytest.raises(GatewayError): collector.read_agentos_context(work_ref=WORK)
    assert len(seen["results"]) == 1 and not seen["child_macro"].exists()


def test_mandatory_over_budget_content_and_accounting_are_not_trimmed(tmp_path, monkeypatch):
    def sources(macro, seen):
        seen["record"].write_text(seen["record"].read_text().replace(
            "do_not_redo: [DNR:KEEP-OWNER]", "do_not_redo: " + json.dumps([
                "DNR:KEEP-OWNER", *("Preserve constraint " + str(i) + ": " + "specific obligation " * 40 for i in range(36))])))
    collector, seen = bound(tmp_path, monkeypatch, source_changes=sources)
    raw, receipt = collector.read_agentos_context(work_ref=WORK)
    bundle = json.loads(raw)
    assert bundle["token_estimate"] > bundle["token_budget"]
    assert raw == seen["results"][0]["stdout"].encode()
    assert receipt["omitted_count"] == len(bundle["omitted_due_to_budget"])
    assert receipt["degraded_count"] == len(bundle["degraded"])
    assert "Preserve constraint 35" in raw.decode()


@pytest.mark.parametrize("path", sorted(context.REQUIRED_COMPILER_PATHS))
def test_missing_required_executable_source_refuses_before_child(tmp_path, monkeypatch, path):
    collector, seen = bound(tmp_path, monkeypatch,
        source_changes=lambda macro, seen: (macro / path).unlink())
    with pytest.raises(GatewayError): collector.read_agentos_context(work_ref=WORK)
    assert seen["results"] == [] and seen["attests"] == []


def test_closed_receipt_rejects_false_identity_or_authority(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    raw, receipt = collector.read_agentos_context(work_ref=WORK)
    mutations = [
        lambda r: r.update(execution_authority=True),
        lambda r: r.update(data_commit="f" * 40),
        lambda r: r.update(bundle_sha256="f" * 64),
        lambda r: r.update(import_policy="ambient_paths"),
        lambda r: r.update(deadline_semantics="hard_wall_clock"),
        lambda r: r.update(compiler_sources_scope="all_runtime_code"),
        lambda r: r.update(generated_at="2026-11-07"),
        lambda r: r.update(secret="unexpected"),
        lambda r: r["source_observation"].update(materialized_generation="invalid"),
        lambda r: r["compiler_sources"].append(copy.deepcopy(r["compiler_sources"][0])),
        lambda r: r["runtime_commitment"].update(owner="self_attested"),
        lambda r: r.update(source_inventory_files=True),
    ]
    for mutate in mutations:
        changed = copy.deepcopy(receipt)
        mutate(changed)
        with pytest.raises(context.AgentOsContextUnavailable):
            context.validate_context_read(raw, changed, work_ref=WORK)
