export type SourceState = 'CURRENT' | 'PARTIAL' | 'HISTORICAL' | 'UNAVAILABLE' | 'CONFLICT' | 'NOT_PROJECTED'

export interface MissionDocument {
  schema: 'mastermind.mission_workspace.v1'
  source?: { source_generation?: Record<string, unknown>; control_room_generated_at?: string | null; fabric_view_generated_at?: string | null }
  read_state: { state: SourceState; reason_codes?: string[]; usable_sections?: string[] }
  program: { work_ref: string; title?: string | null; state?: string | null; next_action?: string | null; evidence?: unknown[] }
  mission: { root_job_id?: string | null; root_job_candidates?: string[]; root_job_ambiguous?: boolean; runtime_root_state?: string; status?: string | null; orchestration_role?: string | null; plan_step_id?: string | null; depth?: number | null; title?: string | null; armed?: Record<string, boolean | null | string>; submission_availability?: string; capability?: { state?: string; detail?: string | null } }
  principal: { accountable_seat?: string | null; current_worker?: string | null; current_sol_target?: string | null; owed_turn?: string | null }
  children: ListSection
  execution: { state?: string; summary_present?: boolean; artifacts?: unknown[]; errors_present?: boolean; next_actions?: string[] }
  review: { required?: boolean | null; reviews_job_id?: string | null; verdict?: string }
  transport: { dispatch_state?: string; reason?: string | null; actionable?: boolean; historical?: boolean; watch_proven?: boolean | null; carrier?: string | null }
  acceptance: { state?: string; reason_codes?: string[]; owner?: string | null; artifact_revision?: string | null; ruling?: string | null }
  posture: { value?: string; rule?: string | null }
  conversation: ListSection
  missingness?: Array<{ missingness_class?: string; target_field?: string; producer_owner?: string; reason?: string }>
  degraded?: unknown[]
  feature_gates?: { conversation?: string; actions?: string; advanced?: string }
}

export interface ListSection { state?: string; coverage?: string; reason_codes?: string[]; total_count?: number | null; items?: Array<Record<string, unknown>>; overflow_count?: number | null }
export type MissionRead = (selection: { workRef: string; rootJobId?: string | null; signal: AbortSignal }) => Promise<MissionDocument>

const validWorkRef = (value: string) => /^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value)
const validJobId = (value: string) => /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value)

export function selectionFromLocation(search = window.location.search) {
  const params = new URLSearchParams(search); const workRef = params.get('work_ref') ?? ''
  const rootJobId = params.get('root_job_id')
  return validWorkRef(workRef) && (!rootJobId || validJobId(rootJobId)) ? { workRef, rootJobId } : null
}

export function createSameOriginMissionRead(nonce: string): MissionRead {
  return async ({ workRef, rootJobId, signal }) => {
  if (!nonce || nonce.length > 512) throw new Error('HOST_NONCE_UNAVAILABLE')
  if (!validWorkRef(workRef) || (rootJobId !== undefined && rootJobId !== null && !validJobId(rootJobId))) throw new Error('INVALID_SELECTION')
  const query = new URLSearchParams({ work_ref: workRef }); if (rootJobId) query.set('root_job_id', rootJobId)
  const response = await fetch(`/api/mission?${query.toString()}`, { method: 'GET', credentials: 'same-origin', signal, headers: { Accept: 'application/json', 'X-CCR-Token': nonce } })
  if (!response.ok) throw new Error(`SOURCE_${response.status}`)
  const document: unknown = await response.json()
  if (!validateMission(document, workRef, rootJobId)) throw new Error('INVALID_SOURCE_DOCUMENT')
  return document
  }
}

export function validateMission(value: unknown, workRef: string, rootJobId?: string | null): value is MissionDocument {
  if (!value || typeof value !== 'object') return false
  const doc = value as Partial<MissionDocument>
  if (doc.schema !== 'mastermind.mission_workspace.v1' || !doc.program || doc.program.work_ref !== workRef || !doc.read_state || typeof doc.read_state.state !== 'string') return false
  if (!doc.mission || !doc.children || !doc.conversation || !doc.execution || !doc.review || !doc.transport || !doc.acceptance || !doc.principal) return false
  if (rootJobId && doc.mission.root_job_id !== rootJobId) return false
  return Array.isArray(doc.children.items) && Array.isArray(doc.conversation.items)
}

export function unavailableMission(workRef = 'No program selected', reason = 'NO_HOST_SELECTION'): MissionDocument {
  return { schema: 'mastermind.mission_workspace.v1', read_state: { state: 'UNAVAILABLE', reason_codes: [reason], usable_sections: [] }, program: { work_ref: workRef }, mission: {}, principal: {}, children: { state: 'NOT_PROJECTED', coverage: 'NOT_PROJECTED', reason_codes: [reason], total_count: null, items: [], overflow_count: null }, execution: {}, review: {}, transport: {}, acceptance: { state: 'NOT_PROJECTED', reason_codes: ['ACCEPTANCE_OWNER_NOT_PROJECTED'] }, posture: {}, conversation: { state: 'UNAVAILABLE', coverage: 'NOT_PROJECTED', reason_codes: ['MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT'], total_count: null, items: [], overflow_count: null }, feature_gates: { conversation: 'UNAVAILABLE', actions: 'READ_ONLY', advanced: 'AVAILABLE' } }
}
