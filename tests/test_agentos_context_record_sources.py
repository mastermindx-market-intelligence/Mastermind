"""Current compiler/capture to private snapshot contribution evidence.

Real disposable Git, compiler and installed capture run in the joined cases.
Structural fixtures test the file/receipt boundary without claiming compilation.
No installed service, provider dispatch or learning acceptance is exercised.
"""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest
import yaml

from control_plane import agentos_context_bundle as contract
from integrations.executive_mcp import installed
from integrations.hermes_harness import agentos_memory_provider as memory
from integrations.hermes_harness.tests.test_agentos_memory_provider import (
    FakeOwner, ManualSpawn, StaticGuard, StaticResolver, _binding,
)
from tests.test_installed_current_agentos_context import (
    acquire, context_child, decode, existing_project, joined, owner, env, isolated_git_env, identity,
)
from tests.test_installed_agentos_context import write_record
from tests.test_workspace_project_git_publisher import git


def test_actual_capture_binds_record_bytes_to_data_not_code(joined, monkeypatch):
    j = joined
    context_child(j, monkeypatch)
    body, _, _ = acquire(j)
    raw, receipt = decode(body, j["args"]["work_ref"])
    assert receipt["schema"] == contract.CURRENT_RECEIPT_SCHEMA_V2
    assert receipt["compiler_code_commit"] == j["code"] != j["current"]
    inventory = receipt["selected_record_sources"]
    assert inventory["data_commit"] == j["current"]
    assert inventory["coverage"] == "PARTIAL" and inventory["retention"] == "COMPLETE"
    path = "agentos/workstreams/" + j["args"]["work_ref"].replace(":", "-") + ".md"
    entry = next(item for item in inventory["entries"] if item["path"] == path)
    content = git(j["integrator"], "show", j["current"] + ":" + path).encode()
    assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert entry["git_blob"] == installed._git_blob_oid(content)
    assert entry["bytes"] == len(content)
    bundle = json.loads(raw)
    for section, item_index in entry["uses"]:
        selected = bundle["sections"][section]["items"][item_index]
        assert selected["path"] == path and selected["kind"] in {"workstream", "constraint"}
    assert inventory["bundle_sha256"] == hashlib.sha256(raw).hexdigest()


def test_actual_selected_omitted_superseded_and_pointer_sources_differ(tmp_path, monkeypatch):
    def changes(macro, seen):
        record = yaml.safe_load(seen["record"].read_text().split("---", 2)[1])
        names = [f"CURRENT-{i:02}" for i in range(40)]
        record["discoveries"] = ["DSC:OLD"] + ["DSC:" + name for name in names]
        record["artifacts"] = ["macro:agentos/discoveries/DSC-POINTER.md"]
        write_record(seen["record"], record)
        for name in ["OLD", "REPLACEMENT", "POINTER", *names]:
            value = {"key": name, "claim": name + ": " + "bounded authored evidence " * 30,
                "falsifier": "pytest tests/test_evidence.py", "so_what": "Preserve its exact source.",
                "kind": "architecture", "verified_at": "2026-11-01", "verified_by": "pytest tests/test_evidence.py",
                "scope": ["macro"], "confidence": "verified"}
            if name == "OLD":
                value["superseded_by"] = "DSC:REPLACEMENT"
            write_record(macro / ("agentos/discoveries/DSC-" + name + ".md"), value)
    _, _, _, read = existing_project(tmp_path, monkeypatch, source_changes=changes)
    raw, receipt = read()
    bundle = json.loads(raw)
    inventory = receipt["selected_record_sources"]
    assert inventory["retention"] == "COMPLETE"
    paths = {entry["path"] for entry in inventory["entries"]}
    selected = {item["path"] for section in bundle["sections"] for item in section["items"]
                if item["kind"] == "discovery"}
    omitted = {item["path"] for item in bundle["omitted_due_to_budget"] if item["kind"] == "discovery"}
    assert selected and omitted and selected <= paths and not paths & omitted
    assert any(item["key"] == "DSC:OLD" for item in bundle["excluded"])
    for key in ("OLD", "REPLACEMENT", "POINTER"):
        assert "agentos/discoveries/DSC-" + key + ".md" not in paths
    assert any(item["kind"] == "artifact" and item["path"].endswith("DSC-POINTER.md")
               for section in bundle["sections"] for item in section["items"]) or any(
                   item["kind"] == "artifact" for item in bundle["omitted_due_to_budget"])
    assert inventory["coverage"] == "PARTIAL"


def item(kind="workstream", key="WS:ONE", path="agentos/workstreams/WS-ONE.md"):
    return {"kind": kind, "key": key, "path": path, "locator": path + "#frontmatter",
        "authority_class": "A4", "status": "active", "updated": None,
        "excerpt": "A selected contribution", "why_included": "Compiler-selected fixture"}


def selected_bundle(rows=None):
    return {"schema": "context_bundle.v1", "target": {"workstream": "WS:ONE"},
        "sections": rows or [{"id": "workstream", "items": [item()]}],
        "degraded": [], "excluded": [], "omitted_due_to_budget": []}


