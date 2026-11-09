import { ORIGINAL_OPERATION_ID_PREFIXES } from "../planning/plan-adoption-status";
import {validateDiscoveryCorrectionRequest,validateDiscoveryCorrectionLookup,type DiscoveryCorrectionLookup} from '../knowledge/library/project-discovery-correction';
import {
  validSourceOperationContextSelection,
  type SourceAction,
} from "./context";
export type SourceOperationMethod =
  "options" | "prepare" | "read" | "submit" | "reconcile" | "advance";
export type BasicSourceLookup = {
  schema: "mastermind.workspace_source_operation_lookup.v1";
  action: SourceAction;
  request_id: string;
  work_ref: string;
} | {
  schema: "mastermind.workspace_source_operation_lookup.v1";
  action: "publish_project_proposal";
  request_id: string;
  work_ref: null;
};
/** Exact original safe lookup; Knowledge never accepts the basic selector. */
export interface LegacyKnowledgeSourceLookup {
  action: 'add_project_file' | 'set_project_communication_preference';
  request_id: string;
  work_ref: string;
  source_commit: string;
  base_revision: string;
  request_sha256: string;
  expected_preference_revision: string | null;
}
export type KnowledgeSourceLookup = LegacyKnowledgeSourceLookup | DiscoveryCorrectionLookup;
export type SourceLookup = BasicSourceLookup | KnowledgeSourceLookup;
export interface SourcePrepare {
  action: SourceAction;
  request: unknown;
}
export interface SourceSubmit {
  action: SourceAction;
  request_id: string;
  work_ref: string;
  preview_witness: unknown;
}
export interface SourceAdvance {
  schema: "mastermind.workspace_source_operation_advance.v1";
  action: "ADOPT_PLAN";
  request_id: string;
  work_ref: string;
  phase_receipt_digest: string;
}
export interface SourceOperationTransport {
  readProjectCreationOptions?(signal:AbortSignal):Promise<unknown>;
  prepareSourceOperation(
    input: SourcePrepare,
    signal: AbortSignal,
  ): Promise<unknown>;
  readSourceOperation(
    input: SourceLookup,
    signal: AbortSignal,
  ): Promise<unknown>;
  submitSourceOperation(
    input: SourceSubmit,
    signal: AbortSignal,
  ): Promise<unknown>;
  reconcileSourceOperation(
    input: SourceLookup,
    signal: AbortSignal,
  ): Promise<unknown>;
  advanceSourceOperation(
    input: SourceAdvance,
    signal: AbortSignal,
  ): Promise<unknown>;
}
export const SOURCE_OPERATION_CAP = 32768;
export const PROJECT_FILE_PREPARE_CAP = 98304;
function invalid(): never {
  throw new Error("SOURCE_OPERATION_REQUEST_INVALID");
}
function hex(value: unknown, length: number): boolean {
  return (
    typeof value === "string" &&
    value.length === length &&
    /^[0-9a-f]+$/.test(value)
  );
}
function clone(
  value: unknown,
  depth = 0,
  budget = { remaining: SOURCE_OPERATION_CAP },
): unknown {
  if (depth > 32) invalid();
  budget.remaining -= 2;
  if (budget.remaining < 0) invalid();
  if (value === null || typeof value === "boolean") return value;
  if (typeof value === "string") {
    for (const char of value) {
      const n = char.codePointAt(0)!;
      if (n >= 0xd800 && n <= 0xdfff) invalid();
    }
    budget.remaining -= new TextEncoder().encode(JSON.stringify(value)).length;
    if (budget.remaining < 0) invalid();
    return value;
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) invalid();
    return value;
  }
  if (typeof value !== "object" || value === null) invalid();
  const array = Array.isArray(value),
    proto = Object.getPrototypeOf(value);
  if (
    array
      ? proto !== Array.prototype
      : proto !== Object.prototype && proto !== null
  )
    invalid();
  const descriptors = Object.getOwnPropertyDescriptors(value),
    keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length > 4097)
    invalid();
  if (array) {
    const length = descriptors.length?.value;
    if (
      !Number.isSafeInteger(length) ||
      length < 0 ||
      length > 4096 ||
      keys.length !== length + 1
    )
      invalid();
    const result: unknown[] = [];
    for (let i = 0; i < length; i++) {
      const d = descriptors[String(i)];
      if (!d || !("value" in d)) invalid();
      result.push(clone(d.value, depth + 1, budget));
    }
    return result;
  }
  const result = Object.create(null) as Record<string, unknown>;
  for (const key of keys as string[]) {
    const d = descriptors[key];
    if (!d || !("value" in d)) invalid();
    clone(key, depth + 1, budget);
    result[key] = clone(d.value, depth + 1, budget);
  }
  return result;
}
function object(value: unknown, keys?: string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) invalid();
  const record = value as Record<string, unknown>;
  if (
    keys &&
    (Object.keys(record).length !== keys.length ||
      keys.some((k) => !Object.hasOwn(record, k)))
  )
    invalid();
  return record;
}
function identity(value: Record<string, unknown>) {
  const action = value.action;
  if (
    typeof action !== "string" ||
    !Object.hasOwn(ORIGINAL_OPERATION_ID_PREFIXES, action)
  )
    invalid();
  const prefix = ORIGINAL_OPERATION_ID_PREFIXES[action as SourceAction];
  if (
    typeof value.request_id !== "string" ||
    !value.request_id.startsWith(prefix) ||
    !hex(value.request_id.slice(prefix.length), 40)
  )
    invalid();
  if (
    typeof value.work_ref !== "string" ||
    /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(value.work_ref)?.[0] !==
      value.work_ref ||
    value.work_ref.length < 5 ||
    value.work_ref.length > 67
  )
    invalid();
}
function witness(value: unknown) {
  const w = object(value, ["original_input", "recipe_fingerprint_sha256"]),
    ref = object(w.original_input, [
      "schema",
      "input_ref",
      "artifact_sha256",
      "payload_sha256",
    ]);
  if (
    ref.schema !== "mastermind.terminal_original_input_reference.v1" ||
    typeof ref.input_ref !== "string" ||
    !ref.input_ref.startsWith("terminal-input:") ||
    !hex(ref.input_ref.slice("terminal-input:".length), 64)
  )
    invalid();
  for (const item of [
    w.recipe_fingerprint_sha256,
    ref.artifact_sha256,
    ref.payload_sha256,
  ])
    if (!hex(item, 64)) invalid();
}
export function sourceOperationRequest(
  method: SourceOperationMethod,
  input: unknown,
): Record<string, unknown> {
  try {
    const filePrepare=method==="prepare"&&input!==null&&typeof input==="object"&&
      Object.getOwnPropertyDescriptor(input,"action")?.value==="add_project_file";
    const requestCap=filePrepare?PROJECT_FILE_PREPARE_CAP:SOURCE_OPERATION_CAP;
    const body = object(clone(input,0,{remaining:requestCap}));
    // A stateful Proxy may change descriptors while clone detaches it. The
    // larger envelope never survives a different detached action.
    if(filePrepare&&body.action!=="add_project_file")invalid();
    if (method === "options") {
      object(body,["action"]);if(body.action!=="publish_project_proposal")invalid();
    } else if (method === "prepare") {
      object(body, ["action", "request"]);
      const request = object(body.request);
      if(filePrepare){
        object(request,["schema","request_id","work_ref","source_commit","base_revision","file"]);
        const file=object(request.file,["display_name","media_type","content_utf8"]);
        if(request.schema!=="mastermind.project_file_add_request.v1"||!hex(request.source_commit,40)||!hex(request.base_revision,64)||
          typeof file.display_name!=="string"||!file.display_name||new TextEncoder().encode(file.display_name).length>128||
          /[\u0000-\u001f\u007f-\u009f/\\]/.test(file.display_name)||
          typeof file.content_utf8!=="string"||new TextEncoder().encode(file.content_utf8).length>32768||
          /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]/.test(file.content_utf8))invalid();
        const dot=file.display_name.lastIndexOf('.'),ext=file.display_name.slice(dot+1).toLowerCase();
        if(dot<1||!['md','txt'].includes(ext)||file.media_type!==(ext==='md'?'text/markdown':'text/plain'))invalid();
      }
      if (
        typeof body.action !== "string" ||
        !Object.hasOwn(ORIGINAL_OPERATION_ID_PREFIXES, body.action)
      )
        invalid();
      if (body.action === 'correct_project_discovery') validateDiscoveryCorrectionRequest(request);
      const prefix =
        ORIGINAL_OPERATION_ID_PREFIXES[body.action as SourceAction];
      if (
        !validSourceOperationContextSelection({
          action: body.action,
          workRef: request.work_ref ?? null,
        })
      )
        invalid();
      if (
        typeof request.request_id !== "string" ||
        !request.request_id.startsWith(prefix) ||
        !hex(request.request_id.slice(prefix.length), 40)
      )
        invalid();
    } else if (method === "submit") {
      object(body, ["action", "request_id", "work_ref", "preview_witness"]);
      identity(body);
      witness(body.preview_witness);
    } else if (method === "advance") {
      object(body, [
        "schema",
        "action",
        "request_id",
        "work_ref",
        "phase_receipt_digest",
      ]);
      identity(body);
      if (
        body.schema !== "mastermind.workspace_source_operation_advance.v1" ||
        body.action !== "ADOPT_PLAN" ||
        !hex(body.phase_receipt_digest, 64)
      )
        invalid();
    } else {
      if(method === "read" && body.action === "publish_project_proposal" && body.work_ref === null) {
        const normalized={...body,work_ref:"WS:VALID"};identity(normalized);
      } else identity(body);
      if (body.action === 'correct_project_discovery') {
        validateDiscoveryCorrectionLookup(input);
      } else if (body.action === "add_project_file" || body.action === "set_project_communication_preference") {
        object(body,["action","request_id","work_ref","source_commit","base_revision","request_sha256","expected_preference_revision"]);
        // This added variant is closed own enumerable data before clone as
        // well; keep every older basic lookup's existing semantics intact.
        const original=Object.getOwnPropertyDescriptors(input as object);
        if(Reflect.ownKeys(original).some(key=>typeof key!=="string" || !original[key]?.enumerable || !("value" in original[key]!)))invalid();
        if(!hex(body.source_commit,40)||!hex(body.base_revision,64)||!hex(body.request_sha256,64)||
          (body.expected_preference_revision!==null&&!hex(body.expected_preference_revision,64))||
          (body.action==="add_project_file"&&body.expected_preference_revision!==null))invalid();
      } else {
        object(body, ["schema", "action", "request_id", "work_ref"]);
        if (body.schema !== "mastermind.workspace_source_operation_lookup.v1") invalid();
      }
    }
    if (
      new TextEncoder().encode(JSON.stringify(body)).length >
      requestCap
    )
      invalid();
    return body;
  } catch {
    return invalid();
  }
}
export function createSourceOperationTransport(
  call: (
    method: SourceOperationMethod,
    path: string,
    body: Record<string, unknown>,
    signal: AbortSignal,
  ) => Promise<unknown>,
): SourceOperationTransport {
  const invoke = (
    method: SourceOperationMethod,
    input: unknown,
    signal: AbortSignal,
  ) => {
    try {
      if (signal.aborted) throw new Error("READ_CANCELLED");
      const body = sourceOperationRequest(method, input);
      const path =
        method === "options" ? "/workspace/source-operation/options?action=publish_project_proposal" : method === "read"
          ? "/workspace/source-operation/operation?" +
            new URLSearchParams({
              action: String(body.action),
              request_id: String(body.request_id),
              work_ref: String(body.work_ref),
              ...(body.action==='correct_project_discovery'?{
                source_commit:String(body.source_commit),base_revision:String(body.base_revision),
                request_sha256:String(body.request_sha256),discovery_ref:String(body.discovery_ref),
                expected_discovery_revision:String(body.expected_discovery_revision),
              }:{}),
              ...((body.action==="add_project_file"||body.action==="set_project_communication_preference")?{
                source_commit:String(body.source_commit),base_revision:String(body.base_revision),
                request_sha256:String(body.request_sha256),expected_preference_revision:String(body.expected_preference_revision),
              }:{}),
            })
          : "/workspace/source-operation/" + method;
      return call(method, path, body, signal);
    } catch {
      return Promise.reject(new Error("SOURCE_OPERATION_REQUEST_INVALID"));
    }
  };
  return {
    readProjectCreationOptions: (signal) => invoke("options",{action:"publish_project_proposal"},signal),
    prepareSourceOperation: (input, signal) => invoke("prepare", input, signal),
    readSourceOperation: (input, signal) => invoke("read", input, signal),
    submitSourceOperation: (input, signal) => invoke("submit", input, signal),
    reconcileSourceOperation: (input, signal) =>
      invoke("reconcile", input, signal),
    advanceSourceOperation: (input, signal) => invoke("advance", input, signal),
  };
}
