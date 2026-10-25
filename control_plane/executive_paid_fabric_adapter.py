"""Control-side canonical paid sealed-input adapter.

Uses the existing Runtime claim/pin/lease and authenticated Fabric Unix client.
It never invokes the manual dynamic router, creates an admission token or
restarts an uncertain Attempt. Legacy attended adapter remains separate.
"""
from __future__ import annotations
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter, _fixed_client
from control_plane.executive_runtime import Runtime,AttemptLease,AttemptStatus,REMOTE_LAUNCH_IDENTITY_KEY
from control_plane.executive_worker_broker import BrokerStateError,BrokerProtocolError
from control_plane.remote_attempt_transport import _read_claim,RemoteTransportPurpose
from control_plane.paid_model_execution_contract import ADAPTER_ID,PROFILE_ID,canonical,digest,compile_request
from control_plane.paid_fabric_wire import require_paid_physical,validate_paid_start_wire
from control_plane.worker_execution_contract import BinaryAttestation,WorkerRunStatus,WorkerResult,CollectionReceipt


@dataclasses.dataclass(frozen=True)
class PaidFabricHostBinding:
    socket_path:str
    host_ref:str
    worker_id:str
    worker_uid:int
    worker_gid:int
    worker_user:str
    provider:str
    model:str
    worker_source_config_digest:str
    execution_profile_digest:str
    service_source_sha256:str
    binary:dict
    permission_profile_sha256:str
    bridge_uid:int
    capture_root:str
    qualification:dict
    schema_version:str='mastermind.paid_fabric_host_binding/v1'

    @property
    def digest(self):return digest(dataclasses.asdict(self))


def _schema_input(spec):
    """Read only the actual Control-created sealed result schema, no fetch."""
    path=Path(spec.result_schema_path)
    root=Path(spec.run_dir)
    if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root):
        raise BrokerStateError('Paid schema is outside original Control input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid()
                or before.st_mode&0o022 or before.st_nlink!=1 or not 0<before.st_size<=256*1024):
            raise BrokerStateError('Paid schema input is not sealed Control data')
        raw=os.read(fd,256*1024+1)
        after=os.fstat(fd)
        identity=lambda i:(i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,i.st_nlink,
            i.st_size,i.st_mtime_ns,i.st_ctime_ns)
        if (identity(before)!=identity(after) or len(raw)!=before.st_size
                or (before.st_dev,before.st_ino)!=(path.lstat().st_dev,path.lstat().st_ino)):
            raise BrokerStateError('Paid schema input changed')
        from control_plane.executive_fabric_composition import _document
        value=_document(raw)
        if type(value) is not dict or not value:raise BrokerStateError('Paid schema input invalid')
        return value
    finally:os.close(fd)


