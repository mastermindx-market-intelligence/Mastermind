"""Real Git/retained-custody reads; no Control socket or installed-account claim."""
import copy
import hashlib
from pathlib import Path

import pytest
import yaml

from common import workspace_discovery_correction_contract as correction
from common import workspace_discovery_original_contract as original
from common import workspace_project_knowledge_read_contract as wire
from common.workspace_project_knowledge_contract import validate_discovery_source
from common.workspace_source_operation_wire import validate_operation_request, operation_response_limit
from control_plane import agentos_project_knowledge as reader
from control_plane.project_source_original_input import ProjectSourceOriginalInput
from control_plane.workspace_source_operations import SourceOperationConflict
from tests.test_project_discovery_correction import correction_owner, old_note, sha, selection
from tests.test_workspace_project_git_publisher import env, isolated_git_env, git, rev_parse


def current(o, **overrides):
    selected = dict(macro_root=o["env"].clone, expected_macro_sha=rev_parse(o["env"].clone, "HEAD"),
        work_ref="WS:ALPHA", discovery_ref="DSC:ORIGINAL-FINDING",
        expected_source_commit=rev_parse(o["env"].clone, "HEAD"))
    return reader.read_project_discovery_source(**dict(selected, **overrides))


def test_exact_current_note_workstream_hash_and_git_blob(correction_owner):
    o = correction_owner
    result = validate_discovery_source(current(o))
    assert result["availability"] == "AVAILABLE", result
    assert result["document"]["content_utf8"] == o["old"]
    assert result["source"]["content_sha256"] == sha(o["old"])
    assert result["source"]["workstream_sha256"] == sha(o["ws"])
    assert result["source"]["revision"] == rev_parse(o["env"].clone, "HEAD:agentos/discoveries/DSC-ORIGINAL-FINDING.md")
    assert result["source"]["revision"] != result["source"]["commit"]


def test_installed_collector_reads_discovery_inside_original_data_capture(tmp_path, monkeypatch):
    from tests.test_installed_current_agentos_context import existing_project
    from tests.discovery_correction_test_support import source_bytes
    from integrations.executive_mcp import installed
    note = old_note().replace("WS:ALPHA", "WS:ONE")
    def source_changes(macro, seen):
        for path in ("scripts/agentos.py", "scripts/project_knowledge_recipes.py"):
            target = macro / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source_bytes(path))
        target = macro / "agentos/discoveries/DSC-ORIGINAL-FINDING.md"
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(note)
        path = seen["record"]
        parts = path.read_text().split("---", 2)
        front = yaml.safe_load(parts[1]); front["discoveries"] = ["DSC:ORIGINAL-FINDING"]
        path.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---" + parts[2])
    collector, seen, _, read = existing_project(tmp_path, monkeypatch, source_changes=source_changes)
    read()  # Actual publisher observation, original canonical DATA view and compiler.
    view = seen["current_view"]
    calls = []
    def runner(argv, **kwargs):
        calls.append(argv)
        return installed._default_packet_runner(argv, **kwargs)
    monkeypatch.setattr(collector, "_runner", runner)
    with view.capture_scope(), collector.canonical_project_data_scope(view, work_ref="WS:ONE"):
        result = collector.read_project_discovery_source(work_ref="WS:ONE",
            discovery_ref="DSC:ORIGINAL-FINDING", expected_source_commit=view.data_commit)
    assert result["availability"] == "AVAILABLE", result
    assert result["source"]["commit"] == view.data_commit
    assert result["document"]["content_utf8"] == note
    assert result["data_observation"]["canonical_data_commit"] == view.data_commit
    assert any(any(str(arg).endswith("scripts/agentos_project_knowledge_entry.py") for arg in argv) for argv in calls)


def test_valid_note_omitted_by_actual_catalogue_is_directly_readable(correction_owner):
    o = correction_owner
    paths = []
    for index in range(72):
        key = "EARLIER-" + str(index).zfill(3)
        path = o["env"].clone / ("agentos/discoveries/DSC-" + key + ".md")
        path.write_text(old_note().replace("key: ORIGINAL-FINDING", "key: " + key))
        paths.append("DSC:" + key)
    ws = o["ws"].replace("\n---\n", "\ndiscoveries: [" + ", ".join(paths) + "]\n---\n", 1)
    (o["env"].clone / "agentos/workstreams/WS-ALPHA.md").write_text(ws)
    git(o["env"].clone, "add", "agentos"); git(o["env"].clone, "commit", "-m", "Bounded sample fixture")
    commit = rev_parse(o["env"].clone, "HEAD")
    catalogue = reader.read_project_knowledge_catalogue(macro_root=o["env"].clone,
        expected_macro_sha=commit, work_ref="WS:ALPHA", timeout=15)
    assert catalogue["availability"] == "AVAILABLE", catalogue
    assert catalogue["project"]["coverage"]["records"]["omitted"] > 0
    assert all(row["path"] != "agentos/discoveries/DSC-ORIGINAL-FINDING.md" for row in catalogue["project"]["records"])
    assert current(o)["document"]["content_utf8"] == o["old"]


