"""Fail-closed contracts for the remote read-only Chairman Control Room."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from control_plane import chairman_control_room as ccr
from control_plane import chairman_control_room_remote as remote


FIXTURES = Path(__file__).parent / "fixtures" / "chairman_control_room"
NOW = "2026-08-28T20:00:00Z"
IDENTITY = remote.BuildIdentity(
    commit="a" * 40,
    tree="b" * 40,
    artifact_digest="sha256:" + "c" * 64,
)
FRESHNESS = {
    remote.SOURCE_AGENT_OS_BRIEF: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_AGENT_OS_STATE: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_ACTIVE_BUILDS: remote.SourceFreshness("fresh", NOW, NOW, None),
    remote.SOURCE_EXECUTIVE_RUNTIME: remote.SourceFreshness("fresh", NOW, NOW, None),
}


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def canonical_doc():
    return ccr.compose_control_room(
        inbox=_load("executive_inbox_v2.json"),
        boot_packet=_load("boot_packet_v1.json"),
        active_builds=_load("active_builds_v1.json"),
        agent_os_state=_load("agent_os_state_v1.json"),
        runtime_jobs=_load("runtime_jobs_v1.json"),
        bindings=_load("bindings_v1.json"),
        binding_problems=(),
        generated_at=NOW,
    )


def _project(doc):
    return remote.project_remote_document(
        doc, observed_at=NOW, freshness=FRESHNESS, build_identity=IDENTITY
    )


def test_remote_projection_is_closed_and_omits_local_authority(canonical_doc):
    projected = _project(canonical_doc)
    assert projected["schema"] == "mastermind.chairman_control_room_remote.v1"
    assert set(projected) == {
        "schema", "observed_at", "code_identity", "source_freshness",
        "degraded", "attention", "work", "unjoined_open_prs",
    }
    assert set(projected["code_identity"]) == {"commit", "tree", "artifact_digest"}
    assert set(projected["source_freshness"]) == remote.COLLECTOR_SOURCES
    assert all(
        set(row) == {"state", "observed_at", "source_time", "reason"}
        for row in projected["source_freshness"].values()
    )
    assert set(projected["attention"]) == {"chairman", "ceo", "coo"}
    assert all(
        set(item) == {
            "attention_id", "kind", "title", "summary", "workstream",
            "state", "reason_code",
        }
        for bucket in projected["attention"].values()
        for item in bucket
    )
    assert all(
        set(card) == {
            "work_ref", "agent_os", "executive", "github",
            "attention_ids", "disagreements",
        }
        for card in projected["work"]
    )
    assert all(
        card["agent_os"] is None or set(card["agent_os"]) == {
            "workstream", "title", "status", "program", "next_action",
            "state", "reason_code", "reason", "depends_on",
            "unmet_dependencies",
        }
        for card in projected["work"]
    )
    assert all(set(card["executive"]) == {"jobs", "joined_by"} for card in projected["work"])
    assert all(
        set(job) == {"job_id", "status", "workstream"}
        for card in projected["work"] for job in card["executive"]["jobs"]
    )
    assert all(set(card["github"]) == {"prs"} for card in projected["work"])
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for card in projected["work"] for pr in card["github"]["prs"]
    )
    assert all(
        set(pr) == {"repo", "number", "url", "title", "branch", "draft", "merge_state"}
        for pr in projected["unjoined_open_prs"]
    )
    encoded = json.dumps(projected, sort_keys=True)
    for forbidden in (
        "macro_root", "bindings", "binding_conflicts", "unbound_surfaces",
        "locator", "seat_ref", "argv", "traceback", "/Users/", "/opt/",
        "X-CCR-Token", "@example.com",
    ):
        assert forbidden not in encoded


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda d: d.__setitem__("future", True), "unexpected_keys"),
        (lambda d: d["work"][0].__setitem__("future", True), "unexpected_keys"),
        (lambda d: d.__setitem__("schema", "mastermind.future.v9"), "schema_mismatch"),
        (lambda d: d.__setitem__("work", {}), "invalid_type"),
        (lambda d: d["work"][0].__setitem__("attention_ids", "not-a-list"), "invalid_type"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("nan")), "non_finite_number"),
        (lambda d: d["work"][0]["executive"]["jobs"][0].__setitem__("status", float("inf")), "non_finite_number"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["host.local"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["/opt/private/file"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["person@example.com"]), "sensitive_value"),
        (lambda d: d["work"][0].__setitem__("disagreements", ["provider_session_id=raw-123"]), "sensitive_value"),
    ],
)
def test_remote_projection_rejects_adversarial_canonical_documents(canonical_doc, mutation, code):
    bad = copy.deepcopy(canonical_doc)
    mutation(bad)
    with pytest.raises(remote.RemoteProjectionError) as exc:
        _project(bad)
    assert exc.value.code == code


def test_remote_projection_rejects_bad_freshness_and_identity(canonical_doc):
    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness={remote.SOURCE_AGENT_OS_BRIEF: FRESHNESS[remote.SOURCE_AGENT_OS_BRIEF]},
            build_identity=IDENTITY,
        )
    assert exc.value.code == "freshness_sources_mismatch"

    with pytest.raises(remote.RemoteProjectionError) as exc:
        remote.project_remote_document(
            canonical_doc,
            observed_at=NOW,
            freshness=FRESHNESS,
            build_identity=remote.BuildIdentity("HEAD", "b" * 40, "sha256:" + "c" * 64),
        )
    assert exc.value.code == "invalid_build_identity"


def test_remote_projection_is_deterministic_and_does_not_mutate_input(canonical_doc):
    before = copy.deepcopy(canonical_doc)
    first = _project(canonical_doc)
    second = _project(canonical_doc)
    assert canonical_doc == before
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
