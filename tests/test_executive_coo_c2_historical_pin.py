"""Historical capability-pin discriminator for the disabled COO profile."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest

import control_plane.executive_agent_capabilities as capabilities
import control_plane.executive_operator_supervisor as supervisor_module
import tests.test_executive_operator_supervisor as supervisor_fixtures
from control_plane.executive_agent_capabilities import (
    COO_DOMAIN_EXECUTION_PROFILE,
    ExecutionCapabilityRegistry,
)
from control_plane.executive_operator_supervisor import (
    ExecutiveOperatorSupervisor,
    ExecutiveOperatorSupervisorError,
)
from control_plane.executive_runtime import AttemptStatus
from control_plane.model_router import ModelRouter


OLD_POLICY_DIGEST = "c2f74c244464bee6d8bbc9d38d430aec362835234ae798b42c045da86c3bdd7a"
CURRENT_POLICY_DIGEST = (
    "6982fcdf97a210d99e9282c40f855fc591a521788c442cb46d628fdf3aaaea06"
)
SELECTED_PROFILE = "operator.appserver.readonly.docs-mcp.native-helper.v1"


def _canonical_bytes() -> bytes:
    return Path(capabilities.DEFAULT_CAPABILITY_POLICY_PATH).read_bytes()


def _write_policy(tmp_path: Path, name: str, raw: object) -> Path:
    path = tmp_path / name
    path.write_bytes(
        json.dumps(raw, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return path


def _historical_fixture(tmp_path: Path):
    current_raw = json.loads(_canonical_bytes())
    assert COO_DOMAIN_EXECUTION_PROFILE in current_raw["profiles"]
    historical_raw = copy.deepcopy(current_raw)
    removed = historical_raw["profiles"].pop(COO_DOMAIN_EXECUTION_PROFILE)
    assert removed == current_raw["profiles"][COO_DOMAIN_EXECUTION_PROFILE]
    assert removed["enabled"] is False
    historical_path = _write_policy(tmp_path, "historical.json", historical_raw)
    historical = ExecutionCapabilityRegistry.load(historical_path)
    current = ExecutionCapabilityRegistry.load()

    assert historical.policy_digest == OLD_POLICY_DIGEST
    assert current.policy_digest == CURRENT_POLICY_DIGEST
    assert COO_DOMAIN_EXECUTION_PROFILE not in historical.profiles
    assert set(historical.profiles) == set(current.profiles) - {
        COO_DOMAIN_EXECUTION_PROFILE
    }
    for profile_id, profile in historical.profiles.items():
        assert profile == current.profiles[profile_id]
    return historical_path, historical, current


def _pending_planner(tmp_path: Path, monkeypatch, policy_path: Path):
    # Compile all immutable identity stamps from the loaded registry before
    # public submit_intent freezes the Job; never rewrite stored constraints.
    class HistoricalRouter:
        @classmethod
        def load(cls, *args, **kwargs):
            return ModelRouter.load(*args, capability_policy_path=policy_path, **kwargs)
    with monkeypatch.context() as seed_patch:
        seed_patch.setattr(supervisor_fixtures, "ModelRouter", HistoricalRouter)
        runtime, root, planner = supervisor_fixtures._seed_dispatchable_operator_planner(tmp_path)
    command_id = f"coo-cycle:{root.job_id}:dispatch:{planner.job_id}:attempt:1"
    identity = {
        "job_id": planner.job_id, "parent_job_id": planner.parent_job_id,
        "root_job_id": planner.root_job_id,
        **{key: planner.constraints[key] for key in (
            "execution_profile_id", "execution_profile_digest",
            "capability_policy_version", "capability_policy_digest",
        )},
    }
    return runtime, planner, command_id, identity


def _supervisor_with_counted_factory(runtime, monkeypatch, *, consumer_registry=None):
    if consumer_registry is not None:
        class BoundRegistry:
            @classmethod
            def load(cls, *args, **kwargs):
                return consumer_registry
        monkeypatch.setattr(supervisor_module, "ExecutionCapabilityRegistry", BoundRegistry)
    adapters = []
    factory_calls = {"count": 0}
    def factory(loader):
        factory_calls["count"] += 1
        adapter = supervisor_fixtures._ActiveAdapter(runtime, loader, cancel_during_collect=False)
        adapters.append(adapter)
        return adapter
    supervisor = ExecutiveOperatorSupervisor(
        runtime, adapter_factory=factory,
        prompt_source=supervisor_fixtures._PromptSource(),
    )
    return supervisor, adapters, factory_calls


def _expected_adapter_digest() -> str:
    return ExecutionCapabilityRegistry.load().resolve(SELECTED_PROFILE).expected_config_digest


def _assert_no_provider_effects(runtime, planner, adapters, factory_calls):
    attempts = runtime.attempts.list_attempts(planner.job_id)
    assert factory_calls["count"] == 0
    assert adapters == []
    assert all(attempt.status is AttemptStatus.CLAIMED for attempt in attempts)
    assert all(attempt.provider_session_id is None for attempt in attempts)
    assert len(attempts) == 1
    with runtime.store.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM harness_session_epochs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM process_generations").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type LIKE 'OHF_%' "
            "OR event_type LIKE 'OPERATOR_OPERATION_%'"
        ).fetchone()[0] == 0


def test_historical_pending_planner_refuses_after_whole_registry_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    historical_path, historical, _current = _historical_fixture(tmp_path)
    runtime, planner, command_id, before = _pending_planner(
        tmp_path, monkeypatch, historical_path
    )
    assert before["execution_profile_id"] == SELECTED_PROFILE
    assert before["capability_policy_digest"] == OLD_POLICY_DIGEST
    stored = copy.deepcopy(runtime.jobs.get_job(planner.job_id))
    assert stored is not None and stored.constraints["capability_policy_digest"] == (
        OLD_POLICY_DIGEST
    )

    supervisor, adapters, factory_calls = _supervisor_with_counted_factory(
        runtime, monkeypatch
    )
    with pytest.raises(
        ExecutiveOperatorSupervisorError, match="operator planner profile is not one reviewed rich read-only lane"
    ):
        asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command_id))

    after = runtime.jobs.get_job(planner.job_id)
    assert after is not None
    for key, value in before.items():
        if key in {"job_id", "parent_job_id", "root_job_id"}:
            assert after.__getattribute__(key) == value
        else:
            assert after.constraints[key] == value
    assert after.constraints == stored.constraints
    _assert_no_provider_effects(runtime, planner, adapters, factory_calls)


def test_current_pin_positive_control_reaches_typed_adapter(
    tmp_path: Path,
) -> None:
    runtime, _root, planner = supervisor_fixtures._seed_dispatchable_operator_planner(
        tmp_path
    )
    adapters: list[supervisor_fixtures._ActiveAdapter] = []

    def factory(loader):
        adapter = supervisor_fixtures._ActiveAdapter(
            runtime, loader, cancel_during_collect=False
        )
        adapters.append(adapter)
        return adapter

    supervisor = ExecutiveOperatorSupervisor(
        runtime,
        adapter_factory=factory,
        prompt_source=supervisor_fixtures._PromptSource(),
    )
    outcome = asyncio.run(
        supervisor.start_cycle_job(
            planner.job_id,
            command_id=f"coo-cycle:{_root.job_id}:dispatch:{planner.job_id}:attempt:1",
        )
    )
    assert outcome.outcome == "TERMINAL"
    assert len(adapters) == 1
    assert adapters[0].profile is not None
    assert adapters[0].profile.expected_config_digest == _expected_adapter_digest()
    assert adapters[0].begin_turn_calls == 1
    assert adapters[0].stop_calls == 1
    assert adapters[0].cancel_calls == 0


def test_changed_selected_profile_refuses_pending_old_pin(
    tmp_path: Path, monkeypatch
) -> None:
    current_raw = json.loads(_canonical_bytes())
    current_raw["profiles"][SELECTED_PROFILE]["enabled"] = False
    changed_path = _write_policy(tmp_path, "changed.json", current_raw)
    changed = ExecutionCapabilityRegistry.load(changed_path)
    assert changed.policy_digest != CURRENT_POLICY_DIGEST

    runtime, planner, command_id, before = _pending_planner(
        tmp_path, monkeypatch, capabilities.DEFAULT_CAPABILITY_POLICY_PATH
    )
    assert before["capability_policy_digest"] == CURRENT_POLICY_DIGEST
    supervisor, adapters, factory_calls = _supervisor_with_counted_factory(
        runtime, monkeypatch, consumer_registry=changed
    )
    with pytest.raises(
        ExecutiveOperatorSupervisorError,
        match="operator capability profile is not admitted",
    ):
        asyncio.run(supervisor.start_cycle_job(planner.job_id, command_id=command_id))

    after = runtime.jobs.get_job(planner.job_id)
    assert after is not None
    assert after.constraints["capability_policy_digest"] == CURRENT_POLICY_DIGEST
    assert after.constraints["execution_profile_id"] == before["execution_profile_id"]
    assert after.constraints["execution_profile_digest"] == before["execution_profile_digest"]
    _assert_no_provider_effects(runtime, planner, adapters, factory_calls)
