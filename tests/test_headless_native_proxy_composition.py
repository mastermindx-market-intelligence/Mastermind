"""Integration evidence only: real broker/adapter/process; native responses are fixtures."""
import asyncio,dataclasses,json,os,pathlib,sys,tempfile,traceback,subprocess
from types import SimpleNamespace
sys.path.insert(0,str(pathlib.Path.cwd()));sys.path.insert(0,str(pathlib.Path('tests').resolve()))
from test_claude_operator_adapter import configured,FakeClient
from control_plane.codex_operator_adapter import _default_process_identity
from test_executive_operator_broker import _Sweeper,_reviewed_codex_adapter
from control_plane.executive_worker_broker import ExecutiveWorkerBroker,BrokerPolicy,PeerCredentials,BROKER_REQUEST_SCHEMA_VERSION
from control_plane.remote_operator_harness_adapter import RemoteOperatorHarnessAdapter
from control_plane.operator_harness_contract import OperationId,TurnRef,EventCursor,compare_launch
class ProcessBackedFixture(FakeClient):
 def start(self):
  self.child=subprocess.Popen([sys.executable,'-B','-c','import sys; sys.stdin.readline()'],stdin=subprocess.PIPE,start_new_session=True)
  self.pid=self.child.pid;self.running=True
 def alive(self): return hasattr(self,'child') and self.child.poll() is None
 def private_group_alive(self): return self.alive()
 def graceful_close(self,**kwargs):
  self.child.stdin.write(b'close\n');self.child.stdin.flush();self.child.stdin.close();code=self.child.wait(timeout=5);self.running=False
  return SimpleNamespace(private_group_empty=True,leader_exit_confirmed_graceful=code==0,controller_returncode=code)
 def terminate(self,**kwargs):
  if self.alive(): self.child.terminate();self.child.wait(timeout=5)
  self.running=False
import pytest
from control_plane.executive_worker_broker import BrokerProtocolError

def prepare(tmp_path):
 root=pathlib.Path(tmp_path).resolve(); a,native,profile,epoch,generation=configured.__wrapped__(root)
 native=ProcessBackedFixture();a.client_factory=lambda *args:native;a.process_identity_observer=_default_process_identity
 parent=root/'workspaces';parent.mkdir(mode=0o700);moved=parent/'workspace';a.workspace_root.rename(moved);a.workspace_root=moved;a.configured_workspace=a._workspace_identity();profile=dataclasses.replace(profile,workspace=a.configured_workspace)
 runroot=root/'runs';runroot.mkdir(mode=0o700)
 policy=BrokerPolicy(control_uid=os.geteuid()+1000,worker_uid=os.geteuid(),worker_gid=os.getegid(),worker_user='fixture-worker',worker_id=profile.worker_id,workspace_root=parent,run_root=runroot,provider_home=a.provider_home,allowed_supplementary_gids=frozenset(set(os.getgroups())-{os.getegid()}))
 binary=dataclasses.replace(_reviewed_codex_adapter(root/'reviewed-binary').binary,path=str(a.binary_path),real_path=str(a.binary_path),version=a.expected_harness_version,sha256=a.binary_digest)
 def factory(workspace,loader,requested):
  assert workspace==a.workspace_root and requested.workspace==profile.workspace
  a.turn_input_loader=loader
  return a
 sweeper=_Sweeper();broker=ExecutiveWorkerBroker(None,policy,sweeper,adapter_id=None,operator_binary_attestation=binary,operator_adapter_factory=factory,operator_harness_armed=True,autonomy_guard=lambda:None,autonomy_canary_factory=lambda p:{})
 peer=PeerCredentials(policy.control_uid,policy.worker_gid,100)
 class LocalWire:
  def __init__(self):self.calls=[];self.drop_start=False
  def request_sync(self,operation,payload,**kwargs):
   self.calls.append(operation)
   req=json.loads(json.dumps({'schema_version':BROKER_REQUEST_SCHEMA_VERSION,'request_id':f'req-{len(self.calls)}','operation':operation,'payload':payload}))
   response=asyncio.run(broker.execute(req,peer=peer))
   if operation=='ohf-start' and self.drop_start:
    self.drop_start=False;raise TimeoutError('fixture dropped durable reply')
   return json.loads(json.dumps(response))['result']
 client=LocalWire();proxy=RemoteOperatorHarnessAdapter(client,turn_input_loader=lambda turn:'Produce the exact bounded read-only result.',capabilities=a.describe_capabilities())
 return proxy,native,profile,epoch,generation,client,sweeper


