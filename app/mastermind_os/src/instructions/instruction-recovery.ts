/** Read-only discovery in the incumbent namespace. Identity grants no action. */
import type {OwnerContext,PendingPointerStore,OperationPointer} from "../orchestration/operation-controller";
import {parseInstructionAdmissionTarget,type InstructionAdmissionTarget} from "../orchestration/instruction-admission-target";
import {decodeStandingInstructions,type StandingInstructionSelection} from "./standing-instructions";
export interface InstructionRecoverySnapshot {selection:StandingInstructionSelection|null;data:unknown;dataGeneration:string|null;generation:string|null;canRead:boolean}
export function instructionRecoveryContext(snapshot:InstructionRecoverySnapshot):OwnerContext|null {
 if(!snapshot.canRead||!snapshot.selection||!snapshot.generation||snapshot.dataGeneration!==snapshot.generation)return null;
 const body=decodeStandingInstructions(snapshot.data,snapshot.selection);
 return body?.schema==="mastermind.workspace_project_instructions.v2"&&body.availability==="AVAILABLE"&&body.recovery_identity
  ?{principalScope:body.recovery_identity.principal_scope,generation:snapshot.generation}:null;
}
export async function readInstructionRecoveryTarget(getCurrent:()=>InstructionRecoverySnapshot,store:PendingPointerStore,signal:AbortSignal):Promise<{pointer:OperationPointer;selection:InstructionAdmissionTarget}|null>{
 const snapshot=getCurrent(),before=instructionRecoveryContext(snapshot);
 if(!before||signal.aborted)return null;
 const pointer=await store.read(before.principalScope,signal);
 const afterSnapshot=getCurrent(),after=instructionRecoveryContext(afterSnapshot);
 if(signal.aborted||!after||before.principalScope!==after.principalScope||before.generation!==after.generation
  ||afterSnapshot.selection?.work_ref!==snapshot.selection?.work_ref||pointer?.kind!=="instruction_pause")return null;
 const selection=parseInstructionAdmissionTarget(pointer.targetKey);
 return selection!==null&&selection.work_ref===snapshot.selection?.work_ref?{pointer,selection}:null;
}
