"""Canonical empty-publication evidence, independent of live installed data."""
import pytest

from control_plane import chairman_control_room as composer
from scripts import chairman_control_room as publisher
from tests.test_workspace_read_service import STAMP, cache_fixture, frame, run, service


def empty_inputs():
    return dict(
        boot_packet={"schema": composer.BOOT_PACKET_SCHEMA, "generated_at": STAMP,
            "mastermind": {"sha": "1" * 40, "branch": "fixture"},
            "macro": {"sha": "2" * 40, "root": "/fixture/macro"},
            "brief": {"schema": composer.AGENT_OS_BRIEF_SCHEMA}, "degraded": []},
        inbox={"schema": composer.EXECUTIVE_INBOX_SCHEMA, "generated_at": STAMP,
            "grounding": {"runtime_db": {"present": True}}, "attention": [], "degraded": []},
        active_builds={"schema": composer.ACTIVE_BUILDS_SCHEMA, "collected_at": STAMP},
        agent_os_state={"schema": composer.AGENT_OS_STATE_SCHEMA, "generated_at": STAMP},
        runtime_jobs=[], bindings=None, binding_problems=[], generated_at=STAMP)


def publish(tmp_path, doc):
    owners, clock, cache = cache_fixture(tmp_path)
    owner = owners[0]
    owner.state_cache["doc"] = doc
    owner.state_cache.pop("source_validity_bounds", None)
    with owner.state_lock:
        publisher._publish_source_validity(owner, doc, tuple(clock), tuple(clock))
    return run(service(cache), frame("programs"))["result"]


def test_canonical_all_sources_unavailable_is_not_available_empty(tmp_path):
    args = {key: None for key in ("boot_packet", "inbox", "active_builds", "agent_os_state", "runtime_jobs", "bindings")}
    doc = composer.compose_control_room(**args, binding_problems=[], generated_at=STAMP)
    assert doc["work"] == [] and doc["degraded"]
    result = publish(tmp_path, doc)
    assert result["availability"] == "UNAVAILABLE"
    assert result["control_room"] is None and result["source_observation"]["state"] == "UNKNOWN"


def test_canonical_positive_empty_is_available(tmp_path):
    doc = composer.compose_control_room(**empty_inputs())
    assert doc["work"] == [] and not doc["degraded"]
    result = publish(tmp_path, doc)
    assert result["availability"] == "AVAILABLE" and result["control_room"] == doc


@pytest.mark.parametrize("source", ["boot_packet", "inbox", "active_builds", "agent_os_state", "runtime_jobs"])
def test_each_missing_canonical_source_refuses_empty(tmp_path, source):
    args = empty_inputs(); args[source] = None
    assert publish(tmp_path, composer.compose_control_room(**args))["availability"] == "UNAVAILABLE"


@pytest.mark.parametrize("field", ["mastermind_sha", "macro_sha", "macro_root", "executive_inbox_schema", "agent_os_brief_schema", "agent_os_state_schema", "agent_os_state_generated_at", "active_builds_schema", "active_builds_collected_at", "runtime_db_present"])
def test_missing_positive_source_evidence_refuses(tmp_path, field):
    doc = composer.compose_control_room(**empty_inputs())
    del doc["sources"][field]
    assert publish(tmp_path, doc)["availability"] == "UNAVAILABLE"


@pytest.mark.parametrize("mutation", ["sources", "degraded", "generation", "counts", "work", "source_failures", "wrong_schema", "wrong_identity", "naive_time", "runtime_integer"])
def test_malformed_empty_publication_refuses(tmp_path, mutation):
    doc = composer.compose_control_room(**empty_inputs())
    if mutation == "sources": doc["sources"] = []
    elif mutation == "degraded": doc["degraded"] = "unavailable"
    elif mutation == "generation": doc["autonomy"]["generated_at"] = "different"
    elif mutation == "counts": doc["autonomy"]["counts"]["total"] = True
    elif mutation == "work": doc["work"] = [{"work_ref": "WS:ORPHAN"}]
    elif mutation == "source_failures": doc["autonomy"]["source_failures"] = ["unavailable"]
    elif mutation == "wrong_schema": doc["sources"]["agent_os_state_schema"] = "unknown"
    elif mutation == "wrong_identity": doc["sources"]["macro_sha"] = "not-a-sha"
    elif mutation == "naive_time": doc["sources"]["active_builds_collected_at"] = "2026-09-21"
    elif mutation == "runtime_integer": doc["sources"]["runtime_db_present"] = 1
    assert publish(tmp_path, doc)["availability"] == "UNAVAILABLE"


def test_unrelated_optional_binding_warning_does_not_deny_positive_empty(tmp_path):
    args = empty_inputs(); args["binding_problems"] = ["fixture optional navigation unavailable"]
    assert publish(tmp_path, composer.compose_control_room(**args))["availability"] == "AVAILABLE"


def test_existing_nonempty_card_currentness_contract_is_preserved(tmp_path):
    _, _, cache = cache_fixture(tmp_path)
    assert run(service(cache), frame("programs"))["result"]["availability"] == "AVAILABLE"
