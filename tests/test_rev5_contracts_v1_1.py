"""Rev 5 D1 contract extension tests (v1 → compatible v1.1).

Acceptance (Rev 5 §9 D1 + change order §3A/§5):
  * old v1 records round-trip UNCHANGED — same keys, same schema label,
    same ``request_digest`` (digest stability pin below);
  * v1.1 records round-trip with the extension blocks populated;
  * a record only declares ``*.v1.1`` when extension content is present;
  * the Hermes plugin routing-law parity is untouched (23/23 in
    ``test_child_execution_contracts.py`` — this file must not weaken it);
  * every ``AdapterDescriptor`` declares runtime kind, descendant policy
    and a SUPPORTED/UNSUPPORTED/UNKNOWN capability map.
"""

import json

import pytest

from control_plane.child_execution_contracts import (
    CHILD_EXECUTION_REQUEST_SCHEMA,
    CHILD_EXECUTION_REQUEST_SCHEMA_V1_1,
    DESCENDANT_POLICIES,
    EXECUTION_BINDING_SCHEMA,
    EXECUTION_BINDING_SCHEMA_V1_1,
    KNOWN_RUNTIME_KINDS,
    FanoutEnvelope,
    LocalitySpec,
    WorkspaceRequirements,
    ChildExecutionRequest,
    ExecutionBinding,
)
from control_plane.worker_adapter import (
    ADAPTER_DESCRIPTORS,
    AdapterCapability,
    capability_status,
    descriptor_problems,
)

#: sha256 of the v1-era canonical payload for the fixture below, computed
#: under the UNEXTENDED v1 code.  The Rev 5 extension must never change
#: a v1 request's digest: a v1-era redelivery after the upgrade is a
#: retry, never an idempotency conflict.
V1_REQUEST_DIGEST_PIN = (
    "5832f479ded965053bf96f395735e1cb8ee33882b4a5e1a4c7ce9c8bbc237413"
)

#: The v1-era serialized key set of ExecutionBinding (25 keys).  A v1
#: binding must serialize with EXACTLY these keys through v1.1 code.
V1_BINDING_KEYS = frozenset({
    "schema", "root_run_ref", "immediate_parent_run_ref", "logical_child_key",
    "request_digest", "effective_complexity", "original_root_orchestrator_ref",
    "task_kind", "job_ref", "attempt_ref", "policy_revision", "decision_ref",
    "scope_digest", "budget_grant_ref", "adapter_id", "model_ref",
    "provider_ref", "pool_ref", "shared_quota_resource_refs", "host_id",
    "worker_id", "host_boot_id", "assignment_generation", "fence_counter",
    "lease_expiry",
})


def _v1_request() -> ChildExecutionRequest:
    return ChildExecutionRequest(
        root_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-a", task_kind="code",
        requested_complexity="C2_COMPLEX_BOUNDED",
        brief_ref="mem://b1", fallback_mode="shared")


def _v1_binding(digest: str) -> ExecutionBinding:
    return ExecutionBinding(
        root_run_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-a", request_digest=digest,
        effective_complexity="C2_COMPLEX_BOUNDED",
        host_id="h1", host_boot_id="b1", adapter_id="hermes-native")


def _v1_1_request() -> ChildExecutionRequest:
    return ChildExecutionRequest(
        root_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-b",
        requested_complexity="C1_ROUTINE_BOUNDED",
        locality=LocalitySpec(parent_host_preference=True),
        runtime_preference="t3-native",
        workspace_requirements=WorkspaceRequirements(
            mode="isolated_patch", base_ref="refs/heads/x"),
        declared_fanout=FanoutEnvelope(
            max_descendants=5, max_concurrent=2,
            reservation_model="envelope_reserved",
            enforcement_ref="dsh://spawn-hook"))


