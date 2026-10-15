"""Sealed acquisition contracts; fixture CLI output is not installed Context proof."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from control_plane import agentos_product_acceptance_basis as basis
from integrations.executive_mcp.installed import InstalledBootPacketCollector, _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from tests.test_agentos_product_acceptance_basis import declaration, execution_ref


def fixture(tmp_path, *, mutation=None):
    repo, macro, code = (tmp_path / name for name in ("mastermind", "macro", "release"))
    repo.mkdir(); macro.mkdir(); (code / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("source\n")
    record = macro / "agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md"
    record.parent.mkdir(parents=True)
    record.write_text("---\nid: CHAIRMAN-CONTROL-ROOM\nrepos: []\nartifacts: []\nowns_paths: []\n---\nactual source record\n")
    commits = []
    for root in (repo, macro):
        for args in (("init", "-q"), ("config", "user.email", "test@example.invalid"),
                     ("config", "user.name", "Test"), ("add", "."), ("commit", "-q", "-m", "fixture")):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        commits.append(subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip())
    packet = declaration()
    packet["repo_sha"] = commits[1]
    entry = packet["acceptance_basis"]["by_commission"]["r2-test"]
    entry["source_record_ref"].update(commit=commits[1], content_sha256=hashlib.sha256(record.read_bytes()).hexdigest())
    entry["current_intent_ref"] = copy.deepcopy(entry["source_record_ref"])
    entry["acceptance_basis_digest"] = basis._canonical_digest({k:v for k,v in entry.items() if k != "acceptance_basis_digest"})
    seen = {"calls": [], "record": record, "macro": macro, "code": code, "repo": repo, "sha": commits[1]}
    python = tmp_path / "sealed-python"
    python.write_text("fixture")
    seen["python"] = python

    def runner(argv, **kwargs):
        seen["calls"].append((list(argv), dict(kwargs)))
        if str(argv[0]) == "git":
            return _default_packet_runner(argv, **kwargs)
        child_macro = Path(argv[argv.index("--macro-root") + 1])
        seen["child_macro"] = child_macro
        value = copy.deepcopy(packet)
        if mutation:
            mutation(value, child_macro, seen)
        return {"code": 0, "stdout": json.dumps(value), "stderr": "",
                "timed_out": False, "limit_exceeded": False, "invalid_utf8": False}

    collector = InstalledBootPacketCollector(source_root=repo, macro_root=macro,
        code_root=code, python_executable=python, runner=runner, expected_source_sha=commits[0])
    return collector, packet, seen


def read(collector, **changes):
    args = dict(work_ref="WS:CHAIRMAN-CONTROL-ROOM", execution_commission_ref=execution_ref(),
                root_objective="The actual objective", timeout=10.0)
    args.update(changes)
    return collector.read_product_acceptance_basis(**args)


def test_workstream_basis_uses_exact_sealed_process_and_verified_materialization(tmp_path):
    collector, packet, seen = fixture(tmp_path)
    result = read(collector)
    assert type(result) is basis.ProductAcceptanceBasisRead
    assert result.macro_commit == seen["sha"]
    assert result.entry == packet["acceptance_basis"]["by_commission"]["r2-test"]
    process = [(argv, kw) for argv, kw in seen["calls"] if str(argv[0]) != "git"]
    assert len(process) == 1
    argv, kw = process[0]
    assert argv[:4] == [str(seen["python"]), "-I", "-B", str(seen["code"] / "scripts/ceo_boot_packet.py")]
    assert argv[argv.index("--workstream") + 1] == "CHAIRMAN-CONTROL-ROOM"
    assert argv[argv.index("--expected-macro-sha") + 1] == seen["sha"]
    assert Path(argv[argv.index("--macro-root") + 1]) == seen["child_macro"] != seen["macro"]
    assert kw["cwd"] == seen["code"]
    assert 0 < kw["timeout"] <= 10.0
    assert kw["max_bytes"] <= 262144
    assert any("show" in a and f'{seen["sha"]}:agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md' in a
               for a, _ in seen["calls"])
    assert not seen["child_macro"].exists()
    assert not collector._collections  # Acceptance reads cannot share the global boot key.


@pytest.mark.parametrize("change", ["schema", "workstream", "source_sha", "objective", "commission", "record_digest"])
def test_workstream_basis_refuses_conflicting_owner_output(tmp_path, change):
    def mutate(value, child, seen):
        entry = value["acceptance_basis"]["by_commission"]["r2-test"]
        if change == "schema": value["schema"] = "mastermind.ceo_boot_packet.v1"
        elif change == "workstream": value["target"]["workstream"] = "WS:FOREIGN"
        elif change == "source_sha": value["repo_sha"] = "f" * 40
        elif change == "objective": entry["current_intent_text"] = "Different ask"
        elif change == "commission": entry["execution_commission_refs"] = []
        else:
            entry["source_record_ref"]["content_sha256"] = "0" * 64
            entry["current_intent_ref"] = copy.deepcopy(entry["source_record_ref"])
        entry["acceptance_basis_digest"] = basis._canonical_digest({k:v for k,v in entry.items() if k != "acceptance_basis_digest"})
    collector, _, seen = fixture(tmp_path, mutation=mutate)
    with pytest.raises((basis.ProductAcceptanceBasisUnavailable, GatewayError)):
        read(collector)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("target", ["live", "materialized"])
def test_workstream_basis_refuses_source_mutate_and_restore(tmp_path, target):
    def mutate(value, child, seen):
        record = seen["record"] if target == "live" else child / "agentos/workstreams/CHAIRMAN-CONTROL-ROOM.md"
        original = record.read_bytes()
        record.write_bytes(b"transient source change\n")
        record.write_bytes(original)
    collector, _, seen = fixture(tmp_path, mutation=mutate)
    with pytest.raises(GatewayError, match="changed|differ"):
        read(collector)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("drift", ["callback", "macro", "code", "unbound_sha", "synthetic"])
def test_basis_reader_refuses_unbound_installed_collector(tmp_path, drift):
    macro = tmp_path / "macro"
    collector = InstalledBootPacketCollector(source_root=tmp_path / "source", macro_root=macro,
        code_root=basis._SOURCE_ROOT if drift != "code" else tmp_path / "foreign-code",
        python_executable=tmp_path / "python", expected_source_sha=None if drift == "unbound_sha" else "a" * 40,
        _allow_synthetic_fixture=drift == "synthetic")
    with pytest.raises(ValueError, match="exact sealed source collector"):
        InstalledBootPacketCollector.product_acceptance_basis_reader(
            (lambda **kw: {}) if drift == "callback" else collector,
            macro_root=tmp_path / "foreign" if drift == "macro" else macro)


def test_isolated_basis_reader_uses_only_the_host_composed_collector(tmp_path, monkeypatch):
    from types import SimpleNamespace
    collector, packet, seen = fixture(tmp_path)
    monkeypatch.setattr(basis, "_SOURCE_ROOT", seen["code"])
    monkeypatch.setattr(basis, "sys", SimpleNamespace(flags=SimpleNamespace(isolated=1, no_site=1)))
    def unqualified(*args, **kw):
        pytest.fail("isolated consumer reached the unqualified source acquisition")
    monkeypatch.setattr(basis, "git_sha", unqualified)
    monkeypatch.setattr(basis, "bounded_subprocess_runner", unqualified)
    reader = collector.product_acceptance_basis_reader(macro_root=seen["macro"])
    result = reader.read(work_ref="WS:CHAIRMAN-CONTROL-ROOM", execution_commission_ref=execution_ref(),
                         root_objective="The actual objective")
    assert result.entry == packet["acceptance_basis"]["by_commission"]["r2-test"]
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("value", [0, -1, 16, float("nan"), float("inf"), True])
def test_context_timeout_is_bounded_before_any_source_read(tmp_path, value):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid timeout reached source owner")
    collector = InstalledBootPacketCollector(source_root=tmp_path / "source", macro_root=tmp_path / "macro",
        code_root=tmp_path / "code", python_executable=tmp_path / "python",
        expected_source_sha="a" * 40, runner=forbidden)
    with pytest.raises(basis.ProductAcceptanceBasisUnavailable, match="BASIS_BINDING_UNAVAILABLE"):
        read(collector, timeout=value)


def test_installed_source_refusal_keeps_the_basis_owner_error_contract(tmp_path, monkeypatch):
    collector = InstalledBootPacketCollector(source_root=tmp_path / "source", macro_root=tmp_path / "macro",
        code_root=basis._SOURCE_ROOT, python_executable=tmp_path / "python", expected_source_sha="a" * 40)
    def refused(**kwargs):
        raise GatewayError("backend_unavailable", "installed source changed")
    monkeypatch.setattr(collector, "read_product_acceptance_basis", refused)
    reader = collector.product_acceptance_basis_reader(macro_root=tmp_path / "macro")
    with pytest.raises(basis.ProductAcceptanceBasisUnavailable, match="CONTEXT_OWNER_UNAVAILABLE"):
        reader.read(work_ref="WS:CHAIRMAN-CONTROL-ROOM", execution_commission_ref=execution_ref(),
                    root_objective="The actual objective")


@pytest.mark.parametrize('fault', ['oserror', 'runtimeerror', 'timeout', 'overflow', 'utf8', 'exit'])
def test_record_acquisition_failure_is_unavailability_not_changed_source(tmp_path, monkeypatch, fault):
    collector, packet, seen = fixture(tmp_path)
    monkeypatch.setattr(basis, '_SOURCE_ROOT', seen['code'])
    runner = collector._runner
    def failed(argv, **kwargs):
        if str(argv[0]) == 'git' and 'show' in argv:
            if fault == 'oserror': raise OSError('private helper detail')
            if fault == 'runtimeerror': raise RuntimeError('private helper detail')
            result = runner(argv, **kwargs)
            if fault == 'timeout': result['timed_out'] = True
            elif fault == 'overflow': result['limit_exceeded'] = True
            elif fault == 'utf8': result['invalid_utf8'] = True
            else: result['code'] = 1
            return result
        return runner(argv, **kwargs)
    collector._runner = failed
    reader = collector.product_acceptance_basis_reader(macro_root=seen['macro'])
    with pytest.raises(basis.ProductAcceptanceBasisUnavailable, match='^CONTEXT_OWNER_UNAVAILABLE$') as error:
        reader.read(work_ref='WS:CHAIRMAN-CONTROL-ROOM', execution_commission_ref=execution_ref(),
                    root_objective='The actual objective')
    assert error.value.__cause__ is None
    assert not seen['child_macro'].exists()


@pytest.mark.parametrize('field,value', [('_expected_source_sha', 'f'*40),
    ('_allow_synthetic_fixture', True), ('_python', Path('/foreign/python'))])
def test_bound_collector_cannot_retarget_after_reader_construction(tmp_path, monkeypatch, field, value):
    collector, _, seen = fixture(tmp_path)
    monkeypatch.setattr(basis, '_SOURCE_ROOT', seen['code'])
    reader = collector.product_acceptance_basis_reader(macro_root=seen['macro'])
    setattr(collector, field, value)
    with pytest.raises(basis.ProductAcceptanceBasisUnavailable, match='^CONTEXT_OWNER_UNAVAILABLE$'):
        reader.read(work_ref='WS:CHAIRMAN-CONTROL-ROOM', execution_commission_ref=execution_ref(),
                    root_objective='The actual objective')
    assert seen['calls'] == []
