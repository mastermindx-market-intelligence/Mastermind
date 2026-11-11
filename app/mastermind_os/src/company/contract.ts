import { projectCompanyConnections, sameConnections } from "./connections";
import type { CompanyConnections } from "./connections";

export const COMPANY_SCHEMA = "mastermind.paperclip_workspace.v1";
export const COMPANY_COMMAND_SCHEMA = "mastermind.paperclip_command.v1";
export const COMPANY_CAP = 2_097_152;
export const companyViews = [
  "overview",
  "people",
  "projects",
  "goals",
  "work",
  "routines",
  "artifacts",
  "activity",
  "task",
  "routine",
  "runtime",
  "receipt",
] as const;
export type CompanyView = (typeof companyViews)[number];
export type CompanySelection = Readonly<{
  view: CompanyView;
  itemId?: string;
  projectId?: string;
  status?: string;
  offset?: number;
  cursor?: string;
  requestId?: string;
}>;
export type CompanyRecord = Readonly<Record<string, string | number>>;
export interface CompanyCollection {
  readonly state: "CURRENT" | "UNAVAILABLE";
  readonly items: readonly CompanyRecord[];
  readonly coverage: string;
  readonly code?: string;
  readonly hasMore: boolean;
  readonly nextOffset: number | null;
  readonly nextCursor: string | null;
  readonly restrictedCount?: number;
}
export interface RuntimeBinding {
  readonly agentId: string;
  readonly runtime: "hermes";
  readonly profileRef: string;
  readonly supervisorSessionRef: string | null;
  readonly gatewayRef: string;
  readonly qualification: "CONFIGURED_NOT_LIVE_VERIFIED";
}
export interface CompanyReceipt {
  readonly requestId: string;
  readonly state: "SAVED" | "EFFECT_UNKNOWN";
  readonly code: string;
  readonly item: CompanyRecord | null;
  readonly candidates: readonly CompanyRecord[];
  readonly retryAllowed: false;
}
export interface CompanySnapshot {
  readonly schema: typeof COMPANY_SCHEMA;
  readonly state: "CURRENT" | "PARTIAL";
  readonly view: CompanyView;
  readonly company: CompanyRecord;
  readonly bindingRevision: string;
  readonly scopeKey: string;
  readonly observedAt: string;
  readonly sourceRevision: string | null;
  readonly qualifiedRevision: string;
  readonly capabilities: readonly "create_backlog"[];
  readonly collections: Readonly<Record<string, CompanyCollection>>;
  readonly item: CompanyRecord | null;
  readonly runtimeBindings: readonly RuntimeBinding[];
  readonly projectBindings: readonly Readonly<{
    projectId: string;
    workRef: string;
  }>[];
  readonly ownership: Readonly<{
    work: "legacy" | "paperclip";
    wake: "legacy" | "paperclip";
    runtime: "hermes";
    admission: "executive";
    routing: "capacity";
  }>;
  readonly receipt?: CompanyReceipt;
  readonly migration?: RuntimeMigration;
  readonly connections?: CompanyConnections;
}
export interface RuntimeMigration {
  readonly state: "PREPARED_NOT_APPLIED";
  readonly agentId: string;
  readonly profileRef: string | null;
  readonly gatewayRef: string | null;
  readonly supervisorSessionRef: string | null;
  readonly targetAdapter: "hermes_gateway";
  readonly workSessionStrategy: "issue";
  readonly configurationCas: "NOT_SUPPORTED_BY_PINNED_AGENT_PATCH";
  readonly requirements: readonly string[];
  readonly retain: readonly string[];
  readonly replace: readonly string[];
  readonly applyAvailable: false;
}
export interface CompanyUnavailable {
  readonly schema: typeof COMPANY_SCHEMA;
  readonly state: "UNAVAILABLE";
  readonly code: string;
  readonly retryAllowed: false;
}
export type CompanyRead = CompanySnapshot | CompanyUnavailable;
export interface BacklogRequest {
  readonly operation: "create_backlog";
  readonly requestId: string;
  readonly bindingRevision: string;
  readonly title: string;
  readonly description: string;
  readonly projectId?: string;
}
export interface BacklogResult {
  readonly schema: typeof COMPANY_COMMAND_SCHEMA;
  readonly state: "SAVED" | "NOT_APPLIED" | "EFFECT_UNKNOWN";
  readonly operation: "create_backlog";
  readonly requestId: string;
  readonly bindingRevision: string;
  readonly scopeKey?: string;
  readonly companyId?: string;
  readonly item?: CompanyRecord;
  readonly code?: string;
  readonly retryAllowed: false;
}
const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const hash = /^[0-9a-f]{64}$/;
export const validCompanyId = (value: unknown): value is string =>
  typeof value === "string" && uuid.test(value);
