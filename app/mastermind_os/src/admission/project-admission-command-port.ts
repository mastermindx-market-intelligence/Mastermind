/** Project controls over the incumbent finite controller and fixed owner port.
 * No authority, identity, selection or provider is inferred from method presence.
 * Status is read-only on the original key; NOT_OBSERVED always remains unknown.
 */
import type { CommandIntent, EffectReceipt, FiniteCommandPort, OperationPointer, OwnerContext } from "../orchestration/operation-controller";
import { decodeProjectAdmissionControl, validProjectAdmissionSelection, type ProjectAdmissionSelection } from "./project-admission";

export type AdmissionKind = "project_pause" | "project_resume";
export type PauseToken = Readonly<{ event_id: number; receipt_digest: string }>;
export interface ProjectAdmissionTransport {
  pause(request: { selection: ProjectAdmissionSelection; command_id: string; signal: AbortSignal }): Promise<unknown>;
  resume(request: { selection: ProjectAdmissionSelection; command_id: string; pause_token: PauseToken; signal: AbortSignal }): Promise<unknown>;
  status(request: { kind: AdmissionKind; selection: ProjectAdmissionSelection; command_id: string; signal: AbortSignal }): Promise<unknown>;
}
export interface ProjectAdmissionSnapshot {
  selection: ProjectAdmissionSelection | null;
  data: unknown;
  /** Generation under which this exact body was returned. */
  dataGeneration: string | null;
  /** Actual monotonic host auth/source invalidation generation. */
  generation: string | null;
  canRead: boolean;
}
const PREFIX = { project_pause: "mmos-project-pause-", project_resume: "mmos-project-resume-" } as const;
const HEX = /^[0-9a-f]{64}$/;
const COMMAND = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const REASONS = new Set(["INVALID_INPUT", "ACCESS_DENIED", "SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "ROOT_MISMATCH", "OWNER_NOT_READY"]);
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function exact(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  if (!object(value)) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(descriptors).length === keys.length && keys.every(key => Object.hasOwn(descriptors,key) && Object.hasOwn(descriptors[key],"value"));
}

function jsonData(value: unknown, seen = new Set<object>(), depth = 0, budget = {left: 400}): boolean {
  if (--budget.left < 0 || depth > 20) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "object" || value === null || seen.has(value)) return false;
  if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null && !Array.isArray(value)) return false;
  seen.add(value);
  const fields = Object.getOwnPropertyDescriptors(value);
  for (const key of Reflect.ownKeys(fields)) {
    if (typeof key !== "string" || !Object.hasOwn(fields[key], "value") || !jsonData(fields[key].value,seen,depth+1,budget)) return false;
  }
  seen.delete(value);return true;
}

