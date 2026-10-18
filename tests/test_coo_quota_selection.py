"""Real schema-v5 additive registration; no host, listener or provider launch."""

import copy
import dataclasses

import pytest

from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.executive_service import ExecutiveControlService
from control_plane.model_router import ModelRouter
from ops.executive_os.coo_quota_selection import (
    COOQuotaSelectionError,
    prepare_current_coo_quota_selection,
)
from tests.test_executive_service import _config


SELECTORS = ("coo_quota_class", "coo_default_quota_class", "coo_operator_quota_class")


def inputs():
    control = {
        "quota_class": "codex-native",
        "coo_quota_class": "codex-coo-06aca5279ab3e353",
        "coo_default_quota_class": "codex-coo-default-06aca5279ab3e353",
        "coo_operator_quota_class": "codex-coo-operator-06aca5279ab3e353",
        "coo_model_alias": "coo.sealed",
        "coo_operator_model_alias": "coo.operator.readonly",
        "coo_autonomy_armed": False,
        "coo_operator_harness_armed": False,
        "ceo_submit_armed": False,
        "operator_harness_binary_digest": "1" * 64,
        "operator_harness_version": "Codex fixture version",
        "proof_base_sha": "2" * 40,
        "proof_source_repository": "/fixture/source",
        "company_consultation": {"armed": True, "native_return_armed": False},
        "preserved_incident": {"issuer": "unknown", "request": "original", "attempt_limit": 1},
    }
    worker = {"schema_version": "mastermind.executive_worker_broker_config/v4",
              "operator_harness_armed": False}
    return control, worker


def prepare(control, worker=None, router=None):
    return prepare_current_coo_quota_selection(
        control, worker or inputs()[1], router=router or ModelRouter.load())


def test_preparation_changes_only_selectors_and_keeps_all_controls_and_incidents():
    control, worker = inputs()
    before, worker_before = copy.deepcopy(control), copy.deepcopy(worker)
    selected = prepare(control, worker)
    assert control == before and worker == worker_before
    assert {k for k in selected if selected[k] != control[k]} == set(SELECTORS)
    assert len(set(selected[k] for k in SELECTORS)) == 3
    assert len({selected[k].rsplit("-", 1)[1] for k in SELECTORS}) == 1
    assert prepare(selected, worker) == selected
    selected["preserved_incident"]["issuer"] = "test-change"
    assert control == before


@pytest.mark.parametrize("changed", ["proof_source", "routing", "capability", "profile", "harness", "version"])
def test_selector_tracks_immutable_binding_but_not_source_only_movement(changed):
    control, worker = inputs()
    router = ModelRouter.load()
    before = prepare(control, worker, router)
    if changed == "proof_source":
        control.update(proof_base_sha="3" * 40, proof_source_repository="/fixture/new-source")
    elif changed == "routing":
        router.policy_version += ".next"
    elif changed in ("capability", "profile"):
        alias = router.model_aliases["coo.operator.readonly"]
        field = "capability_policy_digest" if changed == "capability" else "execution_profile_digest"
        router.model_aliases["coo.operator.readonly"] = dataclasses.replace(alias, **{field: "4" * 64})
    elif changed == "harness":
        control["operator_harness_binary_digest"] = "5" * 64
    else:
        control["operator_harness_version"] += ".next"
    after = prepare(control, worker, router)
    assert all((before[k] == after[k]) is (changed == "proof_source") for k in SELECTORS)


@pytest.mark.parametrize("field,value", [
    ("coo_autonomy_armed", True), ("coo_operator_harness_armed", True),
    ("ceo_submit_armed", True), ("ceo_ingress_armed", True),
    ("coo_autonomy_armed", 0), ("ceo_submit_armed", None),
    ("coo_model_alias", "other"), ("coo_operator_model_alias", "coo.operator.native-return"),
    ("subscription_canary_realm", "other"), ("coo_attended_work_placements", [{"quota_class": "paid"}]),
    ("dialogue_wake_canary_activation", {}),
    ("company_consultation", {"native_return_armed": True}),
    ("coo_quota_class", "custom-quota"),
    ("coo_operator_quota_class", "codex-coo-operator.native-return"),
    ("operator_harness_binary_digest", "0" * 64),
    ("operator_harness_binary_digest", "invalid"),
    ("operator_harness_version", "unproven"),
    ("operator_harness_version", "bad\nversion"),
])
def test_preparation_refuses_live_unknown_or_foreign_selection(field, value):
    control, worker = inputs()
    control[field] = value
    before = copy.deepcopy(control)
    with pytest.raises(COOQuotaSelectionError):
        prepare(control, worker)
    assert control == before


