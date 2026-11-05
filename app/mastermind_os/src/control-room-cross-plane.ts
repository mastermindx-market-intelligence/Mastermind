/** Bounded read-only projection of an installed, source-authorized Session Truth view.
 * The app never acquires owners, infers links, or upgrades a PR/Linear status to liveness.
 */

export type CrossPlaneCard = Readonly<{
  workstream: string;
  pullRequests: readonly Readonly<{
    repository: string;
    number: number;
    delivery: string;
    ci: string;
    declaredCompletion: string | null;
    proofState: string | null;
    linkedIssue: string | null;
  }>[];
  issues: readonly Readonly<{ issueId: string; status: string }>[];
}>;

export type CrossPlaneRead =
  | Readonly<{ state: "UNAVAILABLE"; reason: "NOT_INSTALLED" | "SOURCE_UNAVAILABLE" }>
  | Readonly<{
      state: "AVAILABLE";
      viewState: "CONSUMED" | "DEGRADED";
      observedAt: string | null;
      digestVerified: boolean;
      unknownCount: number;
      unavailableCount: number;
      cards: readonly CrossPlaneCard[];
    }>;

const ROOT_FIELDS = ["schema", "state", "reason_code", "document"] as const;
const DOCUMENT_FIELDS = [
  "schema", "state", "evaluated_at", "stale_after_seconds", "source_receipt",
  "execution", "admission", "finding_counts", "unavailable_sources",
  "digest_check", "cards", "unattributed_findings", "unknowns", "capability",
] as const;
const record = (x: unknown): x is Record<string, unknown> =>
  x !== null && typeof x === "object" && !Array.isArray(x);
const exact = (x: Record<string, unknown>, fields: readonly string[]) =>
  Object.keys(x).length === fields.length && fields.every((k) => Object.hasOwn(x, k));
const bounded = (x: unknown, max: number): x is string =>
  typeof x === "string" && x.length > 0 && x.length <= max;
const timestamp = (x: unknown): x is string =>
  bounded(x, 40) &&
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(x) &&
  Number.isFinite(Date.parse(x));
const invalid = (): never => { throw new Error("CONTROL_ROOM_CROSS_PLANE_INVALID"); };
const array = (x: unknown, max: number): x is unknown[] => Array.isArray(x) && x.length <= max;
const issueId = (x: unknown): x is string => bounded(x, 32) && /^MAS-[0-9]+$/.test(x);

export function decodeCrossPlaneRead(raw: unknown): CrossPlaneRead {
  // Existing seven-field Control Room payloads remain valid, but a missing
  // feature is visible as NOT_INSTALLED rather than healthy/zero drift.
  if (raw === undefined) return Object.freeze({ state: "UNAVAILABLE", reason: "NOT_INSTALLED" });
  if (!record(raw) || !exact(raw, ROOT_FIELDS) ||
      raw.schema !== "mastermind.control_room_cross_plane_read.v1") return invalid();
  if (raw.state === "UNAVAILABLE") {
    if (raw.reason_code !== "source_unavailable" || raw.document !== null) return invalid();
    return Object.freeze({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
  }
  if (raw.state !== "AVAILABLE" || raw.reason_code !== null || !record(raw.document)) return invalid();
  const doc = raw.document;
  if (!exact(doc, DOCUMENT_FIELDS) || doc.schema !== "mastermind.executive_cross_plane_view.v1" ||
      (doc.state !== "CONSUMED" && doc.state !== "DEGRADED") ||
      !(doc.evaluated_at === null || timestamp(doc.evaluated_at)) ||
      !record(doc.capability) || doc.capability.read_only !== true || doc.capability.effect !== "NONE" ||
      !record(doc.execution) || doc.execution.state !== "NOT_PROJECTED" ||
      !record(doc.source_receipt) || !array(doc.cards, 32) ||
      !array(doc.unknowns, 128) || !array(doc.unavailable_sources, 16) ||
      !array(doc.unattributed_findings, 128) ||
      !(doc.digest_check === null || record(doc.digest_check))) return invalid();
  const cards: CrossPlaneCard[] = doc.cards.map((row) => {
    if (!record(row) || !bounded(row.workstream, 64) ||
        !/^WS:[A-Z0-9][A-Z0-9-]*$/.test(row.workstream) ||
        !record(row.github) || !array(row.github.pull_requests, 64) ||
        !record(row.linear) || !array(row.linear.issues, 64)) return invalid();
    const pullRequests = row.github.pull_requests.map((pr) => {
      if (!record(pr) || !bounded(pr.repository, 160) ||
          !/^[^/\s]+\/[^/\s]+$/.test(pr.repository) ||
          !Number.isSafeInteger(pr.number) || (pr.number as number) <= 0 ||
          !record(pr.delivery) || !bounded(pr.delivery.state, 48) ||
          !bounded(pr.delivery.ci, 48) || !record(pr.proof) ||
          !(pr.proof.declared_completion === null || bounded(pr.proof.declared_completion, 80)) ||
          !(pr.proof.proof_state === null || bounded(pr.proof.proof_state, 80)) ||
          !(pr.linked_linear_issue_id === null || issueId(pr.linked_linear_issue_id))) return invalid();
      return Object.freeze({
        repository: pr.repository as string, number: pr.number as number,
        delivery: pr.delivery.state as string, ci: pr.delivery.ci as string,
        declaredCompletion: pr.proof.declared_completion as string | null,
        proofState: pr.proof.proof_state as string | null,
        linkedIssue: pr.linked_linear_issue_id as string | null,
      });
    });
    const issues = row.linear.issues.map((issue) => {
      if (!record(issue) || !issueId(issue.issue_id) || !bounded(issue.status, 80)) return invalid();
      return Object.freeze({ issueId: issue.issue_id, status: issue.status as string });
    });
    return Object.freeze({
      workstream: row.workstream as string,
      pullRequests: Object.freeze(pullRequests), issues: Object.freeze(issues),
    });
  });
  return Object.freeze({
    state: "AVAILABLE", viewState: doc.state,
    observedAt: doc.evaluated_at as string | null,
    digestVerified: record(doc.digest_check) && doc.digest_check.state === "VERIFIED",
    unknownCount: doc.unknowns.length, unavailableCount: doc.unavailable_sources.length,
    cards: Object.freeze(cards),
  });
}
