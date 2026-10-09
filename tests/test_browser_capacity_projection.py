from dataclasses import replace
import pytest

from control_plane import executive_host_placement_preference as ehpp
from control_plane.browser_host_observation import (
    BrowserHostObservation,
    BrowserHostState,
    qualify_browser_host,
)
from control_plane.executive_steward import Freshness, SourceOwner, SourceRef
from control_plane.browser_capacity_projection import (
    BrowserCapacityBinding,
    BrowserCapacityBindingError,
    bind_browser_capacity_candidate,
)

HOST = "host-" + "1" * 64
BOOT = "boot-" + "2" * 64
DIGEST = "a" * 64
NOW = 1_800_000_000_000


def capacity_candidate(**changes):
    values = dict(
        worker_id="worker-a",
        provider="openai",
        quota_class="routine",
        host_ref=HOST,
        boot_ref=BOOT,
        capacity_capability_id="capability-worker-a",
        worker_source_config_digest="3" * 64,
        capacity_observation_sha256="4" * 64,
        decision_time_ms=NOW,
        request_fingerprint="5" * 64,
        host_capacity_snapshot_sha256="6" * 64,
        physical_evidence_digest="7" * 64,
        score=(1, 2, 3, 4, 5),
    )
    values.update(changes)
    values["qualification_receipt_id"] = ehpp._qualification_receipt_id(**values)
    return ehpp.QualifiedHostCandidate(**values, _seal=ehpp._QUALIFICATION_SEAL)


def browser_qualification(**changes):
    row = BrowserHostObservation(
        host_ref=changes.pop("host_ref", HOST),
        boot_ref=changes.pop("boot_ref", BOOT),
        profile_ref=changes.pop("profile_ref", "chrome-profile-a"),
        browser_instance_ref=changes.pop("browser_instance_ref", "chrome-instance-a"),
        connector_generation=changes.pop("connector_generation", "devtools-generation-a"),
        browser_version=changes.pop("browser_version", "154.0.8037.95"),
        backend_version=changes.pop("backend_version", "1.10.1"),
        backend_schema_digest=changes.pop("backend_schema_digest", DIGEST),
        remote_debugging_enabled=changes.pop("remote_debugging_enabled", True),
        user_consent_observed=changes.pop("user_consent_observed", True),
        connected=changes.pop("connected", True),
        observed_at_ms=changes.pop("observed_at_ms", NOW - 1000),
        expires_at_ms=changes.pop("expires_at_ms", NOW + 14000),
        source=changes.pop(
            "source",
            SourceRef(
                SourceOwner.SURFACE_BINDINGS,
                "browser-surface-a",
                "2026-10-06T08:00:00Z",
                Freshness.CURRENT,
            ),
        ),
    )
    assert not changes
    return qualify_browser_host(
        row,
        expected_backend_schema_digest=DIGEST,
        trusted_now_ms=NOW,
    )


def test_matching_capacity_and_browser_facts_bind_without_selecting():
    candidate = capacity_candidate()
    result = bind_browser_capacity_candidate(candidate, browser_qualification())
    assert isinstance(result, BrowserCapacityBinding)
    assert result.worker_id == candidate.worker_id
    assert result.capacity_qualification_receipt_id == candidate.qualification_receipt_id
    assert result.host_ref == HOST
    assert result.boot_ref == BOOT
    assert result.profile_ref == "chrome-profile-a"
    assert result.backend_schema_digest == DIGEST
    assert result.is_placement is False
    assert result.is_admission is False
    assert "score" not in result.to_dict()


@pytest.mark.parametrize(
    "browser,code",
    [
        (lambda: browser_qualification(host_ref="host-" + "9" * 64), "HOST_MISMATCH"),
        (lambda: browser_qualification(boot_ref="boot-" + "9" * 64), "BOOT_MISMATCH"),
        (lambda: browser_qualification(connected=False), "BROWSER_NOT_READY"),
        (lambda: browser_qualification(connected=None), "BROWSER_NOT_READY"),
    ],
)
def test_mismatched_or_unready_browser_fact_cannot_qualify_capacity(browser, code):
    with pytest.raises(BrowserCapacityBindingError, match=code):
        bind_browser_capacity_candidate(capacity_candidate(), browser())


def test_binding_preserves_capacity_ranking_inputs_unchanged():
    candidate = capacity_candidate()
    score = candidate.score
    bind_browser_capacity_candidate(candidate, browser_qualification())
    assert candidate.score == score
    assert candidate.qualification_receipt_id == capacity_candidate().qualification_receipt_id


def test_backend_generation_is_part_of_binding_digest():
    candidate = capacity_candidate()
    first = bind_browser_capacity_candidate(candidate, browser_qualification())
    second = bind_browser_capacity_candidate(
        candidate,
        browser_qualification(
            connector_generation="devtools-generation-b",
            browser_instance_ref="chrome-instance-b",
        ),
    )
    assert first.binding_digest != second.binding_digest


def test_binding_cannot_be_forged_directly():
    with pytest.raises(BrowserCapacityBindingError, match="binding seal"):
        BrowserCapacityBinding(
            worker_id="worker-a",
            capacity_qualification_receipt_id="0" * 64,
            host_ref=HOST,
            boot_ref=BOOT,
            profile_ref="chrome-profile-a",
            browser_instance_ref="chrome-instance-a",
            connector_generation="devtools-generation-a",
            backend_schema_digest=DIGEST,
            binding_digest="1" * 64,
        )


def test_foreign_objects_do_not_count_as_owner_qualifications():
    with pytest.raises(BrowserCapacityBindingError):
        bind_browser_capacity_candidate(object(), browser_qualification())
    with pytest.raises(BrowserCapacityBindingError):
        bind_browser_capacity_candidate(capacity_candidate(), object())
