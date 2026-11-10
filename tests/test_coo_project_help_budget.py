"""Same installed DATA view, original deadlines and drained read ownership.

The inherited current-DATA fixture uses actual local Git publication/adoption,
the installed collector's physical children, bounded Runtime and the issued
Session Bridge. Its credential/PR/source-seal/provider seams stay explicit.
Instrumentation observes original methods/results; it supplies no owner DTO.
No socket, installed enrollment or live provider is used here.
"""
import asyncio
import dataclasses
import hashlib
import time

import pytest

from common.session_bridge_private_contract import SessionBridgeIngressOwner
from control_plane import coo_project_help_read as help_read
from control_plane.project_canonical_data import CanonicalProjectDataMode
from control_plane.workspace_owned_task import remaining_read_seconds
from integrations.executive_mcp import installed as collector_module
from integrations.mastermind_workspace_app.project_discovery import ProjectDiscoveryCapture
from integrations.session_bridge.installed import build_runtime_session_bridge
from tests.test_coo_project_help_authority import (
    qualified_help, full_joined, owner, env, isolated_git_env, identity,
)
from tests.test_workspace_project_git_publisher import git


def _observe_originals(f, monkeypatch):
    views, children, closed = [], [], []
    observe = CanonicalProjectDataMode.observe
    close = ProjectDiscoveryCapture.close
    runner = f.j["collector"]._runner

    def observed(owner, principal, **options):
        view = observe(owner, principal, **options)
        views.append(view)
        return view

    def child(argv, **options):
        entry = next((str(part).rsplit("/", 1)[-1] for part in argv
            if str(part).endswith(("/scripts/agentos_project_discovery_entry.py",
                                  "/scripts/agentos_project_plan_entry.py"))), None)
        if entry is not None:
            bound = collector_module._CANONICAL_PROJECT_DATA.get()
            assert bound is not None and bound[0] is f.j["collector"] and bound[2] == f.work
            children.append((entry, bound[1]))
        return runner(argv, **options)

    def released(capture):
        close(capture)
        closed.append(capture)

    monkeypatch.setattr(CanonicalProjectDataMode, "observe", observed)
    monkeypatch.setattr(ProjectDiscoveryCapture, "close", released)
    monkeypatch.setattr(f.j["collector"], "_runner", child)
    return views, children, closed


def _events(f):
    return [event.to_dict() for event in f.j["runtime"].events.list_events()]