def _v1_1_binding(digest: str) -> ExecutionBinding:
    return ExecutionBinding(
        root_run_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-b", request_digest=digest,
        effective_complexity="C1_ROUTINE_BOUNDED",
        runtime_kind="t3-native",
        t3_environment_ref="env-9", t3_server_ref="srv-1",
        project_ref="proj-2", thread_ref="th-3", run_ref="run-4",
        provider_instance_ref="pi-1", native_session_ref="ns-7",
        workspace_ref="ws-1", base_ref="base-1", writer_epoch=3,
        lease_ref="lease-9", operation_key="clientRequestId-42",
        caller_namespace="principal://fable",
        descendant_policy="bounded_native_fanout",
        declared_fanout_envelope=FanoutEnvelope(
            max_descendants=8, max_concurrent=2,
            reservation_model="envelope_reserved",
            enforcement_ref="t3://effect-worker-admission"))


# --- old v1 records round-trip unchanged ---------------------------------------


def test_v1_request_digest_is_pinned_across_the_extension():
    assert _v1_request().request_digest == V1_REQUEST_DIGEST_PIN


def test_v1_request_round_trips_unchanged():
    request = _v1_request()
    payload = request.to_dict()
    assert request.schema == CHILD_EXECUTION_REQUEST_SCHEMA
    assert "locality" not in payload and "runtime_preference" not in payload
    assert "workspace_requirements" not in payload
    assert "declared_fanout" not in payload
    rebuilt = ChildExecutionRequest.from_dict(payload)
    assert rebuilt == request
    assert rebuilt.schema == CHILD_EXECUTION_REQUEST_SCHEMA
    assert rebuilt.request_digest == V1_REQUEST_DIGEST_PIN


def test_v1_binding_round_trips_with_exactly_the_v1_key_set():
    binding = _v1_binding(V1_REQUEST_DIGEST_PIN)
    payload = binding.to_dict()
    assert frozenset(payload) == V1_BINDING_KEYS
    assert binding.schema == EXECUTION_BINDING_SCHEMA
    rebuilt = ExecutionBinding.from_dict(payload)
    assert rebuilt == binding
    assert rebuilt.schema == EXECUTION_BINDING_SCHEMA


def test_v1_binding_constructed_positionally_still_binds():
    """Positional construction (broker call sites) is unaffected: the
    extension fields all append AFTER the v1 field order."""
    binding = ExecutionBinding(
        "root-1", "parent-1", "child-a", V1_REQUEST_DIGEST_PIN,
        "C2_COMPLEX_BOUNDED")
    assert binding.host_id == "" and binding.runtime_kind == ""
    request = _v1_request()
    assert binding.binds_request(request)


def test_v1_redelivery_after_upgrade_is_retry_not_conflict():
    """Rev 5 §9 'Attach new binding fields compatibly': a v1-era request
    redelivered through v1.1 code keeps its digest, so the idempotency
    machinery sees a retry, never a manufactured conflict."""
    original = _v1_request()
    redelivered = ChildExecutionRequest.from_dict(json.loads(
        json.dumps(original.to_dict())))
    assert original.is_idempotent_retry(redelivered)
    assert not original.is_idempotency_conflict(redelivered)


# --- v1.1 records round-trip ----------------------------------------------------


def test_v1_1_request_round_trips_and_upgrades_schema():
    request = _v1_1_request()
    assert request.schema == CHILD_EXECUTION_REQUEST_SCHEMA_V1_1
    payload = request.to_dict()
    assert payload["schema"] == CHILD_EXECUTION_REQUEST_SCHEMA_V1_1
    assert payload["locality"] == {"parent_host_preference": True,
                                   "hard_affinity": False,
                                   "hard_affinity_reason": ""}
    rebuilt = ChildExecutionRequest.from_dict(payload)
    assert rebuilt == request
    assert rebuilt.schema == CHILD_EXECUTION_REQUEST_SCHEMA_V1_1
    assert rebuilt.declared_fanout.enforcement_ref == "dsh://spawn-hook"


def test_v1_1_binding_round_trips_full_native_chain():
    request = _v1_1_request()
    binding = _v1_1_binding(request.request_digest)
    assert binding.schema == EXECUTION_BINDING_SCHEMA_V1_1
    assert binding.runtime_kind == "t3-native"
    rebuilt = ExecutionBinding.from_dict(json.loads(json.dumps(binding.to_dict())))
    assert rebuilt == binding
    assert rebuilt.t3_environment_ref == "env-9"
    assert rebuilt.writer_epoch == 3
    assert rebuilt.operation_key == "clientRequestId-42"
    assert rebuilt.caller_namespace == "principal://fable"
    assert rebuilt.binds_request(request)