@pytest.mark.parametrize("attack", ["stale_data", "foreign", "wrong_key", "duplicate", "malformed", "symlink", "body_budget", "missing"])
def test_current_note_refuses_unqualified_source(correction_owner, attack):
    o = correction_owner
    if attack == "stale_data":
        result = current(o, expected_source_commit="f" * 40)
    else:
        path = o["env"].clone / "agentos/discoveries/DSC-ORIGINAL-FINDING.md"
        if attack == "foreign": path.write_text(o["old"].replace("scope: [WS:ALPHA]", "scope: [WS:OTHER]"))
        elif attack == "wrong_key": path.write_text(o["old"].replace("key: ORIGINAL-FINDING", "key: FOREIGN-FINDING"))
        elif attack == "duplicate": path.write_text(o["old"].replace("key: ORIGINAL-FINDING", "key: ORIGINAL-FINDING\nkey: ORIGINAL-FINDING"))
        elif attack == "malformed": path.write_text("---\nkey: [unclosed\n---\n")
        elif attack == "symlink": path.unlink(); path.symlink_to("../workstreams/WS-ALPHA.md")
        elif attack == "body_budget": path.write_text(o["old"] + "x" * 32768)
        else: path.unlink()
        git(o["env"].clone, "add", "agentos"); git(o["env"].clone, "commit", "-m", "Unqualified source fixture")
        result = current(o)
    assert result["availability"] == "UNAVAILABLE", result
    assert result["source"] is None and result["document"] is None


def test_original_note_survives_current_source_loss_without_compile_or_write(correction_owner, monkeypatch):
    o = correction_owner; preview = o["service"].prepare(o["request"], o["who"])
    lookup = correction.request_lookup(o["request"])
    status = o["service"].read_status(lookup, o["who"])
    before = (list(o["calls"]), len(o["reads"]), len(o["runtime"].store.list_events()), o["pr"].create_calls)
    (o["env"].clone / "scripts/agentos.py").unlink()
    (o["env"].clone / "agentos/discoveries/DSC-ORIGINAL-FINDING.md").unlink()
    monkeypatch.setattr(type(o["compiler"]), "_read", lambda *args, **kwargs: pytest.fail("history must not compile"))
    result = o["service"].read_original(lookup, o["who"])
    assert original.validate(result, lookup=lookup, principal_scope=preview["owner_context"]["principal_scope"]) == result
    assert result["original"]["content_utf8"] == o["old"]
    assert result["custody"] == {"kind": "ORIGINAL_CORRECTION_INPUT", **preview["preview_witness"]}
    assert set(result["original"]) == {"source_commit", "discovery_ref", "content_sha256", "workstream_sha256", "media_type", "content_utf8"}
    assert "data_observation" not in result and "code_context" not in result
    assert o["service"].read_status(lookup, o["who"]) == status
    assert before == (list(o["calls"]), len(o["reads"]), len(o["runtime"].store.list_events()), o["pr"].create_calls)


@pytest.mark.parametrize("field", ["source_commit", "base_revision", "request_sha256", "discovery_ref", "expected_discovery_revision"])
def test_original_note_rejects_changed_full_original_lookup(correction_owner, field):
    o = correction_owner; o["service"].prepare(o["request"], o["who"])
    lookup = correction.request_lookup(o["request"])
    lookup[field] = "DSC:OTHER-FINDING" if field == "discovery_ref" else "f" * (40 if field == "source_commit" else 64)
    with pytest.raises(SourceOperationConflict): o["service"].read_original(lookup, o["who"])


@pytest.mark.parametrize("attack", ["revoke", "actor", "ws_bytes", "note_bytes", "request"])
def test_original_note_rechecks_permission_and_retained_material(correction_owner, monkeypatch, attack):
    o = correction_owner; o["service"].prepare(o["request"], o["who"])
    actual = ProjectSourceOriginalInput.read
    def changed(self, *args, **kwargs):
        result = actual(self, *args, **kwargs)
        if attack == "revoke": o["bindings"]["profiles"]["member-0"]["project_discovery_correct"] = None
        elif attack == "actor": result["actor"]["principal_scope"] = "f" * 64
        elif attack == "ws_bytes": result["initial_snapshot"]["workstream_text"] += "changed"
        elif attack == "note_bytes": result["initial_snapshot"]["discovery_text"] += "changed"
        else: result["request"]["correction_reason"] += " changed"
        return result
    monkeypatch.setattr(ProjectSourceOriginalInput, "read", changed)
    with pytest.raises((ValueError, PermissionError)):
        o["service"].read_original(correction.request_lookup(o["request"]), o["who"])


def test_missing_original_note_never_prepares_or_implies_no_effect(correction_owner):
    o = correction_owner; lookup = correction.request_lookup(o["request"])
    with pytest.raises(SourceOperationConflict): o["service"].read_original(lookup, o["who"])
    status = o["service"].read_status(lookup, o["who"])
    assert status["disposition"] == "unknown" and status["receipt"] is None
    assert o["calls"] == [] and o["pr"].create_calls == 0


def test_new_selector_and_history_operation_do_not_widen_legacy_shapes(correction_owner):
    o = correction_owner
    selected = {"work_ref": "WS:ALPHA", "discovery_ref": "DSC:ORIGINAL-FINDING", "expected_source_commit": o["request"]["source_commit"]}
    assert wire.selection(selected, operation="project_discovery_source") == selected
    with pytest.raises(ValueError): wire.selection(selected, operation="project_knowledge_source")
    with pytest.raises(ValueError): wire.selection(dict(selected, path="private.md"), operation="project_discovery_source")
    lookup = correction.request_lookup(o["request"])
    assert validate_operation_request("read_original", lookup) == lookup
    assert operation_response_limit("read_original") == original.MAX_RESPONSE_BYTES
    with pytest.raises(ValueError): validate_operation_request("read_original", dict(lookup, action="add_project_file"))
