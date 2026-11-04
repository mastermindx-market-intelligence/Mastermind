"""Private direct-native composition for the existing Runtime and Service owners.

These values are data, not caller admission. Only the fixed authenticated App
peer and the normal host's current guard issue a DirectNativeAccess capability.
No service, queue, schema migration or provider transport is defined here.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
import re
from typing import Any, Callable, Mapping

PROFILE = "native_research_only"
POLICY = "mastermind.direct_native_readonly/v1"
POLICY_KEY = "direct_native_policy"
INTENT_SCHEMA = "mastermind.ceo_direct_native_intent.v1"
RECEIPT_SCHEMA = "mastermind.ceo_direct_native_receipt.v1"
PROVENANCE_SCHEMA = "mastermind.authenticated_direct_native.v1"
SUBMIT_SCHEMA = "mastermind.ceo_ingress.direct_native_submit.v1"
RESULT_SCHEMA = "mastermind.ceo_ingress.direct_native.v1"
TERMINAL_SCHEMA = "mastermind.direct_native_terminal/v1"
BINDING_SCHEMA = "mastermind.direct_native_binding/v1"
_ACCESS = object()
_ADMISSION = object()
_DISPATCH = object()
_HEX = re.compile(r"[0-9a-f]{64}")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require_digest(value: Any) -> str:
    if type(value) is not str or _HEX.fullmatch(value) is None:
        raise ValueError("direct native digest is invalid")
    return value


def public_payload(output: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("summary", "current_state", "completed_steps", "next_actions")
    value = {key: copy.deepcopy(output.get(key)) for key in keys}
    if (any(type(value[key]) is not str for key in ("summary", "current_state"))
            or any(type(value[key]) is not list or any(type(item) is not str for item in value[key])
                   for key in ("completed_steps", "next_actions"))):
        raise ValueError("direct native output has no closed public payload")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class DirectNativeAccess:
    principal_scope: str
    work_ref: str
    authority_generation_digest: str
    _guard: Callable[[], str] = dataclasses.field(repr=False, compare=False)
    _capability: object = dataclasses.field(repr=False, compare=False)

    def check(self) -> None:
        if self._capability is not _ACCESS:
            raise ValueError("direct native access is not host-issued")
        require_digest(self.principal_scope)
        require_digest(self.authority_generation_digest)
        if (not callable(self._guard) or inspect.iscoroutinefunction(self._guard)
                or inspect.iscoroutinefunction(getattr(self._guard, "__call__", None))):
            raise ValueError("direct native current access guard is absent")
        observed = self._guard()
        if inspect.isawaitable(observed):
            if inspect.iscoroutine(observed):
                observed.close()
            raise ValueError("direct native access guard must be synchronous")
        if observed != self.authority_generation_digest:
            raise ValueError("direct native authority generation changed")


def _issue_access(principal_scope: str, work_ref: str, generation: str,
                  guard: Callable[[], str]) -> DirectNativeAccess:
    access = DirectNativeAccess(principal_scope, work_ref, generation, guard, _ACCESS)
    access.check()
    return access


def receiver_binding(principal_scope: str, source: Mapping[str, Any]) -> str:
    require_digest(principal_scope)
    return digest({"principal_scope": principal_scope, "work_ref": source["work_ref"],
                   "commission_ref": source["commission_ref"]})

_BINDING_KEYS = frozenset({'worker_id','base_sha','eligible_quota_classes','provider','model','effort','cost_class',
    'routing_policy_version','execution_profile_id','execution_profile_digest',
    'capability_policy_version','capability_policy_digest'})


def normalize_binding(value):
    if type(value) is not dict or set(value) != _BINDING_KEYS:
        raise ValueError('direct native host binding is not closed')
    if (type(value['worker_id']) is not str or re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}',value['worker_id']) is None
            or type(value['base_sha']) is not str or re.fullmatch('[0-9a-f]{40}',value['base_sha']) is None
            or value['provider'] != 'codex' or type(value['eligible_quota_classes']) is not list
            or not value['eligible_quota_classes'] or len(value['eligible_quota_classes']) > 2
            or len(set(value['eligible_quota_classes'])) != len(value['eligible_quota_classes'])):
        raise ValueError('direct native host binding is invalid')
    for key in _BINDING_KEYS - {'eligible_quota_classes'}:
        if type(value[key]) is not str or not value[key] or len(value[key]) > 160:
            raise ValueError('direct native host binding field is invalid')
    require_digest(value['execution_profile_digest']);require_digest(value['capability_policy_digest'])
    return copy.deepcopy(value)


@dataclasses.dataclass(frozen=True, slots=True)
class DirectNativeAdmission:
    access: DirectNativeAccess
    source: dict
    binding: dict
    _capability: object = dataclasses.field(repr=False, compare=False)
    _material_digest: str = dataclasses.field(repr=False)
    _execution_access: DirectNativeExecutionAccess | None = dataclasses.field(default=None,repr=False,compare=False)

    def check(self):
        from control_plane.executive_runtime import normalize_executive_dialogue_source
        if self._capability is not _ADMISSION or type(self.access) is not DirectNativeAccess:
            raise ValueError('direct native admission is not host-issued')
        self.access.check()
        if digest(dict(source=self.source,binding=self.binding)) != self._material_digest:
            raise ValueError('issued direct admission material changed')
        if self._execution_access is not None:
            if type(self._execution_access) is not DirectNativeExecutionAccess or self._execution_access.access is not self.access:
                raise ValueError('direct admission execution binding changed')
            self._execution_access.check()
        normalize_binding(self.binding)
        source = normalize_executive_dialogue_source(self.source, work_ref=self.access.work_ref).to_dict()
        if source != self.source:
            raise ValueError('direct native source is not canonical')


def _issue_admission(access, source, binding, *, execution_access=None):
    source=copy.deepcopy(source);binding=normalize_binding(binding)
    value = DirectNativeAdmission(access, source, binding, _ADMISSION,
        digest(dict(source=source,binding=binding)),execution_access)
    value.check()
    return value


def job_is_direct(job):
    # A hint for Supervisor branching only. Runtime always rejoins JOB_CREATED
    # and the complete provenance before any claim, terminal write or read.
    return job.constraints.get(POLICY_KEY) == POLICY


def admission_material(admission):
    admission.check()
    return dict(schema_version=PROVENANCE_SCHEMA, principal_scope=admission.access.principal_scope,
        receiver_binding_digest=receiver_binding(admission.access.principal_scope,admission.source),
        authority_generation_digest=admission.access.authority_generation_digest,
        source=copy.deepcopy(admission.source),source_digest=digest(admission.source),
        binding=normalize_binding(admission.binding))

_EXECUTION = object()


@dataclasses.dataclass(frozen=True, slots=True)
class DirectNativeExecutionAccess:
    """Separate current execution grant; queued admission/read grants none."""
    access: DirectNativeAccess
    _execution_guard: Callable[[], None] = dataclasses.field(repr=False, compare=False)
    _capability: object = dataclasses.field(repr=False, compare=False)

    @property
    def principal_scope(self): return self.access.principal_scope
    @property
    def work_ref(self): return self.access.work_ref
    @property
    def authority_generation_digest(self): return self.access.authority_generation_digest

    def check(self):
        if self._capability is not _EXECUTION or type(self.access) is not DirectNativeAccess:
            raise ValueError('native execution grant is not host-issued')
        self.access.check()
        if (not callable(self._execution_guard) or inspect.iscoroutinefunction(self._execution_guard)
                or inspect.iscoroutinefunction(getattr(self._execution_guard,'__call__',None))):
            raise ValueError('native execution owner guard is unavailable')
        result=self._execution_guard()
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result): result.close()
            raise ValueError('native execution guard must be synchronous')
        if result is not None: raise ValueError('native execution guard refused')
        self.access.check()


def _issue_execution_access(access, guard):
    value=DirectNativeExecutionAccess(access,guard,_EXECUTION)
    value.check()
    return value
