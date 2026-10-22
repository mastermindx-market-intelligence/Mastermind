"""Source-only binding contracts. Fake adapter positives are OFFLINE MECHANICS.

The four byte fixtures preserve the exact accepted historical receipts. No test
reads a workstation receipt, calls a provider, registers a worker or proves that
an external adapter is supported in production.
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from control_plane import external_pool_binding as binding
from control_plane import worker_adapter
from control_plane.executive_capacity_join import MAX_CANDIDATES
from control_plane.executive_runtime import WorkerRegistry, WorkerStatus
from control_plane.model_router import ModelRouter, ProviderAlias


RECEIPTS = {
    'grok': (
        b'{\n'
        b'  "run_id": "rs_20260929T063139Z_52100",\n'
        b'  "host": "ubuntu2",\n'
        b'  "requested_model": "grok-4.6",\n'
        b'  "served_model": "not independently attested",\n'
        b'  "source_delta_sha256": "f7e163a729ab066ffa4f600af2b0163fbeab4cc84efed9656dd898fb48dac365",\n'
        b'  "terminal": {\n'
        b'    "root": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "lease_id": "4c4abc664461",\n'
        b'    "account": "default",\n'
        b'    "host": "ubuntu2",\n'
        b'    "run_id": "rs_20260929T063139Z_52100",\n'
        b'    "schema": "mastermind.native.remote-terminal.v1",\n'
        b'    "mode": "grok",\n'
        b'    "model": "grok-4.6",\n'
        b'    "started": true,\n'
        b'    "returncode": 0,\n'
        b'    "cleanup": {\n'
        b'      "census_proven": true,\n'
        b'      "error_code": null,\n'
        b'      "identity_verified": true,\n'
        b'      "reason": "normal_completion",\n'
        b'      "residual_count": 0,\n'
        b'      "sigkill_sent": false,\n'
        b'      "sigterm_sent": false,\n'
        b'      "status": "not_needed",\n'
        b'      "stderr_capture_complete": true,\n'
        b'      "stderr_capture_error": null,\n'
        b'      "stdin_delivery_complete": true,\n'
        b'      "stdin_delivery_error": null,\n'
        b'      "stdout_capture_complete": true,\n'
        b'      "stdout_capture_error": null\n'
        b'    },\n'
        b'    "capture": {\n'
        b'      "stdout_bytes": 155,\n'
        b'      "stderr_bytes": 0,\n'
        b'      "stdout_truncated": false,\n'
        b'      "stderr_truncated": false\n'
        b'    },\n'
        b'    "output_complete": true,\n'
        b'    "cleanup_proven": true\n'
        b'  },\n'
        b'  "broker_settled": true,\n'
        b'  "artifact": {\n'
        b'    "nonce": "remote-grok-01a0e2a5-20260929",\n'
        b'    "hostname": "ubuntu2",\n'
        b'    "cwd": "/home/ubuntu2/lanes/tmp/grok-onboarding-01a0e2a5",\n'
        b'    "status": "READY"\n'
        b'  },\n'
        b'  "accepted_scope": "remote Grok CLI created bounded artifact through normal provider and physical host admission",\n'
        b'  "observed_at": "2026-09-29T06:34:37.041338+00:00"\n'
        b'}'
    ),
    'cursor': (
        b'{\n'
        b'  "observed_at": "2026-09-29T06:58:58.393210+00:00",\n'
        b'  "host": "ubuntu1",\n'
        b'  "mode": "cursor",\n'
        b'  "requested_model": "composer-2.5",\n'
        b'  "run_id": "rs_20260929T065559Z_48026",\n'
        b'  "artifact": {\n'
        b'    "nonce": "remote-cursor-01a0e2a5-20260929",\n'
        b'    "hostname": "mastermind-pc",\n'
        b'    "cwd": "/home/longr/lanes/tmp/cursor-onboarding-01a0e2a5",\n'
        b'    "status": "READY"\n'
        b'  },\n'
        b'  "terminal": {\n'
        b'    "root": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "lease_id": "8bc0bfe278a8",\n'
        b'    "account": "default",\n'
        b'    "host": "ubuntu1",\n'
        b'    "run_id": "rs_20260929T065559Z_48026",\n'
        b'    "schema": "mastermind.native.remote-terminal.v1",\n'
        b'    "mode": "cursor",\n'
        b'    "model": "composer-2.5",\n'
        b'    "started": true,\n'
        b'    "returncode": 0,\n'
        b'    "cleanup": {\n'
        b'      "census_proven": true,\n'
        b'      "error_code": null,\n'
        b'      "identity_verified": true,\n'
        b'      "reason": "leader_exited_with_descendants",\n'
        b'      "residual_count": 0,\n'
        b'      "session_id": 3544420,\n'
        b'      "sigkill_member_count": 0,\n'
        b'      "sigkill_sent": false,\n'
        b'      "sigterm_member_count": 4,\n'
        b'      "sigterm_sent": true,\n'
        b'      "status": "terminated",\n'
        b'      "stderr_capture_complete": true,\n'
        b'      "stderr_capture_error": null,\n'
        b'      "stdin_delivery_complete": true,\n'
        b'      "stdin_delivery_error": null,\n'
        b'      "stdout_capture_complete": true,\n'
        b'      "stdout_capture_error": null\n'
        b'    },\n'
        b'    "capture": {\n'
        b'      "stdout_bytes": 69,\n'
        b'      "stderr_bytes": 0,\n'
        b'      "stdout_truncated": false,\n'
        b'      "stderr_truncated": false\n'
        b'    },\n'
        b'    "output_complete": true,\n'
        b'    "cleanup_proven": true\n'
        b'  },\n'
        b'  "lease": {\n'
        b'    "id": "8bc0bfe278a8",\n'
        b'    "pool": "cursor",\n'
        b'    "account": "default",\n'
        b'    "host": "ubuntu1",\n'
        b'    "orchestrator_id": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "state": "released"\n'
        b'  },\n'
        b'  "state": "BOUNDED_ROUTE_ACCEPTED",\n'
        b'  "served_model_and_billed_usage": "unattested",\n'
        b'  "limitations": "transport/task qualification only; not general quality or fleet-wide qualification"\n'
        b'}\n'
    ),
    'oc-free': (
        b'{\n'
        b'  "observed_at": "2026-09-29T06:58:58.614650+00:00",\n'
        b'  "host": "ubuntu1",\n'
        b'  "mode": "oc-free",\n'
        b'  "requested_model": "mimo-v2.5-free",\n'
        b'  "run_id": "rs_20260929T065623Z_48949",\n'
        b'  "artifact": {\n'
        b'    "nonce": "remote-oc-free-01a0e2a5-20260929",\n'
        b'    "hostname": "mastermind-pc",\n'
        b'    "cwd": "/home/longr/lanes/tmp/oc-free-onboarding-01a0e2a5",\n'
        b'    "status": "READY"\n'
        b'  },\n'
        b'  "terminal": {\n'
        b'    "root": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "lease_id": "3c85677d0e5f",\n'
        b'    "account": "C1",\n'
        b'    "host": "ubuntu1",\n'
        b'    "run_id": "rs_20260929T065623Z_48949",\n'
        b'    "schema": "mastermind.native.remote-terminal.v1",\n'
        b'    "mode": "oc-free",\n'
        b'    "model": "mimo-v2.5-free",\n'
        b'    "started": true,\n'
        b'    "returncode": 0,\n'
        b'    "cleanup": {\n'
        b'      "census_proven": true,\n'
        b'      "error_code": null,\n'
        b'      "identity_verified": true,\n'
        b'      "reason": "normal_completion",\n'
        b'      "residual_count": 0,\n'
        b'      "sigkill_sent": false,\n'
        b'      "sigterm_sent": false,\n'
        b'      "status": "not_needed",\n'
        b'      "stderr_capture_complete": true,\n'
        b'      "stderr_capture_error": null,\n'
        b'      "stdin_delivery_complete": true,\n'
        b'      "stdin_delivery_error": null,\n'
        b'      "stdout_capture_complete": true,\n'
        b'      "stdout_capture_error": null\n'
        b'    },\n'
        b'    "capture": {\n'
        b'      "stdout_bytes": 60,\n'
        b'      "stderr_bytes": 978,\n'
        b'      "stdout_truncated": false,\n'
        b'      "stderr_truncated": false\n'
        b'    },\n'
        b'    "output_complete": true,\n'
        b'    "cleanup_proven": true\n'
        b'  },\n'
        b'  "lease": {\n'
        b'    "id": "3c85677d0e5f",\n'
        b'    "pool": "ocfree",\n'
        b'    "account": "C1",\n'
        b'    "host": "ubuntu1",\n'
        b'    "orchestrator_id": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "state": "released"\n'
        b'  },\n'
        b'  "state": "BOUNDED_ROUTE_ACCEPTED",\n'
        b'  "served_model_and_billed_usage": "unattested",\n'
        b'  "limitations": "transport/task qualification only; not general quality or fleet-wide qualification",\n'
        b'  "deviation": "First Python command had SyntaxError; worker corrected it and read its output. Artifact accepted after2 shellcommands+1read, not claimed exact-one-command compliance."\n'
        b'}\n'
    ),
    'codex-native': (
        b'{\n'
        b'  "observed_at": "2026-09-29T07:01:42.860746+00:00",\n'
        b'  "host": "mb",\n'
        b'  "mode": "codex-native",\n'
        b'  "requested_model": "gpt-6-sol",\n'
        b'  "run_id": "rs_20260929T070048Z_59320",\n'
        b'  "artifact": {\n'
        b'    "nonce": "remote-codex-native-01a0e2a5-20260929",\n'
        b'    "hostname": "MacBook-Pro-9.lan",\n'
        b'    "cwd": "/Users/chriswong/lanes/tmp/codex-native-onboarding-01a0e2a5",\n'
        b'    "status": "READY"\n'
        b'  },\n'
        b'  "terminal": {\n'
        b'    "root": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "lease_id": "ff793d9789fa",\n'
        b'    "account": "default",\n'
        b'    "host": "mb",\n'
        b'    "run_id": "rs_20260929T070048Z_59320",\n'
        b'    "schema": "mastermind.native.remote-terminal.v1",\n'
        b'    "mode": "codex-native",\n'
        b'    "model": "gpt-6-sol",\n'
        b'    "started": true,\n'
        b'    "returncode": 0,\n'
        b'    "cleanup": {\n'
        b'      "census_proven": true,\n'
        b'      "error_code": null,\n'
        b'      "identity_verified": true,\n'
        b'      "reason": "normal_completion",\n'
        b'      "residual_count": 0,\n'
        b'      "sigkill_sent": false,\n'
        b'      "sigterm_sent": false,\n'
        b'      "status": "not_needed",\n'
        b'      "stderr_capture_complete": true,\n'
        b'      "stderr_capture_error": null,\n'
        b'      "stdin_delivery_complete": true,\n'
        b'      "stdin_delivery_error": null,\n'
        b'      "stdout_capture_complete": true,\n'
        b'      "stdout_capture_error": null\n'
        b'    },\n'
        b'    "capture": {\n'
        b'      "stdout_bytes": 64,\n'
        b'      "stderr_bytes": 1558,\n'
        b'      "stdout_truncated": false,\n'
        b'      "stderr_truncated": false\n'
        b'    },\n'
        b'    "output_complete": true,\n'
        b'    "cleanup_proven": true\n'
        b'  },\n'
        b'  "lease": {\n'
        b'    "id": "ff793d9789fa",\n'
        b'    "pool": "codex-native",\n'
        b'    "account": "default",\n'
        b'    "host": "mb",\n'
        b'    "orchestrator_id": "01a0e2a5-33b8-71f0-8723-4ccb1daee9fb",\n'
        b'    "state": "released"\n'
        b'  },\n'
        b'  "state": "BOUNDED_ROUTE_ACCEPTED",\n'
        b'  "served_model_and_billed_usage": "unattested",\n'
        b'  "limitations": "transport/task qualification only; not general quality or fleet-wide qualification"\n'
        b'}\n'
    ),
}


class MechanicsOnlyAdapter:
    """Not a production adapter; methods must never execute during preparation."""

    adapter_id = "mechanics-only"

    async def status(self, ref):
        raise AssertionError("preparation must not observe or launch a worker")


class MechanicsOnlyCodexAdapter(MechanicsOnlyAdapter):
    adapter_id = "codex-cli"


def owner_for(mode, router, alias_name):
    evidence, role = binding._read_receipt(RECEIPTS[mode])
    alias = router.resolve_model_alias(alias_name)
    return binding.PoolBindingOwnerInputs(
        worker_id="fixture-worker", quota_class="fixture-quota",
        account_label="explicit-owner-account", provider=alias.provider_alias,
        model_alias=alias_name, model=evidence.requested_model,
        adapter_id=alias.adapter_id, routing_policy_version=router.policy_version,
        execution_profile_id=alias.execution_profile_id,
        execution_profile_digest=alias.execution_profile_digest,
        capability_policy_version=alias.capability_policy_version,
        capability_policy_digest=alias.capability_policy_digest,
        effort=alias.effort, cost_class=alias.cost_class, role=role,
        host_alias=evidence.host, host_ref="host-" + "1" * 64,
        capacity_capability_id="owner-host-capacity",
        worker_source_config_digest="2" * 64, capabilities=("code",),
    )


@pytest.fixture
def offline_mechanics(monkeypatch):
    """Use real validators with TEST-ONLY reviewed-class registrations.

    These patches are local to the test. They do not change source descriptors,
    production routes, enrollment or adapter readiness.
    """
    def make(mode="oc-free"):
        cls = MechanicsOnlyCodexAdapter if mode == "codex-native" else MechanicsOnlyAdapter
        descriptor = worker_adapter.AdapterDescriptor(
            adapter_id=cls.adapter_id, implemented=True,
            implementation=f"{__name__}.{cls.__name__}",
        )
        monkeypatch.setitem(worker_adapter.ADAPTER_DESCRIPTORS, cls.adapter_id, descriptor)
        if mode == "codex-native":
            monkeypatch.setattr(worker_adapter, "_codex_constructed_adapters",
                                lambda: worker_adapter._CONSTRUCTED_REVIEWED_ADAPTERS)
        canonical = ModelRouter.load()
        template = canonical.resolve_model_alias("fast.engineering")
        evidence, _ = binding._read_receipt(RECEIPTS[mode])
        alias = dataclasses.replace(
            template, model_alias="fixture.external", provider_alias="fixture-provider",
            adapter_id=cls.adapter_id, model=evidence.requested_model,
        )
        router = ModelRouter(
            policy_version=canonical.policy_version,
            providers={"fixture-provider": ProviderAlias("fixture-provider", cls.adapter_id, True, True)},
            model_aliases={alias.model_alias: alias}, routes=canonical.routes,
            capability_registry=canonical.capability_registry, source_path=canonical.source_path,
        )
        owner = owner_for(mode, router, alias.model_alias)
        adapter = worker_adapter.construct_reviewed_adapter(cls.adapter_id)
        return owner, router, adapter
    return make


def prepare(mode, values):
    owner, router, adapter = values
    return binding.prepare_pool_binding(RECEIPTS[mode], owner=owner, router=router, adapter=adapter)


@pytest.mark.parametrize("mode", tuple(RECEIPTS))
def test_all_accepted_receipts_offline_mechanics_only(mode, offline_mechanics):
    result = prepare(mode, offline_mechanics(mode))
    assert result.evidence.mode == mode
    assert result.owner.model == result.evidence.requested_model
    assert result.capacity_join.host_ref == "host-" + "1" * 64
    assert result.metadata["qualified_route_role"] == result.owner.role
    assert result.metadata["qualified_route_mode"] == mode
    assert "status" not in result.quota_registration
    assert not hasattr(result, "available")
    assert not hasattr(result, "capacity")
    # This API handles one binding; four evidence options do not widen acquisition.
    assert MAX_CANDIDATES == 3


@pytest.mark.parametrize("receipt", [b"", b"{}", b"x" * 65_537,
                                    RECEIPTS["oc-free"][:-1], RECEIPTS["oc-free"] + b"\n",
                                    bytearray(RECEIPTS["oc-free"])])
def test_unpinned_or_unbounded_receipts_refuse(receipt, offline_mechanics):
    owner, router, adapter = offline_mechanics()
    with pytest.raises(binding.PoolBindingRefusal, match="RECEIPT_"):
        binding.prepare_pool_binding(receipt, owner=owner, router=router, adapter=adapter)


@pytest.mark.parametrize("mode", ["grok", "cursor", "codex-native"])
def test_operator_receipt_cannot_be_relabeled_execute(mode, offline_mechanics):
    owner, router, adapter = offline_mechanics(mode)
    with pytest.raises(binding.PoolBindingRefusal, match="ROLE_NOT_PINNED"):
        prepare(mode, (dataclasses.replace(owner, role="execute"), router, adapter))


@pytest.mark.parametrize("change,code", [
    ({"host_alias": "another-host"}, "HOST_ALIAS_MISMATCH"),
    ({"model": "another-model"}, "QUALIFIED_MODEL_MISMATCH"),
    ({"role": "operator"}, "ROLE_NOT_PINNED"),
    ({"routing_policy_version": "changed"}, "ROUTING_POLICY_VERSION_MISMATCH"),
    ({"execution_profile_digest": "3" * 64}, "EXECUTION_PROFILE_DIGEST_MISMATCH"),
    ({"capability_policy_digest": "3" * 64}, "CAPABILITY_POLICY_DIGEST_MISMATCH"),
    ({"capability_policy_version": "changed"}, "CAPABILITY_POLICY_VERSION_MISMATCH"),
    ({"cost_class": "frontier"}, "COST_CLASS_MISMATCH"),
    ({"effort": "different"}, "EFFORT_MISMATCH"),
    ({"model_alias": "missing"}, "MODEL_ALIAS_NOT_WORKER_ELIGIBLE"),
    ({"capabilities": ("arbitrary-capability", "code")}, "CAPABILITY_WIDENED"),
])
def test_owner_cannot_change_qualified_or_canonical_identity(change, code, offline_mechanics):
    owner, router, adapter = offline_mechanics()
    with pytest.raises(binding.PoolBindingRefusal, match=code):
        prepare("oc-free", (dataclasses.replace(owner, **change), router, adapter))


@pytest.mark.parametrize("change", [
    {"worker_id": "x" * 65}, {"quota_class": "x" * 65},
    {"quota_class": "UPPER"}, {"account_label": ""},
    {"host_ref": "local-unbound"}, {"worker_source_config_digest": "missing"},
    {"capabilities": ["code"]}, {"capabilities": ("code", "code")},
    {"role": []}, {"capabilities": ()},
])
def test_malformed_owner_inputs_refuse(change, offline_mechanics):
    owner, _, _ = offline_mechanics()
    with pytest.raises(binding.PoolBindingRefusal):
        dataclasses.replace(owner, **change)


def test_alias_cannot_disagree_with_provider_descriptor(offline_mechanics):
    owner, router, adapter = offline_mechanics()
    router.providers[owner.provider] = dataclasses.replace(router.providers[owner.provider], adapter_id="different")
    with pytest.raises(binding.PoolBindingRefusal, match="ADAPTER_MISMATCH"):
        prepare("oc-free", (owner, router, adapter))


def test_disabled_profile_refuses(offline_mechanics):
    owner, router, adapter = offline_mechanics()
    registry = router.capability_registry
    registry.profiles[owner.execution_profile_id] = dataclasses.replace(
        registry.profiles[owner.execution_profile_id], enabled=False)
    with pytest.raises(binding.PoolBindingRefusal, match="EXECUTION_PROFILE_UNRESOLVED"):
        prepare("oc-free", (owner, router, adapter))


def test_unreviewed_instance_cannot_impersonate_constructed_adapter(offline_mechanics):
    owner, router, _ = offline_mechanics()
    with pytest.raises(binding.PoolBindingRefusal, match="ADAPTER_NOT_REVIEWED"):
        prepare("oc-free", (owner, router, MechanicsOnlyAdapter()))


def test_codex_adapter_cannot_relabel_free_provider(offline_mechanics):
    owner, router, adapter = offline_mechanics()
    with pytest.raises(binding.PoolBindingRefusal, match="MODE_ADAPTER_MISMATCH"):
        prepare("oc-free", (dataclasses.replace(owner, adapter_id="codex-cli"), router, adapter))


def test_actual_unimplemented_descriptor_stays_refused():
    router = ModelRouter.load()
    owner = dataclasses.replace(owner_for("oc-free", router, "fast.engineering"), adapter_id="openai-compatible")
    with pytest.raises(binding.PoolBindingRefusal, match="ADAPTER_NOT_IMPLEMENTED"):
        prepare("oc-free", (owner, router, object()))


def test_current_canonical_codex_alias_does_not_claim_qualified_native_model():
    router = ModelRouter.load()
    owner = owner_for("codex-native", router, "coo.sealed")
    with pytest.raises(binding.PoolBindingRefusal, match="MODEL_MISMATCH"):
        prepare("codex-native", (owner, router, object()))


def test_preparation_is_immutable_and_registration_arguments_are_detached(offline_mechanics):
    owner, router, adapter = offline_mechanics()
    result = prepare("oc-free", (owner, router, adapter))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.owner.role = "operator"
    with pytest.raises(TypeError):
        result.metadata["capacity_join"]["host_ref"] = "changed"
    with pytest.raises(TypeError):
        result.registration_kwargs()  # Caller must explicitly supply status.
    with pytest.raises(binding.PoolBindingRefusal, match="STATUS_BUSY_FORBIDDEN"):
        result.registration_kwargs(status=WorkerStatus.BUSY)
    first = result.registration_kwargs(status=WorkerStatus.OFFLINE)
    inspect.signature(WorkerRegistry.register_worker).bind(None, **first["worker"])
    inspect.signature(WorkerRegistry.register_quota_class).bind(None, **first["quota"])
    first["quota"]["metadata"]["capacity_join"]["host_ref"] = "changed"
    first["worker"]["capabilities"].append("arbitrary-capability")
    second = result.registration_kwargs(status=WorkerStatus.OFFLINE)
    assert second["quota"]["metadata"]["capacity_join"]["host_ref"] == owner.host_ref
    assert second["worker"]["capabilities"] == ["code"]
    assert second["worker"]["status"] == WorkerStatus.OFFLINE
    assert first["worker"]["quota_classes"][owner.quota_class]["metadata"]["capacity_join"]["host_ref"] == owner.host_ref
    # Mutating the original router cannot rewrite a prepared result.
    router.model_aliases.clear()
    assert result.owner.model == "mimo-v2.5-free"
