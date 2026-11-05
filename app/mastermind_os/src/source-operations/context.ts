/** Fixed source-action identity context. No source/CAS/adoption readiness is inferred. */
export type SourceAction = 'publish_project_proposal' | 'ADOPT_PLAN' | 'ACCEPT_DIRECTION'
  | 'add_project_file' | 'set_project_communication_preference';
export interface SourceOperationContextSelection { action: SourceAction; workRef: string | null }
export interface SourceOperationContext {
  schema: 'mastermind.workspace_source_operation_context.v1';
  selection: { action: SourceAction; work_ref: string | null };
  owner_context: { principal_scope: string };
  can_inspect: true;
}
const actions = new Set<unknown>(['publish_project_proposal','ADOPT_PLAN','ACCEPT_DIRECTION',
  'add_project_file','set_project_communication_preference']);
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error();
  const proto = Object.getPrototypeOf(value);
  if (proto !== Object.prototype && proto !== null) throw new Error();
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const own = Reflect.ownKeys(descriptors);
  if (own.length !== keys.length || own.some(k => typeof k !== 'string' || !keys.includes(k))) throw new Error();
  const result: Record<string, unknown> = {};
  for (const key of keys) {
    const d = descriptors[key];
    if (!d || !('value' in d) || d.get || d.set) throw new Error();
    result[key] = d.value;
  }
  return result;
}
export function validSourceOperationContextSelection(value: unknown): value is SourceOperationContextSelection {
  try {
    const v = object(value, ['action','workRef']);
    return typeof v.action === 'string' && actions.has(v.action)
      && ((v.workRef === null && v.action === 'publish_project_proposal')
        || (typeof v.workRef === 'string' && /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.exec(v.workRef)?.[0] === v.workRef
          && v.workRef.length >= 5 && v.workRef.length <= 67));
  } catch { return false; }
}
export function decodeSourceOperationContext(raw: unknown, selected: SourceOperationContextSelection): SourceOperationContext {
  try {
    if (!validSourceOperationContextSelection(selected)) throw new Error();
    const body = object(raw,['schema','selection','owner_context','can_inspect']);
    const selection = object(body.selection,['action','work_ref']);
    const owner = object(body.owner_context,['principal_scope']);
    if (body.schema !== 'mastermind.workspace_source_operation_context.v1' || body.can_inspect !== true
      || selection.action !== selected.action || selection.work_ref !== selected.workRef
      || typeof owner.principal_scope !== 'string' || owner.principal_scope.length !== 64 || !/^[0-9a-f]{64}$/.test(owner.principal_scope)) throw new Error();
    return {schema:'mastermind.workspace_source_operation_context.v1',
      selection:{action:selected.action,work_ref:selected.workRef},
      owner_context:{principal_scope:owner.principal_scope},can_inspect:true};
  } catch { throw new Error('SOURCE_OPERATION_CONTEXT_INVALID'); }
}