def test_v1_1_extension_content_participates_in_the_digest():
    """A request that adds locality/workspace/fan-out is semantically
    different work — its digest must differ from the bare v1 core."""
    bare = ChildExecutionRequest(
        root_ref="root-1", immediate_parent_run_ref="parent-1",
        logical_child_key="child-b",
        requested_complexity="C1_ROUTINE_BOUNDED")
    assert _v1_1_request().request_digest != bare.request_digest


def test_v1_1_labelled_payload_without_extension_content_is_v1():
    """A v1.1-labelled payload with no extension fields IS a v1 record;
    the label alone must not leak into equality or re-serialization."""
    payload = _v1_binding(V1_REQUEST_DIGEST_PIN).to_dict()
    payload["schema"] = EXECUTION_BINDING_SCHEMA_V1_1
    rebuilt = ExecutionBinding.from_dict(payload)
    assert rebuilt.schema == EXECUTION_BINDING_SCHEMA
    assert rebuilt == _v1_binding(V1_REQUEST_DIGEST_PIN)


def test_unknown_schema_label_is_rejected():
    payload = _v1_binding(V1_REQUEST_DIGEST_PIN).to_dict()
    payload["schema"] = "ExecutionBinding.v99"
    with pytest.raises(ValueError, match="schema"):
        ExecutionBinding.from_dict(payload)
    payload = _v1_request().to_dict()
    payload["schema"] = "ChildExecutionRequest.v99"
    with pytest.raises(ValueError, match="schema"):
        ChildExecutionRequest.from_dict(payload)


def test_runtime_kind_is_normalized_to_canonical_form():
    binding = ExecutionBinding(
        root_run_ref="r", immediate_parent_run_ref="p", logical_child_key="c",
        request_digest="a" * 64, effective_complexity="C0_MECHANICAL",
        runtime_kind="  T3-NATIVE  ")
    assert binding.runtime_kind == "t3-native"


def test_known_runtime_kinds_cover_the_rev5_change_order_list():
    for kind in ("hermes-native", "t3-native", "dsh-acp", "opencode-free-cli"):
        assert kind in KNOWN_RUNTIME_KINDS


# --- extension validation -------------------------------------------------------


def test_hard_affinity_requires_reason():
    with pytest.raises(ValueError, match="hard_affinity_reason"):
        LocalitySpec(hard_affinity=True)
    LocalitySpec(hard_affinity=True,
                 hard_affinity_reason="exact mutable workspace lease ws-1")


def test_workspace_mode_must_be_supported_intent():
    with pytest.raises(ValueError, match="mode"):
        WorkspaceRequirements(mode="writable_free_for_all")
    for mode in ("read_only_snapshot", "single_writer", "isolated_patch"):
        WorkspaceRequirements(mode=mode)


def test_fanout_envelope_bounds_are_sane():
    with pytest.raises(ValueError, match="max_descendants"):
        FanoutEnvelope(max_descendants=-1)
    with pytest.raises(ValueError, match="max_concurrent"):
        FanoutEnvelope(max_descendants=4, max_concurrent=0)
    with pytest.raises(ValueError, match="reservation_model"):
        FanoutEnvelope(max_descendants=4, reservation_model="double_dip")


@pytest.mark.parametrize("policy", sorted(DESCENDANT_POLICIES))
def test_descendant_policy_vocabulary_is_enforced(policy):
    legal = dict(
        root_run_ref="r", immediate_parent_run_ref="p", logical_child_key="c",
        request_digest="a" * 64, effective_complexity="C0_MECHANICAL",
        descendant_policy=policy)
    if policy == "bounded_native_fanout":
        legal["declared_fanout_envelope"] = FanoutEnvelope(
            max_descendants=6, enforcement_ref="t3://admission-hook")
    ExecutionBinding(**legal)
    with pytest.raises(ValueError, match="descendant_policy"):
        ExecutionBinding(**{**legal, "descendant_policy": policy + "x"})


