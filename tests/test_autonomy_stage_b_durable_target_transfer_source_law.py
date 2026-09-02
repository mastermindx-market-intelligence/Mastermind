from __future__ import annotations
import ast, copy, json, re
from pathlib import Path
import pytest

R=Path(__file__).resolve().parents[1]
D=R/"docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md"
P=R/"docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md"
C=R/"config/wake_session_targets.json"; S=R/"control_plane/session_targets.py"
B=R/"control_plane/runtime_binding_projection.py"; A=R/"control_plane/wake_ack_ingress.py"
L=R/"control_plane/wake_ledger.py"; W=R/"control_plane/wake_persist.py"; E=R/"control_plane/executive_runtime.py"
ACK=["obligation_id","ack_mode","target_seat","session_alias","reasoning_surface","binding_id","acknowledged_at","claimed_obligation_ids","operator_authority_receipt","binding_generation","delivered_command_id"]
PATHS=["docs/superpowers/specs/2026-09-01-autonomy-stage-b-durable-target-transfer-design.md","docs/superpowers/plans/2026-09-01-autonomy-stage-b-durable-target-transfer.md","tests/test_autonomy_stage_b_durable_target_transfer_source_law.py"]

def text(p): return p.read_text()
def block(p,a,b):
 m=re.search(re.escape(a)+r"\s*```json\s*(.*?)\s*```\s*"+re.escape(b),text(p),re.S); assert m; return json.loads(m.group(1))
def definition(p,name):
 src=text(p); nodes=ast.parse(src).body
 for part in name.split("."):
  n=next(x for x in nodes if isinstance(x,(ast.ClassDef,ast.FunctionDef)) and x.name==part); nodes=n.body if isinstance(n,ast.ClassDef) else []
 return ast.get_source_segment(src,n) or ""
def fields(p,name):
 n=next(x for x in ast.parse(text(p)).body if isinstance(x,ast.ClassDef) and x.name==name)
 return [x.target.id for x in n.body if isinstance(x,ast.AnnAssign) and isinstance(x.target,ast.Name)]
def validate(x):
 assert x["schema"]=="mastermind.autonomy_stage_b_f0_contract.v3"
 assert x["supported_modes"]==[] and x["supported_surfaces"]==[]
 assert x["claim"]=="SPEC_ONLY / NO_CURRENTLY_AUTHORIZED_MODES / PRODUCTION_INERT"
 assert x["stage_b1"]=="NOT_AUTHORIZED / ZERO_SUPPORTED_MODES / PRODUCTION_DISARMED"
 assert all(v["state"]=="HELD" for v in x["modes"].values())
 assert x["root_authority"]["state"]=="MISSING_OWNER" and "different aliases" in x["root_authority"]["discriminator"]
 assert x["codex_ceo_target"]["state"]=="ABSENT" and x["codex_ceo_target"]["production_armed"] is False
 assert x["command"]["caller_id"] is False and x["command"]["foreign"]=="COMMAND_REPLAY_CONFLICT" and "no retry/failover" in x["command"]["unknown"]
 assert x["ack"]["command_id"]=="<destination_wake_id>:ACK" and x["ack"]["type"]=="control_plane.wake_ledger.WakeAcknowledgement" and x["ack"]["fields"]==ACK
 assert x["ack"]["forbidden"]==["consumed_turn_reference","acknowledgement_token","mastermind.wake_consumption_ack/v1"]
 assert x["history"]["state"]=="NOT_BUILT"
 assert x["projection"][0]=="copy all roots and seats" and x["projection"][-1]=="call with_root_job_bindings once with complete map"
 assert x["no_rebuild"]["tables"]==[] and x["no_rebuild"]["migrations"]==[] and x["no_rebuild"]["registries"]==[] and x["no_rebuild"]["production_armed"] is False
 assert x["next"]=="STAGE-B-P0_ROOT_TARGET_AUTHORITY_ARCHITECTURE_FREEZE"

def test_contract_and_mutations():
 x=block(D,"<!-- STAGE_B_F0_CORRECTION_CONTRACT_BEGIN -->","<!-- STAGE_B_F0_CORRECTION_CONTRACT_END -->"); validate(x); assert "chatgpt-web" not in json.dumps(x)
 for path,value in [(('supported_modes',),['INITIAL_ASSIGNMENT']),(('modes','INITIAL_ASSIGNMENT','state'),'SUPPORTED'),(('root_authority','state'),'EXISTING'),(('codex_ceo_target','state'),'EXISTING'),(('command','caller_id'),True),(('ack','type'),'mastermind.wake_consumption_ack/v1'),(('projection',),['replace root']),(('no_rebuild','tables'),['targets']),(('no_rebuild','production_armed'),True)]:
  y=copy.deepcopy(x); c=y
  for k in path[:-1]: c=c[k]
  c[path[-1]]=value
  with pytest.raises(AssertionError): validate(y)

def test_current_root_and_target_gaps():
 c=json.loads(text(C)); assert c["root_job_bindings"]=={} and "tests overlay exact bindings" in c["notes"]
 d=definition(S,"SessionTargetRegistry.policy_digest"); assert "root_job_bindings" not in d
 o=definition(S,"SessionTargetRegistry.with_root_job_bindings"); assert "root_job_bindings=resolved" in o and "self.root_job_bindings" not in o
 assert not any(t["target_seat"]=="ceo" and t["reasoning_surface"]=="codex" for t in c["targets"].values())
 assert c["targets"]["EXECUTIVE-CEO-A"]["reasoning_surface"]=="chatgpt-sol"
 assert "chatgpt-web" not in text(S) and "binding.reasoning_surface != target.reasoning_surface" in definition(S,"_binding_must_match")

def test_current_binding_ack_and_release_owners():
 b=text(B); assert '_PROVIDER_TO_REASONING_SURFACE = {"openai-codex": "codex"}' in b and "current_harness_binding_source(attempt_id, connection=connection)" in b
 assert "persists nothing" in definition(B,"project_runtime_binding") and fields(L,"WakeAcknowledgement")==ACK
 l=text(L); assert "consumed_turn_reference" not in l and "acknowledgement_token" not in l and 'return f"{oid}:ACK"' in definition(L,"ledger_command_id")
 a=definition(A,"acknowledge_consumed_wakes")
 for t in ["runtime.store.transaction() as connection","list_ledger_records_on_connection","project_runtime_binding","_require_current_process_generation","append_records_on_connection"]: assert t in a
 assert "class WakeLedgerRepository" in text(W)
 e=text(E); assert "ORCHESTRATION_WORK_ADMITTED" in e and "mastermind.operator_harness_reconcile_observation/v1" in e and "ohf-work-admit:" in e

def test_plan_parks_and_orders_predecessor():
 g=block(P,"<!-- STAGE_B1_CORRECTION_GATE_BEGIN -->","<!-- STAGE_B1_CORRECTION_GATE_END -->")
 assert g["schema"]=="mastermind.autonomy_stage_b1_correction_gate.v3" and g["pull_request"]==368 and g["paths"]==PATHS
 assert g["records_only"] is True and g["runtime_effect"] is False and g["provider_effect"] is False and g["production_armed"] is False
 assert g["stage_b1"]=="PARKED" and g["supported_modes"]==[] and g["supported_surfaces"]==[] and g["global_static_fence_defect"]=="SEPARATE_PATH_DISJOINT_OPERATION"
 p=text(P); assert p.index("3. FREEZE_P0_ROOT_TARGET_AUTHORITY")<p.index("6. FREEZE_NEW_STAGE_B1_SOURCE_LAW")