def capture(tmp_path, bundle, contents=None, *, corrupt=None):
    uses = contract.selected_record_uses(bundle, work_ref="WS:ONE")
    objects = {}
    for path in uses:
        raw = (contents or {}).get(path, b"Exact source bytes\n")
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        objects[path] = ("100644", installed._git_blob_oid(raw))
    plan = SimpleNamespace(head="b" * 40, file_objects=objects)
    if corrupt:
        corrupt(tmp_path, plan)
    raw = json.dumps(bundle).encode()
    value = installed._agentos_selected_record_sources(tmp_path, plan, raw=raw, bundle=bundle,
        work_ref="WS:ONE", remaining=lambda: 1.0)
    return raw, value


def test_record_deduplication_preserves_all_uses_and_equal_bytes_at_distinct_paths(tmp_path):
    constraint = {**item(), "kind": "constraint", "locator": "agentos/workstreams/WS-ONE.md#landmines"}
    dependency = item("dependency", "WS:TWO", "agentos/workstreams/WS-TWO.md")
    bundle = selected_bundle([{"id": "workstream", "items": [item(), constraint, dependency]},
        {"id": "handoff", "items": [item("handoff", "WS:ONE", "agentos/handoffs/ordinary-transfer.md")]},
        {"id": "artifacts", "items": [{**item(), "kind": "artifact"}]}])
    _, inventory = capture(tmp_path, bundle)
    assert len(inventory["entries"]) == 3 and inventory["selected_items"] == 4
    assert len({entry["sha256"] for entry in inventory["entries"]}) == 1
    assert next(entry for entry in inventory["entries"] if entry["path"].endswith("WS-ONE.md"))["uses"] == [[0, 0], [0, 1]]
    assert inventory["retention"] == "COMPLETE" and inventory["coverage"] == "PARTIAL"


@pytest.mark.parametrize("change", [
    lambda b: b["sections"][0].update(id="discoveries"),
    lambda b: b["sections"][0]["items"][0].update(key="WS:FOREIGN"),
    lambda b: b["sections"][0]["items"][0].update(kind="new_unqualified_kind"),
    lambda b: b["sections"][0]["items"][0].update(path="agentos/workstreams/../WS-ONE.md"),
    lambda b: b["sections"][0]["items"][0].update(path="/agentos/workstreams/WS-ONE.md"),
    lambda b: b["sections"][0]["items"][0].update(locator="agentos/workstreams/WS-ONE.md#unread-body"),
    lambda b: b["sections"][0]["items"][0].update(extra_origin="invented"),
])
def test_unqualified_selected_item_is_not_inventory_overflow(change):
    bundle = selected_bundle()
    change(bundle)
    with pytest.raises(contract.AgentOsContextUnavailable):
        contract.selected_record_uses(bundle, work_ref="WS:ONE")


@pytest.mark.parametrize("bad", ["blob", "mode", "symlink", "membership"])
def test_plan_integrity_failure_refuses_capture(tmp_path, bad):
    def corrupt(root, plan):
        path = "agentos/workstreams/WS-ONE.md"
        if bad == "blob":
            (root / path).write_text("Different bytes\n")
        elif bad == "mode":
            plan.file_objects[path] = ("120000", plan.file_objects[path][1])
        elif bad == "membership":
            del plan.file_objects[path]
        else:
            (root / "outside.md").write_text("Exact source bytes\n")
            (root / path).unlink()
            (root / path).symlink_to(root / "outside.md")
    with pytest.raises(installed.GatewayError):
        capture(tmp_path, selected_bundle(), corrupt=corrupt)


@pytest.mark.parametrize("reason", ["INVENTORY_BYTES", "RECORD_BYTES"])
def test_evidence_overflow_keeps_context_and_explicit_missing_count(tmp_path, reason):
    bundle = selected_bundle()
    contents = None
    if reason == "INVENTORY_BYTES":
        bundle["sections"][0]["items"] += [item("dependency", f"WS:DEP-{i}",
            f"agentos/workstreams/WS-DEP-{i}.md") for i in range(40)]
    else:
        contents = {"agentos/workstreams/WS-ONE.md": b"x" * (contract.MAX_RECORD_SOURCE_BYTES + 1)}
    before = deepcopy(bundle)
    raw, inventory = capture(tmp_path, bundle, contents)
    assert bundle == before and json.loads(raw) == before
    assert inventory["retention"] == "OVERFLOW" and inventory["coverage"] == "PARTIAL"
    assert inventory["overflow_reason"] == reason
    assert inventory["entries"] == [] and inventory["retained_items"] == 0
    assert inventory["omitted_items"] == inventory["selected_items"] > 0
    assert len(json.dumps(inventory).encode()) < contract.MAX_RECORD_INVENTORY_BYTES


@pytest.fixture
def actual_receipt(tmp_path, monkeypatch):
    _, _, _, read = existing_project(tmp_path, monkeypatch)
    return read()