export const validCompanyScope = (value: unknown): value is string =>
  typeof value === "string" && hash.test(value);
const fail = (): never => {
  throw new Error("COMPANY_RESPONSE_INVALID");
};
const object = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : fail();
const text = (value: unknown, max = 16000): string =>
  typeof value === "string" && value.length <= max ? value : fail();
const id = (value: unknown): string => (validCompanyId(value) ? value : fail());
const scope = (value: unknown): string =>
  validCompanyScope(value) ? value : fail();
const recordKeys = new Set([
  "id",
  "name",
  "title",
  "description",
  "status",
  "role",
  "reportsTo",
  "adapterType",
  "lastHeartbeatAt",
  "updatedAt",
  "goalId",
  "leadAgentId",
  "level",
  "parentId",
  "ownerAgentId",
  "identifier",
  "priority",
  "projectId",
  "assigneeAgentId",
  "statusVersion",
  "actorType",
  "actorId",
  "action",
  "entityType",
  "entityId",
  "createdAt",
  "issueId",
  "authorAgentId",
  "authorUserId",
  "body",
  "routineId",
  "startedAt",
  "finishedAt",
  "revisionNumber",
  "changeSummary",
  "mediaKind",
  "sourceKind",
  "agentId",
  "url",
  "kind",
  "provider",
  "reviewState",
  "healthStatus",
  "summary",
  "executionWorkspaceId",
  "createdByRunId",
  "invocationSource",
  "errorCode",
]);
function record(value: unknown): CompanyRecord {
  const row = object(value),
    result: Record<string, string | number> = {};
  if (
    typeof row.id !== "string" ||
    row.id.length < 1 ||
    row.id.length > 256 ||
    Object.keys(row).length > recordKeys.size
  )
    fail();
  for (const [key, item] of Object.entries(row)) {
    if (
      !recordKeys.has(key) ||
      (typeof item !== "string" && typeof item !== "number")
    )
      fail();
    if (typeof item === "number") {
      if (!Number.isSafeInteger(item) || item < 0) fail();
      result[key] = item;
    } else result[key] = text(item);
  }
  return Object.freeze(result);
}
function records(raw: unknown, max = 50): readonly CompanyRecord[] {
  if (!Array.isArray(raw) || raw.length > max) return fail();
  return Object.freeze(raw.map(record));
}
function collection(raw: unknown): CompanyCollection {
  const value = object(raw);
  if (
    (value.state !== "CURRENT" && value.state !== "UNAVAILABLE") ||
    typeof value.hasMore !== "boolean"
  )
    fail();
  const offset = value.nextOffset;
  if (
    offset !== null &&
    (!Number.isSafeInteger(offset) ||
      (offset as number) < 0 ||
      (offset as number) > 100050)
  )
    fail();
  return Object.freeze({
    state: value.state as CompanyCollection["state"],
    items: records(value.items),
    coverage: text(value.coverage, 64),
    hasMore: value.hasMore as boolean,
    nextOffset: offset as number | null,
    nextCursor: value.nextCursor === null ? null : text(value.nextCursor, 2048),
    ...(typeof value.code === "string" ? { code: text(value.code, 96) } : {}),
    ...(Number.isSafeInteger(value.restrictedCount) &&
    (value.restrictedCount as number) >= 0
      ? { restrictedCount: value.restrictedCount as number }
      : {}),
  });
}
export function validateCompanySelection(value: CompanySelection): void {
  if (
    !companyViews.includes(value.view) ||
    Object.keys(value).some(
      (key) =>
        ![
          "view",
          "itemId",
          "projectId",
          "status",
          "offset",
          "cursor",
          "requestId",
        ].includes(key),
    )
  )
    throw new Error("COMPANY_SELECTION_INVALID");
  for (const key of ["itemId", "projectId", "requestId"] as const)
    if (value[key] !== undefined && !validCompanyId(value[key]))
      throw new Error("COMPANY_SELECTION_INVALID");
  if (
    ["task", "routine", "runtime"].includes(value.view) !==
      (value.itemId !== undefined) ||
    (value.view === "receipt") !== (value.requestId !== undefined)
  )
    throw new Error("COMPANY_SELECTION_INVALID");
  if (
    value.projectId !== undefined &&
    !["work", "routines", "artifacts"].includes(value.view)
  )
    throw new Error("COMPANY_SELECTION_INVALID");
  if (
    value.offset !== undefined &&
    (!Number.isSafeInteger(value.offset) ||
      value.offset < 0 ||
      value.offset > 100000 ||
      !["people", "projects", "goals", "work", "routines"].includes(value.view))
  )
    throw new Error("COMPANY_SELECTION_INVALID");
  if (
    value.cursor !== undefined &&
    (value.view !== "artifacts" || !value.cursor || value.cursor.length > 2048)
  )
    throw new Error("COMPANY_SELECTION_INVALID");
  if (
    value.status !== undefined &&
    (value.view !== "work" ||
      ![
        "backlog",
        "todo",
        "in_progress",
        "in_review",
        "done",
        "blocked",
        "cancelled",
      ].includes(value.status))
  )
    throw new Error("COMPANY_SELECTION_INVALID");
}
export function companyQuery(selection: CompanySelection): string {
  validateCompanySelection(selection);
  return new URLSearchParams(
    Object.entries(selection).map(([key, value]) => [key, String(value)]),
  ).toString();
}
export function validateBacklogRequest(value: BacklogRequest): void {
  if (new TextEncoder().encode(JSON.stringify(value)).byteLength > 32768)
    throw new Error("COMPANY_COMMAND_TOO_LARGE");
  if (
    value.operation !== "create_backlog" ||
    !validCompanyId(value.requestId) ||
    !validCompanyScope(value.bindingRevision) ||
    typeof value.title !== "string" ||
    !value.title.trim() ||
    value.title.length > 300 ||
    typeof value.description !== "string" ||
    value.description.length > 16000 ||
    (value.projectId !== undefined && !validCompanyId(value.projectId)) ||
    Object.keys(value).some(
      (key) =>
        ![
          "operation",
          "requestId",
          "bindingRevision",
          "title",
          "description",
          "projectId",
        ].includes(key),
    )
  )
    throw new Error("COMPANY_COMMAND_INVALID");
}
export function decodeCompanyRead(
  raw: unknown,
  selected: CompanySelection,
): CompanyRead {
  const value = object(raw);
  if (
    value.schema !== COMPANY_SCHEMA ||
    (value.view !== undefined && value.view !== selected.view)
  )
    fail();
  if (value.state === "UNAVAILABLE")
    return Object.freeze({
      schema: COMPANY_SCHEMA,
      state: "UNAVAILABLE",
      code: text(value.code, 96),
      retryAllowed: false,
    });
  if (
    (value.state !== "CURRENT" && value.state !== "PARTIAL") ||
    value.view !== selected.view
  )
    fail();
  const company = record(value.company);
  id(company.id);
  const collections = object(value.collections),
    decoded: Record<string, CompanyCollection> = {};
  if (Object.keys(collections).length > 8) fail();
  for (const [key, entry] of Object.entries(collections)) {
    if (
      ![
        "people",
        "projects",
        "goals",
        "work",
        "routines",
        "activity",
        "artifacts",
        "comments",
        "runs",
        "revisions",
        "products",
        "executions",
      ].includes(key)
    )
      fail();
    decoded[key] = collection(entry);
    if (key !== "artifacts") decoded[key].items.forEach((row) => id(row.id));
  }
  const ownership = object(value.ownership);
  if (
    !["legacy", "paperclip"].includes(String(ownership.work)) ||
    !["legacy", "paperclip"].includes(String(ownership.wake)) ||
    ownership.runtime !== "hermes" ||
    ownership.admission !== "executive" ||
    ownership.routing !== "capacity"
  )
    fail();
  if (
    !Array.isArray(value.capabilities) ||
    value.capabilities.some((cap) => cap !== "create_backlog") ||
    value.capabilities.length > 1
  )
    fail();
  if (
    !Array.isArray(value.runtimeBindings) ||
    value.runtimeBindings.length > 128
  )
    fail();
  const runtimeBindings = (value.runtimeBindings as unknown[]).map(
    (rawBinding) => {
      const binding = object(rawBinding);
      if (
        binding.runtime !== "hermes" ||
        binding.qualification !== "CONFIGURED_NOT_LIVE_VERIFIED"
      )
        fail();
      return Object.freeze({
        agentId: id(binding.agentId),
        runtime: "hermes" as const,
        profileRef: text(binding.profileRef, 192),
        supervisorSessionRef:
          binding.supervisorSessionRef === null
            ? null
            : text(binding.supervisorSessionRef, 192),
        gatewayRef: text(binding.gatewayRef, 192),
        qualification: "CONFIGURED_NOT_LIVE_VERIFIED" as const,
      });
    },
  );
  if (
    !Array.isArray(value.projectBindings) ||
    value.projectBindings.length > 256
  )
    fail();
  const projectBindings = (value.projectBindings as unknown[]).map(
    (rawBinding) => {
      const binding = object(rawBinding),
        workRef = text(binding.workRef, 132);
      if (!/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(workRef)) fail();
      return Object.freeze({ projectId: id(binding.projectId), workRef });
    },
  );
  const item = value.item === null ? null : record(value.item);
  if (selected.itemId && (!item || item.id !== selected.itemId)) fail();
  let receipt: CompanyReceipt | undefined;
  if (selected.view === "receipt") {
    const source = object(value.receipt);
    if (
      source.requestId !== selected.requestId ||
      !["SAVED", "EFFECT_UNKNOWN"].includes(String(source.state)) ||
      source.retryAllowed !== false
    )
      fail();
    receipt = Object.freeze({
      requestId: id(source.requestId),
      state: source.state as CompanyReceipt["state"],
      code: text(source.code, 96),
      item: source.item === null ? null : record(source.item),
      candidates: records(source.candidates, 5),
      retryAllowed: false,
    });
    if (receipt.state === "SAVED" && receipt.item === null) fail();
    if (receipt.item) id(receipt.item.id);
    receipt.candidates.forEach((row) => id(row.id));
  }
  let migration: RuntimeMigration | undefined;
  if (selected.view === "runtime") {
    const source = object(value.migration);
    if (
      source.schema !== "mastermind.paperclip_hermes_migration.v1" ||
      source.agentId !== selected.itemId ||
      source.companyId !== company.id ||
      source.state !== "PREPARED_NOT_APPLIED" ||
      source.applyAvailable !== false ||
      source.executionRequested !== false ||
      source.targetAdapter !== "hermes_gateway" ||
      source.workSessionStrategy !== "issue" ||
      source.configurationCas !== "NOT_SUPPORTED_BY_PINNED_AGENT_PATCH"
    )
      fail();
    const strings = (raw: unknown) => {
      if (!Array.isArray(raw) || raw.length > 32) return fail();
      return Object.freeze(raw.map((item) => text(item, 192)));
    };
    migration = Object.freeze({
      state: "PREPARED_NOT_APPLIED",
      agentId: id(source.agentId),
      profileRef:
        source.profileRef === null ? null : text(source.profileRef, 192),
      gatewayRef:
        source.gatewayRef === null ? null : text(source.gatewayRef, 192),
      supervisorSessionRef:
        source.supervisorSessionRef === null
          ? null
          : text(source.supervisorSessionRef, 192),
      targetAdapter: "hermes_gateway",
      workSessionStrategy: "issue",
      configurationCas: "NOT_SUPPORTED_BY_PINNED_AGENT_PATCH",
      requirements: strings(source.requirements),
      retain: strings(source.retain),
      replace: strings(source.replace),
      applyAvailable: false,
    });
  }
  const observedAt = text(value.observedAt, 64);
  if (!Number.isFinite(Date.parse(observedAt))) fail();
  const snapshot: CompanySnapshot = Object.freeze({
    schema: COMPANY_SCHEMA,
    state: value.state as CompanySnapshot["state"],
    view: selected.view,
    company,
    bindingRevision: scope(value.bindingRevision),
    scopeKey: scope(value.scopeKey),
    observedAt,
    sourceRevision:
      value.sourceRevision === null ? null : text(value.sourceRevision, 40),
    qualifiedRevision: text(value.qualifiedRevision, 40),
    capabilities: Object.freeze(value.capabilities as "create_backlog"[]),
    collections: Object.freeze(decoded),
    item,
    ownership: Object.freeze(
      ownership,
    ) as unknown as CompanySnapshot["ownership"],
    runtimeBindings: Object.freeze(runtimeBindings),
    projectBindings: Object.freeze(projectBindings),
    ...(receipt ? { receipt } : {}),
    ...(migration ? { migration } : {}),
  });
  const connections = projectCompanyConnections(snapshot);
  if (value.connections !== undefined && !sameConnections(value.connections, connections)) fail();
  return Object.freeze({ ...snapshot, connections });
}
export function decodeBacklogResult(
  raw: unknown,
  request: BacklogRequest,
  expectedScope: string,
  expectedCompany: string,
): BacklogResult {
  const value = object(raw);
  if (
    value.schema !== COMPANY_COMMAND_SCHEMA ||
    value.operation !== request.operation ||
    value.requestId !== request.requestId ||
    value.bindingRevision !== request.bindingRevision ||
    value.retryAllowed !== false ||
    !["SAVED", "NOT_APPLIED", "EFFECT_UNKNOWN"].includes(String(value.state))
  )
    fail();
  if (
    value.state === "SAVED" &&
    (value.scopeKey !== expectedScope ||
      value.companyId !== expectedCompany ||
      value.executionRequested !== false)
  )
    fail();
  if (value.state === "SAVED") {
    const item = record(value.item);
    id(item.id);
    if (item.title !== request.title) fail();
  }
  return Object.freeze({
    schema: COMPANY_COMMAND_SCHEMA,
    state: value.state as BacklogResult["state"],
    operation: "create_backlog",
    requestId: request.requestId,
    bindingRevision: request.bindingRevision,
    retryAllowed: false,
    ...(value.state === "SAVED"
      ? {
          scopeKey: expectedScope,
          companyId: expectedCompany,
          item: record(value.item),
        }
      : { code: text(value.code, 96) }),
  });
}