def test_actual_private_help_uses_two_data_views_for_four_original_children(
        qualified_help, monkeypatch, tmp_path):
    f = qualified_help
    views, children, closed = _observe_originals(f, monkeypatch)
    before = _events(f)
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "unused.sock")
    result = asyncio.run(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
    assert result["scope"] == f.scope
    assert result["targets"]["state"] == "AVAILABLE" and result["targets"]["items"] == []
    assert result["observation"]["mission"]["mission_read_state"] == "PARTIAL"
    assert result["execution_authority"] is result["native_origin_attested"] is False
    assert len(views) == len(closed) == 2 and len(children) == 4
    assert views[0] is not views[1]
    for view in views:
        assert [entry for entry, selected in children if selected is view] == [
            "agentos_project_discovery_entry.py", "agentos_project_plan_entry.py"]
        assert view.data_commit == f.j["current"]
        assert view._operation.selected_work_ref == f.work
    assert all(capture._active == [False] for capture in closed)
    assert _events(f) == before


@pytest.mark.parametrize("fault", ["permission", "adoption", "discovery_owner"])
def test_same_view_refuses_late_original_plan_changes(qualified_help, monkeypatch, fault):
    f = qualified_help
    views, children, closed = _observe_originals(f, monkeypatch)
    before = _events(f)
    collector = f.j["collector"]
    original = collector._runner
    changed = []

    def after_plan(argv, **options):
        result = original(argv, **options)
        if not changed and any(str(part).endswith("/scripts/agentos_project_plan_entry.py") for part in argv):
            changed.append(fault)
            if fault == "permission":
                document = f.j["document"]
                document["profiles"][document["primary_profile"]]["enabled"] = False
            elif fault == "adoption":
                # Real canonical DATA movement after the original physical
                # child. No Runtime Event or adopted-source response is edited.
                source = f.source_plan["source"]
                plan_path = f.j["integrator"] / source["path"]
                raw = plan_path.read_bytes()
                amended = raw.replace(b"Observe original project help", b"Observe revised project help")
                assert amended != raw
                plan_path.write_bytes(amended)
                git(f.j["integrator"], "add", source["path"])
                git(f.j["integrator"], "commit", "-m", "Fixture next actual plan revision")
                revision = git(f.j["integrator"], "rev-parse", "HEAD").strip()
                path = f.j["integrator"] / "agentos/decisions/DEC-EG2-HELP.md"
                text = path.read_text()
                assert source["commit"] in text and source["content_sha256"] in text
                path.write_text(text.replace(source["commit"], revision).replace(
                    source["content_sha256"], hashlib.sha256(amended).hexdigest()))
                git(f.j["integrator"], "add", str(path.relative_to(f.j["integrator"])))
                git(f.j["integrator"], "commit", "-m", "Fixture late adoption record movement")
                git(f.j["integrator"], "push", "origin", "main")
            else:
                from integrations.mastermind_workspace_app.project_discovery import InstalledProjectDiscovery
                f.workspace._project_discovery = InstalledProjectDiscovery(f.j["data"]).installed_binding()
        return result

    monkeypatch.setattr(collector, "_runner", after_plan)
    with pytest.raises(ValueError):
        help_read.capture_project_help_authority(f.provider, f.frame)
    assert changed == [fault] and len(views) == 1
    assert [entry for entry, _ in children] == ["agentos_project_discovery_entry.py", "agentos_project_plan_entry.py"]
    assert all(capture._active == [False] for capture in closed)
    assert _events(f) == before


@pytest.mark.parametrize("replacement_kind", ["reissued", "equal_token_copy"])
def test_same_issuer_replacement_does_not_replace_original_read_binding(
        qualified_help, monkeypatch, tmp_path, replacement_kind):
    f = qualified_help
    before = _events(f)
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "unused-binding.sock")
    original = SessionBridgeIngressOwner.handle_frame
    binding = f.workspace._canonical_project_data
    calls = []

    async def replace_after_original_target(owner, frame):
        result = await original(owner, frame)
        calls.append(frame["arguments"]["kind"])
        if len(calls) == 4:
            # Authentic reissuance has a new qualifier callback. The second
            # case is an adversarial equal-valued copy of the original nominal
            # token, retaining every actual owner; it is not a new enrollment.
            replacement = (f.j["data"].installed_binding() if replacement_kind == "reissued"
                else dataclasses.replace(binding))
            assert replacement is not binding and replacement.owner is binding.owner
            if replacement_kind == "equal_token_copy":
                assert replacement == binding
            f.workspace._canonical_project_data = replacement
        return result

    monkeypatch.setattr(SessionBridgeIngressOwner, "handle_frame", replace_after_original_target)
    with pytest.raises(ValueError, match="PROJECT_HELP_UNAVAILABLE"):
        asyncio.run(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
    assert calls == ["fabric_attempt", "codex"] * 2 and _events(f) == before


def test_discovery_cannot_borrow_missing_or_foreign_plan_enrollment(qualified_help, monkeypatch):
    from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData

    f = qualified_help
    views, _, _ = _observe_originals(f, monkeypatch)
    data = f.j["data"]
    foreign = InstalledCanonicalProjectData(collector=data.collector, policy=data.policy,
        load_bindings=data.loader, git_identity=data.identity, events=data.events,
        runtime_guard=data.runtime_guard)
    original = f.workspace._canonical_project_data
    before = _events(f)
    try:
        for binding in (None, foreign.installed_binding()):
            f.workspace._canonical_project_data = binding
            with pytest.raises(ValueError, match="CANONICAL_DATA_UNAVAILABLE"):
                help_read.capture_project_help_authority(f.provider, f.frame)
    finally:
        f.workspace._canonical_project_data = original
    assert views == [] and _events(f) == before


def test_expired_outer_deadline_refuses_before_original_workspace_read(qualified_help, monkeypatch):
    f = qualified_help
    before = _events(f)
    monkeypatch.setattr(f.workspace, "_read_mission_v3", lambda *a, **k: pytest.fail("expired read reached Mission"))
    monkeypatch.setattr(f.workspace, "_read_project_plan", lambda *a, **k: pytest.fail("expired read reached Plan"))
    with pytest.raises(ValueError, match="deadline expired"):
        help_read.capture_project_help_authority(f.provider, f.frame, deadline=time.monotonic() - 1)
    assert _events(f) == before


@pytest.mark.parametrize("stage", ["before_targets", "before_second_capture"])
def test_actual_expiry_stops_next_stage_after_owned_work_closes(
        qualified_help, monkeypatch, tmp_path, stage):
    f = qualified_help
    views, children, closed = _observe_originals(f, monkeypatch)
    before = _events(f)
    bridge = build_runtime_session_bridge(f.j["runtime"], dialogue_socket_path=tmp_path / "unused-expiry.sock")
    actual_capture = help_read.capture_project_help_authority
    actual_target = SessionBridgeIngressOwner.handle_frame
    completed, targets, deadlines = [], [], []

    def capture(*args, **options):
        value = actual_capture(*args, **options)
        completed.append(value)
        deadlines.append(options["deadline"])
        if stage == "before_targets":
            # Actual time elapses after an original owner has returned. The
            # source deadline is never replaced, advanced or supplied by a DTO.
            time.sleep(max(0, options["deadline"] - time.monotonic()) + 0.01)
        return value

    async def target(owner, frame):
        value = await actual_target(owner, frame)
        targets.append(frame["arguments"]["kind"])
        if stage == "before_second_capture" and len(targets) == 4:
            await asyncio.sleep(max(0, deadlines[0] - time.monotonic()) + 0.01)
        return value

    monkeypatch.setattr(help_read, "capture_project_help_authority", capture)
    monkeypatch.setattr(SessionBridgeIngressOwner, "handle_frame", target)
    with pytest.raises(ValueError, match="deadline expired"):
        asyncio.run(f.provider.read_project_help(f.frame, session_bridge_owner=bridge))
    assert len(completed) == len(views) == len(closed) == 1
    assert len(children) == 2 and all(capture._active == [False] for capture in closed)
    assert targets == ([] if stage == "before_targets" else ["fabric_attempt", "codex"] * 2)
    assert _events(f) == before


@pytest.mark.parametrize("invalid", [True, float("nan"), float("inf"), "future"])
def test_deadline_cannot_expand_or_malformed_value_bypass_owner_budget(invalid):
    with pytest.raises(ValueError):
        remaining_read_seconds(invalid, maximum=15.0)
    assert remaining_read_seconds(None, maximum=15.0) == 15.0
    assert remaining_read_seconds(time.monotonic() + 30, maximum=15.0) == 15.0
