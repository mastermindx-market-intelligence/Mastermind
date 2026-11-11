import type { ProjectExecutionContextAvailable } from "./project-execution-context";
import type { LaunchBindingConfig } from "../orchestration/executive-launch-command-port";

export type ProjectExecutionOperation = "preview" | "submit" | "status";
export interface ProjectExecutionTransport {
  request(operation: ProjectExecutionOperation, arguments_: Readonly<Record<string, unknown>>, signal: AbortSignal): Promise<unknown>;
}
/** Evidence for a completed prior run; the server independently requalifies it. */
export interface ProjectExecutionPreviousRun {
  readonly schema: "mastermind.project_execution_parent.v1";
  readonly root_job_id: string;
  readonly root_event_id: number;
  readonly root_event_sha256: string;
  readonly project_execution_source_sha256: string;
  readonly input_fingerprint_sha256: string;
  readonly attempt_id: string;
  readonly result_envelope_sha256: string;
  readonly terminal_receipt_sha256: string;
}
export interface ProjectExecutionPreview {
  readonly schema: "mastermind.project_execution_preview.v1";
  readonly work_ref: string;
  readonly context_sha256: string;
  readonly execution_state: "WORK_CAPABLE" | "QUEUED_NATIVE_RETURN" | "PLAN_ONLY" | "AUTONOMY_OFF" | "EXECUTION_UNAVAILABLE";
  readonly execution_binding_sha256: string | null;
  readonly execution_profile_bindings?: Readonly<Partial<Record<"research_only" | "bounded_code_change", string>>>;
  readonly continuation_mode: "DURABLE" | "ATTENDED" | null;
  readonly coordinator: { readonly provider: string; readonly model: string; readonly effort: string } | null;
  readonly previous_run?: ProjectExecutionPreviousRun | null;
  readonly execution_scope?: { readonly repository: "mastermindx-market-intelligence/Mastermind"; readonly commit: string } | null;
  readonly binding: LaunchBindingConfig;
}
export const projectExpectedContext = (context: ProjectExecutionContextAvailable) => ({
  record_source: context.recordSource, adoption: context.adoption,
  adoption_decision_source: context.adoptionDecisionSource,
});
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
const hex = (v: unknown, n = 64): v is string => typeof v === "string" && new RegExp("^[a-f0-9]{" + n + "}$").test(v);
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const work = (v: unknown): v is string => typeof v === "string" && /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(v) && v.length >= 5 && v.length <= 67;
const invalid = (): never => { throw Error("PROJECT_EXECUTION_INPUT_INVALID"); };
const source = (v: unknown) => object(v) && exact(v, ["repository", "commit", "path", "content_sha256"]) &&
  typeof v.repository === "string" && ["mastermindx-market-intelligence/macro", "mastermindx-market-intelligence/Mastermind"].includes(v.repository) &&
  hex(v.commit, 40) && hex(v.content_sha256) && typeof v.path === "string" && v.path.length <= 512 &&
  !v.path.startsWith("/") && !/[\u0000\r\n\\]/.test(v.path) && v.path.endsWith(".md") && v.path.split("/").every(x => !!x && x !== "." && x !== "..");
const previousRunIsValid = (v: unknown): v is ProjectExecutionPreviousRun =>
  object(v) && exact(v, ["schema", "root_job_id", "root_event_id", "root_event_sha256",
    "project_execution_source_sha256", "input_fingerprint_sha256", "attempt_id",
    "result_envelope_sha256", "terminal_receipt_sha256"]) &&
  v.schema === "mastermind.project_execution_parent.v1" &&
  typeof v.root_job_id === "string" && /^JOB-[0-9]+$/.test(v.root_job_id) &&
  typeof v.root_event_id === "number" && Number.isSafeInteger(v.root_event_id) && v.root_event_id > 0 &&
  typeof v.attempt_id === "string" && v.attempt_id.length > 0 && [...v.attempt_id].length <= 128 &&
  !/[\u0000-\u001f]/.test(v.attempt_id) &&
  ["root_event_sha256", "project_execution_source_sha256", "input_fingerprint_sha256",
    "result_envelope_sha256", "terminal_receipt_sha256"].every(key => hex(v[key]));