class CanonicalPaidFabricWorkerAdapter(AttendedFabricWorkerAdapter):
    adapter_id=ADAPTER_ID
    requires_attempt_lease=True
    requires_recovery_lease=True

    def __init__(self,runtime,binding_source,*,heartbeat_interval_seconds=5.0):
        from control_plane.executive_paid_fabric_composition import PaidBindingSource
        if type(binding_source) is not PaidBindingSource:
            raise BrokerStateError('Paid adapter requires exact root-installed source')
        super().__init__(runtime,binding_source,request_client_factory=binding_source.client_for,
                         heartbeat_interval_seconds=heartbeat_interval_seconds)
        self._paid_observations={}

    async def prepare_paid_launch_spec(self,spec,*,lease):
        if not isinstance(lease,AttemptLease):raise BrokerStateError('Paid lease unavailable')
        current,_,payload=self._resolve(spec,launch=True)
        if current!=lease.attempt:raise BrokerStateError('Paid original claim changed')
        compile_request(payload)
        return spec  # Actual Control paths remain unchanged; no remote worktree.

    def _resolve(self,spec,*,launch,control_recovery=None):
        job,attempt,quota,join=_read_claim(self.runtime,job_id=spec.job_id,
            attempt_id=spec.run_id,purpose=RemoteTransportPurpose.LAUNCH if launch else RemoteTransportPurpose.RECOVERY)
        if (spec.worker_id!=attempt.worker_id or job.constraints.get('execution_profile_id')!=PROFILE_ID
                or job.orchestration_role not in {'work','repair'}
                or job.allowed_write_paths or job.validation_commands
                or set(job.requested_authorities) not in ({'READ'},{'READ','RESEARCH'})):
            raise BrokerStateError('Paid job/grant/profile is outside sealed analysis')
        physical=self.binding_source(join.capacity_join.host_ref,attempt.worker_id)
        if (type(physical) is not PaidFabricHostBinding or physical.provider!=quota.provider
                or physical.provider!='glm' or physical.model!=spec.model
                or physical.execution_profile_digest!=job.constraints.get('execution_profile_digest')
                or physical.worker_source_config_digest!=join.capacity_join.worker_source_config_digest
                or physical.worker_uid!=spec.expected_worker_uid or physical.worker_gid!=spec.expected_worker_gid):
            raise BrokerStateError('Paid physical route differs from current canonical claim')
        worker=self.runtime.workers.get_worker(attempt.worker_id)
        if worker is None or worker.provider!='glm' or worker.worker_type!='canonical-paid-fabric':
            raise BrokerStateError('Paid Worker provenance unavailable')
        from control_plane.executive_runtime import _dialogue_source_from_root_creation
        with self.runtime.store.read() as connection:
            source=_dialogue_source_from_root_creation(connection,root_job_id=job.root_job_id)
        if source is None or spec.effective_grant_digest!=attempt.effective_grant_digest:
            raise BrokerStateError('Paid commission/grant provenance unavailable')
        from control_plane.executive_worker_broker import _launch_spec_to_json
        payload=dict(binding=dict(root_id=job.root_job_id,job_id=job.job_id,attempt_id=attempt.attempt_id,
                effective_grant_digest=attempt.effective_grant_digest,
                commission_sha256=source.commission_ref.content_sha256),
            physical_binding_sha256=physical.digest,launch_spec=_launch_spec_to_json(spec),validation_commands=[],
            paid_route=dict(provider='glm',host_ref=physical.host_ref,model=physical.model,
                            parent_job_id=job.parent_job_id),
            paid_input=dict(prompt=spec.prompt,result_schema=_schema_input(spec)),
            paid_physical_binding=dataclasses.asdict(physical),
            paid_source_config=self.binding_source.source_for(physical),
            paid_account=worker.account_label,paid_quota_class=quota.quota_class)
        context=control_recovery if control_recovery is not None else self._control_recovery.get(spec.run_id)
        if context is not None:
            from control_plane.worker_execution_contract import _validate_control_recovery_context
            _validate_control_recovery_context(context)
            if Path(context['source_workspace'])!=Path(str(job.worktree)).resolve(strict=False):
                raise BrokerStateError('Paid Control recovery source changed')
            payload['control_recovery']=dict(context)
        require_paid_physical(payload)
        compile_request(payload)
        check=self.runtime.workers.get_worker(attempt.worker_id)
        current=_read_claim(self.runtime,job_id=spec.job_id,attempt_id=spec.run_id,
            purpose=RemoteTransportPurpose.LAUNCH if launch else RemoteTransportPurpose.RECOVERY)
        if check!=worker or current!=(job,attempt,quota,join):
            raise BrokerStateError('Paid source/claim changed during join')
        return attempt,physical,payload

    async def start(self,spec,*,lease=None,control_recovery=None):
        if not isinstance(lease,AttemptLease):raise BrokerStateError('Paid original lease required')
        if control_recovery is not None:
            if spec.run_id in self._control_recovery:raise BrokerStateError('Paid recovery already bound')
            self._control_recovery[spec.run_id]=dict(control_recovery)
        attempt,physical,payload=self._resolve(spec,launch=True)
        if attempt!=lease.attempt or spec.run_id in self._bound:
            raise BrokerStateError('Paid original START already attempted or claim changed')
        client=self.binding_source.client_for(physical,payload)
        pinned=self.runtime.attempts.pin_remote_launch_identity(spec.run_id,
            fence_generation=attempt.fence_generation,lease_token=lease.lease_token,
            expected_version=attempt.version,identity_digest=self._identity(physical,payload))
        current,check,check_payload=self._resolve(spec,launch=False)
        self._pin_matches(current,check,check_payload)
        validated=self.runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=lease.lease_token)
        from control_plane.fabric_control_start import command_from_validated_pin
        command=command_from_validated_pin(validated,payload)
        self._bound[spec.run_id]=(client,payload,physical,spec)
        self._leases[spec.run_id]=lease
        task=asyncio.create_task(client.request('start',{**payload,'control_start':command},
                                               timeout_seconds=float(spec.timeout_seconds)+60))
        try:
            while not task.done():
                done,_=await asyncio.wait({task},timeout=self._heartbeat_interval)
                if done:break
                self.runtime.attempts.heartbeat_attempt(spec.run_id,
                    fence_generation=attempt.fence_generation,lease_token=lease.lease_token)
            result=await task
            self.runtime.attempts.validate_pinned_remote_launch(pinned,lease_token=lease.lease_token)
            ref,att=validate_paid_start_wire(result,{**payload,'control_start':command})
            self._refs[spec.run_id],self._attestations[spec.run_id]=ref,att
            return ref
        finally:
            if not task.done():
                task.cancel()  # Local await only; never cancels original owner.
                await asyncio.gather(task,return_exceptions=True)

    def _subject_ref(self,subject):
        from control_plane.worker_execution_contract import PaidModelProcessRef
        run=subject.run_id if type(subject) is PaidModelProcessRef else getattr(subject,'attempt_id',None)
        ref=self._refs.get(run)
        if ref is None or (type(subject) is PaidModelProcessRef and subject!=ref):
            raise BrokerStateError('Paid original process unavailable')
        self._known(ref)
        self._validate_lease(run)
        return ref

    def expected_worker_uid(self,attempt):return self._subject_ref(attempt).effective_uid

    def presence(self,attempt):
        from control_plane.executive_supervisor import ProcessPresence
        # Synchronous callers may use only already-authenticated paid evidence.
        # They never inspect a remote PID through the Control kernel.
        try:
            ref=self._subject_ref(attempt)
            if ref.run_id in self._paid_observations:return ProcessPresence.ABSENT
        except Exception:pass
        return ProcessPresence.UNKNOWN

    def run_is_proven_terminal(self,attempt):
        try:return self._subject_ref(attempt).run_id in self._paid_observations
        except Exception:return False

    def control_recovery_context(self,spec):
        context=self._control_recovery.get(spec.run_id)
        if context is None:return None
        attempt,physical,payload=self._resolve(spec,launch=False)
        self._pin_matches(attempt,physical,payload)
        return dict(context)

    def paid_launch_identity(self,ref):
        _,payload,physical,spec=self._known(ref)
        self._validate_lease(ref.run_id)
        attempt,current,current_payload=self._resolve(spec,launch=False)
        self._pin_matches(attempt,current,current_payload)
        return json.loads(canonical(dict(physical_binding_sha256=physical.digest,request=payload)))

    def launch_attestation(self,ref):
        self._known(ref)
        self._validate_lease(ref.run_id)
        return json.loads(canonical(self._attestations[ref.run_id]))

    def assignment_launch_identity(self,ref):return self.paid_launch_identity(ref)
    def assignment_physical_binding(self,ref):
        return json.loads(canonical(dataclasses.asdict(self._known(ref)[2])))

    def validate_remote_recovery_coordinates(self,spec,binding):
        from control_plane.paid_model_recovery import PaidModelRecoveryBinding
        if type(binding) is not PaidModelRecoveryBinding:
            raise BrokerStateError('Paid recovery requires its exact contract')
        binding.validate_wire()
        if binding.adapter_id!=ADAPTER_ID or binding.control_recovery is None:
            raise BrokerStateError('Paid original recovery coordinates unavailable')
        attempt,physical,payload=self._resolve(spec,launch=False,control_recovery=binding.control_recovery)
        self._pin_matches(attempt,physical,payload)
        if (binding.capture_root!=physical.capture_root
                or binding.launch_identity_sha256!=self._identity(physical,payload)
                or binding.recover_launch_spec(type(spec))!=spec):
            raise BrokerStateError('Paid original recovery source differs')

    async def _paid_request(self,ref,operation,**extra):
        client,payload,physical,spec=self._known(ref)
        self._validate_lease(ref.run_id)
        current,check,check_payload=self._resolve(spec,launch=False)
        self._pin_matches(current,check,check_payload)
        result=await client.request(operation,dict(binding=payload['binding'],run_id=ref.run_id,
            physical_binding_sha256=physical.digest,**extra),timeout_seconds=60)
        self._validate_lease(ref.run_id)
        if (result.get('adapter_id')!=ADAPTER_ID or result.get('binding')!=payload['binding']
                or result.get('physical_binding_sha256')!=physical.digest):
            raise BrokerProtocolError('Paid result original attribution changed')
        return result

    async def status(self,ref):
        result=await self._paid_request(ref,'status')
        if result['run']['process_ref']!=ref.to_dict():raise BrokerProtocolError('Paid process changed')
        return WorkerRunStatus(result['run']['status'])

    async def collect_result(self,ref):
        response=await self._paid_request(ref,'collect')
        value=response['collection']
        if value['process_ref']!=ref.to_dict():raise BrokerProtocolError('Paid collection process changed')
        output=dict(value['result']);output['status']=WorkerRunStatus(output['status'])
        if output['artifact_manifest'] or output['git_manifest'] or output['provider_session_id'] is not None:
            raise BrokerProtocolError('Paid collection claimed unsupported artifacts/Git/session')
        result=WorkerResult(**output)
        observation=response['paid_observation']
        from control_plane.paid_fabric_wire import validate_owned_terminal,paid_collection_from_owned_terminal
        validate_owned_terminal(observation['owned_terminal'],observation['owned_launch'])
        raw=observation['capture']['stdout_utf8'].encode('utf-8')
        original=self._known(ref)[1]
        start=dict(adapter_id=ADAPTER_ID,binding=original['binding'],request_sha256='',
            physical_binding_sha256=original['physical_binding_sha256'],process_ref=ref.to_dict(),
            launch_attestation=self.launch_attestation(ref))
        expected=paid_collection_from_owned_terminal(original,start,observation['owned_terminal'],raw)
        if expected!=value:raise BrokerProtocolError('Paid retained exact bytes differ from collection')
        self._paid_observations[ref.run_id]=dict(launch_identity=self.paid_launch_identity(ref),**observation)
        return CollectionReceipt(ref,result,value['stdout_sha256'],value['stderr_sha256'],value['result_sha256'])

    def paid_terminal_observation(self,ref):
        self._known(ref)
        value=self._paid_observations.get(ref.run_id)
        if value is None:raise BrokerStateError('Paid original terminal not collected')
        return json.loads(canonical(value))

    async def prepare_cleanup_evidence(self,ref,*args,**kwargs):
        self.paid_terminal_observation(ref)

    async def reattach(self,spec,binding,*,lease):
        if not isinstance(lease,AttemptLease) or lease.attempt.attempt_id!=spec.run_id:
            raise BrokerStateError('Paid recovery requires its actual adopted Runtime lease')
        self._leases[spec.run_id]=lease
        self._validate_lease(spec.run_id)
        self.validate_remote_recovery_coordinates(spec,binding)
        attempt,physical,payload=self._resolve(spec,launch=False,control_recovery=binding.control_recovery)
        if spec.run_id in self._bound:raise BrokerStateError('Paid original recovery already attached')
        self._leases[spec.run_id]=lease
        client=self.binding_source.client_for(physical,payload)
        from control_plane.executive_fabric_bridge_broker import start_request_sha256
        result=await client.request('status',dict(binding=payload['binding'],run_id=spec.run_id,
            physical_binding_sha256=physical.digest,start_request_sha256=start_request_sha256(payload)))
        if result.get('start_state')!='EXISTS':raise BrokerStateError('Paid original start remains unknown')
        self._validate_lease(spec.run_id)
        current,check,check_payload=self._resolve(spec,launch=False,control_recovery=binding.control_recovery)
        self._pin_matches(current,check,check_payload)
        if check_payload!=payload or check!=physical:
            raise BrokerStateError('Paid source moved during original recovery')
        ref,att=validate_paid_start_wire(result['start_result'],payload)
        if digest(att)!=binding.launch_attestation_sha256:
            raise BrokerStateError('Paid original attestation changed during recovery')
        if ref!=binding.process_ref:raise BrokerStateError('Paid original process changed during recovery')
        self._control_recovery[spec.run_id]=dict(binding.control_recovery)
        self._bound[spec.run_id]=(client,payload,physical,spec)
        self._refs[spec.run_id],self._attestations[spec.run_id]=ref,att
        return ref
