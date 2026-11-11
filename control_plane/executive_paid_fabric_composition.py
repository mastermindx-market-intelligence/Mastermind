"""Root-installed paid source and ordinary placement composition.

Data consistency is not Capacity/realm admission. Empty disabled definitions
select nothing. Real claim/Runtime pin/paid lease and actual owned remote image
remain mandatory at the existing private broker consume boundary.
"""
from __future__ import annotations
import dataclasses
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType

from control_plane.executive_fabric_composition import (
    _read_pinned,_document,_absolute_path,FabricCompositionError,
)
from control_plane.executive_fabric_bridge_broker import BridgeConfig,_TRUSTED_CONFIG
from control_plane.paid_model_execution_contract import ADAPTER_ID,PROFILE_ID,canonical,digest

PAID_CONFIG_SCHEMA='mastermind.executive_paid_fabric_bridge_config/v1'
PAID_BINDINGS_SCHEMA='mastermind.executive_paid_fabric_bindings/v1'
_SOURCE_READ=object()
_ROUTE_FIELDS=frozenset('schema model_alias provider_alias adapter_id model effort cost_class routing_policy_version execution_profile_id execution_profile_digest capability_policy_version capability_policy_digest'.split())


@dataclasses.dataclass(frozen=True)
class PaidBridgeConfig(BridgeConfig):
    @classmethod
    def from_document(cls,value):
        from ops.executive_os.canonical_paid_definition import _validate_paid_bridge_document
        _validate_paid_bridge_document(value)
        fields={f.name for f in dataclasses.fields(BridgeConfig)}-{'source_sha256','_trust'}
        if set(value)!=fields:raise FabricCompositionError('Paid config fields changed')
        result=dict(value)
        for key in ('socket_path','workspace_root','run_root'):result[key]=_absolute_path(value[key])
        if result['workspace_root']==result['run_root']:
            raise FabricCompositionError('Paid Control roots must remain distinct')
        result['validation_commands']=()
        return cls(**result)


def load_paid_config(path):
    from control_plane.paid_fabric_backend import _root_source
    path=_absolute_path(str(path))
    raw=_root_source(path)
    config=PaidBridgeConfig.from_document(_document(raw))
    return dataclasses.replace(config,source_sha256=hashlib.sha256(raw).hexdigest(),_trust=_TRUSTED_CONFIG)


def verify_installed_source(config,directory,release_root):
    from control_plane.paid_fabric_backend import _root_source
    from ops.executive_os import canonical_paid_definition as definition
    directory=Path(directory)
    files={name:_root_source(directory/name) for name in definition.FILES}
    profile=_document(files['profile.json'])
    if profile.get('schema_version')=='mastermind.executive_paid_fabric_profile/v2':
        from ops.executive_os.canonical_paid_qualification import verify_qualified_artifacts
        verified=verify_qualified_artifacts(files)
        hashes=verified['hashes']
        rows=verified['bindings']
    else:
        hashes=definition.verify_candidate(files)
        rows=[]
    if hashlib.sha256(files['bridge.json']).hexdigest()!=config.source_sha256:
        raise FabricCompositionError('Paid installed config moved')
    profile=_document(files['profile.json'])
    manifest_raw=_root_source(Path(release_root)/'.executive-release-manifest.json')
    if (profile['release_commit']!=Path(release_root).name
            or profile['release_manifest_sha256']!=hashlib.sha256(manifest_raw).hexdigest()):
        raise FabricCompositionError('Paid source is not the selected installed release')
    # This disabled source check does not create or select a worker binding.
    return dict(profile=profile,hashes=hashes,bindings=rows)