def test_worker_must_be_disarmed_even_when_control_is_closed():
    control, worker = inputs()
    worker["operator_harness_armed"] = True
    with pytest.raises(COOQuotaSelectionError, match="disarmed Worker"):
        prepare(control, worker)


def test_current_selector_registration_preserves_stale_rows_and_passes_real_composition(tmp_path, monkeypatch):
    control, worker = inputs()
    legacy_config = _config(tmp_path, **{
        **{k: control[k] for k in SELECTORS},
        "operator_harness_binary_digest": control["operator_harness_binary_digest"],
        "operator_harness_version": control["operator_harness_version"],
        "coo_autonomy_armed": True, "coo_operator_harness_armed": True,
    })
    runtime = Runtime.at(legacy_config.runtime_root)
    current_router = ModelRouter.load()
    legacy_router = copy.deepcopy(current_router)
    legacy_router.policy_version = "2026-08-24.stage4"
    for name in ("coo.sealed", "coo.operator.readonly"):
        legacy_router.model_aliases[name] = dataclasses.replace(
            legacy_router.model_aliases[name],
            capability_policy_version="2026-10-11.native-return-host-source",
            capability_policy_digest="7" * 64,
        )
    # Isolated fixture only: the existing APIs create historical immutable rows.
    # No service.start, listener, provider dispatch or live Runtime is used.
    # A fail-on-use host guard makes this registration test unable to arm/drive.
    def host_guard():
        pytest.fail("registration-only fixture reached host autonomy admission")

    with monkeypatch.context() as old:
        old.setattr(ModelRouter, "load", lambda: legacy_router)
        legacy_service = ExecutiveControlService(legacy_config, autonomy_guard=host_guard)
        legacy_service.runtime = runtime
        legacy_service._register_worker()
    historical = {k: runtime.workers.get_quota_class(legacy_config.worker_id, control[k]) for k in SELECTORS}
    proof_before = runtime.workers.get_quota_class(legacy_config.worker_id, legacy_config.quota_class)
    old_selection = ExecutiveControlService(legacy_config, autonomy_guard=host_guard)
    old_selection.runtime = runtime
    with pytest.raises(StateConflict, match="different policy"):
        old_selection._register_worker()
    with pytest.raises(StateConflict, match="drifted"):
        old_selection._require_coo_worker_composed()

    selected = prepare(control, worker, current_router)
    current_config = dataclasses.replace(legacy_config, **{k: selected[k] for k in SELECTORS})
    current_service = ExecutiveControlService(current_config, autonomy_guard=host_guard)
    current_service.runtime = runtime
    current_service._register_worker()
    current_service._require_coo_worker_composed()
    for field in SELECTORS:
        assert runtime.workers.get_quota_class(legacy_config.worker_id, control[field]) == historical[field]
        assert runtime.workers.get_quota_class(legacy_config.worker_id, selected[field]) is not None
    assert runtime.workers.get_quota_class(legacy_config.worker_id, legacy_config.quota_class) == proof_before
    added = [e for e in runtime.events.list_events() if e.event_type == "WORKER_QUOTA_REGISTERED"]
    assert {e.quota_class for e in added} == {selected[k] for k in SELECTORS}
    current_service._register_worker()
    current_service._require_coo_worker_composed()
    assert [e for e in runtime.events.list_events() if e.event_type == "WORKER_QUOTA_REGISTERED"] == added
    assert runtime.jobs.list_jobs() == [] and runtime.attempts.list_attempts() == []
