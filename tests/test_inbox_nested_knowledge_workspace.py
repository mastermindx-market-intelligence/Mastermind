"""Inbox -> CCR -> existing Workspace/Mission warning disclosure.

Uses the incumbent cache and owner-observation fixtures. This is pure/local
consumer integration, not installed namespace or authenticated browser proof.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

from control_plane import chairman_control_room as ccr
from control_plane import executive_inbox as inbox
from control_plane.workspace_read_service import WorkspaceReadService
from integrations.mastermind_workspace_app.contract import canonical, MAX_RESPONSE_BYTES
from tests.test_mission_workspace import _owner_observation_inputs
from tests.test_workspace_read_service import cache_fixture, run
from scripts import chairman_control_room as cache_owner


# Exact four supplied brief.inputs.degraded strings from retained ee1aeed54 packet.
WARNINGS = [
    "active_builds.v1 open_prs is TRUNCATED at the gh --limit cap — some open PRs are missing from the join, so a wave may read 'unknown' while its PR is open",
    "active_builds.v1 merged window is TRUNCATED — a merged PR may read 'unknown'",
    "uncommitted-work scan skipped over 0 worktrees (one `git status` each) — re-run with --scan-uncommitted for stranded work",
    "active_builds.v1 is 420h old — PR state predates the last nightly sweep",
]


def test_nested_knowledge_warnings_survive_existing_workspace_mission_consumer(tmp_path):
    from tests.test_chairman_control_room import _load

    packet = _load("boot_packet_v1.json")
    packet["degraded"] = []
    packet["brief"]["inputs"] = {"degraded": list(WARNINGS)}
    runtime_projection = SimpleNamespace(
        attention=[], degraded=[], counts=None, suppressed=None,
    )

    def project(value):
        return inbox.compose_inbox(
            runtime_projection=runtime_projection, boot_packet=value,
            mastermind_grounding={}, runtime_grounding={"present": True},
            generated_at="2026-09-21T00:00:00Z",
        )

    without = copy.deepcopy(packet)
    without["brief"]["inputs"] = {}
    plain = project(without)
    disclosed = project(packet)
    assert disclosed["attention"] == plain["attention"]
    assert disclosed["runtime_counts"] == plain["runtime_counts"]
    assert disclosed["suppressed"] == plain["suppressed"]
    assert all(any(warning in entry for entry in disclosed["degraded"])
               for warning in WARNINGS)

    composed = ccr.compose_control_room(
        inbox=disclosed, boot_packet=packet,
        active_builds=_load("active_builds_v1.json"),
        agent_os_state=_load("agent_os_state_v1.json"),
        runtime_jobs=_load("runtime_jobs_v1.json"),
        bindings=_load("bindings_v1.json"), binding_problems=(),
        generated_at="2026-09-21T00:00:00Z",
    )
    inherited = [entry for entry in composed["degraded"]
                 if any(warning in entry for warning in WARNINGS)]
    assert len(inherited) == len(WARNINGS)

    # Use the existing canonical cache/selection fixture, replacing only its
    # source-owned warning list with the real CCR compositor output above.
    owners, clock, cache = cache_fixture(tmp_path)
    document = owners[0].state_cache["doc"]
    document["degraded"] = inherited
    owners[0].state_cache.pop("source_validity_bounds", None)
    with owners[0].state_lock:
        cache_owner._publish_source_validity(
            owners[0], document, tuple(clock), tuple(clock),
        )
    fabric = _owner_observation_inputs()["fabric_view"]
    fabric = json.loads(json.dumps(fabric).replace("JOB-1", "JOB-001"))
    provider = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda principal: True,
        armed={}, runtime_identity={},
        acquire=lambda *args, **kwargs: copy.deepcopy(fabric),
    )
    result = run(provider)
    assert result["ok"] is True
    assert result["result"]["schema"] == "mastermind.mission_workspace.v2"
    assert all(any(warning in entry for entry in result["result"]["degraded"])
               for warning in WARNINGS)
    assert len(canonical(result)) + 1 <= MAX_RESPONSE_BYTES