def test_full_native_proxy_broker_adapter_result_and_clean_stop(tmp_path):
 proxy,native,profile,epoch,generation,client,sweeper=prepare(tmp_path)
 try:
  assert proxy.validate_requested_profile(profile).accepted
  session=proxy.start_session(operation_id=OperationId('ohf-op:start:'+epoch.attempt_id),requested=profile,epoch=epoch,generation=generation)
  assert session.provider_session_id==native.sid
  launch=compare_launch(profile,proxy.observed_attestation(generation));assert launch.decision.value=='ALLOW'
  turn=TurnRef('turn','epoch','generation','attempt')
  assert proxy.begin_turn(operation_id=OperationId('ohf-op:turn'),turn=turn,generation=generation,launch=launch).acknowledged
  events,cursor=proxy.read_events(EventCursor('attempt','epoch','generation',turn_id='turn'))
  assert len(events)==1 and cursor.local_sequence==1
  assert proxy.collect_candidate_result(turn).complete_job_permitted is False
  assert proxy.observe_raw_role_result(turn).canonical_result_json=='{"answer":"verified"}'
  assert proxy.graceful_stop(generation,operation_id=OperationId('ohf-op:stop')).process_liveness.value=='PROVEN_DEAD'
  assert native.child.returncode==0 and sweeper.calls==['operator_terminal']
  assert client.calls==['ohf-validate','ohf-start','ohf-begin-turn','ohf-collect-turn','ohf-stop']
 finally: native.terminate()


def test_lost_native_start_response_has_readonly_receipt_recovery_not_resume(tmp_path):
 proxy,native,profile,epoch,generation,client,sweeper=prepare(tmp_path)
 operation=OperationId('ohf-op:start:'+epoch.attempt_id);client.drop_start=True
 try:
  with pytest.raises(TimeoutError):proxy.start_session(operation_id=operation,requested=profile,epoch=epoch,generation=generation)
  status=proxy.materialization_status(operation_id=operation,requested=profile,epoch=epoch,generation=generation)
  assert status.receipt.provider_session_id==native.sid
  assert status.receipt.attempt_id==epoch.attempt_id and status.receipt.worker_id==profile.worker_id
  assert client.calls==['ohf-start','ohf-materialization-status']
  assert [m for m,_ in native.calls]==['initialize']
  assert proxy.graceful_stop(generation,operation_id=OperationId('ohf-op:stop')).process_liveness.value=='PROVEN_DEAD'
  assert native.child.returncode==0 and sweeper.calls==['operator_terminal']
 finally:native.terminate()


def test_unsupported_native_resume_never_reaches_broker(tmp_path):
 proxy,native,profile,epoch,generation,client,sweeper=prepare(tmp_path)
 try:
  with pytest.raises(BrokerProtocolError,match='does not support native resume'):
   proxy.resume_session(operation_id=None,requested=profile,epoch=epoch,generation=generation,provider_session=None)
  assert not native.alive() and native.calls==[] and client.calls==[] and sweeper.calls==[]
 finally:native.terminate()


def test_real_native_model_guard_survives_proxy_serialization(tmp_path):
 proxy,native,profile,epoch,generation,client,sweeper=prepare(tmp_path)
 try:
  invalid=dataclasses.replace(profile,requested_model='claude-opus-5-5')
  assert proxy.validate_requested_profile(invalid).accepted is False
  assert native.calls==[] and not native.alive() and sweeper.calls==[]
  assert client.calls==['ohf-validate']
 finally:native.terminate()
