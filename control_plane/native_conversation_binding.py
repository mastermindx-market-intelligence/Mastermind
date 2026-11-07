"""Installed native operator selection over existing routing and Worker owners.

This source reads one configured registration. It registers nothing, owns no
credentials, selects no provider fallback and cannot enable a disabled profile.
Actual process/account/tool/confinement attestation remains the original OHF
launch owner; preview only claims a current registered worker.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from common.fresh_conversation_contract import canonical_digest
from control_plane.executive_agent_capabilities import DSH_NATIVE_CONVERSATION_PROFILE_ID
from control_plane.executive_capacity_join import read_remote_capacity_joins
from control_plane.model_router import ModelRouter

_SEAL = object()


@dataclass(frozen=True, slots=True)
class NativeConversationRegistration:
    worker_id: str
    quota_class: str
    model_alias: str
    host_ref: str
    worker_source_config_digest: str

    def __post_init__(self):
        from control_plane.remote_worker_transport import validate_host_ref
        for value in (self.worker_id, self.quota_class, self.model_alias):
            if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
                raise ValueError("native registration identity is malformed")
        validate_host_ref(self.host_ref)
        if not re.fullmatch(r"[0-9a-f]{64}", self.worker_source_config_digest):
            raise ValueError("native registration source digest is malformed")


@dataclass(frozen=True, slots=True)
class NativeConversationBindingSource:
    _seal: object
    _service: object
    _runtime: object
    _registration: NativeConversationRegistration
    _guard: object
    _snapshot_digest: str

    def _read(self):
        from control_plane.executive_service import ExecutiveControlService
        if (self._seal is not _SEAL or type(self._service) is not ExecutiveControlService
                or self._service._require_runtime() is not self._runtime
                or type(self._registration) is not NativeConversationRegistration
                or not callable(self._guard) or self._guard() is not None):
            raise ValueError("native installed registration source is unavailable")
        selection = self._registration
        router = ModelRouter.load()
        alias = router.model_aliases[selection.model_alias]
        # resolve(), never profiles[]: disabled declarations cannot authorize execution.
        profile = router.capability_registry.resolve(alias.execution_profile_id)
        if (not alias.worker_eligible or alias.adapter_id != "acp" or alias.provider_alias != "acp"
                or profile.profile_id != DSH_NATIVE_CONVERSATION_PROFILE_ID
                or profile.execution_surface != "dsh-native-web-acp" or profile.write_capable
                or profile.auth_realm != "dedicated-worker-account" or profile.sandbox_policy != "read-only"
                or profile.approval_policy != "never" or profile.network_policy != "disabled"
                or profile.native_helper_policy.value != "DISABLED"):
            raise ValueError("native installed capability is unavailable")
        registry = self._runtime.workers
        worker = registry.get_worker(selection.worker_id)
        quota = registry.get_quota_class(selection.worker_id, selection.quota_class)
        joined = read_remote_capacity_joins(registry, [(selection.worker_id, selection.quota_class)])
        if (worker is None or worker.provider != "acp" or not worker.account_label or not worker.worker_type
                or quota is None or quota.provider != "acp" or len(joined) != 1
                or joined[0].provider != "acp" or joined[0].capacity_join.host_ref != selection.host_ref
                or joined[0].capacity_join.worker_source_config_digest != selection.worker_source_config_digest
                or (quota.model, quota.effort, quota.cost_class) != (alias.model, alias.effort, alias.cost_class)
                or not set(alias.capabilities).issubset(quota.capabilities)):
            raise ValueError("native original Worker/quota registration differs")
        fields = dict(routing_policy_version=router.policy_version,
            execution_profile_id=alias.execution_profile_id, execution_profile_digest=alias.execution_profile_digest,
            capability_policy_version=alias.capability_policy_version, capability_policy_digest=alias.capability_policy_digest)
        if any(quota.metadata.get(key) != value for key, value in fields.items()):
            raise ValueError("native original quota capability identity differs")
        binary, version = quota.metadata.get("harness_binary_digest"), quota.metadata.get("harness_version")
        if (type(binary) is not str or not re.fullmatch(r"[0-9a-f]{64}", binary)
                or type(version) is not str or not 1 <= len(version) <= 128):
            raise ValueError("native original binary identity is unavailable")
        base = self._service._require_current_coo_binding()
        binding = {**base, **{"operator_" + key: value for key, value in fields.items()},
            "operator_eligible_quota_classes": [selection.quota_class], "operator_provider": "acp",
            "operator_model": alias.model, "operator_effort": alias.effort, "operator_cost_class": alias.cost_class,
            "operator_harness_binary_digest": binary, "operator_harness_version": version,
            "operator_harness_armed": True}
        snapshot = dict(binding=binding, capacity=joined[0].to_dict(),
            worker=dict(worker_id=worker.worker_id, provider=worker.provider,
                account_label=worker.account_label, worker_type=worker.worker_type))
        if self._guard() is not None:
            raise ValueError("native installed registration changed during observation")
        return binding, canonical_digest(snapshot)

    def current_binding(self):
        if getattr(self._service, "_native_conversation_binding_source", None) is not self:
            raise ValueError("native installed source was replaced")
        binding, digest = self._read()
        if digest != self._snapshot_digest:
            raise ValueError("native installed registration changed")
        return binding


def bind_installed_native_conversation(service, *, registration, current):
    """Called by trusted installed composition after the existing registration.

    The current callback is the original installed-source lifetime predicate.
    Serialized config, a browser principal or a policy candidate cannot mint it.
    """
    if (type(registration) is not NativeConversationRegistration or not callable(current)
            or getattr(service, "_native_conversation_binding_source", None) is not None):
        raise ValueError("native installed source is absent or already bound")
    source = NativeConversationBindingSource(_SEAL, service, service._require_runtime(), registration, current, "")
    _binding, digest = source._read()
    source = NativeConversationBindingSource(_SEAL, service, source._runtime, registration, current, digest)
    service._native_conversation_binding_source = source
    try:
        source.current_binding()
    except Exception:
        if service._native_conversation_binding_source is source:
            service._native_conversation_binding_source = None
        raise
    return source
