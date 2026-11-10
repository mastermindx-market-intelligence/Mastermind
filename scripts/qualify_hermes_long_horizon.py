#!/usr/bin/env python3
"""Opt-in installed Hermes API qualification in disposable homes, without inference.

Run with the installed Hermes committed dependency-environment interpreter. This explicitly loads the given
source's committed native dependency generation. It does not discover live plugins,
start agents, call models, read credentials or change production profile settings.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile



NATIVE_API_FILES = (
    "hermes_cli/plugins.py", "hermes_cli/plugins_loader.py", "hermes_cli/plugins_dispatch.py",
    "hermes_cli/plugins_ledger.py", "hermes_cli/plugins_content.py", "hermes_cli/plugins_manifest.py",
    "hermes_state.py", "hermes_state_compression.py", "hermes_state_sessions.py",
    "hermes_state_messages.py", "registration_lifecycle.py", "tools/registry.py", "pm/environments.py",
)


def native_fingerprint(root: Path) -> tuple[dict, str]:
    values = {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in NATIVE_API_FILES}
    digest = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return values, digest


def git_head(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()


def fixture():
    return {"schema": "mastermind.project_task_tree.v1", "workstream": "WS:NATIVE-QUALIFICATION",
        "objective": "Preserve the original project across native compaction",
        "requirements": [{"id": "R1", "text": "Preserve reconnect behavior"},
                         {"id": "R2", "text": "Preserve mobile acceptance"}],
        "allowed_paths": ["app"], "non_goals": ["No live model or production mutation"],
        "tasks": [{"id": name, "title": name, "requirement_ids": [req], "depends_on": deps,
                   "acceptance": [{"id": "A1", "text": "Observe the native consumer"}],
                   "state": "pending", "evidence": []}
                  for name, req, deps in (("T1", "R1", []), ("T2", "R2", ["T1"]))]}


def write_plan(path: Path, value: dict) -> None:
    path.write_text("# Qualification fixture\n```mastermind-plan\n" + json.dumps(value) + "\n```\n", encoding="utf-8")


def qualify(root: Path, expected: str, expected_api: str) -> dict:
    if not __debug__:
        raise RuntimeError("QUALIFICATION_ASSERTIONS_REQUIRED")
    if git_head(root) != expected:
        raise RuntimeError("HERMES_SOURCE_CHANGED")
    native_files, api_digest = native_fingerprint(root)
    if api_digest != expected_api:
        raise RuntimeError("HERMES_NATIVE_API_BYTES_CHANGED")
    dirty = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "HEAD", "--", *NATIVE_API_FILES],
                           check=True, capture_output=True, text=True, timeout=10).stdout.splitlines()
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("HERMES_COMMITTED_VENV_INTERPRETER_REQUIRED")
    os.environ["HERMES_DISABLE_LAZY_INSTALLS"] = "1"
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # Reuse Hermes's own committed dependency selector, not guessed venv paths
    # or a pip install. Existing production processes are never switched.
    from pm.environments import activate_dependencies
    activate_dependencies(root)
    sys.path.insert(0, str(repo))
    source_paths = ["integrations/session_bridge/project_task_context.py",
                    "integrations/session_bridge/long_horizon_guidance.py",
                    "integrations/session_bridge/hermes_project_plugin.py",
                    "skills/mastermind-long-horizon/SKILL.md",
                    "skills/mastermind-long-horizon/references/native-hermes.md",
                    "skills/mastermind-long-horizon/references/native-t3.md",
                    "skills/mastermind-long-horizon/references/continuity-patterns.md",
                    "scripts/qualify_hermes_long_horizon.py",
                    "scripts/build_hermes_long_horizon_plugin.py",
                    "integrations/session_bridge/hermes_project_plugin.yaml"]
    source_hashes = {p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in source_paths}
    checks = []
    with tempfile.TemporaryDirectory(prefix="mmx-horizon-native-") as temp:
        base = Path(temp)
        home, other = base / "profile-a", base / "profile-b"
        home.mkdir(); other.mkdir()
        os.environ["HERMES_HOME"] = str(home)
        os.environ["HERMES_ROOT"] = str(base)
        from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
        from hermes_state import SessionDB
        from tools.registry import registry
        from integrations.session_bridge import project_task_context as source
        from integrations.session_bridge import hermes_project_plugin as plugin
        plan = fixture()
        plan_path = base / "workspace/docs/plans/native.md"
        plan_path.parent.mkdir(parents=True)
        write_plan(plan_path, plan)
        binding = {"workspace_root": str(base / "workspace"), "plan_path": "docs/plans/native.md",
                   "workstream": plan["workstream"], "plan_contract_sha256": source.contract_digest(plan)}
        config = {"plugins": {"enabled": [plugin.PLUGIN_NAME], "entries": {
            plugin.PLUGIN_NAME: {"settings": {"session_bindings": {"native-root": binding}}}}}}
        (home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
        (other / "config.yaml").write_text(json.dumps({"plugins": {"entries": {}}}), encoding="utf-8")

        @contextmanager
        def installed(profile):
            manager = PluginManager(scope_key=str(profile))
            manager._discovered = True  # do not discover production/default plugins
            manifest = PluginManifest(name=plugin.PLUGIN_NAME, key=plugin.PLUGIN_NAME, source="user")
            ctx = PluginContext(manifest, manager)
            handles = []
            # Capture the real native leases, forwarding every registration.
            for method in ("register_skill", "register_system_prompt_section", "register_hook", "register_tool"):
                original = getattr(ctx, method)
                def capture(*args, _original=original, **kwargs):
                    handle = _original(*args, **kwargs)
                    handles.append(handle)
                    return handle
                setattr(ctx, method, capture)
            try:
                plugin.register(ctx)
                yield manager, ctx, handles
            finally:
                for handle in reversed(handles):
                    if handle is not None:
                        handle.dispose()

        database = SessionDB(db_path=home / "state.db")
        try:
            database.create_session("native-root", "cli", cwd=str(base / "workspace"))
            with installed(home) as (manager, ctx, leases):
                assert len(leases) == 4 and all(x.active for x in leases)
                assert f"{plugin.PLUGIN_NAME}:execute-project" in manager._plugin_skills
                sections = manager.render_system_prompt_sections({"session_id": "native-root"})
                assert len(sections) == 1 and sections[0].id == plugin.SECTION_ID
                assert "original project" not in sections[0].content  # no mutable objective in cached habits
                checks.append("actual_native_skill_and_prompt_registration")
                responses = manager.invoke_hook("pre_llm_call", session_id="native-root", user_message="side question")
                assert any("Preserve mobile acceptance" in row.get("context", "") for row in responses if isinstance(row, dict))
                native = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=manager.scope_key, session_id="native-root"))
                assert native["ok"] and native["context"]["focus"]["id"] == "T1"
                assert not json.loads(registry.dispatch(plugin.TOOL_NAME, {"session_id": "native-root"},
                    scope=manager.scope_key, session_id="unrelated"))["ok"]
                checks.append("actual_native_hook_and_empty_argument_tool_dispatch")
                task = plan["tasks"][0]
                task["state"] = "done"
                task["evidence"] = [{"criterion_id": "A1", "result": "pass",
                    "definition_sha256": source.definition_digests(plan)["T1"],
                    "ref": "https://github.com/example/repo/commit/" + "a" * 40}]
                write_plan(plan_path, plan)
                assert database.try_acquire_compression_lock("native-root", "qualification", ttl_seconds=60)
                database.publish_compression_child(parent_session_id="native-root", child_session_id="native-child",
                    source="cli", messages=[{"role": "user", "content": "Disposable compaction handoff"}],
                    compression_lock_holder="qualification", cwd=str(base / "workspace"))
                native = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=manager.scope_key, session_id="native-child"))
                assert native["ok"], native
                assert native["context"]["focus"]["id"] == "T2"
                assert native["context"]["native_plan_binding"]["relation"] == "NATIVE_COMPRESSION_CONTINUATION"
                assert native["context"]["source_complete_ids"] == ["T1"]
                assert len(native["context"]["requirements"]) == 2
                checks.append("actual_native_leased_compression_restores_latest_plan")
                for name, marker in (("fork", "_branched_from"), ("delegate", "_delegate_from"), ("reset", "_reset_from")):
                    database.create_session("native-" + name, "cli", parent_session_id="native-root",
                                            model_config={marker: "native-root"})
                    result = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=manager.scope_key,
                                                        session_id="native-" + name))
                    assert not result["ok"] and result["reason"] == "HERMES_SESSION_NOT_BOUND", result
                checks.append("native_fork_delegate_reset_do_not_inherit")
                # Ambient environment remains profile-a; explicit profile-b must
                # not read profile-a's same-named session configuration.
                with installed(other) as (other_manager, _, _):
                    result = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=other_manager.scope_key,
                                                        session_id="native-root"))
                    assert not result["ok"] and result["reason"] == "HERMES_SESSION_NOT_BOUND", result
                checks.append("native_profile_isolation_with_same_session_id")
                retained = registry.get_entry(plugin.TOOL_NAME, scope=manager.scope_key).handler
                try:
                    plugin.register(ctx)
                    raise AssertionError("collision accepted")
                except source.PlanContextError as exc:
                    assert str(exc) == "HERMES_CONTEXT_TOOL_COLLISION"
                checks.append("native_tool_collision_refused_without_override")
            assert not json.loads(retained({}, session_id="native-root"))["ok"]
            assert registry.get_entry(plugin.TOOL_NAME, scope=str(home)) is None
            checks.append("native_unload_removes_tool_and_fences_retained_handler")
            with installed(home) as (manager, _, _):
                result = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=manager.scope_key, session_id="native-child"))
                assert result["ok"] and result["context"]["focus"]["id"] == "T2", result
                assert result["context"]["native_plan_binding"]["configured_session_id"] == "native-root"
                checks.append("fresh_native_manager_recovers_persisted_compression_identity")
                config["plugins"]["entries"][plugin.PLUGIN_NAME]["settings"]["session_bindings"] = {}
                (home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
                result = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=manager.scope_key, session_id="native-child"))
                assert not result["ok"], result
                checks.append("native_config_revocation_is_observed_without_rebinding")
            # Exercise the real manifest parser, packaged relative imports,
            # loader attribution and native unload, not just manual registration.
            from scripts.build_hermes_long_horizon_plugin import build
            from hermes_cli.plugins_manifest import parse_manifest_file
            package = base / "packaged-plugin"
            package_receipt = build(package, source_root=repo)
            config["plugins"]["entries"][plugin.PLUGIN_NAME]["settings"]["session_bindings"] = {"native-root": binding}
            (home / "config.yaml").write_text(json.dumps(config), encoding="utf-8")
            packed_manager = PluginManager(scope_key=str(home))
            packed_manager._discovered = True
            manifest = parse_manifest_file(package / "plugin.yaml", package, source="user", prefix="")
            assert manifest is not None
            try:
                packed_manager._load_plugin(manifest)
                loaded = packed_manager._plugins[plugin.PLUGIN_NAME]
                assert loaded.enabled and loaded.error is None, loaded.error
                result = json.loads(registry.dispatch(plugin.TOOL_NAME, {}, scope=packed_manager.scope_key, session_id="native-child"))
                assert result["ok"] and result["context"]["focus"]["id"] == "T2", result
                assert package_receipt["installed"] is False
                checks.append("real_packaged_manifest_import_loader_and_native_tool_round_trip")
            finally:
                packed_manager.unload(plugin.PLUGIN_NAME)
            assert registry.get_entry(plugin.TOOL_NAME, scope=str(home)) is None
            checks.append("real_packaged_plugin_native_unload")
        finally:
            database.close()
    if git_head(root) != expected or native_fingerprint(root)[1] != api_digest:
        raise RuntimeError("HERMES_SOURCE_CHANGED_DURING_QUALIFICATION")
    if source_hashes != {p: hashlib.sha256((repo / p).read_bytes()).hexdigest() for p in source_paths}:
        raise RuntimeError("CANDIDATE_SOURCE_CHANGED_DURING_QUALIFICATION")
    return {"schema": "mastermind.hermes_horizon_native_qualification.v1", "status": "PASS",
            "hermes_sha": expected, "native_api_sha256": api_digest, "native_api_files": native_files,
            "native_dirty_paths": dirty, "source_sha256": source_hashes, "checks": checks,
            "model_calls": 0, "production_profiles_modified": 0, "native_runtime_started": False,
            "qualification_scope": "INSTALLED_NATIVE_APIS_WITH_DISPOSABLE_PROFILE_STATE",
            "live_agent_behavior": "UNPROVEN", "mission_accepted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--expected-hermes-sha", required=True)
    parser.add_argument("--expected-native-api-sha256", required=True)
    args = parser.parse_args()
    if (not args.hermes_root.is_absolute() or not re.fullmatch(r"[0-9a-f]{40}", args.expected_hermes_sha)
            or not re.fullmatch(r"[0-9a-f]{64}", args.expected_native_api_sha256)):
        parser.error("explicit absolute source root and 40-hex inspected revision required")
    result = qualify(args.hermes_root, args.expected_hermes_sha, args.expected_native_api_sha256)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