export function projectExecutionPreviousRun(value: unknown): ProjectExecutionPreviousRun {
  if (!previousRunIsValid(value)) return invalid();
  return structuredClone(value);
}
export function projectExecutionArguments(operation: ProjectExecutionOperation, raw: unknown): Record<string, unknown> {
  if (!["preview","submit","status"].includes(operation) || !object(raw) || !work(raw.work_ref)) return invalid();
  const fields = ["operation_key","work_ref"];
  if (operation !== "status") fields.push("expected_context", ...(Object.hasOwn(raw, "previous_run") ? ["previous_run"] : []));
  if (operation === "submit") fields.push("context_sha256","execution_binding_sha256","execution_profile","objective","handoff_text","continuation_mode",
    ...["allowed_write_paths","validation"].filter(k => Object.hasOwn(raw,k)));
  if (!exact(raw,fields) || typeof raw.operation_key !== "string" ||
      !(operation === "preview" ? /^mmos-project-preview-[a-f0-9]{40}$/ : /^mmos-project-execute-[a-f0-9]{40}$/).test(raw.operation_key)) return invalid();
  if (operation !== "status") {
    if (Object.hasOwn(raw, "previous_run") && !previousRunIsValid(raw.previous_run)) return invalid();
    const c = raw.expected_context;
    if (!object(c) || !exact(c,["record_source","adoption","adoption_decision_source"]) || !source(c.record_source)) return invalid();
    const record = c.record_source as Record<string, unknown>;
    if (record.repository !== "mastermindx-market-intelligence/macro" || record.path !== "agentos/workstreams/WS-" + raw.work_ref.slice(3) + ".md") return invalid();
    const adoption = c.adoption;
    if (adoption === null) { if (c.adoption_decision_source !== null) return invalid(); }
    else if (!object(adoption)) return invalid();
    else if (adoption.state === "UNAVAILABLE") {
      if (!exact(adoption,["state","reason"]) || !["SOURCE_UNAVAILABLE","NOT_DECLARED","LINEAGE_INVALID","PROPOSAL_MISMATCH","CONTENT_OVER_BUDGET"].includes(String(adoption.reason)) ||
          c.adoption_decision_source !== null) return invalid();
    } else if (adoption.state === "AVAILABLE") {
      if (!exact(adoption,["state","decision_ref","adopted_source","display_revision","matches_authored_record"]) ||
          typeof adoption.decision_ref !== "string" || !/^DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(adoption.decision_ref) ||
          !source(adoption.adopted_source) || typeof adoption.matches_authored_record !== "boolean" ||
          !(adoption.display_revision === null || typeof adoption.display_revision === "string" && adoption.display_revision.length <= 128) ||
          !source(c.adoption_decision_source)) return invalid();
      const decision = c.adoption_decision_source as Record<string,unknown>;
      if (decision.repository !== "mastermindx-market-intelligence/macro" ||
          decision.path !== "agentos/decisions/DEC-" + adoption.decision_ref.slice(4) + ".md") return invalid();
    } else return invalid();
  }
  if (operation === "submit") {
    if (!hex(raw.context_sha256) || !hex(raw.execution_binding_sha256) || !["DURABLE","ATTENDED"].includes(String(raw.continuation_mode)) ||
        !["research_only","bounded_code_change"].includes(String(raw.execution_profile)) ||
        typeof raw.objective !== "string" || !raw.objective.trim() || [...raw.objective].length > 4000 || raw.objective.includes("\0") ||
        !(raw.handoff_text === null || typeof raw.handoff_text === "string" && !raw.handoff_text.includes("\0") && new TextEncoder().encode(raw.handoff_text).length <= 32768)) return invalid();
    const paths = raw.allowed_write_paths;
    if (paths !== undefined && (!Array.isArray(paths) || paths.length > 16 ||
        paths.some(p => typeof p !== "string" || !p || p.length > 256 || p.startsWith("/") || /[\\*?\u0000\r\n]/.test(p) ||
          p.split("/").some(x => !x || [".","..",".git"].includes(x))))) return invalid();
    const validation = raw.validation;
    if (validation !== undefined) {
      if (!object(validation) || Object.keys(validation).some(k => !["pytest_targets","compileall_paths","git_diff_check"].includes(k))) return invalid();
      for (const key of ["pytest_targets","compileall_paths"]) if (validation[key] !== undefined &&
          (!Array.isArray(validation[key]) || (validation[key] as unknown[]).length > 8 ||
            (validation[key] as unknown[]).some(p => typeof p !== "string" || !p.trim() || p.length > 256))) return invalid();
      if (validation.git_diff_check !== undefined && typeof validation.git_diff_check !== "boolean") return invalid();
    }
    const validations = object(validation) && (validation.git_diff_check === true ||
      Array.isArray(validation.pytest_targets) && validation.pytest_targets.length > 0 ||
      Array.isArray(validation.compileall_paths) && validation.compileall_paths.length > 0);
    if (raw.execution_profile === "bounded_code_change" ? !Array.isArray(paths) || paths.length === 0 || !validations :
        Array.isArray(paths) && paths.length > 0 || !!validations) return invalid();
  }
  const serialized = JSON.stringify(raw);
  if (new TextEncoder().encode(serialized).length > 57344) return invalid();
  return JSON.parse(serialized) as Record<string,unknown>;
}
export function projectExecutionResult(raw: unknown, operation: ProjectExecutionOperation): Record<string, unknown> {
  if (!object(raw) || !exact(raw,["schema","operation","ok","data","error"]) ||
      raw.schema !== "mastermind.project_execution_private_result.v1" || raw.operation !== operation || typeof raw.ok !== "boolean" ||
      (raw.ok ? raw.error !== null || !object(raw.data) : raw.data !== null || !object(raw.error) || !exact(raw.error,["code","message"]) ||
        typeof raw.error.code !== "string" || typeof raw.error.message !== "string")) throw Error("PROJECT_EXECUTION_RESPONSE_INVALID");
  return raw;
}
export function decodeProjectExecutionPreview(raw: unknown, workRef: string): ProjectExecutionPreview {
  const envelope = projectExecutionResult(raw,"preview");
  if (!envelope.ok) throw Error("PROJECT_EXECUTION_UNAVAILABLE");
  const v = envelope.data as Record<string,unknown>;
  if (!exact(v,["schema","work_ref","context_sha256","execution_state","execution_binding_sha256","continuation_mode","coordinator","binding",
      ...["previous_run", "execution_scope", "execution_profile_bindings"].filter(key => Object.hasOwn(v, key))]) ||
      (Object.hasOwn(v, "previous_run") && v.previous_run !== null && !previousRunIsValid(v.previous_run)) ||
      (Object.hasOwn(v, "execution_scope") && v.execution_scope !== null &&
        !(object(v.execution_scope) && exact(v.execution_scope, ["repository", "commit"]) &&
          v.execution_scope.repository === "mastermindx-market-intelligence/Mastermind" && hex(v.execution_scope.commit, 40))) ||
      v.schema !== "mastermind.project_execution_preview.v1" || v.work_ref !== workRef || !hex(v.context_sha256) ||
      !["WORK_CAPABLE","QUEUED_NATIVE_RETURN","PLAN_ONLY","AUTONOMY_OFF","EXECUTION_UNAVAILABLE"].includes(String(v.execution_state)) ||
      !(v.execution_binding_sha256 === null || hex(v.execution_binding_sha256)) ||
      !(v.continuation_mode === null || ["DURABLE","ATTENDED"].includes(String(v.continuation_mode))) ||
      !(v.coordinator === null || object(v.coordinator) && exact(v.coordinator,["provider","model","effort"]) &&
        Object.values(v.coordinator).every(x => typeof x === "string" && x.length > 0 && x.length <= 128)) || !object(v.binding) ||
      !exact(v.binding,["workstream","priority","attemptLimit","projects","profiles"]) ||
      v.binding.workstream !== workRef || v.binding.priority !== 0 || v.binding.attemptLimit !== 1 ||
      !Array.isArray(v.binding.projects) || v.binding.projects.length !== 1 ||
      !object(v.binding.projects[0]) || !exact(v.binding.projects[0],["ref","label"]) ||
      v.binding.projects[0].ref !== "executive-infrastructure" || typeof v.binding.projects[0].label !== "string" ||
      !Array.isArray(v.binding.profiles) || v.binding.profiles.length > 2 ||
      v.binding.profiles.some(x => !object(x) || !exact(x,["ref","label"]) ||
        !["research_only","bounded_code_change"].includes(String(x.ref)) || typeof x.label !== "string") ||
      new Set(v.binding.profiles.map(x => (x as {ref:string}).ref)).size !== v.binding.profiles.length ||
      (v.execution_state === "WORK_CAPABLE" && (!hex(v.execution_binding_sha256) || !v.continuation_mode || !v.coordinator || v.binding.profiles.length === 0))) throw Error("PROJECT_EXECUTION_RESPONSE_INVALID");
  if (Object.hasOwn(v, "execution_profile_bindings")) {
    const bindings = v.execution_profile_bindings;
    const refs = (v.binding as { profiles: Array<{ ref: string }> }).profiles.map(profile => profile.ref);
    if (!object(bindings) || !exact(bindings, refs) || !Object.values(bindings).every(value => hex(value)) ||
        (Object.hasOwn(bindings, "research_only") && bindings.research_only !== v.execution_binding_sha256))
      throw Error("PROJECT_EXECUTION_RESPONSE_INVALID");
  }
  return structuredClone(v) as unknown as ProjectExecutionPreview;
}