def test_bounded_native_fanout_requires_enforced_envelope():
    base = dict(root_run_ref="r", immediate_parent_run_ref="p",
                logical_child_key="c", request_digest="a" * 64,
                effective_complexity="C0_MECHANICAL",
                descendant_policy="bounded_native_fanout")
    with pytest.raises(ValueError, match="declared_fanout_envelope"):
        ExecutionBinding(**base)
    # zero-descendant bounded envelope is a contradiction in terms
    with pytest.raises(ValueError, match="at least one"):
        ExecutionBinding(**{**base, "declared_fanout_envelope": FanoutEnvelope(
            max_descendants=0)})
    # a promise without a named native enforcement mechanism is insufficient
    with pytest.raises(ValueError, match="enforcement_ref"):
        ExecutionBinding(**{**base, "declared_fanout_envelope": FanoutEnvelope(
            max_descendants=4)})
    # lawful: envelope + named enforcement
    ExecutionBinding(**{**base, "declared_fanout_envelope": FanoutEnvelope(
        max_descendants=4, enforcement_ref="dsh://spawn-hook")})


def test_writer_epoch_must_be_non_negative():
    with pytest.raises(ValueError, match="writer_epoch"):
        ExecutionBinding(
            root_run_ref="r", immediate_parent_run_ref="p",
            logical_child_key="c", request_digest="a" * 64,
            effective_complexity="C0_MECHANICAL", writer_epoch=-1)


# --- descriptor contract (worker_adapter) ---------------------------------------


def test_every_descriptor_declares_runtime_policy_and_capabilities():
    problems = [problem
                for descriptor in ADAPTER_DESCRIPTORS.values()
                for problem in descriptor_problems(descriptor)]
    assert problems == []


def test_descriptor_extension_fields_are_optional_and_defaulted():
    descriptor = ADAPTER_DESCRIPTORS["codex-cli"]
    assert descriptor.runtime_kind == "codex-cli"
    assert descriptor.descendant_policy in DESCENDANT_POLICIES
    assert descriptor.capabilities


def test_capability_status_is_fail_closed():
    assert capability_status("codex-cli", "cancel") == "SUPPORTED"
    assert capability_status("t3-native", "launch") == "UNKNOWN"
    assert capability_status("hermes-native", "resume") == "UNKNOWN"
    assert capability_status("hermes-native", "descendant_admission") == "UNKNOWN"


def test_adapter_capability_status_vocabulary():
    with pytest.raises(ValueError, match="status"):
        AdapterCapability(capability="resume", status="MAYBE")
    AdapterCapability(capability="resume", status="UNKNOWN")


def test_incomplete_descriptor_reports_problems():
    from control_plane.worker_adapter import AdapterDescriptor
    problems = descriptor_problems(AdapterDescriptor(adapter_id="stub"))
    assert any("runtime_kind" in p for p in problems)
    assert any("descendant_policy" in p for p in problems)
    assert any("capability map" in p for p in problems)


def test_rev5_lane_seams_are_registered_named_not_implemented():
    """The lane seams are REGISTERED (one reviewed id each, runtime kind
    declared, capability map present) but implemented=False until the
    lane's full composition is reviewed — naming selects nothing.

    Deliberately does NOT pin ``descendant_policy``: each Rev 5 lane owns
    flipping its own seam's policy (e.g. DSH moving ``dsh-acp`` to
    ``bounded_native_fanout`` with a named native enforcement once its
    hook is proven) — that is the lane's charter, not this contract's
    invariant.  The invariants here are the ones the shared contract
    owns: reviewed registration, declared runtime kind, a capability
    map, and no live binding before review."""
    for lane_id in ("t3-native", "dsh-acp"):
        descriptor = ADAPTER_DESCRIPTORS[lane_id]
        assert descriptor.runtime_kind == lane_id
        assert not descriptor.implemented
        assert descriptor.descendant_policy in DESCENDANT_POLICIES
        assert descriptor.capabilities
        # naming the route selects nothing and launches nothing
        assert capability_status(lane_id, "launch") in ("UNKNOWN", "UNSUPPORTED")
