import type { CommandIntent, EffectReceipt, FiniteCommandPort, OperationPointer, OwnerContext } from "../orchestration/operation-controller";
import type { OrchestratorCommandBinding } from "../orchestration/host-command-bindings";
import { decodeExecutiveLaunchReceipt } from "../orchestration/executive-launch-command-port";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import type { LaunchForm } from "../orchestration/ui/LaunchOrchestrator";
import type { ProjectExecutionContextAvailable } from "./project-execution-context";
import { decodeProjectExecutionPreview, projectExecutionArguments, projectExecutionResult, projectExpectedContext,
  type ProjectExecutionPreview, type ProjectExecutionPreviousRun, type ProjectExecutionTransport } from "./project-execution-transport";

const prefix = "mmos-project-execute-";
const object = (v: unknown): v is Record<string,unknown> => v !== null && typeof v === "object" && !Array.isArray(v);
export function projectExecutionOperationKey(principalScope: string, request: Readonly<Record<string,unknown>>): string {
  const {operation_key: _key, ...body} = request;
  return prefix + sha256Hex(canonicalJson({principal_scope:principalScope,request:body})).slice(0,40);
}
export interface ProjectExecutionCapability {
  preview(context: ProjectExecutionContextAvailable, signal: AbortSignal, previousRun?: ProjectExecutionPreviousRun): Promise<ProjectExecutionPreview>;
  makeLaunchIntent(form: LaunchForm, context: ProjectExecutionContextAvailable, preview: ProjectExecutionPreview): CommandIntent | null;
}
export class ProjectExecutionCommandPort implements FiniteCommandPort, ProjectExecutionCapability {
  constructor(private readonly transport: ProjectExecutionTransport, private readonly owner: () => OwnerContext | null) {}
  context() { return this.owner(); }
  async preview(context: ProjectExecutionContextAvailable, signal: AbortSignal, previousRun?: ProjectExecutionPreviousRun) {
    const owner = this.owner();
    if (!owner || signal.aborted) throw Error("PROJECT_EXECUTION_UNAVAILABLE");
    const body = {work_ref:context.workRef,expected_context:projectExpectedContext(context),
      ...(previousRun ? {previous_run: previousRun} : {})};
    const args = projectExecutionArguments("preview",{...body,operation_key:"mmos-project-preview-" +
      sha256Hex(canonicalJson({principal_scope:owner.principalScope,...body})).slice(0,40)});
    const raw = await this.transport.request("preview",args,signal);
    const current = this.owner();
    if (signal.aborted || current?.principalScope !== owner.principalScope || current.generation !== owner.generation)
      throw Error("PROJECT_EXECUTION_CONTEXT_CHANGED");
    const preview = decodeProjectExecutionPreview(raw,context.workRef);
    if (canonicalJson(preview.previous_run ?? null) !== canonicalJson(previousRun ?? null))
      throw Error("PROJECT_EXECUTION_CONTEXT_CHANGED");
    return preview;
  }
  makeLaunchIntent(form: LaunchForm, context: ProjectExecutionContextAvailable, preview: ProjectExecutionPreview): CommandIntent | null {
    const owner = this.owner();
    if (!owner || form.frontierModelAlias !== undefined || preview.execution_state !== "WORK_CAPABLE" || preview.work_ref !== context.workRef ||
        form.workstreamRef !== context.workRef || form.projectRef !== "executive-infrastructure" ||
        !preview.binding.profiles.some(p=>p.ref === form.profileRef)) return null;
    try {
      // Select the offered profile's own binding. A missing map entry never
      // falls back to the scalar binding before the server revalidates it.
      const bindingDigest = preview.execution_profile_bindings === undefined
        ? preview.execution_binding_sha256
        : preview.execution_profile_bindings[form.profileRef as "research_only" | "bounded_code_change"];
      const body = {work_ref:context.workRef,expected_context:projectExpectedContext(context),
        context_sha256:preview.context_sha256,execution_binding_sha256:bindingDigest,
        execution_profile:form.profileRef,objective:form.goal,handoff_text:form.handoffText || null,continuation_mode:preview.continuation_mode,
        ...(preview.previous_run ? {previous_run: preview.previous_run} : {}),
        ...(form.profileRef === "bounded_code_change" ? {allowed_write_paths:form.allowedWritePaths,validation:form.validation} : {}),
};
      const payload = projectExecutionArguments("submit",{...body,operation_key:projectExecutionOperationKey(owner.principalScope,body)});
      return {kind:"launch",targetKey:context.workRef,payload};
    } catch { return null; }
  }
  prepare(intent: CommandIntent): OperationPointer {
    const owner = this.owner();
    if (!owner || intent.kind !== "launch") throw Error("INVALID_PAYLOAD");
    const payload = projectExecutionArguments("submit",intent.payload);
    if (intent.targetKey !== payload.work_ref || payload.operation_key !== projectExecutionOperationKey(owner.principalScope,payload))
      throw Error("INVALID_PAYLOAD");
    return {kind:"launch",targetKey:intent.targetKey,operationKey:payload.operation_key as string};
  }
  private receipt(pointer: OperationPointer, disposition: EffectReceipt["disposition"], reason: string): EffectReceipt {
    return {...pointer,disposition,reason};
  }
  private async call(pointer: OperationPointer, operation: "submit" | "status", args: Record<string,unknown>, signal: AbortSignal) {
    const owner = this.owner();
    if (!owner || signal.aborted) return this.receipt(pointer,"unknown","TRANSPORT_ERROR");
    try {
      const raw = await this.transport.request(operation,projectExecutionArguments(operation,args),signal);
      const current = this.owner();
      if (signal.aborted || current?.principalScope !== owner.principalScope || current.generation !== owner.generation)
        return this.receipt(pointer,"unknown","OWNER_CHANGED");
      const value = projectExecutionResult(raw,operation);
      if (!value.ok) {
        const code = (value.error as {code:string}).code;
        return this.receipt(pointer,operation === "submit" &&
          ["invalid_input","refused","context_changed","source_unavailable","execution_unavailable","input_too_large","previous_run_already_continued","previous_workspace_unavailable"].includes(code)
            ? "refused" : "unknown",code.toUpperCase());
      }
      const data = value.data as Record<string,unknown>;
      if (Object.keys(data).length !== 4 || data.operation_key !== pointer.operationKey ||
          data.work_ref !== pointer.targetKey || data.state !== "ACCEPTED" ||
          !object(data.receipt) || data.receipt.schema !== "mastermind.ceo_intent_receipt.v2")
        return this.receipt(pointer,"unknown","UNKNOWN_RECEIPT");
      return decodeExecutiveLaunchReceipt(pointer,data.receipt);
    } catch { return this.receipt(pointer,"unknown","TRANSPORT_ERROR"); }
  }
  submit(pointer: OperationPointer, intent: CommandIntent, signal: AbortSignal): Promise<EffectReceipt> {
    try {
      const expected = this.prepare(intent);
      if (canonicalJson(expected) !== canonicalJson(pointer)) throw Error("INVALID_PAYLOAD");
    } catch { return Promise.resolve(this.receipt(pointer,"refused","INVALID_PAYLOAD")); }
    return this.call(pointer,"submit",intent.payload as Record<string,unknown>,signal);
  }
  readOperation(pointer: OperationPointer, signal: AbortSignal) {
    return this.call(pointer,"status",{operation_key:pointer.operationKey,work_ref:pointer.targetKey},signal);
  }
}
/** Route only project commands through the existing owner/store/controller. */
export function attachProjectExecution(base: OrchestratorCommandBinding, transport: ProjectExecutionTransport): OrchestratorCommandBinding {
  const project = new ProjectExecutionCommandPort(transport,()=>base.port.context());
  const isProject = (key: string) => key.startsWith(prefix);
  return {...base,projectExecution:project,port:{
    context:()=>base.port.context(),
    prepare:intent=>typeof intent.payload.operation_key === "string" && isProject(intent.payload.operation_key)
      ? project.prepare(intent) : base.port.prepare(intent),
    submit:(pointer,intent,signal)=>isProject(pointer.operationKey) ? project.submit(pointer,intent,signal) : base.port.submit(pointer,intent,signal),
    readOperation:(pointer,signal)=>isProject(pointer.operationKey) ? project.readOperation(pointer,signal) : base.port.readOperation(pointer,signal),
  }};
}
