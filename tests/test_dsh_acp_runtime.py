"""Rev 5 DSH lane tests: dsh-acp runtime descriptor, descendant policy
enforcement, two-level root lineage, and the binding-required lane gate.

Evidence anchors (M2, 2026-11-08, dsh 0.2.2-rc.1):
* live ACP session receipts under
  ~/.hermes/profiles/engineering/cache/scratch/dsh-acp-probe/ — the
  mmx-acp session that spawned native child fe1d0c8f-… via the ``subagent``
  tool and settled only after the child completed;
* the three-row refusal receipt (``acp`` as an app argument is rejected:
  "too many arguments. Expected 0 arguments but got 1: acp");
* the @deepseek-ai/dsh-subagent contract (enforced maxActiveSubagents /
  maxDepth envelope, process-local in-process children).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from control_plane.child_execution_contracts import (
    ChildExecutionRequest,
    ExecutionBinding,
)
from control_plane.execution_binding_compat import (
    BINDING_REQUIRED,
    ExecutionBindingCompatError,
    binding_for_launch_spec,
)
from control_plane.dsh_acp_runtime import (
    BOUNDED_NATIVE_FANOUT,
    DESCENDANT_POLICIES,
    DSH_ACP_RUNTIME,
    DSH_ACP_RUNTIME_ID,
    DSH_RUNTIME_KIND,
    DescendantPolicyViolation,
    DshAcpCapability,
    DshAcpProviderConfig,
    DshDescendantPolicy,
    DshExecutiveToolsBridge,
    DshRuntimeDescriptor,
    NativeFanoutEnvelope,
    SUPPORTED,
    UNKNOWN,
    UNSUPPORTED,
    descendant_policy,
)
from control_plane.dsh_lineage import (
    DshNativeRef,
    LineageConservationError,
    LineageLevel,
    assert_lineage_conservation,
    child_request_from_binding,
    native_chain_matches,
    run_ref,
    two_level_glm_dsflash_chain,
)
from control_plane.worker_adapter import (
    ADAPTER_DESCRIPTORS,
    AdapterBindingError,
    adapter_descriptor,
    adapter_implementation,
)


# --- helpers -----------------------------------------------------------------

def _binding_for(request: ChildExecutionRequest, *, run_tag: str = "") -> ExecutionBinding:
    """A synthetic broker-issued binding fencing exactly this request."""
    return ExecutionBinding(
        root_run_ref=request.root_ref,
        immediate_parent_run_ref=request.immediate_parent_run_ref,
        logical_child_key=request.logical_child_key,
        request_digest=request.request_digest,
        effective_complexity=request.requested_complexity or "C2_COMPLEX_BOUNDED",
        job_ref=f"job:{run_tag or request.logical_child_key}",
        attempt_ref=f"attempt:{run_tag or request.logical_child_key}",
    )


def _root_request(key: str = "glm-director") -> ChildExecutionRequest:
    return ChildExecutionRequest(
        root_ref="root/run-2026-11-08",
        immediate_parent_run_ref="root/run-2026-11-08",
        logical_child_key=key,
        task_kind="implementation",
        requested_complexity="C2_COMPLEX_BOUNDED",
    )


# --- descriptor identity and provider config ---------------------------------

def test_runtime_is_dsh_distinct_from_model_deepseek():
    assert DSH_RUNTIME_KIND == "dsh"
    assert DSH_ACP_RUNTIME.runtime_kind == "dsh"
    # Selecting a DeepSeek model elsewhere is NOT this harness.
    assert DSH_ACP_RUNTIME.distinct_from_model == "deepseek"
    assert DSH_ACP_RUNTIME.runtime_kind != DSH_ACP_RUNTIME.distinct_from_model


def test_descriptor_refuses_collapsing_runtime_into_model():
    with pytest.raises(ValueError):
        DshRuntimeDescriptor(
            runtime_kind="deepseek", distinct_from_model="deepseek",
            descendant_policy=descendant_policy())


def test_provider_config_records_exact_t3_shape():
    config = DSH_ACP_RUNTIME.provider_config
    assert isinstance(config, DshAcpProviderConfig)
    assert config.executable == "dsh"
    # One literal argument per row; the acp-app profile takes ZERO app
    # arguments, so the rows are the launcher flags only.
    assert config.argument_rows == ("--profile", "mmx-acp")
    assert config.launch_argv() == ("dsh", "--profile", "mmx-acp")
    # The T3-doc two-row shape against the SHIPPED profile is also verified
    # live: `acp` is the profile NAME, not an app argument.
    assert config.shipped_profile_argument_rows == ("--profile", "acp")
    assert "settings.json" in config.t3_persistence
    assert "Local ACP command" in config.t3_ui_path
    # Credentials stay with DSH; nothing embeds them here.  The note names
    # the apiKeyEnv MECHANISM (dsh reads its own env), never a key value.
    blob = repr(config)
    assert "apiKeyEnv" in config.environment_overrides_note
    for forbidden in ("ZAI_API_KEY=", "DEEPSEEK_API_KEY=", "Bearer ", "sk-"):
        assert forbidden not in blob


def test_three_row_app_argument_shape_is_refused_by_the_profile():
    # The three-row reading (--profile, <name>, acp — `acp` as an APP
    # argument) fails to boot the acp-app profile: "too many arguments.
    # Expected 0 arguments but got 1: acp" (live refusal receipt).  The
    # descriptor must therefore never emit it.
    config = DSH_ACP_RUNTIME.provider_config
    assert "acp" not in config.argument_rows[1:]


def test_capability_discovery_recorded_from_real_probes():
    caps = DSH_ACP_RUNTIME.capabilities
    for name in ("resume", "import", "models", "permissions", "usage"):
        cap = caps[name]
        assert isinstance(cap, DshAcpCapability)
        assert cap.status in ("SUPPORTED", "UNSUPPORTED", "UNKNOWN")
        assert cap.evidence, f"{name} capability lacks evidence"
    # Live-observed facts from the M2 probe.
    assert caps["resume"].status == SUPPORTED
    assert caps["import"].status == SUPPORTED
    assert caps["models"].status == SUPPORTED
    assert caps["permissions"].status == SUPPORTED
    # Usage is context-window only; per-model-call usage is UNKNOWN —
    # reserve conservatively per managed turn plus the declared envelope.
    assert caps["usage"].status == SUPPORTED
    assert "context-window" in caps["usage"].scope
    assert caps["usage_per_model_call"].status == UNKNOWN
    # Preserved limitations (Rev 5 l.369).
    assert caps["acp_workspace_rollback_rewinds_conversation"].status == UNSUPPORTED
    assert caps["session_transcript_replay"].status == UNSUPPORTED


def test_capability_status_is_lawful():
    with pytest.raises(ValueError):
        DshAcpCapability(status="PARTIAL")


# --- registry discipline -----------------------------------------------------

def test_registry_row_names_the_route_and_binds_nothing():
    assert DSH_ACP_RUNTIME_ID in ADAPTER_DESCRIPTORS
    descriptor = adapter_descriptor("dsh-acp")
    assert descriptor.adapter_id == DSH_ACP_RUNTIME_ID
    assert descriptor.implemented is False
    # Fail closed: a routing policy can never bind a live worker through
    # this id until the composition is reviewed.
    with pytest.raises(AdapterBindingError):
        adapter_implementation("dsh-acp")


# --- descendant policy: the choice and its evidence --------------------------

def test_policy_is_bounded_native_fanout_chosen_by_evidence():
    policy = DSH_ACP_RUNTIME.descendant_policy
    assert policy.policy == BOUNDED_NATIVE_FANOUT
    assert policy.policy in DESCENDANT_POLICIES
    assert policy.envelope is not None
    assert policy.envelope.max_active_subagents == 8
    assert policy.envelope.max_depth == 1
    assert policy.envelope.host_scope == "process-local"
    evidence = " ".join(policy.evidence)
    # The live observation that decided it: a native child spawned behind
    # the ACP parent and the prompt settled only after the child completed.
    assert "fe1d0c8f-82d2-45f5-ba27-3e9c7770593a" in evidence
    assert "ACTIVATION_LIMIT_REACHED" in evidence
    assert "in-process" in evidence


def test_fabric_per_child_without_a_real_hook_is_refused():
    # A configuration promise without a real native enforcement mechanism
    # is insufficient (Rev 5 descendant policy) — construction fails.
    with pytest.raises(DescendantPolicyViolation):
        DshDescendantPolicy(policy="fabric_per_child")
    # Even with a claimed hook, carrying an envelope too would double
    # reserve; refused.
    with pytest.raises(DescendantPolicyViolation):
        DshDescendantPolicy(
            policy="fabric_per_child",
            admission_hook_evidence="hypothetical out-of-process provider",
            envelope=NativeFanoutEnvelope(max_active_subagents=4, max_depth=1))


def test_bounded_policy_requires_the_actual_envelope():
    with pytest.raises(DescendantPolicyViolation):
        DshDescendantPolicy(policy=BOUNDED_NATIVE_FANOUT)


def test_envelope_drift_from_the_reserved_one_refuses_admission():
    policy = DSH_ACP_RUNTIME.descendant_policy
    # Matching observation passes.
    policy.validate_profile_observation(8, 1)
    # A silently widened profile (e.g. desktop-style 16/4 overrides) is a
    # reservation lie — refuse until re-reserved or re-qualified.
    with pytest.raises(DescendantPolicyViolation, match="drifted"):
        policy.validate_profile_observation(16, 4)
    with pytest.raises(DescendantPolicyViolation, match="drifted"):
        policy.validate_profile_observation(8, 2)


def test_per_child_reservation_on_a_bounded_lane_is_double_counting():
    policy = DSH_ACP_RUNTIME.descendant_policy
    # The ONE reservation is the envelope at the dsh process's host; a
    # per-child slot reservation on top charges the same children twice.
    with pytest.raises(DescendantPolicyViolation, match="double counting"):
        policy.reserve_descendant_slot("dsh-child-1")


def test_disabled_policy_refuses_every_native_child():
    policy = DshDescendantPolicy(policy="native_fanout_disabled")
    with pytest.raises(DescendantPolicyViolation, match="native_fanout_disabled"):
        policy.reserve_descendant_slot("any-child")
    with pytest.raises(DescendantPolicyViolation, match="refused"):
        policy.account_observed_child(1)


def test_observed_children_account_inside_the_envelope():
    policy = DSH_ACP_RUNTIME.descendant_policy
    assert policy.account_observed_child(3) == 3
    assert policy.account_observed_child(8) == 8
    # A hidden child beyond the reserved envelope is a policy violation —
    # dsh should have refused it (ACTIVATION_LIMIT_REACHED); observing more
    # means the profile was altered without re-qualification.
    with pytest.raises(DescendantPolicyViolation, match="exceed"):
        policy.account_observed_child(9)
    with pytest.raises(DescendantPolicyViolation, match="depth"):
        policy.account_observed_child(2, observed_depth=2)


def test_fabric_per_child_with_a_real_hook_admits_per_child():
    # The other branch remains constructible when a REAL hook exists — but
    # the shipped dsh-acp descriptor does not claim it (no hook in the
    # shipped composition).
    policy = DshDescendantPolicy(
        policy="fabric_per_child",
        admission_hook_evidence=(
            "out-of-process provider backend calling Executive admission "
            "at startActivation with the parent's root/binding"))
    # Children are admitted individually through the fabric hook; the
    # per-child reservation IS the model here (no envelope to double on).
    policy.reserve_descendant_slot("fabric-child-1")
    assert policy.account_observed_child(2) == 2


# --- two-level root lineage (GLM director → DS Flash child) -------------------

def test_two_level_chain_carries_the_same_root_to_the_grandchild():
    root_ref = "root/run-2026-11-08"
    # Level 1: the GLM director child of the root run.
    glm_request = _root_request("glm-director")
    glm_binding = _binding_for(glm_request, run_tag="glm")
    assert glm_binding.binds_request(glm_request)
    # Level 2: the DS Flash child OF THE DIRECTOR — derived, never re-rooted.
    ds_request = child_request_from_binding(
        glm_binding, "ds-flash-child",
        task_kind="implementation", requested_complexity="C2_COMPLEX_BOUNDED")
    assert ds_request.root_ref == root_ref
    assert ds_request.immediate_parent_run_ref == run_ref(glm_binding)
    ds_binding = _binding_for(ds_request, run_tag="dsflash")
    assert ds_binding.binds_request(ds_request)

    root_native = DshNativeRef(acp_session_id="acp-root-1111")
    glm_native = DshNativeRef(
        t3_thread_id="t3-thread-glm", acp_session_id="acp-root-1111",
        native_child_session="dsh-glm-2222", native_parent_session="acp-root-1111")
    ds_native = DshNativeRef(
        t3_thread_id="t3-thread-ds", acp_session_id="acp-root-1111",
        native_child_session="dsh-ds-3333", native_parent_session="dsh-glm-2222")

    level1, level2 = two_level_glm_dsflash_chain(
        root_ref,
        glm_run_binding=glm_binding, dsflash_run_binding=ds_binding,
        glm_request=glm_request, dsflash_request=ds_request,
        root_native=root_native, glm_native=glm_native, dsflash_native=ds_native)
    # The SAME root on the grandchild (level 2) — the Rev 5 requirement.
    assert level2.binding.root_run_ref == root_ref == level1.binding.root_run_ref
    assert level2.request.root_ref == root_ref
    # Immediate parent advances exactly one level.
    assert level2.request.immediate_parent_run_ref == run_ref(level1.binding)
    # Idempotency triples stay distinct per level.
    assert level1.request.idempotency_key() != level2.request.idempotency_key()
    assert native_chain_matches((level1, level2), root_native=root_native)


def test_lineage_refuses_re_rooting_and_level_skips():
    root_ref = "root/run-2026-11-08"
    glm_request = _root_request("glm-director")
    glm_binding = _binding_for(glm_request, run_tag="glm")
    ds_request = child_request_from_binding(glm_binding, "ds-flash-child")
    ds_binding = _binding_for(ds_request, run_tag="dsflash")

    good_l1 = LineageLevel(depth=1, request=glm_request, binding=glm_binding)
    good_l2 = LineageLevel(depth=2, request=ds_request, binding=ds_binding)
    assert_lineage_conservation(root_ref, (good_l1, good_l2))

    # A forged level-2 that re-roots under a different root is refused.
    forged_request = dataclasses.replace(ds_request, root_ref="root/OTHER")
    forged_binding = _binding_for(forged_request, run_tag="evil")
    with pytest.raises(LineageConservationError, match="root conservation"):
        assert_lineage_conservation(
            root_ref, (good_l1, LineageLevel(depth=2, request=forged_request,
                                             binding=forged_binding)))

    # A chain that skips level 1 is refused.
    with pytest.raises(LineageConservationError, match="root conservation|order"):
        assert_lineage_conservation(root_ref, (good_l2,))

    # A level whose binding does not fence its request is refused at
    # construction (identity triple or digest mismatch).
    other_request = dataclasses.replace(ds_request, task_kind="different-kind")
    with pytest.raises(LineageConservationError, match="fence"):
        LineageLevel(depth=2, request=other_request, binding=ds_binding)


def test_lineage_refuses_duplicate_child_identity():
    root_ref = "root/run-2026-11-08"
    glm_request = _root_request("glm-director")
    glm_binding = _binding_for(glm_request, run_tag="glm")
    ds_request = child_request_from_binding(glm_binding, "ds-flash-child")
    ds_binding = _binding_for(ds_request, run_tag="dsflash")
    l1 = LineageLevel(depth=1, request=glm_request, binding=glm_binding)
    l2 = LineageLevel(depth=2, request=ds_request, binding=ds_binding)
    # A second child of the SAME parent with the SAME logical key: the same
    # idempotency triple — a repeat or a conflict, never a new chain level.
    twin_request = child_request_from_binding(
        glm_binding, "ds-flash-child", task_kind="different-task")
    twin_binding = _binding_for(twin_request, run_tag="twin")
    l3 = LineageLevel(depth=3, request=twin_request, binding=twin_binding)
    with pytest.raises(LineageConservationError, match="duplicate"):
        assert_lineage_conservation(root_ref, (l1, l2, l3))


def test_same_key_different_digest_is_a_conflict_not_new_work():
    base = _root_request("glm-director")
    altered = dataclasses.replace(base, task_kind="different-task")
    assert base.idempotency_key() == altered.idempotency_key()
    assert base.request_digest != altered.request_digest
    assert base.is_idempotency_conflict(altered)
    assert not base.is_idempotent_retry(altered)


def test_native_chain_mismatch_is_detected():
    root_ref = "root/run-2026-11-08"
    glm_request = _root_request("glm-director")
    glm_binding = _binding_for(glm_request, run_tag="glm")
    ds_request = child_request_from_binding(glm_binding, "ds-flash-child")
    ds_binding = _binding_for(ds_request, run_tag="dsflash")
    root_native = DshNativeRef(acp_session_id="acp-root-1111")
    glm_native = DshNativeRef(
        acp_session_id="acp-root-1111", native_child_session="dsh-glm-2222",
        native_parent_session="acp-root-1111")
    # The DS child claims the WRONG native parent (not the GLM child).
    bad_ds_native = DshNativeRef(
        acp_session_id="acp-root-1111", native_child_session="dsh-ds-3333",
        native_parent_session="someone-else")
    with pytest.raises(LineageConservationError, match="native"):
        two_level_glm_dsflash_chain(
            root_ref,
            glm_run_binding=glm_binding, dsflash_run_binding=ds_binding,
            glm_request=glm_request, dsflash_request=ds_request,
            root_native=root_native, glm_native=glm_native,
            dsflash_native=bad_ds_native)


# --- binding-required lane gate ----------------------------------------------

class _Spec:
    """Minimal launch-spec stand-in for the compat gate."""

    job_id = "job:dsflash"
    run_id = "attempt:dsflash"
    worker_id = ""


def test_dsh_acp_lane_is_binding_required():
    assert DSH_ACP_RUNTIME.binding_required is True
    # A placement child on this lane never starts without the broker-issued
    # ExecutionBinding.v1 (typed refusal, WO-16 discipline).
    with pytest.raises(ExecutionBindingCompatError) as excinfo:
        binding_for_launch_spec(_Spec(), None, required=True)
    assert excinfo.value.code == BINDING_REQUIRED


# --- Executive tools bridge ---------------------------------------------------

def test_executive_tools_bridge_uses_the_qualified_native_seam():
    bridge = DSH_ACP_RUNTIME.executive_tools_bridge
    assert isinstance(bridge, DshExecutiveToolsBridge)
    assert "dsh-mcp-client" in bridge.seam
    assert "cordis.patch.yml" in bridge.seam
    # T3 does NOT forward arbitrary agent MCP configuration — the WHY must
    # say so (pinned-source evidence mcpOverAcpBridge.ts).
    assert "does not forward" in bridge.why
    fragment = bridge.patch_layer_fragment()
    assert "subagent-fabric" in fragment
    # The fragment is loopback/pinned-stdio only; no credentials.
    for forbidden in ("apiKey", "API_KEY", "token", "password"):
        assert forbidden not in fragment
    assert "127.0.0.1" in fragment


def test_descriptor_serializes_with_policy_and_provenance():
    payload = DSH_ACP_RUNTIME.to_dict()
    assert payload["runtime_id"] == DSH_ACP_RUNTIME_ID
    assert payload["runtime_kind"] == "dsh"
    assert payload["descendant_policy"]["policy"] == BOUNDED_NATIVE_FANOUT
    assert payload["descendant_policy"]["envelope"]["max_active_subagents"] == 8
    assert payload["provider_config"]["argument_rows"] == ["--profile", "mmx-acp"]
    assert DSH_ACP_RUNTIME.provenance
    # Stable digest over the canonical serialization.
    assert DSH_ACP_RUNTIME.digest() == hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