@pytest.mark.parametrize("change", [
    lambda r: r["selected_record_sources"].update(data_commit="f" * 40),
    lambda r: r["selected_record_sources"].update(coverage="COMPLETE"),
    lambda r: r["selected_record_sources"].update(omitted_items=1),
    lambda r: r["selected_record_sources"]["entries"][0]["uses"][0].__setitem__(0, True),
    lambda r: r["selected_record_sources"]["entries"][0].update(path="agentos/workstreams/WS-FOREIGN.md"),
])
def test_conflicting_inventory_refuses_even_if_resealed(actual_receipt, change):
    raw, receipt = actual_receipt
    changed = deepcopy(receipt)
    change(changed)
    inventory = changed["selected_record_sources"]
    inventory["inventory_sha256"] = contract.canonical_digest({k: v for k, v in inventory.items() if k != "inventory_sha256"})
    with pytest.raises(contract.AgentOsContextUnavailable):
        contract.validate_current_context_read(raw, changed, work_ref="WS:ONE")


def make_provider(raw, receipt):
    binding = _binding(workstream="WS:ONE", max_context_bytes=memory.MAX_HOST_CONTEXT_BYTES)
    guard, spawn = StaticGuard(), ManualSpawn()
    provider = memory.create_provider(ports=memory.AgentOsHostPorts(
        StaticResolver({binding.session_id: binding}), guard),
        reader=FakeOwner({"WS:ONE": (raw, receipt)}).read, spawn=spawn)
    provider.initialize(session_id=binding.session_id, hermes_home=binding.hermes_home,
                        agent_identity=binding.profile)
    provider.prepare_context()
    spawn.run_all()
    return provider, guard


def test_v2_self_contained_bundle_identity_cannot_be_changed_by_resealing(actual_receipt):
    raw, receipt = actual_receipt
    changes = [
        lambda b: b.update(repo_sha="f" * 40),
        lambda b: b.update(token_budget=3999),
        lambda b: b.update(generated_at="2026-01-01T00:00:00Z"),
        lambda b: b["degraded"].append("changed accounting"),
        lambda b: b["omitted_due_to_budget"].append({"kind": "artifact", "path": "unread.md"}),
    ]
    for change in changes:
        bundle = json.loads(raw)
        change(bundle)
        changed_raw = json.dumps(bundle).encode()
        changed = deepcopy(receipt)
        changed["bundle_sha256"] = hashlib.sha256(changed_raw).hexdigest()
        inventory = changed["selected_record_sources"]
        inventory["bundle_sha256"] = changed["bundle_sha256"]
        inventory["inventory_sha256"] = contract.canonical_digest({k: v for k, v in inventory.items() if k != "inventory_sha256"})
        with pytest.raises(contract.AgentOsContextUnavailable):
            contract.validate_current_context_read(changed_raw, changed, work_ref="WS:ONE")


def test_private_snapshot_keeps_full_receipt_without_claiming_delivery(actual_receipt):
    raw, receipt = actual_receipt
    provider, guard = make_provider(raw, receipt)
    observed = provider.context_observation()
    assert observed is not None and provider.readiness()["context_supplied"] is False
    private = provider._record_sources_observation(rendered_context_sha256=observed["rendered_context_sha256"])
    assert private == receipt["selected_record_sources"]
    assert observed["receipt_sha256"] == contract.canonical_digest(receipt)
    assert set(observed) == {"bundle_sha256", "receipt_sha256", "rendered_context_sha256", "rendered_context_bytes", "remaining_ms"}
    private["entries"].clear()
    assert provider._record_sources_observation(rendered_context_sha256=observed["rendered_context_sha256"])["entries"]
    text = provider.prefetch("a model query cannot select another inventory")
    envelope, verbatim = text.split("Owner-produced context_bundle.v1 (verbatim):\n")
    assert verbatim == raw.decode() and '"entries"' not in envelope
    assert '"schema": "mastermind.agentos_context_prompt_observation.v1"' in envelope
    assert '"source_receipt_schema": "mastermind.agentos_current_context_receipt.v2"' in envelope
    assert provider._record_sources_observation(rendered_context_sha256="f" * 64) is None
    guard.revoked = frozenset({"session-alpha"})
    assert provider._record_sources_observation(rendered_context_sha256=observed["rendered_context_sha256"]) is None


def test_historical_v1_receipt_and_rendering_are_not_upgraded(actual_receipt):
    raw, receipt = actual_receipt
    legacy = {k: v for k, v in receipt.items() if k != "selected_record_sources"}
    legacy["schema"] = contract.CURRENT_RECEIPT_SCHEMA
    assert contract.validate_current_context_read(raw, legacy, work_ref="WS:ONE") == (raw, legacy)
    provider, _ = make_provider(raw, legacy)
    observed = provider.context_observation()
    assert provider._record_sources_observation(rendered_context_sha256=observed["rendered_context_sha256"]) is None
    assert '"schema": "mastermind.agentos_current_context_receipt.v1"' in provider.prefetch("q")
    mixed = {**legacy, "selected_record_sources": receipt["selected_record_sources"]}
    with pytest.raises(contract.AgentOsContextUnavailable):
        contract.validate_current_context_read(raw, mixed, work_ref="WS:ONE")