function sameSelection(a: unknown, b: ProjectAdmissionSelection): boolean {
  return validProjectAdmissionSelection(a) && a.work_ref === b.work_ref && a.root_job_id === b.root_job_id;
}
function positive(value: unknown): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value > 0; }
function digest(value: unknown): value is string { return typeof value === "string" && HEX.exec(value)?.[0]===value; }
function token(value: unknown): value is PauseToken {
  return exact(value,["event_id","receipt_digest"]) && positive(value.event_id) && digest(value.receipt_digest);
}
function kind(value: unknown): value is AdmissionKind { return value === "project_pause" || value === "project_resume"; }
function validPointer(pointer: OperationPointer): pointer is OperationPointer & {kind: AdmissionKind; targetKey: string} {
  return kind(pointer.kind) && typeof pointer.targetKey === "string" && new RegExp(`^${PREFIX[pointer.kind]}[0-9a-f]{40}$`).exec(pointer.operationKey)?.[0]===pointer.operationKey;
}
/** Decode full fixed body before promoting a terminal controller receipt. */
export function projectAdmissionReceipt(value: unknown, pointer: OperationPointer, selection: ProjectAdmissionSelection, status = false): EffectReceipt {
  const outcome = (disposition: EffectReceipt["disposition"]): EffectReceipt => ({...pointer,disposition});
  if (!validProjectAdmissionSelection(selection) || !validPointer(pointer) || pointer.targetKey !== selection.work_ref) return outcome("unknown");
  try {
    if (!jsonData(value)) return outcome("unknown");
    if (new TextEncoder().encode(JSON.stringify({ok:true,result:value})+"\n").length > 32768) return outcome("unknown");
    const field = status ? "state" : "disposition";
    if (!exact(value,["schema","selection",field,"receipt","reason_codes"])) return outcome("unknown");
    const schemaBase = pointer.kind === "project_pause" ? "admission" : "resumption";
    if (value.schema !== `mastermind.workspace_project_${schemaBase}_${status ? "status" : "action"}_result.v1`) return outcome("unknown");
    if (!exact(value.selection, Object.hasOwn(selection,"root_job_id") ? ["work_ref","root_job_id","command_id"] : ["work_ref","command_id"])) return outcome("unknown");
    const {command_id, ...selected} = value.selection;
    if (command_id !== pointer.operationKey || !sameSelection(selected,selection)) return outcome("unknown");
    const reasons = value.reason_codes;
    if (!Array.isArray(reasons)) return outcome("unknown");
    if (value[field] === (status ? "OBSERVED" : "COMMITTED")) {
      const resumed = pointer.kind === "project_resume", receipt = value.receipt;
      const keys = ["schema","work_ref","state","event_id","command_id","request_digest","committed_at_ms", ...(resumed ? ["pause_event_id","pause_receipt_digest"] : [])];
      if (!exact(receipt,keys) || reasons.length !== 0 || receipt.schema !== `mastermind.workstream_admission_${resumed ? "resumption" : "suspension"}_receipt.v1`
          || receipt.state !== (resumed ? "RESUMED" : "PAUSED") || receipt.work_ref !== selection.work_ref || receipt.command_id !== pointer.operationKey
          || typeof receipt.command_id !== "string" || COMMAND.exec(receipt.command_id)?.[0]!==receipt.command_id || !positive(receipt.event_id) || !digest(receipt.request_digest)
          || typeof receipt.committed_at_ms !== "number" || !Number.isSafeInteger(receipt.committed_at_ms) || receipt.committed_at_ms < 0
          || (resumed && (!positive(receipt.pause_event_id) || receipt.event_id <= receipt.pause_event_id || !digest(receipt.pause_receipt_digest)))) return outcome("unknown");
      return outcome("accepted");
    }
    if (!status && value[field] === "NOT_DISPATCHED" && value.receipt === null && reasons.length === 1 && REASONS.has(reasons[0])) return outcome("refused");
    return outcome("unknown");
  } catch { return outcome("unknown"); }
}