@dataclasses.dataclass(frozen=True)
class PaidBindingSource:
    path:Path
    expected_sha256:str
    bindings:tuple
    _identity:tuple
    _sources:object
    _quota_classes:object
    _origin:object=dataclasses.field(default=None,repr=False,compare=False)

    @classmethod
    def from_path(cls,path,expected_sha256):
        raw,identity=_read_pinned(_absolute_path(str(path)),expected_sha256)
        document=_document(raw)
        if (type(document) is not dict or set(document)!={'schema_version','bindings'}
                or document['schema_version']!=PAID_BINDINGS_SCHEMA
                or type(document['bindings']) is not list or not 1<=len(document['bindings'])<=3):
            raise FabricCompositionError('Actual paid qualification is not installed')
        from control_plane.executive_paid_fabric_adapter import PaidFabricHostBinding
        from control_plane.paid_fabric_wire import require_paid_physical
        rows=[];sources={};quotas={};instances=set()
        for row in document['bindings']:
            if type(row) is not dict or set(row)!={'physical_binding','source_config','quota_class'}:
                raise FabricCompositionError('Paid source binding fields changed')
            physical=PaidFabricHostBinding(**row['physical_binding'])
            source=row['source_config']
            # Pure source consistency is not a synthetic Job/claim or admission.
            from control_plane.paid_fabric_wire import require_paid_source
            require_paid_source(row['physical_binding'],source)
            # Different reference labels do not create another physical host
            # allowance. Same qualified boot instance cannot be duplicated in
            # this bounded installed owner, even through another registry alias.
            instance=source['qualification']['boot_id']
            if instance in instances:
                raise FabricCompositionError('Paid physical instance duplicated')
            instances.add(instance)
            key=(physical.host_ref,physical.worker_id)
            if key in sources or type(row['quota_class']) is not str or not row['quota_class']:
                raise FabricCompositionError('Paid source duplicate or quota invalid')
            rows.append(physical);sources[key]=source;quotas[key]=row['quota_class']
        return cls(Path(path),expected_sha256,tuple(rows),identity,
                   MappingProxyType(sources),MappingProxyType(quotas),_SOURCE_READ)

    def _current(self):
        if self._origin is not _SOURCE_READ:raise FabricCompositionError('Paid root source was not acquired')
        raw,identity=_read_pinned(self.path,self.expected_sha256)
        if identity!=self._identity:raise FabricCompositionError('Paid installed source changed')
        # Frozen containers do not freeze nested DATA. Rejoin every cached row
        # to the same root-read document before selection; a detached or mutated
        # binary/source dictionary never becomes installed qualification.
        expected={'schema_version':PAID_BINDINGS_SCHEMA,'bindings':[]}
        for physical in self.bindings:
            key=(physical.host_ref,physical.worker_id)
            expected['bindings'].append(dict(physical_binding=dataclasses.asdict(physical),
                source_config=self._sources[key],quota_class=self._quota_classes[key]))
        if canonical(_document(raw))!=canonical(expected):
            raise FabricCompositionError('Paid installed source projection changed')

    def __call__(self,host_ref,worker_id):
        self._current()
        matches=[p for p in self.bindings if (p.host_ref,p.worker_id)==(host_ref,worker_id)]
        if len(matches)!=1:raise FabricCompositionError('Exact paid source binding unavailable')
        return matches[0]

    def source_for(self,physical):
        if self(physical.host_ref,physical.worker_id)!=physical:
            raise FabricCompositionError('Paid source route changed')
        return json.loads(canonical(self._sources[(physical.host_ref,physical.worker_id)]))

    def quota_for(self,physical):
        self.source_for(physical)
        return self._quota_classes[(physical.host_ref,physical.worker_id)]

    def client_for(self,physical,payload):
        self.source_for(physical)
        from control_plane.executive_fabric_adapter import _fixed_client
        return _fixed_client(physical)


@dataclasses.dataclass(frozen=True)
class PaidWorkPlacement:
    model_alias:str
    quota_class:str


def normalize_paid_execution_route(value):
    if type(value) is not dict or set(value)!=_ROUTE_FIELDS:
        raise ValueError('Paid route fields invalid')
    if (value['schema']!='mastermind.canonical_paid_work_route/v1'
            or value['provider_alias']!='glm' or value['adapter_id']!=ADAPTER_ID
            or value['execution_profile_id']!=PROFILE_ID
            or value['model_alias']!='glm.paid.sealed-input'
            or value['model']!='glm-5.3-flash'):
        raise ValueError('Paid route is outside source profile')
    import re
    for key,item in value.items():
        if type(item) is not str or not item or len(item)>128 or any(ord(c)<32 for c in item):
            raise ValueError('Paid route scalar invalid')
        if key.endswith('_digest') and re.fullmatch(r'[0-9a-f]{64}',item) is None:
            raise ValueError('Paid route digest invalid')
    return dict(value)


def placement_member(router,placement):
    if type(placement) is not PaidWorkPlacement:raise ValueError('Paid placement requires typed source')
    alias=router.resolve_model_alias(placement.model_alias)
    if (not alias.worker_eligible or alias.adapter_id!=ADAPTER_ID
            or alias.execution_profile_id!=PROFILE_ID):
        raise ValueError('Paid source alias unavailable')
    route={k:getattr(alias,k) for k in _ROUTE_FIELDS-{'schema','routing_policy_version'}}
    route.update(schema='mastermind.canonical_paid_work_route/v1',routing_policy_version=router.policy_version)
    return dict(provider_realm='glm',quota_class=placement.quota_class,
                paid_execution_route=normalize_paid_execution_route(route))


PAID_INSTALLED_BINDINGS=Path('/Library/Application Support/MastermindExecutive/config/fabric-glm-paid-01/bindings.json')


def installed_paid_source(raw,*,installed_control):
    """Resolve only the fixed root publication from the installed constructor.

    The stanza is an identity reference, not readiness or an execution arm.
    Runtime claim, current Capacity and existing R1/autonomy remain separate.
    """
    if 'canonical_paid_fabric' not in raw:return None
    value=raw['canonical_paid_fabric']
    if (installed_control is not True or type(value) is not dict
            or set(value)!={'bindings_path','bindings_sha256'}
            or value['bindings_path']!=str(PAID_INSTALLED_BINDINGS)):
        raise FabricCompositionError('paid source requires the fixed installed Control composition')
    return PaidBindingSource.from_path(PAID_INSTALLED_BINDINGS,value['bindings_sha256'])