export function createProjectAdmissionCommandPort(getCurrent: () => ProjectAdmissionSnapshot, transport: ProjectAdmissionTransport): FiniteCommandPort {
  function current() {
    const snapshot = getCurrent();
    if (!snapshot.canRead || !snapshot.selection || !validProjectAdmissionSelection(snapshot.selection) || !snapshot.generation || snapshot.dataGeneration!==snapshot.generation) return null;
    const data = decodeProjectAdmissionControl(snapshot.data,snapshot.selection);
    return data?.availability === "AVAILABLE" ? {snapshot,data} : null;
  }
  let retainedIdentity: { context: OwnerContext; selection: ProjectAdmissionSelection } | null = null;
  let departedGeneration: string | null = null;
  function context(): OwnerContext | null {
    const snapshot=getCurrent();
    if(!snapshot.canRead || !snapshot.selection || !validProjectAdmissionSelection(snapshot.selection) || !snapshot.generation) {
      retainedIdentity=null;return null;
    }
    if(retainedIdentity && (retainedIdentity.context.generation!==snapshot.generation || !sameSelection(snapshot.selection,retainedIdentity.selection)))retainedIdentity=null;
    if(departedGeneration===snapshot.generation)return null;
    const body=snapshot.dataGeneration===snapshot.generation ? decodeProjectAdmissionControl(snapshot.data,snapshot.selection) : null;
    if(body?.availability==="AVAILABLE") {
      const owner={principalScope:body.owner_context.principal_scope,generation:snapshot.generation};
      if(retainedIdentity && retainedIdentity.context.principalScope!==owner.principalScope) {
        // A principal change without a host epoch is a broken host boundary.
        // Hold rather than accepting an unobserved A→B→A as the original user.
        departedGeneration=snapshot.generation;retainedIdentity=null;return null;
      }
      retainedIdentity={context:owner,selection:{...snapshot.selection}};
    }
    // The independently host-fenced identity survives a failed current-state
    // read in the SAME epoch/selection. Only original status can use this;
    // prepare/submit still demand a freshly decoded current capability.
    return retainedIdentity ? {...retainedIdentity.context} : null;
  }
  function permitted(intent: CommandIntent) {
    const value = current();
    if (!value || !kind(intent.kind) || intent.targetKey !== value.snapshot.selection!.work_ref
        || !exact(intent.payload,intent.kind === "project_resume" ? ["selection","pause_token"] : ["selection"])
        || !sameSelection(intent.payload.selection,value.snapshot.selection!)) return null;
    const resumed = intent.kind === "project_resume";
    if (!(resumed ? value.data.permissions.resume && value.data.state === "PAUSED" : value.data.permissions.pause && value.data.state !== "PAUSED")) return null;
    if (resumed && (!token(intent.payload.pause_token) || !value.data.pause_token
        || intent.payload.pause_token.event_id !== value.data.pause_token.event_id || intent.payload.pause_token.receipt_digest !== value.data.pause_token.receipt_digest)) return null;
    return value;
  }
  return {
    context,
    prepare(intent) {
      if (!permitted(intent) || !kind(intent.kind)) throw new Error("PROJECT_CONTROL_UNAVAILABLE");
      const bytes = new Uint8Array(20); globalThis.crypto.getRandomValues(bytes);
      return {kind:intent.kind,targetKey:intent.targetKey,operationKey:PREFIX[intent.kind]+Array.from(bytes,x=>x.toString(16).padStart(2,"0")).join("")};
    },
    async submit(pointer,intent,signal) {
      const value = permitted(intent), before = context();
      if (!value || !before || !validPointer(pointer) || pointer.kind !== intent.kind || pointer.targetKey !== intent.targetKey || signal.aborted) return {...pointer,disposition:"refused"};
      const selection = {...value.snapshot.selection!};
      try {
        const request = {selection,command_id:pointer.operationKey,signal};
        const response = pointer.kind === "project_resume" ? await transport.resume({...request,pause_token:intent.payload.pause_token as PauseToken}) : await transport.pause(request);
        const after = context();
        if (signal.aborted || !after || after.principalScope !== before.principalScope || after.generation !== before.generation || !sameSelection(getCurrent().selection,selection)) return {...pointer,disposition:"unknown"};
        return projectAdmissionReceipt(response,pointer,selection);
      } catch { return {...pointer,disposition:"unknown"}; }
    },
    async readOperation(pointer,signal) {
      const before=context(), snapshot=getCurrent();
      if (!before || !snapshot.selection || !validPointer(pointer) || pointer.targetKey!==snapshot.selection.work_ref || signal.aborted) return {...pointer,disposition:"unknown"};
      const selection={...snapshot.selection};
      try {
        const response=await transport.status({kind:pointer.kind,selection,command_id:pointer.operationKey,signal});
        const after=context();
        if (signal.aborted || !after || after.principalScope!==before.principalScope || after.generation!==before.generation || !sameSelection(getCurrent().selection,selection)) return {...pointer,disposition:"unknown"};
        return projectAdmissionReceipt(response,pointer,selection,true);
      } catch {return {...pointer,disposition:"unknown"};}
    },
  };
}
