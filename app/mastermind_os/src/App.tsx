import type { AuthState, MissionHost } from "./host";
import type {
  ObservedMissionAssociation,
  WindowDocument,
} from "./workspace-contract";
import { observedMissionAssociation } from "./workspace-contract";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { MetaCeoOffice } from "./meta-ceo/MetaCeoOffice";
import { useOfficeProjection } from "./meta-ceo/useOfficeProjection";
import { Projects } from "./projects/Projects";
import { Inbox } from "./inbox/Inbox";
import { Knowledge } from "./knowledge/Knowledge";
import { ConversationWindow } from "./conversations/ConversationWindow";
import { useObservedConversation } from "./conversations/useObservedConversation";
import {
  OperationController,
  type OperationKind,
  type OperationState,
} from "./orchestration/operation-controller";
import {
  LaunchOrchestrator,
  type LaunchForm,
} from "./orchestration/ui/LaunchOrchestrator";
import { SessionWorkspace } from "./orchestration/ui/SessionWorkspace";
import {
  COMMAND_ROUTE_UNAVAILABLE,
  completeOrchestratorCommandBinding,
  launchIntentFromBinding,
  messageIntentFromBinding,
  readCommandView,
  readOwnerContext,
  sessionMatchesSelection,
  stopIntentFromBinding,
  subscribeCommandView,
  type OrchestratorCommandBinding,
} from "./orchestration/host-command-bindings";
import {
  allEvidence,
  decodeMission,
  decodeMissionv3,
  locationSelectionInput,
  normalizeSelection,
  programsFromControlRoom,
  relationshipsForMission,
  selectionFromLocation,
  unavailableMission,
  type MissionDocument,
  type MissionSelection,
  type Missionv3Document,
  type UnavailableMission,
} from "./mission";
import {
  decodeResultEnvelope,
  normalizeResultSelection,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "./result";
import {
  decodeWorkDocument,
  WORK_GROUP_ORDER,
  type WorkDocument,
} from "./work";
export const navigation = [
  "Today",
  "Projects",
  "Inbox",
  "Conversations",
  "Knowledge",
  "Work",
  "Programs",
  "Fleet & Capacity",
  "Mission Workspace",
  "Conversation",
  "Activity",
  "Connections",
  "Evidence",
] as const;
type View = (typeof navigation)[number];
const primaryNavigation: readonly View[] = [
  "Today",
  "Projects",
  "Inbox",
  "Conversations",
  "Knowledge",
];
type OperationalView = "Work" | "Programs" | "Fleet & Capacity";
function OperationalNavigation({ label, onNavigate }: {
  label: string;
  onNavigate: (view: OperationalView) => void;
}) {
  return (
    <nav className="card" aria-label={label}>
      <div className="segmented">
        <button type="button" onClick={() => onNavigate("Work")}>Work</button>
        <button type="button" onClick={() => onNavigate("Programs")}>Open Programs</button>
        <button type="button" onClick={() => onNavigate("Fleet & Capacity")}>Fleet &amp; Capacity</button>
      </div>
    </nav>
  );
}
const missionNavigation: readonly View[] = [
  "Mission Workspace",
  "Conversation",
  "Activity",
  "Connections",
  "Evidence",
];
const projectTabs = ["Overview", "Plan", "Work", "Evidence", "More"] as const;
type ProjectTab = (typeof projectTabs)[number];
const navGlyph: Record<View, string> = {
  Today: "⌂",
  Projects: "◫",
  Inbox: "▤",
  Conversations: "◌",
  Knowledge: "□",
  Work: "▤",
  Programs: "◫",
  "Fleet & Capacity": "◇",
  "Mission Workspace": "◎",
  Conversation: "◌",
  Activity: "↯",
  Connections: "⌘",
  Evidence: "□",
};
interface BuildReceipt {
  version: string;
  source_revision: string;
  build_identity: string;
  transport: string;
  state: string;
  native_client_ref?: string | null;
}
declare global {
  interface Window {
    MastermindMissionHost?: MissionHost;
  }
}
type ProgramIndex =
  | ReturnType<typeof programsFromControlRoom>
  | { programs: []; state: "PENDING"; reason: "SOURCE_READ_PENDING" };
type WorkState =
  | { kind: "PENDING" }
  | { kind: "DOCUMENT"; document: WorkDocument }
  | { kind: "UNAVAILABLE"; reason: string };
const display = (v: unknown, f = "Not established") =>
  typeof v === "string" && v ? v : f;
const label = (v: unknown) => display(v, "UNKNOWN").replaceAll("_", " ");
const isDoc = (v: MissionDocument | UnavailableMission): v is MissionDocument =>
  !("kind" in v);
const isDocv3 = (
  v: Missionv3Document | UnavailableMission | null,
): v is Missionv3Document => !!v && !("kind" in v);
function State({ value }: { value: unknown }) {
  return (
    <span className={`state state-${String(value ?? "UNKNOWN").toLowerCase()}`}>
      {label(value)}
    </span>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

function WorkQueue({
  state,
  rootJobId = null,
}: {
  state: WorkState;
  rootJobId?: string | null;
}) {
  if (state.kind === "PENDING")
    return (
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              Company-wide lifecycle and next-action ownership from the bounded
              Executive projection.
            </p>
          </div>
          <State value="SOURCE_READ_PENDING" />
        </div>
        <Empty>Reading the bounded Work projection…</Empty>
      </section>
    );
  if (state.kind === "UNAVAILABLE")
    return (
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              The fixed Work read did not return a qualified document.
            </p>
          </div>
          <State value="UNAVAILABLE" />
        </div>
        <p>Work source unavailable. This is not evidence of zero work.</p>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>{state.reason}</code>
        </details>
      </section>
    );

  const doc = state.document;
  if (doc.availability === "UNAVAILABLE")
    return (
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              The canonical Work owner returned a typed refusal document.
            </p>
          </div>
          <State value="UNAVAILABLE" />
        </div>
        <p>
          Work is unavailable in this observation. This is not evidence of zero
          work.
        </p>
        <p className="muted">
          Coverage is partial by contract; no empty queue or ownership all-clear
          is inferred.
        </p>
        <details className="reason-details" open>
          <summary>Technical details</summary>
          <code>{doc.reason_codes.join(", ") || "source_unavailable"}</code>
        </details>
      </section>
    );

  return (
    <div className="today-view">
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Work</h2>
            <p className="muted">
              Read-only company work projection. Lifecycle, ownership, capacity,
              effects and acceptance stay separate.
            </p>
          </div>
          <State value={doc.availability} />
        </div>
        <p className="muted">
          {rootJobId
            ? `Exact project root ${rootJobId}; other roots remain outside this project view.`
            : `${doc.coverage.count} of ${doc.coverage.total ?? "unknown"} roots observed · ${label(doc.coverage.completeness)}${doc.coverage.truncated ? " · truncated" : ""}`}
        </p>
        <p className="muted">
          Queue effect <b>{label(doc.effect_exception.value)}</b> ·{" "}
          {label(doc.effect_exception.reason)}
        </p>
      </section>
      <div className="today-grid">
        {WORK_GROUP_ORDER.map((group) => {
          const rows = rootJobId
            ? doc.groups[group].filter((row) => row.root_job_id === rootJobId)
            : doc.groups[group];
          return (
            <section className="card" key={group}>
              <div className="section-title">
                <div>
                  <h2>{label(group)}</h2>
                  <p className="muted">
                    {rows.length} roots in this qualified group
                  </p>
                </div>
              </div>
              {rows.length === 0 ? (
                <Empty>No roots were projected into this group.</Empty>
              ) : (
                <ul className="items">
                  {rows.map((row) => (
                    <li key={row.root_job_id}>
                      <div>
                        <code>{row.root_job_id}</code>
                        <State value={row.lifecycle.status} />
                      </div>
                      <span>
                        Next actor <b>{label(row.next_actor.value)}</b> ·
                        Capacity <b>{label(row.capacity.value)}</b>
                      </span>
                      <small>
                        Effect {label(row.effect.value)} · Acceptance{" "}
                        {label(row.acceptance.state)}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}

function ResultRefs({
  d,
  onPick,
  selectedKey,
  disabled,
}: {
  d: Missionv3Document;
  onPick: (selection: ResultSelection) => void;
  selectedKey: string | null;
  disabled: boolean;
}) {
  const index = d.result_refs;
  return (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>Result navigation</h2>
          <p className="muted">
            Unvalidated navigation from the bounded Mission v3 reference index.
            Each row identifies exactly one tuple; this view never constructs a
            URL or command outside the fixed selection.
          </p>
        </div>
        <State value={index.availability} />
      </div>
      <p className="muted index-summary">
        <span>{index.refs.length} result refs</span>
        <span>{index.absent_job_ids.length} absent</span>
        <span>{index.omitted_job_ids.length} omitted</span>
      </p>
      {index.availability === "UNAVAILABLE" ? (
        <Empty>
          No result index was published for this Mission v3 selection.
        </Empty>
      ) : index.refs.length === 0 && index.absent_job_ids.length === 0 ? (
        <Empty>
          No qualifying result references were returned by the bounded
          same-snapshot index. No result history is implied.
        </Empty>
      ) : (
        <ul className="items">
          {index.refs.map((ref) => {
            const key = `${ref.job_id}|${ref.attempt_id}|${ref.result_envelope_digest}`;
            const sel: ResultSelection = {
              workRef: d.program.work_ref,
              rootJobId: ref.root_job_id,
              jobId: ref.job_id,
              attemptId: ref.attempt_id,
              resultEnvelopeDigest: ref.result_envelope_digest,
            };
            return (
              <li key={key}>
                <button
                  className={key === selectedKey ? "selected" : ""}
                  onClick={() => onPick(sel)}
                  disabled={disabled}
                >
                  <code>{ref.job_id}</code>
                  <span>{label(ref.orchestration_role)}</span>
                  <small>attempt {ref.attempt_id}</small>
                  <small>
                    digest {ref.result_envelope_digest.slice(0, 12)}…
                  </small>
                </button>
              </li>
            );
          })}
          {index.absent_job_ids.map((jobId) => (
            <li key={`absent-${jobId}`}>
              <code>{jobId}</code>
              <span>absent</span>
              <small>No result was emitted for this job in the snapshot.</small>
            </li>
          ))}
        </ul>
      )}
      {(index.omitted_job_ids.length > 0 || index.truncated) && (
        <p className="muted">
          Omitted IDs:{" "}
          {index.omitted_job_ids.length > 0
            ? index.omitted_job_ids.map(label).join(", ")
            : "none reported"}
          {index.truncated ? " · owner snapshot was truncated" : ""}
        </p>
      )}
    </section>
  );
}

type ResultState =
  | { kind: "IDLE" }
  | { kind: "PENDING"; selection: ResultSelection }
  | {
      kind: "READY";
      selection: ResultSelection;
      document: ResultEnvelopeDigestShape;
    }
  | { kind: "UNAVAILABLE"; selection: ResultSelection; reason: string };

function ResultCard({ state }: { state: ResultState }) {
  if (state.kind === "IDLE") return null;
  const title =
    state.selection.jobId + " / " + state.selection.attemptId.slice(0, 8) + "…";
  if (state.kind === "PENDING") {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value="SOURCE_READ_PENDING" />
        </div>
        <p className="muted">Reading the exact selected tuple…</p>
        <code>{title}</code>
      </section>
    );
  }
  if (state.kind === "UNAVAILABLE") {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value="UNAVAILABLE" />
        </div>
        <p className="muted">{state.reason}</p>
        <code>{title}</code>
      </section>
    );
  }
  const doc = state.document;
  const result = doc.result;
  if (doc.availability === "UNAVAILABLE" || !result) {
    return (
      <section className="card">
        <div className="section-title">
          <h2>Result detail</h2>
          <State value={doc.availability} />
        </div>
        <p className="muted">
          The bounded result read returned a typed unavailability response:{" "}
          <code>{doc.reason_codes[0] ?? "SOURCE_UNAVAILABLE"}</code>. This is
          not a producer acceptance and adds no result history.
        </p>
        <code>{title}</code>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>
            {(doc.reason_codes[0] ?? "SOURCE_UNAVAILABLE") +
              " · selection " +
              doc.selection.work_ref +
              " / " +
              doc.selection.root_job_id +
              " / " +
              doc.selection.job_id +
              " / " +
              doc.selection.attempt_id +
              " / " +
              doc.selection.result_envelope_digest}
          </code>
        </details>
      </section>
    );
  }
  const counts = result.counts.findings;
  const review = result.review;
  const verdictLabel =
    review === null
      ? "Not a review role"
      : "Review verdict: " +
        label(review.verdict) +
        " · latest revision UNPROVEN";
  return (
    <section className="card">
      <div className="section-title">
        <h2>Result detail</h2>
        <State value={doc.availability} />
      </div>
      {doc.availability !== "AVAILABLE" ? (
        <p className="muted">
          <code>{doc.reason_codes.join(" · ")}</code>
        </p>
      ) : null}
      <dl>
        <dt>Role</dt>
        <dd>{label(result.role)}</dd>
        <dt>Execution</dt>
        <dd>{label(result.execution_status)}</dd>
        <dt>Acceptance</dt>
        <dd>
          <State value={result.acceptance} />
        </dd>
        <dt>Review</dt>
        <dd>{review === null ? "Not a review role" : verdictLabel}</dd>
        <dt>Findings</dt>
        <dd>
          {counts === null
            ? "No findings tracked for this role"
            : `Total ${counts.total} · blocking ${counts.blocking} · warning ${counts.warning} · info ${counts.info}`}
        </dd>
        <dt>Next actions</dt>
        <dd>
          {result.counts.next_actions === 0
            ? "None reported"
            : `${result.counts.next_actions} item(s)`}
        </dd>
        <dt>Envelope digest</dt>
        <dd>
          <code>{result.selection.result_envelope_digest}</code>
        </dd>
        {review ? (
          <>
            <dt>Reviewed job and attempt</dt>
            <dd>
              <code>
                {review.reviewed_job_id} · {review.reviewed_attempt_id}
              </code>
            </dd>
            <dt>Reviewed role-result digest</dt>
            <dd>
              <code>{review.reviewed_result_digest}</code>
            </dd>
          </>
        ) : null}
        <dt>Role-result digest</dt>
        <dd>
          <code>{result.role_result_digest}</code>
        </dd>
        <dt>Selection</dt>
        <dd>
          <code>
            {result.selection.root_job_id +
              " · " +
              result.selection.job_id +
              " · " +
              result.selection.attempt_id}
          </code>
        </dd>
        <dt>Omitted</dt>
        <dd>
          {result.omitted.length === 0
            ? "Whole content shown for this role."
            : result.omitted.map((x) => label(x)).join(" · ")}
        </dd>
      </dl>
      {result.content === null ? (
        <Empty>
          Content omitted by owner. Counts and digests remain, but the full role
          result body was not delivered within the bounded response. A full
          result link is not provided.
        </Empty>
      ) : (
        <article className="result-content">
          <h3>Structured role result</h3>
          <pre className="visible-text">
            {JSON.stringify(result.content.role_result, null, 2)}
          </pre>
          <h3>Summary</h3>
          <pre className="visible-text">{result.content.summary}</pre>
          {result.content.next_actions.length > 0 ? (
            <>
              <h3>Next actions</h3>
              <ul className="artifact-list">
                {result.content.next_actions.map((x, i) => (
                  <li key={`na-${i}`}>{x}</li>
                ))}
              </ul>
            </>
          ) : null}
        </article>
      )}
    </section>
  );
}
function Mission({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="hero">
        <div>
          <span className="eyebrow">PROGRAM</span>
          <h2>{d.program.title || d.program.work_ref}</h2>
          <p>
            {display(
              d.program.next_action,
              "No next action was projected by the source.",
            )}
          </p>
        </div>
        <div className="facts">
          <div>
            <small>MISSION ROOT</small>
            <code>
              {display(
                d.mission.root_job_id,
                d.mission.runtime_root_state === "CONFLICT"
                  ? "Conflict; no root selected"
                  : "Unknown; no root selected",
              )}
            </code>
          </div>
          <div>
            <small>RUNTIME ROOT STATE</small>
            <State value={d.mission.runtime_root_state} />
          </div>
          <div>
            <small>EXECUTION</small>
            <State value={d.execution.state} />
          </div>
        </div>
      </section>
      <div className="grid">
        <section className="card">
          <div className="section-title">
            <h2>Mission</h2>
            <State value={d.mission.status} />
          </div>
          <dl>
            <dt>Role</dt>
            <dd>{display(d.mission.orchestration_role)}</dd>
            <dt>Capability</dt>
            <dd>
              <State value={d.mission.capability.state} />
            </dd>
            <dt>Submission</dt>
            <dd>
              <State value={d.mission.submission_availability} />
            </dd>
          </dl>
        </section>
        <section className="card">
          <div className="section-title">
            <h2>Principal</h2>
            <State value={d.transport.dispatch_state} />
          </div>
          <dl>
            <dt>Accountable seat</dt>
            <dd>{display(d.principal.accountable_seat)}</dd>
            <dt>Current worker</dt>
            <dd>
              {display(
                d.principal.current_worker?.worker_id ??
                  d.principal.current_worker?.attempt_id,
              )}
            </dd>
            <dt>Owed turn</dt>
            <dd>
              {d.principal.owed_turn
                ? `${display(d.principal.owed_turn.seat)} · ${display(
                    d.principal.owed_turn.reason,
                  )}`
                : "Not established"}
            </dd>
            <dt>Transport</dt>
            <dd>{display(d.transport.reason)}</dd>
          </dl>
        </section>
        <section className="card">
          <div className="section-title">
            <h2>Review and acceptance</h2>
            <State value={d.acceptance.state} />
          </div>
          <dl>
            <dt>Execution</dt>
            <dd>
              <State value={d.execution.state} />
            </dd>
            <dt>Review</dt>
            <dd>
              <State value={d.review.verdict} />
            </dd>
            <dt>Transport</dt>
            <dd>
              <State value={d.transport.dispatch_state} />
            </dd>
            <dt>Acceptance</dt>
            <dd>
              <State value={d.acceptance.state} />
            </dd>
            <dt>Posture</dt>
            <dd>
              <State value={d.posture.value} />
            </dd>
            <dt>Rule</dt>
            <dd>{display(d.posture.rule)}</dd>
          </dl>
        </section>
      </div>
      <section className="card">
        <div className="section-title">
          <h2>Mission tree</h2>
          <State value={d.children.state} />
        </div>
        <p className="muted">
          {d.children.coverage === "INCOMPLETE"
            ? "Known-subset evidence; the complete tree is not established."
            : d.children.reason_codes.join(" · ") ||
              "Complete source coverage."}
        </p>
        <div className="unjoined" aria-label="Unjoined jobs">
          <b>Unjoined jobs</b>
          <span>
            {d.children.unjoined_job_count === null
              ? "Count unknown"
              : `${d.children.unjoined_job_count} reported`}
          </span>
          {d.children.unjoined_job_ids.length ? (
            <ul>
              {d.children.unjoined_job_ids.map((id) => (
                <li key={id}>
                  <code>{id}</code>
                </li>
              ))}
            </ul>
          ) : d.children.unjoined_job_count === 0 ? (
            <small>No unjoined job IDs were reported.</small>
          ) : (
            <small>No bounded unjoined identities were projected.</small>
          )}
        </div>
        {d.children.items.length ? (
          <ul className="items">
            {d.children.items.map((x, index) => (
              <li key={x.job_id ?? `unidentified-child-${index}`}>
                <code>{display(x.job_id, "Unidentified child")}</code>
                <span>{label(x.status)}</span>
                <small>
                  {display(x.orchestration_role)} · parent{" "}
                  {display(x.parent_job_id)} · attempt{" "}
                  {x.latest_attempt?.status ?? "not established"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            No items are rendered. This is not evidence of zero work.
          </Empty>
        )}
      </section>
    </>
  );
}
function Activity({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="card activity-summary">
        <div className="section-title">
          <div>
            <h2>Activity</h2>
            <p className="muted">
              The same admitted Mission document, organized by current work
              posture. Opening this view performs no extra read and starts no
              work.
            </p>
          </div>
          <State value={d.execution.state} />
        </div>
        <div className="activity-facts">
          <div>
            <small>EXECUTION</small>
            <State value={d.execution.state} />
          </div>
          <div>
            <small>REVIEW</small>
            <State value={d.review.verdict} />
          </div>
          <div>
            <small>TRANSPORT</small>
            <State value={d.transport.dispatch_state} />
          </div>
          <div>
            <small>ACCEPTANCE</small>
            <State value={d.acceptance.state} />
          </div>
          <div>
            <small>POSTURE</small>
            <State value={d.posture.value} />
          </div>
        </div>
      </section>
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Live work</h2>
            <p className="muted">
              Canonical child facts from this Mission snapshot. Missing joins
              remain missing; a row is never promoted to running from UI state.
            </p>
          </div>
          <State value={d.children.state} />
        </div>
        {d.children.items.length ? (
          <ul className="items activity-items">
            {d.children.items.map((item, index) => (
              <li key={item.job_id ?? `unidentified-activity-${index}`}>
                <code>{display(item.job_id, "Unidentified child")}</code>
                <State value={item.status} />
                <small>
                  {display(item.orchestration_role)} · attempt{" "}
                  {item.latest_attempt?.status ?? "not established"}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            No bounded child rows are available. This is not evidence of zero
            work.
          </Empty>
        )}
        <p className="muted">
          {d.children.coverage === "INCOMPLETE"
            ? "Coverage is incomplete; known rows are not the complete queue."
            : "The owner reported complete child coverage for this observation."}
        </p>
      </section>
    </>
  );
}

function Connections({ d }: { d: MissionDocument }) {
  const rs = useMemo(() => relationshipsForMission(d), [d]),
    [mode, setMode] = useState<"graph" | "list">("graph"),
    [selected, setSelected] = useState(rs[0]?.id ?? null),
    focus = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (selected && !rs.some((x) => x.id === selected))
      setSelected(rs[0]?.id ?? null);
  }, [rs, selected]);
  useEffect(() => {
    if (selected) focus.current?.focus();
  }, [mode, selected]);
  const button = (rel: (typeof rs)[number]) => (
    <button
      ref={rel.id === selected ? focus : undefined}
      className={rel.id === selected ? "selected" : ""}
      onClick={() => setSelected(rel.id)}
    >
      <code>{rel.from}</code>
      <span>contains</span>
      <code>{rel.to}</code>
      <small>{rel.kind}</small>
    </button>
  );
  return (
    <section className="card connections">
      <div className="section-title">
        <div>
          <h2>Connections</h2>
          <p className="muted">
            One source-derived model. It adds no graph authority.
          </p>
        </div>
        <div
          className="segmented"
          role="group"
          aria-label="Connection presentation"
        >
          <button
            onClick={() => setMode("graph")}
            aria-pressed={mode === "graph"}
          >
            Graph
          </button>
          <button
            onClick={() => setMode("list")}
            aria-pressed={mode === "list"}
          >
            List
          </button>
        </div>
      </div>
      {rs.length === 0 ? (
        <Empty>
          No joined relationships are available. Missing joins remain gaps.
        </Empty>
      ) : mode === "graph" ? (
        <div className="relation-graph" role="list">
          {rs.map((rel) => (
            <div role="listitem" key={rel.id}>
              {button(rel)}
            </div>
          ))}
        </div>
      ) : (
        <ul className="relationship-list">
          {rs.map((rel) => (
            <li key={rel.id}>{button(rel)}</li>
          ))}
        </ul>
      )}
      <p className="selection-note" aria-live="polite">
        {selected
          ? `Selected relationship: ${selected}`
          : "No relationship selected."}
      </p>
    </section>
  );
}
function Evidence({ d }: { d: MissionDocument }) {
  const refs = allEvidence(d);
  return (
    <>
      <section className="card">
        <div className="section-title">
          <h2>Evidence</h2>
          <State value={d.read_state.state} />
        </div>
        <dl>
          <dt>Projection created</dt>
          <dd>
            {d.generated_at ? (
              <time dateTime={d.generated_at}>{d.generated_at}</time>
            ) : (
              "Unavailable"
            )}
          </dd>
          <dt>Control Room source</dt>
          <dd>{display(d.source.control_room_generated_at)}</dd>
          <dt>Fabric source</dt>
          <dd>{display(d.source.fabric_view_generated_at)}</dd>
        </dl>
        <div className="generation">
          <h3>Source generations</h3>
          {Object.entries(d.source.source_generation).length ? (
            <ul>
              {Object.entries(d.source.source_generation).map(([k, v]) => (
                <li key={k}>
                  <code>{k}</code>
                  <span>{String(v)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Empty>No generation receipt was projected.</Empty>
          )}
        </div>
      </section>
      <section className="card">
        <h2>Qualified evidence references</h2>
        {refs.length ? (
          <ul className="evidence-list">
            {refs.map(({ facet, evidence }, i) => (
              <li key={`${facet}-${evidence.ref}-${i}`}>
                <div>
                  <b>{facet}</b>
                  <State value={evidence.freshness_state} />
                </div>
                <code>
                  {evidence.owner} · {evidence.ref} · {evidence.field}
                </code>
                <small>
                  Source time: {display(evidence.source_time)} · observed:{" "}
                  {display(evidence.observed_at)} · revision:{" "}
                  {display(evidence.source_revision)}
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>No qualified evidence tuples were projected.</Empty>
        )}
      </section>
      <section className="card">
        <h2>Artifacts and next actions</h2>
        {d.execution.artifacts.length ? (
          <ul className="artifact-list">
            {d.execution.artifacts.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : (
          <Empty>No allowlisted artifact reference was projected.</Empty>
        )}
        {d.execution.next_actions.length ? (
          <ul className="artifact-list">
            {d.execution.next_actions.map((x, i) => (
              <li key={i}>{x}</li>
            ))}
          </ul>
        ) : null}
      </section>
    </>
  );
}

function ProjectTabs({
  active,
  onChange,
}: {
  active: ProjectTab;
  onChange: (tab: ProjectTab) => void;
}) {
  return (
    <nav className="card" aria-label="Project sections">
      <div className="segmented" role="tablist" aria-label="Project workspace">
        {projectTabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={active === tab}
            onClick={() => onChange(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
    </nav>
  );
}

function ProjectPlan({ d }: { d: MissionDocument }) {
  return (
    <>
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Plan</h2>
            <p className="muted">
              Agent OS plan content is not projected through the current
              approved app source.
            </p>
          </div>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          This project view does not reconstruct a plan from Mission, Work,
          GitHub, or conversation data. The current Mission context below is
          shown only to preserve continuity while the plan owner is absent.
        </p>
      </section>
      <section className="card">
        <div className="section-title">
          <h2>Current project context</h2>
          <State value={d.read_state.state} />
        </div>
        <dl>
          <dt>Project</dt>
          <dd>{d.program.title || d.program.work_ref}</dd>
          <dt>Next source-qualified action</dt>
          <dd>
            {display(
              d.program.next_action,
              "No next action was projected by the Mission source.",
            )}
          </dd>
          <dt>Accountable seat</dt>
          <dd>{display(d.principal.accountable_seat)}</dd>
          <dt>Owed turn</dt>
          <dd>
            {d.principal.owed_turn
              ? `${display(d.principal.owed_turn.seat)} · ${display(d.principal.owed_turn.reason)}`
              : "Not established"}
          </dd>
        </dl>
      </section>
    </>
  );
}

function ProjectMore({
  d,
  sessionPanel,
  onNavigate,
}: {
  d: MissionDocument;
  sessionPanel: React.ReactNode;
  onNavigate: (view: OperationalView) => void;
}) {
  return (
    <>
      <section className="card">
        <div className="section-title">
          <div>
            <h2>More</h2>
            <p className="muted">
              Sessions, journal, resources and systems stay views over their
              existing owners.
            </p>
          </div>
          <State value={d.read_state.state} />
        </div>
      </section>
      {sessionPanel}
      <OperationalNavigation label="Project operations" onNavigate={onNavigate} />
      <Connections d={d} />
      <section className="card source-gap">
        <div className="section-title">
          <h2>Journal</h2>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          No qualified journal source is installed in this project view. No
          history is inferred.
        </p>
      </section>
      <section className="card source-gap">
        <div className="section-title">
          <h2>Resources &amp; systems</h2>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          Capacity and system health require their canonical owners; project
          selection does not grant access or authority.
        </p>
      </section>
    </>
  );
}
function Conversation({
  document,
  pending,
  refresh,
  selection,
  association,
  contentAvailable,
}: {
  document?: WindowDocument | null;
  pending?: boolean;
  refresh?: () => void;
  selection?: MissionSelection | null;
  association?: ObservedMissionAssociation | null;
  contentAvailable?: boolean;
}) {
  const refreshControl = (
    <button onClick={refresh} disabled={!!pending || !contentAvailable}>
      Refresh window
    </button>
  );
  if (document)
    return (
      <section className="card">
        <div className="section-title">
          <h2>
            {association
              ? "Observed window for this Mission"
              : "Unbound current window"}
          </h2>
          <State
            value={association ? "OBSERVED_MISSION_ASSOCIATION" : "UNBOUND"}
          />
        </div>
        {association ? (
          <div className="unjoined" role="note">
            <b>Observed window for this Mission</b>
            <p>
              Job {association.job_id} · Attempt {association.attempt_id}. The
              content owner observed this Job/Attempt and the separately
              authorized Mission owner placed that same current Job/Attempt
              under this selected root. Independent owner observations. This
              display does not prove shared identity, later liveness, complete
              history, terminal acceptance, review approval, or action/result
              correspondence.
            </p>
            <p>
              Window observed at {association.window_observed_at}. Mission
              document generated at{" "}
              {association.mission_generated_at ?? "unavailable"}.
            </p>
          </div>
        ) : (
          <div className="unjoined" role="note">
            <b>NOT_LINKED_TO_SELECTED_MISSION</b>
            <p>
              {selection
                ? `No relationship is proven between this current window and ${selection.workRef} / ${selection.rootJobId}.`
                : "No relationship is proven between this current window and any Mission selection."}
            </p>
          </div>
        )}
        <p className="muted">
          {association
            ? `Coverage ${label(document.view.coverage)}. This window does not establish full history, Mission evidence, action or result correlation, review, or product acceptance.`
            : `Global current permitted turn · observed ${document.view.observed_at} · coverage ${label(document.view.coverage)}. This window does not establish full history, Mission evidence, action or result correlation, review, or product acceptance.`}
        </p>
        {document.view.items.map((item) => (
          <article key={item.id}>
            <State value={item.state} />
            {item.kind === "withheld" ? (
              <Empty>Content withheld by its owner.</Empty>
            ) : (
              <pre className="visible-text">{item.text}</pre>
            )}
          </article>
        ))}
        {document.view.items.length === 0 ? (
          <Empty>
            No visible response was returned in this observed window.
          </Empty>
        ) : null}
        {document.view.gaps.length ? (
          <p className="muted">The source reported gaps in this window.</p>
        ) : null}
        {refreshControl}
      </section>
    );
  return (
    <section className="card">
      <div className="section-title">
        <h2>Conversation</h2>
        <State value={pending ? "SOURCE_READ_PENDING" : "UNAVAILABLE"} />
      </div>
      <p className="muted">
        {window.MastermindMissionHost?.readCurrentWindow
          ? "The current permitted conversation window is unavailable."
          : "This app has no connected conversation source yet."}
      </p>
      <Empty>
        {window.MastermindMissionHost?.readCurrentWindow
          ? "Sign in with permitted conversation access, then open this view again."
          : "No conversation content is shown until a connected source is installed. Existing owner and effect boundaries remain unchanged."}
      </Empty>
      <details className="reason-details">
        <summary>Technical details</summary>
        <code>CONVERSATION_TRANSPORT_UNAVAILABLE</code>
      </details>
      {refreshControl}
    </section>
  );
}

export function App() {
  const native = "__TAURI_INTERNALS__" in window,
    initialLocation = useMemo(() => locationSelectionInput(), []),
    initial = useMemo(
      () =>
        initialLocation.hasIdentity
          ? initialLocation.selection
          : normalizeSelection(window.MastermindMissionHost?.selection),
      [initialLocation],
    ),
    [selection, setSelection] = useState<MissionSelection | null>(initial),
    [active, setActive] = useState<View>("Today"),
    [projectTab, setProjectTab] = useState<ProjectTab | null>(null),
    [index, setIndex] = useState<ProgramIndex>({
      programs: [],
      state: "PENDING",
      reason: "SOURCE_READ_PENDING",
    }),
    [workState, setWorkState] = useState<WorkState>({ kind: "PENDING" }),
    [mission, setMission] = useState<MissionDocument | UnavailableMission>(() =>
      unavailableMission(
        initial,
        initial ? "SOURCE_NOT_READ" : "EXACT_SELECTION_REQUIRED",
      ),
    ),
    [notice, setNotice] = useState("A qualified source has not been read."),
    [build, setBuild] = useState<BuildReceipt | null>(null),
    [authState, setAuthState] = useState<AuthState | null>(
      () => window.MastermindMissionHost?.auth?.getState() ?? null,
    ),
    [authRevision, setAuthRevision] = useState(0),
    [windowDocument, setWindowDocument] = useState<WindowDocument | null>(null),
    [windowPending, setWindowPending] = useState(false),
    [windowRevision, setWindowRevision] = useState(0),
    [association, setAssociation] = useState<ObservedMissionAssociation | null>(
      null,
    ),
    invalidation = useRef(0),
    pairAbort = useRef<AbortController | null>(null),
    selectionSeq = useRef(0),
    commandSlot = useRef<{
      controller: OperationController;
      /** Binding object this controller was created from; identity matters. */
      binding: OrchestratorCommandBinding;
      principalScope: string;
      generation: string;
    } | null>(null),
    pendingCommand = useRef<{
      generation: string;
      principalScope: string;
      /** Binding this pending was dispatched under; identity matters. */
      binding: OrchestratorCommandBinding;
      kind: OperationKind;
      selectionSeq: number;
      complete: (
        outcome: { status: "accepted" } | { status: "refused" },
      ) => void;
    } | null>(null),
    [viewTick, setViewTick] = useState(0),
    [commandStatus, setCommandStatus] = useState<OperationState | null>(null),
    [heldKind, setHeldKind] = useState<OperationKind | null>(null),
    [launchDraftDismissed, setLaunchDraftDismissed] = useState(false),
    // True only while a Check-status recover() is actually in flight. A
    // static checking/PENDING_POINTER hold (a persisted pointer with no
    // recovery promise) is NOT busy — its recovery control stays usable.
    [recoverInFlight, setRecoverInFlight] = useState(false),
    previousAuth = useRef<string | null>(
      authState ? JSON.stringify(authState) : null,
    ),
    previousHostGeneration = useRef(
      window.MastermindMissionHost?.invalidationGeneration?.() ?? 0,
    ),
    bumpInvalidation = () => {
      invalidation.current += 1;
      pairAbort.current?.abort();
    },
    [missionV3, setMissionV3] = useState<
      Missionv3Document | UnavailableMission | null
    >(null),
    [resultState, setResultState] = useState<ResultState>({ kind: "IDLE" }),
    resultRequest = useRef(0),
    missionRequest = useRef(0),
    programRequest = useRef(0),
    programSelection = useRef(selection),
    workRequest = useRef(0),
    missionSelectionState =
      native &&
      !window.MastermindMissionHost?.readPrograms &&
      !window.MastermindMissionHost?.readProgramsObservation
        ? "NATIVE"
        : selection?.workRef !== programSelection.current?.workRef ||
            selection?.rootJobId !== programSelection.current?.rootJobId
          ? "PENDING"
          : index.state,
    selectionRefused =
      index.state === "AVAILABLE" &&
      !!selection &&
      !index.programs.some(
        (program) =>
          program.workRef === selection.workRef &&
          program.rootState === "RESOLVED" &&
          program.rootJobId === selection.rootJobId,
      );
  const office = useOfficeProjection(authRevision, selection);
  const observedConversation = useObservedConversation(
    authRevision,
    selection,
    authState?.content,
  );
  const resultContext = useMemo(
    () => ({ selection, authRevision, missionV3 }),
    [selection, authRevision, missionV3],
  );
  const commandBinding = completeOrchestratorCommandBinding(
    window.MastermindMissionHost?.commandBinding,
  );
  const commandView = commandBinding ? readCommandView(commandBinding) : null;
  void viewTick;
  const signedIn = authState?.status === "signed_in";
  const ownerContext =
    signedIn && commandBinding ? readOwnerContext(commandBinding.port) : null;
  const commandReady = !!commandBinding && signedIn && !!ownerContext;
  const canLaunch =
    commandReady &&
    !!commandView &&
    commandView.projects.length > 0 &&
    commandView.profiles.length > 0;
  const sessionExact =
    commandReady &&
    sessionMatchesSelection(commandView?.session ?? null, selection);
  useEffect(() => {
    if (!commandBinding) return;
    return subscribeCommandView(commandBinding, () =>
      setViewTick((n) => n + 1),
    );
  }, [commandBinding]);
  useEffect(() => {
    if (!commandBinding || !ownerContext) {
      if (commandSlot.current) {
        commandSlot.current.controller.invalidate();
        commandSlot.current = null;
      }
      return;
    }
    const cur = commandSlot.current;
    // One controller per owner epoch AND per binding object: a replaced
    // binding supersedes the route it carried even when the owner context it
    // reports is unchanged, so view churn on the same binding keeps this
    // controller while a swap invalidates it before the next dispatch.
    if (
      cur &&
      cur.principalScope === ownerContext.principalScope &&
      cur.generation === ownerContext.generation &&
      cur.binding === commandBinding
    )
      return;
    if (cur) cur.controller.invalidate();
    commandSlot.current = {
      controller: new OperationController(
        commandBinding.port,
        commandBinding.store,
      ),
      binding: commandBinding,
      principalScope: ownerContext.principalScope,
      generation: ownerContext.generation,
    };
  }, [commandBinding, ownerContext?.principalScope, ownerContext?.generation]);
  const currentResultContext = useRef(resultContext);
  currentResultContext.current = resultContext;
  const resultController = useRef<AbortController | null>(null);
  useEffect(() => {
    resultRequest.current++;
    resultController.current?.abort();
    setResultState({ kind: "IDLE" });
    return () => {
      resultRequest.current++;
      resultController.current?.abort();
    };
  }, [resultContext]);
  const routeHeading = useRef<HTMLHeadingElement>(null),
    // Project tabs and data refreshes retain focus. Collection/detail and exact
    // project identity changes can remove the content action that held it.
    viewIdentity = JSON.stringify([
      active,
      active === "Projects" && projectTab && selection
        ? [selection.workRef, selection.rootJobId]
        : null,
    ]),
    previousView = useRef(viewIdentity);
  useLayoutEffect(() => {
    if (previousView.current === viewIdentity) return;
    previousView.current = viewIdentity;
    // A removed content action leaves focus on body. Preserve connected
    // controls (including navigation), and never move focus for data refreshes.
    if (!document.activeElement || document.activeElement === document.body)
      routeHeading.current?.focus();
  }, [viewIdentity]);
  useEffect(
    () =>
      window.MastermindMissionHost?.auth?.subscribe((state) => {
        const serialized = JSON.stringify(state);
        const generation =
          window.MastermindMissionHost?.invalidationGeneration?.() ?? 0;
        if (
          serialized === previousAuth.current &&
          generation === previousHostGeneration.current
        )
          return;
        previousAuth.current = serialized;
        previousHostGeneration.current = generation;
        office.invalidateAuth();
        observedConversation.invalidateAuth();
        commandSlot.current?.controller.invalidate();
        const pending = pendingCommand.current;
        if (pending) {
          pending.complete({ status: "refused" });
          pendingCommand.current = null;
        }
        setHeldKind(null);
        bumpInvalidation();
        // Invalidate rendered and in-flight source data at the notification,
        // not after replacement reads resolve or a passive effect runs.
        programRequest.current++;
        workRequest.current++;
        missionRequest.current++;
        resultRequest.current++;
        resultController.current?.abort();
        setIndex({
          programs: [],
          state: "PENDING",
          reason: "SOURCE_READ_PENDING",
        });
        setWorkState(
          state.acquisition
            ? { kind: "PENDING" }
            : { kind: "UNAVAILABLE", reason: "AUTHENTICATION_REQUIRED" },
        );
        setMission(
          unavailableMission(
            null,
            state.acquisition
              ? "SOURCE_READ_PENDING"
              : "AUTHENTICATION_REQUIRED",
          ),
        );
        setAuthState(state);
        setAuthRevision((n) => n + 1);
        setWindowDocument(null);
        setAssociation(null);
        setMissionV3(null);
        setResultState({ kind: "IDLE" });
      }),
    [],
  );
  useEffect(() => {
    // Selection change clears result detail. The bounded read for the new
    // tuple must be reissued; we never carry stale detail across a click.
    setResultState({ kind: "IDLE" });
  }, [selection]);
  useEffect(() => {
    // New result_refs revision (root/work_ref pair changed under the hood)
    // also clears any in-flight detail even if the user kept their click.
    setResultState({ kind: "IDLE" });
  }, [missionV3]);
  useEffect(() => {
    if (resultState.kind !== "READY") return;
    if (authState && !authState.acquisition) {
      setResultState({ kind: "IDLE" });
    }
  }, [authState?.acquisition, resultState]);
  useEffect(() => {
    bumpInvalidation();
    const controller = new AbortController();
    pairAbort.current = controller;
    const started = invalidation.current;
    const hostGeneration =
      window.MastermindMissionHost?.invalidationGeneration?.() ?? 0;
    let attached = true;
    setWindowDocument(null);
    setAssociation(null);
    setWindowPending(false);
    const host = window.MastermindMissionHost;
    const readWindow = host?.readCurrentWindow;
    const readV3 = host?.readMissionV3;
    const stillCurrent = () =>
      attached &&
      !controller.signal.aborted &&
      started === invalidation.current &&
      hostGeneration === (host?.invalidationGeneration?.() ?? 0);
    if (active !== "Conversation" && active !== "Conversations")
      return () => {
        attached = false;
        controller.abort();
      };
    const run = async () => {
      const conversationRead = observedConversation.begin();
      setWindowPending(true);
      let pairMission: Missionv3Document | null = null;
      if (authState?.acquisition && selection && readV3) {
        try {
          const raw = await readV3({ ...selection, signal: controller.signal });
          if (!stillCurrent()) return;
          // Same full decoder as the main Mission path: a fresh response that
          // fails the closed contract can never establish an association, so
          // the window stays UNBOUND rather than trusting an unknown shape.
          pairMission = decodeMissionv3(raw, selection);
        } catch {
          if (!stillCurrent()) return;
          pairMission = null;
        }
      }
      if (!stillCurrent()) return;
      if (!authState?.content || !readWindow) {
        observedConversation.accept(conversationRead, pairMission, null);
        setWindowPending(false);
        return;
      }
      try {
        const value = await readWindow({ signal: controller.signal });
        if (!stillCurrent()) return;
        setWindowDocument(value);
        setAssociation(
          observedMissionAssociation(value, pairMission, selection),
        );
        observedConversation.accept(conversationRead, pairMission, value);
      } catch {
        if (!stillCurrent()) return;
        setWindowDocument(null);
        setAssociation(null);
        observedConversation.accept(conversationRead, pairMission, null);
      } finally {
        if (stillCurrent()) setWindowPending(false);
      }
    };
    void run();
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    active,
    selection,
    authRevision,
    windowRevision,
    authState?.content,
    authState?.acquisition,
  ]);
  useEffect(() => {
    if (!initialLocation.hasIdentity && initial) {
      const location = new URL(window.location.href);
      location.search = new URLSearchParams({
        work_ref: initial.workRef,
        root_job_id: initial.rootJobId,
      }).toString();
      window.history.replaceState(
        window.history.state,
        "",
        `${location.pathname}${location.search}${location.hash}`,
      );
    }
  }, [initial, initialLocation.hasIdentity]);
  useEffect(() => {
    let attached = true;
    if (!native)
      return () => {
        attached = false;
      };
    import("@tauri-apps/api/core")
      .then(({ invoke }) => invoke<BuildReceipt>("readiness"))
      .then((r) => {
        if (attached) setBuild(r);
      })
      .catch(() => {
        if (attached)
          setNotice(
            "Native readiness receipt unavailable. No source request was attempted.",
          );
      });
    return () => {
      attached = false;
    };
  }, [native]);
  useEffect(() => {
    let attached = true;
    const current = ++programRequest.current,
      controller = new AbortController();
    // A changed selection must wait for its own collection read before the
    // Mission effect can use the preceding selection's AVAILABLE index.
    programSelection.current = selection;
    const officeRead = office.beginPrograms();
    if (
      native &&
      !window.MastermindMissionHost?.readPrograms &&
      !window.MastermindMissionHost?.readProgramsObservation
    ) {
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "NATIVE_TRANSPORT_UNCONFIGURED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    // A refused owner read emits auth state. Re-reading on that notification
    // without acquisition authority creates a feedback loop while signed out.
    if (authState && !authState.acquisition) {
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "AUTHENTICATION_REQUIRED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    const read = window.MastermindMissionHost?.readPrograms;
    const readObservation =
      window.MastermindMissionHost?.readProgramsObservation;
    if (typeof read !== "function" && typeof readObservation !== "function") {
      setIndex({
        programs: [],
        state: "UNAVAILABLE",
        reason: "QUALIFIED_PROGRAM_READ_UNAVAILABLE",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setIndex({
      programs: [],
      state: "PENDING",
      reason: "SOURCE_READ_PENDING",
    });
    Promise.resolve()
      .then(async () => {
        if (readObservation) {
          const observation = await readObservation({
            signal: controller.signal,
          });
          return { raw: observation.controlRoom, observation };
        }
        return {
          raw: await read!({ signal: controller.signal }),
          observation: null,
        };
      })
      .then(({ raw, observation }) => {
        if (
          attached &&
          programRequest.current === current &&
          !controller.signal.aborted
        ) {
          setIndex(programsFromControlRoom(raw));
          office.acceptPrograms(officeRead, observation);
        }
      })
      .catch(() => {
        if (
          attached &&
          programRequest.current === current &&
          !controller.signal.aborted
        )
          setIndex({
            programs: [],
            state: "UNAVAILABLE",
            reason: "SOURCE_UNAVAILABLE",
          });
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    native,
    authRevision,
    authState?.acquisition,
    selection?.workRef,
    selection?.rootJobId,
  ]);
  useEffect(() => {
    let attached = true;
    const current = ++workRequest.current;
    const controller = new AbortController();
    const host = window.MastermindMissionHost;
    const read = host?.readWork;
    if (native && !read) {
      setWorkState({
        kind: "UNAVAILABLE",
        reason: "NATIVE_TRANSPORT_UNCONFIGURED",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (authState && !authState.acquisition) {
      setWorkState({ kind: "UNAVAILABLE", reason: "AUTHENTICATION_REQUIRED" });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (typeof read !== "function") {
      setWorkState({
        kind: "UNAVAILABLE",
        reason: "QUALIFIED_WORK_READ_UNAVAILABLE",
      });
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setWorkState({ kind: "PENDING" });
    Promise.resolve()
      .then(() => read({ signal: controller.signal }))
      .then((raw) => {
        if (
          !attached ||
          workRequest.current !== current ||
          controller.signal.aborted
        )
          return;
        const document = decodeWorkDocument(raw);
        if (!document) throw new Error("WORK_RESPONSE_INVALID");
        setWorkState({ kind: "DOCUMENT", document });
      })
      .catch(() => {
        if (
          attached &&
          workRequest.current === current &&
          !controller.signal.aborted
        )
          setWorkState({ kind: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [native, authRevision, authState?.acquisition]);
  useEffect(() => {
    const restoreSelection = () => {
      const next = selectionFromLocation();
      office.clearSelection(next);
      observedConversation.clear();
      selectionSeq.current += 1;
      commandSlot.current?.controller.invalidate();
      bumpInvalidation();
      setWindowDocument(null);
      setAssociation(null);
      setWindowPending(false);
      setMissionV3(null);
      setResultState({ kind: "IDLE" });
      setMission(
        unavailableMission(
          next,
          next ? "PROGRAM_SELECTION_PENDING" : "EXACT_SELECTION_REQUIRED",
        ),
      );
      setSelection(next);
      setProjectTab(next ? "Overview" : null);
      setActive("Projects");
    };
    window.addEventListener("popstate", restoreSelection);
    return () => window.removeEventListener("popstate", restoreSelection);
  }, []);
  useEffect(() => {
    let attached = true;
    const current = ++missionRequest.current,
      controller = new AbortController();
    const officeRead = office.beginMission();
    if (
      native &&
      !window.MastermindMissionHost?.readMissionV3 &&
      !window.MastermindMissionHost?.readMission
    ) {
      setMission(
        unavailableMission(selection, "NATIVE_TRANSPORT_UNCONFIGURED"),
      );
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (!selection) {
      setMission(unavailableMission(null, "EXACT_SELECTION_REQUIRED"));
      setNotice(
        "Choose a Program with one resolved mission before opening the workspace.",
      );
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (missionSelectionState === "PENDING") {
      setMission(unavailableMission(selection, "PROGRAM_SELECTION_PENDING"));
      setNotice("Reading Programs before resolving the exact mission pair…");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (missionSelectionState === "UNAVAILABLE") {
      setMission(unavailableMission(selection, "PROGRAM_SOURCE_UNAVAILABLE"));
      setNotice("Program source unavailable. No mission pair was guessed.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (selectionRefused) {
      setMission(unavailableMission(selection, "EXACT_SELECTION_UNRESOLVED"));
      setNotice(
        "The Program source did not resolve one exact mission pair. No mission was read.",
      );
      return () => {
        attached = false;
        controller.abort();
      };
    }
    if (authState && !authState.acquisition) {
      setMissionV3(null);
      setMission(unavailableMission(selection, "AUTHENTICATION_REQUIRED"));
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    const readV3 = window.MastermindMissionHost?.readMissionV3;
    const read = readV3 ?? window.MastermindMissionHost?.readMission;
    setMissionV3(null);
    if (typeof read !== "function") {
      setMission(
        unavailableMission(selection, "QUALIFIED_HOST_READ_UNAVAILABLE"),
      );
      setNotice("Workspace connection unavailable. Current work was not read.");
      return () => {
        attached = false;
        controller.abort();
      };
    }
    setMission(unavailableMission(selection, "SOURCE_READ_PENDING"));
    setNotice("Reading the exact selected mission pair…");
    Promise.resolve()
      .then(() => read({ ...selection, signal: controller.signal }))
      .then((raw) => {
        if (!attached || missionRequest.current !== current) return;
        const v3 = readV3 ? decodeMissionv3(raw, selection) : null;
        const decoded = readV3 ? v3 : decodeMission(raw, selection);
        office.acceptMission(officeRead, decoded);
        if (decoded) {
          if (v3) {
            // Existing presentation components consume the same observation's
            // v2 fields; there is no second acquisition or fallback read.
            const { result_refs: _refs, ...body } = v3;
            setMission({ ...body, schema: "mastermind.mission_workspace.v2" });
            setMissionV3(v3);
          } else {
            setMission(decoded as MissionDocument);
          }
          setNotice(
            "Source and observation clocks are displayed as projected; this render did not refresh them.",
          );
        } else {
          setMission(
            unavailableMission(selection, "SELECTION_OR_SCHEMA_MISMATCH"),
          );
          setNotice(
            "The response failed the closed contract or exact pair check.",
          );
        }
      })
      .catch(() => {
        if (
          attached &&
          missionRequest.current === current &&
          !controller.signal.aborted
        ) {
          setMission(unavailableMission(selection, "SOURCE_UNAVAILABLE"));
          setNotice(
            "Mission source unavailable. No mission, relationship, or content was fabricated.",
          );
        }
      });
    return () => {
      attached = false;
      controller.abort();
    };
  }, [
    selection,
    native,
    missionSelectionState,
    selectionRefused,
    authRevision,
    authState?.acquisition,
  ]);
  const candidate = isDoc(mission) ? mission : null,
    d =
      candidate &&
      (!authState || authState.acquisition) &&
      selection &&
      candidate.program.work_ref === selection.workRef &&
      (candidate.mission.root_job_id === null ||
        candidate.mission.root_job_id === selection.rootJobId)
        ? candidate
        : null,
    conversationActive =
      active === "Conversation" || active === "Conversations",
    legacyConversationState = windowPending
      ? "SOURCE_READ_PENDING"
      : association
        ? "OBSERVED_MISSION_ASSOCIATION"
        : windowDocument && authState?.content
          ? "UNBOUND"
          : "UNAVAILABLE",
    conversationState =
      active === "Conversations"
        ? observedConversation.projection.conversation.source.state
        : legacyConversationState,
    headerState = conversationActive
      ? conversationState
      : active === "Inbox" || active === "Knowledge"
        ? office.projection.mission.source.state
        : active === "Projects"
          ? office.projection.programs.source.state
          : active === "Today"
            ? index.state === "PENDING"
              ? "SOURCE_READ_PENDING"
              : index.state
            : active === "Work"
              ? workState.kind === "PENDING"
                ? "SOURCE_READ_PENDING"
                : workState.kind === "DOCUMENT"
                  ? workState.document.availability
                  : "UNAVAILABLE"
              : active === "Fleet & Capacity"
                ? "NOT_PROJECTED"
                : (d?.read_state.state ?? "UNAVAILABLE"),
    headerSummary =
      active === "Conversations"
        ? observedConversation.projection.conversation.source.state ===
          "CURRENT"
          ? "Observed owner window for the exact selected Mission; session identity and send authority remain separate."
          : "Conversation content is shown only from a qualified paired Mission and Current Window observation."
        : active === "Conversation"
          ? association
            ? "Observed window for this Mission from separately authorized owner observations."
            : windowDocument && authState?.content
              ? "A global current permitted window. No relationship to the selected Mission is proven."
              : "No Mission-linked conversation is currently established."
          : active === "Inbox"
            ? "Owner-defined attention for the selected Mission; company-wide attention is not inferred."
            : active === "Knowledge"
              ? "Supplied Mission references retain exact provenance; canonical record content is not reconstructed."
              : active === "Projects"
                ? "Exact Project identities from the supplied owner collection; company-wide coverage is not established."
                : active === "Today"
                  ? d && d.read_state.state !== "CURRENT"
                    ? `Selected mission projection is ${label(d.read_state.state)}; source qualification is not current.`
                    : index.state === "PENDING"
                      ? "Reading the bounded Programs projection; no company-wide queue is inferred."
                      : index.state === "AVAILABLE"
                        ? `${index.programs.length} Programs from the bounded source observation.`
                        : "Program source unavailable; current company movement is not inferred."
                  : active === "Work"
                    ? workState.kind === "PENDING"
                      ? "Reading the bounded Work projection; no queue is inferred yet."
                      : workState.kind === "DOCUMENT"
                        ? workState.document.availability === "AVAILABLE"
                          ? `${workState.document.coverage.count} Work roots from the bounded Executive observation.`
                          : "Work owner returned a typed unavailable observation; no empty queue is inferred."
                        : "Work source unavailable; no empty queue is inferred."
                    : active === "Fleet & Capacity"
                      ? "Fleet health and placement require their canonical Capacity source."
                      : d
                        ? d.mission.root_job_id &&
                          d.read_state.state === "CURRENT"
                          ? "A bounded source-qualified mission, current as of its owner observation."
                          : d.mission.root_job_id
                            ? `This mission projection is ${label(d.read_state.state)}; source qualification is not current.`
                            : "A qualified reconciliation state; no mission root is established."
                        : "No producer document is currently admitted.",
    visibleNotice =
      active === "Conversations"
        ? windowPending
          ? "Reading the paired Mission and current permitted window…"
          : observedConversation.projection.conversation.source.state ===
              "CURRENT"
            ? "Observed conversation window for the selected Mission; no recipient or send authority is inferred."
            : "No qualified observed conversation is currently established."
        : active === "Conversation"
          ? association
            ? "Observed window for this Mission. Independent owner observations."
            : windowDocument && authState?.content
              ? "This current permitted window is not linked to the selected Mission."
              : windowPending
                ? "Reading the current permitted window…"
                : "No Mission-linked conversation is currently established."
          : active === "Work"
            ? workState.kind === "PENDING"
              ? "Reading the source-qualified Work queue…"
              : workState.kind === "DOCUMENT"
                ? workState.document.availability === "AVAILABLE"
                  ? "Work queue is source-qualified; ownership, capacity, effects, and acceptance remain evidence-bound."
                  : "Work projection unavailable; zero work is not inferred."
                : "Work source unavailable; zero work is not inferred."
            : active === "Fleet & Capacity"
              ? "Capacity source not connected. No host readiness was inferred."
              : notice,
    open = (w: string, r: string | null) => {
      if (r) {
        office.clearSelection({ workRef: w, rootJobId: r });
        observedConversation.clear();
        selectionSeq.current += 1;
        commandSlot.current?.controller.invalidate();
        bumpInvalidation();
        setWindowDocument(null);
        setAssociation(null);
        setWindowPending(false);
        const next = { workRef: w, rootJobId: r },
          location = new URL(window.location.href);
        location.search = new URLSearchParams({
          work_ref: next.workRef,
          root_job_id: next.rootJobId,
        }).toString();
        window.history.pushState(
          null,
          "",
          `${location.pathname}${location.search}${location.hash}`,
        );
        setMission(unavailableMission(next, "SOURCE_READ_PENDING"));
        setNotice("Reading the exact selected mission pair…");
        setSelection(next);
        setProjectTab("Overview");
        setActive("Projects");
      }
    };
  const settleCommand = (
    state: OperationState,
    bindingAtStart: OrchestratorCommandBinding,
  ) => {
    const pending = pendingCommand.current;
    // Adjudicate against the live route, not the captured one: a binding
    // object that was replaced — even by one carrying the same owner scope
    // and generation — supersedes the dispatch it received. Its receipt may
    // not navigate, may not complete a newer action, and may not publish a
    // terminal admission over the route the user now sees.
    const liveBinding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    if (liveBinding !== bindingAtStart) {
      // A superseded route's receipt may release only the pending it
      // dispatched. A newer pending started under the replacement binding
      // belongs to its own route's receipt: publish nothing and release
      // nothing here.
      if (pending && pending.binding === bindingAtStart) {
        pending.complete({ status: "refused" });
        pendingCommand.current = null;
        setHeldKind(null);
      }
      return;
    }
    setCommandStatus(state);
    if (!pending) return;
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = readOwnerContext(bindingAtStart.port);
    if (liveAuth?.status !== "signed_in" || !ctx) return;
    if (
      ctx.generation !== pending.generation ||
      ctx.principalScope !== pending.principalScope
    ) {
      pending.complete({ status: "refused" });
      pendingCommand.current = null;
      setHeldKind(null);
      return;
    }
    if (state.status !== "accepted" && state.status !== "refused") {
      setHeldKind(pending.kind);
      return;
    }
    if (state.status === "accepted" && pending.kind === "launch") {
      if (pending.selectionSeq !== selectionSeq.current) {
        pending.complete({ status: "refused" });
        pendingCommand.current = null;
        setHeldKind(null);
        return;
      }
      const sel = state.missionSelection
        ? normalizeSelection(state.missionSelection)
        : null;
      if (sel) open(sel.workRef, sel.rootJobId);
    }
    pending.complete({ status: state.status });
    pendingCommand.current = null;
    setHeldKind(null);
  };
  const beginCommand = (
    kind: OperationKind,
    intent: ReturnType<typeof launchIntentFromBinding>,
    onComplete: (
      outcome: { status: "accepted" } | { status: "refused" },
    ) => void,
  ) => {
    const binding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = binding ? readOwnerContext(binding.port) : null;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !intent) {
      onComplete({ status: "refused" });
      return;
    }
    if (pendingCommand.current) {
      // Another action is already held for this composition: refuse the NEW
      // callback exactly once so its own guard releases immediately. The
      // original held callback, pointer, and guard are never replaced or
      // released here — only its own receipt may settle them.
      onComplete({ status: "refused" });
      return;
    }
    let controller = commandSlot.current?.controller ?? null;
    if (
      !commandSlot.current ||
      commandSlot.current.binding !== binding ||
      commandSlot.current.principalScope !== ctx.principalScope ||
      commandSlot.current.generation !== ctx.generation
    ) {
      commandSlot.current?.controller.invalidate();
      controller = new OperationController(binding.port, binding.store);
      commandSlot.current = {
        controller,
        binding,
        principalScope: ctx.principalScope,
        generation: ctx.generation,
      };
    }
    if (!controller) {
      onComplete({ status: "refused" });
      return;
    }
    pendingCommand.current = {
      generation: ctx.generation,
      principalScope: ctx.principalScope,
      binding,
      kind,
      selectionSeq: selectionSeq.current,
      complete: onComplete,
    };
    setHeldKind(kind);
    void Promise.resolve()
      .then(() => controller.begin(intent))
      .then((state) => settleCommand(state, binding))
      .catch(() => {
        const current = controller.getState();
        if (current.status === "unknown") settleCommand(current, binding);
        else setHeldKind(kind);
      });
  };
  const checkCommandStatus = () => {
    if (recoverInFlight) return;
    const binding = completeOrchestratorCommandBinding(
      window.MastermindMissionHost?.commandBinding,
    );
    const liveAuth = window.MastermindMissionHost?.auth?.getState();
    const ctx = binding ? readOwnerContext(binding.port) : null;
    const slot = commandSlot.current;
    if (!binding || liveAuth?.status !== "signed_in" || !ctx || !slot) return;
    if (
      slot.generation !== ctx.generation ||
      slot.principalScope !== ctx.principalScope ||
      slot.binding !== binding
    )
      return;
    // Read-only recovery: recover() resolves through readOperation only and
    // never prepares or submits. The control is disabled exactly while this
    // asynchronous recovery is in flight — not for a static held pointer.
    setRecoverInFlight(true);
    void Promise.resolve()
      .then(() => slot.controller.recover())
      .then((state) => settleCommand(state, binding))
      .catch(() => {})
      .finally(() => setRecoverInFlight(false));
  };
  const commandBusy =
    commandStatus?.status === "submitting" ||
    commandStatus?.status === "checking";
  const showCheckStatus =
    !!heldKind &&
    commandStatus?.status !== "accepted" &&
    commandStatus?.status !== "refused" &&
    commandStatus?.status !== "submitting";
  const checkStatusControl = showCheckStatus ? (
    <div className="form-actions">
      {commandStatus?.reason ? <code>{commandStatus.reason}</code> : null}
      <button
        type="button"
        onClick={checkCommandStatus}
        disabled={recoverInFlight}
      >
        Check status
      </button>
    </div>
  ) : null;
  const commandPanel =
    canLaunch && commandView && launchDraftDismissed ? (
      <section className="card">
        <div className="section-title">
          <h2>Launch Orchestrator</h2>
        </div>
        <p className="muted">Launch draft dismissed.</p>
        <button
          type="button"
          onClick={() => {
            setLaunchDraftDismissed(false);
            routeHeading.current?.focus();
          }}
        >
          New launch
        </button>
      </section>
    ) : canLaunch && commandView ? (
      <>
        <LaunchOrchestrator
          projects={commandView.projects}
          profiles={commandView.profiles}
          submitting={heldKind === "launch" && commandBusy}
          error={
            commandStatus?.status === "refused"
              ? commandStatus.reason
              : undefined
          }
          onSubmit={(form: LaunchForm, onComplete) => {
            const binding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding,
            );
            const liveAuth = window.MastermindMissionHost?.auth?.getState();
            const ctx = binding ? readOwnerContext(binding.port) : null;
            if (!binding || liveAuth?.status !== "signed_in" || !ctx) {
              onComplete({ status: "refused" });
              return;
            }
            const intent = launchIntentFromBinding(binding, form);
            beginCommand("launch", intent, onComplete);
          }}
          onCancel={() => {
            // Dismiss an unsent draft only. A held command keeps its original
            // completion handle and durable pointer until owner reconciliation.
            if (
              pendingCommand.current?.kind === "launch" ||
              heldKind === "launch"
            ) return;
            setLaunchDraftDismissed(true);
            routeHeading.current?.focus();
          }}
        />
        {heldKind === "launch" ? checkStatusControl : null}
      </>
    ) : (
      <section className="card">
        <div className="section-title">
          <div>
            <h2>Launch Orchestrator</h2>
          </div>
          <span className="state state-unavailable">UNAVAILABLE</span>
        </div>
        <p className="muted">Command route is not available.</p>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
        </details>
        {heldKind === "launch" ? checkStatusControl : null}
      </section>
    );
  const sessionUnavailableCard = (
    <section className="card">
      <div className="section-title">
        <div>
          <h2>Session Workspace</h2>
        </div>
        <span className="state state-unavailable">UNAVAILABLE</span>
      </div>
      <p className="muted">
        Session is unavailable for the exact selected mission.
      </p>
      <details className="reason-details">
        <summary>Technical details</summary>
        <code>{COMMAND_ROUTE_UNAVAILABLE}</code>
      </details>
    </section>
  );
  const sessionPanel = commandBinding ? (
    sessionExact && commandView?.session ? (
      <>
        <SessionWorkspace
          sessionKey={commandView.session.sessionKey}
          title={commandView.session.title}
          messages={commandView.session.messages}
          observedAt={commandView.session.observedAt}
          connection={commandView.session.connection}
          coverage={commandView.session.coverage}
          turnBusy={commandView.session.turnBusy}
          sending={heldKind === "message" && commandBusy}
          unavailableReason={commandView.session.unavailableReason}
          stopLabel={commandView.session.stopLabel}
          stopping={heldKind === "stop" && commandBusy}
          onSend={(text, onComplete) => {
            const presented = commandView.session;
            const binding = completeOrchestratorCommandBinding(
              window.MastermindMissionHost?.commandBinding,
            );
            const liveAuth = window.MastermindMissionHost?.auth?.getState();
            const ctx = binding ? readOwnerContext(binding.port) : null;
            const view = binding ? readCommandView(binding) : null;
            const current = selection;
            if (
              !presented ||
              !binding ||
              liveAuth?.status !== "signed_in" ||
              !ctx ||
              !sessionMatchesSelection(view?.session ?? null, current) ||
              view?.session?.sessionKey !== presented.sessionKey
            ) {
              onComplete({ status: "refused" });
              return;
            }
            const intent = messageIntentFromBinding(
              binding,
              presented.sessionKey,
              text,
            );
            beginCommand("message", intent, onComplete);
          }}
          onStop={
            commandView.session.stopLabel
              ? (onComplete) => {
                  const presented = commandView.session;
                  const binding = completeOrchestratorCommandBinding(
                    window.MastermindMissionHost?.commandBinding,
                  );
                  const liveAuth =
                    window.MastermindMissionHost?.auth?.getState();
                  const ctx = binding ? readOwnerContext(binding.port) : null;
                  const view = binding ? readCommandView(binding) : null;
                  if (
                    !presented ||
                    !binding ||
                    liveAuth?.status !== "signed_in" ||
                    !ctx ||
                    !sessionMatchesSelection(
                      view?.session ?? null,
                      selection,
                    ) ||
                    view?.session?.sessionKey !== presented.sessionKey
                  ) {
                    onComplete({ status: "refused" });
                    return;
                  }
                  const intent = stopIntentFromBinding(
                    binding,
                    presented.sessionKey,
                  );
                  beginCommand("stop", intent, onComplete);
                }
              : undefined
          }
        />
        {heldKind === "message" || heldKind === "stop"
          ? checkStatusControl
          : null}
      </>
    ) : (
      <>
        {sessionUnavailableCard}
        {heldKind === "message" || heldKind === "stop"
          ? checkStatusControl
          : null}
      </>
    )
  ) : (
    // No command route is installed at all: Conversation shows the same fixed
    // unavailable code as Work, with no fabricated session or dispatch state.
    sessionUnavailableCard
  );
  const pickResult = (sel: ResultSelection) => {
    const valid = normalizeResultSelection(sel);
    if (!valid) return;
    if (!window.MastermindMissionHost?.readResult) {
      setResultState({
        kind: "UNAVAILABLE",
        selection: valid,
        reason: "QUALIFIED_RESULT_READ_UNAVAILABLE",
      });
      return;
    }
    resultController.current?.abort();
    const context = resultContext;
    setResultState({ kind: "PENDING", selection: valid });
    const current = ++resultRequest.current;
    const controller = new AbortController();
    resultController.current = controller;
    let raceAborted = false;
    Promise.resolve()
      .then(() =>
        window.MastermindMissionHost!.readResult!({
          workRef: valid.workRef,
          rootJobId: valid.rootJobId,
          jobId: valid.jobId,
          attemptId: valid.attemptId,
          resultEnvelopeDigest: valid.resultEnvelopeDigest,
          signal: controller.signal,
        }),
      )
      .then((raw) => {
        if (
          resultRequest.current !== current ||
          raceAborted ||
          currentResultContext.current !== context ||
          controller.signal.aborted
        )
          return;
        const decoded = decodeResultEnvelope(raw, valid);
        if (!decoded) {
          setResultState({
            kind: "UNAVAILABLE",
            selection: valid,
            reason: "RESULT_RESPONSE_INVALID",
          });
          return;
        }
        setResultState({ kind: "READY", selection: valid, document: decoded });
      })
      .catch((err: Error) => {
        if (
          resultRequest.current !== current ||
          raceAborted ||
          currentResultContext.current !== context ||
          controller.signal.aborted
        )
          return;
        if (err?.message === "READ_CANCELLED") {
          raceAborted = true;
          return;
        }
        setResultState({
          kind: "UNAVAILABLE",
          selection: valid,
          reason: "RESULT_SOURCE_UNAVAILABLE",
        });
      });
  };
  const resultRefs =
    d && missionV3 && isDocv3(missionV3) ? (
      <ResultRefs
        d={missionV3}
        onPick={pickResult}
        selectedKey={
          resultState.kind === "READY" || resultState.kind === "PENDING"
            ? `${resultState.selection.jobId}|${resultState.selection.attemptId}|${resultState.selection.resultEnvelopeDigest}`
            : null
        }
        disabled={!authState?.acquisition}
      />
    ) : null;
  const navigateOperationalView = (view: OperationalView) => {
    setProjectTab(null);
    setActive(view);
  };
  let content: React.ReactNode;
  if (active === "Today")
    content = (
      <>
        <MetaCeoOffice
          key={JSON.stringify([authRevision, selection])}
          projection={office.projection}
          draft={office.draft}
          onDraftChange={office.changeDraft}
        />
        <OperationalNavigation label="Company operations" onNavigate={navigateOperationalView} />
      </>
    );
  else if (active === "Inbox")
    content = (
      <Inbox
        projection={office.projection}
        onNavigateMission={
          office.projection.mission.source.state === "CURRENT"
            ? (target, mode) => {
                if (mode === "current") open(target.workRef, target.rootJobId);
              }
            : undefined
        }
      />
    );
  else if (active === "Conversations")
    content = (
      <>
        <ConversationWindow
          projection={observedConversation.projection}
          draft={observedConversation.draft}
          onDraftChange={observedConversation.changeDraft}
        />
        <button
          type="button"
          disabled={windowPending || !authState?.content}
          onClick={() => {
            bumpInvalidation();
            setWindowRevision((n) => n + 1);
          }}
        >
          Refresh observed window
        </button>
        {sessionPanel}
      </>
    );
  else if (active === "Knowledge")
    content = <Knowledge projection={office.projection} />;
  else if (active === "Projects")
    content =
      projectTab && selection ? (
        <>
          <section className="hero">
            <div>
              <span className="eyebrow">PROJECT</span>
              <h2>{d?.program.title || selection.workRef}</h2>
              <p>Exact project context · {selection.rootJobId}</p>
            </div>
            <div className="facts">
              <div>
                <small>PROJECT IDENTITY</small>
                <code>{selection.workRef}</code>
              </div>
              <div>
                <small>MISSION ROOT</small>
                <code>{selection.rootJobId}</code>
              </div>
              <div>
                <small>OWNER STATE</small>
                <State
                  value={
                    d?.read_state.state ??
                    ("reason" in mission &&
                    (mission.reason === "SOURCE_READ_PENDING" ||
                      mission.reason === "PROGRAM_SELECTION_PENDING")
                      ? "SOURCE_READ_PENDING"
                      : "UNAVAILABLE")
                  }
                />
              </div>
            </div>
          </section>
          <ProjectTabs active={projectTab} onChange={setProjectTab} />
          {!d ? (
            <section className="card empty-panel">
              <h2>{projectTab}</h2>
              <State value="UNAVAILABLE" />
              <Empty>
                The exact project Mission is not currently admitted. No project
                facts are borrowed from another selection.
              </Empty>
              <details className="reason-details">
                <summary>Technical details</summary>
                <code>
                  {"reason" in mission ? mission.reason : "SOURCE_UNAVAILABLE"}
                </code>
              </details>
            </section>
          ) : projectTab === "Overview" ? (
            <>
              <Mission d={d} />
              {resultRefs}
              <ResultCard state={resultState} />
            </>
          ) : projectTab === "Plan" ? (
            <ProjectPlan d={d} />
          ) : projectTab === "Work" ? (
            <>
              {commandPanel}
              <WorkQueue state={workState} rootJobId={selection.rootJobId} />
            </>
          ) : projectTab === "Evidence" ? (
            <Evidence d={d} />
          ) : (
            <ProjectMore d={d} sessionPanel={sessionPanel} onNavigate={navigateOperationalView} />
          )}
        </>
      ) : (
        <Projects
          programs={office.projection.programs}
          selectedProject={selection}
          onNavigateMission={
            office.projection.programs.source.state === "CURRENT"
              ? (target, mode) => {
                  if (mode === "current")
                    open(target.workRef, target.rootJobId);
                }
              : undefined
          }
        />
      );
  else if (active === "Programs")
    content = (
      <section className="card">
        <div className="section-title">
          <h2>Programs</h2>
          <State
            value={
              index.state === "PENDING" ? "SOURCE_READ_PENDING" : index.state
            }
          />
        </div>
        {index.state === "PENDING" ? (
          <Empty>Reading the bounded Control Room projection…</Empty>
        ) : index.programs.length ? (
          <div className="programs">
            {index.programs.map((p) => (
              <button
                key={p.workRef}
                disabled={!p.rootJobId}
                onClick={() => open(p.workRef, p.rootJobId)}
              >
                <b>{p.title || p.workRef}</b>
                <span>
                  {label(p.state)} ·{" "}
                  {display(p.nextAction, "No next action projected")}
                </span>
                <small>
                  {p.rootJobId
                    ? `Mission ${p.rootJobId}`
                    : p.rootState === "CONFLICT"
                      ? `Root conflict: ${p.rootCandidates.join(", ") || "multiple responsibility rows"}`
                      : "Root unknown; no mission was guessed"}
                </small>
              </button>
            ))}
          </div>
        ) : index.state === "AVAILABLE" ? (
          <Empty>
            No Programs were projected. This is not evidence of zero work.
          </Empty>
        ) : (
          <Empty>
            Workspace connection unavailable. Programs will appear when an
            approved source is available.
          </Empty>
        )}
        {index.state === "UNAVAILABLE" ? (
          <details className="reason-details">
            <summary>Technical details</summary>
            <code>{index.reason}</code>
          </details>
        ) : null}
      </section>
    );
  else if (active === "Work")
    content = (
      <>
        {commandPanel}
        <WorkQueue state={workState} />
      </>
    );
  else if (active === "Fleet & Capacity")
    content = (
      <section className="card source-gap">
        <div className="section-title">
          <div>
            <h2>Fleet & Capacity</h2>
            <p className="muted">
              Resource health and placement are separate from Mission lifecycle
              and require their canonical Capacity source.
            </p>
          </div>
          <State value="NOT_PROJECTED" />
        </div>
        <p>
          This read-only app does not infer host readiness from browser,
          provider, or Mission state. Capacity will appear here only when the
          qualified fleet/placement feed is connected.
        </p>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>CAPACITY_SOURCE_NOT_CONNECTED</code>
        </details>
      </section>
    );
  else if (active === "Conversation")
    content = (
      <>
        {sessionPanel}
        <Conversation
          document={authState?.content ? windowDocument : null}
          pending={windowPending}
          refresh={() => {
            bumpInvalidation();
            setWindowRevision((n) => n + 1);
          }}
          selection={selection}
          association={association}
          contentAvailable={!!authState?.content}
        />
      </>
    );
  else if (!d)
    content = (
      <section className="card empty-panel">
        <h2>{active}</h2>
        <State value="UNAVAILABLE" />
        <Empty>
          The workspace is not connected. Mission content will appear when an
          approved source is available.
        </Empty>
        <details className="reason-details">
          <summary>Technical details</summary>
          <code>
            {"reason" in mission ? mission.reason : "SOURCE_UNAVAILABLE"}
          </code>
        </details>
      </section>
    );
  else if (active === "Mission Workspace")
    content = (
      <>
        <Mission d={d} />
        {missionV3 && isDocv3(missionV3) ? (
          <ResultRefs
            d={missionV3}
            onPick={(sel) => {
              const valid = normalizeResultSelection(sel);
              if (!valid) return;
              if (!window.MastermindMissionHost?.readResult) {
                setResultState({
                  kind: "UNAVAILABLE",
                  selection: valid,
                  reason: "QUALIFIED_RESULT_READ_UNAVAILABLE",
                });
                return;
              }
              resultController.current?.abort();
              const context = resultContext;
              setResultState({ kind: "PENDING", selection: valid });
              const current = ++resultRequest.current;
              const controller = new AbortController();
              resultController.current = controller;
              let raceAborted = false;
              Promise.resolve()
                .then(() =>
                  window.MastermindMissionHost!.readResult!({
                    workRef: valid.workRef,
                    rootJobId: valid.rootJobId,
                    jobId: valid.jobId,
                    attemptId: valid.attemptId,
                    resultEnvelopeDigest: valid.resultEnvelopeDigest,
                    signal: controller.signal,
                  }),
                )
                .then((raw) => {
                  if (
                    resultRequest.current !== current ||
                    raceAborted ||
                    currentResultContext.current !== context ||
                    controller.signal.aborted
                  )
                    return;
                  // The host returns the decoded frozen envelope — including
                  // the typed allowed 503 body as a validated UNAVAILABLE
                  // envelope. No kind sniffing, no blind cast: the value is
                  // re-validated against the exact selected tuple before it
                  // is admitted for rendering.
                  const decoded = decodeResultEnvelope(raw, valid);
                  if (!decoded) {
                    setResultState({
                      kind: "UNAVAILABLE",
                      selection: valid,
                      reason: "RESULT_RESPONSE_INVALID",
                    });
                    return;
                  }
                  setResultState({
                    kind: "READY",
                    selection: valid,
                    document: decoded,
                  });
                })
                .catch((err: Error) => {
                  if (
                    resultRequest.current !== current ||
                    raceAborted ||
                    currentResultContext.current !== context ||
                    controller.signal.aborted
                  )
                    return;
                  if (err?.message === "READ_CANCELLED") {
                    raceAborted = true;
                    return;
                  }
                  setResultState({
                    kind: "UNAVAILABLE",
                    selection: valid,
                    reason: "RESULT_SOURCE_UNAVAILABLE",
                  });
                });
            }}
            selectedKey={
              resultState.kind === "READY" || resultState.kind === "PENDING"
                ? `${resultState.selection.jobId}|${resultState.selection.attemptId}|${resultState.selection.resultEnvelopeDigest}`
                : null
            }
            disabled={!authState?.acquisition}
          />
        ) : null}
        <ResultCard state={resultState} />
      </>
    );
  else if (active === "Activity") content = <Activity d={d} />;
  else if (active === "Connections") content = <Connections d={d} />;
  else if (active === "Evidence") content = <Evidence d={d} />;
  else content = <Conversation />;
  return (
    <div className="shell">
      <a className="skip" href="#content" onClick={event => {
        event.preventDefault();
        document.getElementById("content")?.focus();
      }}>
        Skip to workspace
      </a>
      <aside>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            M
          </span>
          <span className="brand-copy">
            mastermind<small>EXECUTIVE OS</small>
          </span>
        </div>
        <div className="nav-section">
          <span className="nav-section-label">COMPANY</span>
          <nav aria-label="Company navigation">
            {primaryNavigation.map((x) => (
              <button
                key={x}
                className={active === x ? "active" : ""}
                aria-label={x}
                aria-current={active === x ? "page" : undefined}
                onClick={() => {
                  setProjectTab(null);
                  setActive(x);
                }}
              >
                <span className="nav-glyph" aria-hidden="true">
                  {navGlyph[x]}
                </span>
                <span className="nav-label">{x}</span>
              </button>
            ))}
          </nav>
        </div>
        <div className="nav-section mission-nav">
          <span className="nav-section-label">CURRENT MISSION</span>
          {selection ? (
            <div className="mission-context">
              <b>{d?.program.title || selection.workRef}</b>
              <small>Exact mission selected</small>
            </div>
          ) : (
            <div className="mission-context mission-context-empty">
              No exact mission selected
            </div>
          )}
          <nav aria-label="Mission navigation">
            {missionNavigation.map((x) => (
              <button
                key={x}
                className={active === x ? "active" : ""}
                aria-label={x}
                aria-current={active === x ? "page" : undefined}
                onClick={() => {
                  setProjectTab(null);
                  setActive(x);
                }}
              >
                <span className="nav-glyph" aria-hidden="true">
                  {navGlyph[x]}
                </span>
                <span className="nav-label">{x}</span>
              </button>
            ))}
          </nav>
        </div>
        <div className="side-note">
          <b>Source-qualified viewer</b>
          <br />
          Lifecycle, review, transport, acceptance and source freshness remain
          separate facts.
        </div>
      </aside>
      <main id="content" tabIndex={-1}>
        <header>
          <div>
            <span className="eyebrow">{active}</span>
            <h1 ref={routeHeading} tabIndex={-1}>
              {active}
            </h1>
            <p>{headerSummary}</p>
          </div>
          <div className="facts">
            <State value={headerState} />
            {authState ? (
              <div>
                <small>
                  {authState.status === "unconfigured"
                    ? "Sign-in setup pending"
                    : authState.status.replaceAll("_", " ")}
                </small>
                {authState.reason && authState.status !== "unconfigured" ? (
                  <p className="muted">
                    {authState.reason === "POPUP_BLOCKED"
                      ? "Allow the sign-in popup and try again."
                      : authState.reason === "POPUP_CLOSED"
                        ? "Sign-in window closed. Try again when ready."
                        : authState.reason.includes("EXPIRED") ||
                            authState.reason.includes("TIMEOUT")
                          ? "Sign-in timed out. Please try again."
                          : authState.acquisition
                            ? "Workspace connected. Conversation access is unavailable."
                            : "Sign-in could not complete. Please try again."}
                  </p>
                ) : null}
                <button
                  disabled={authState.status === "unconfigured"}
                  onClick={() => {
                    const auth = window.MastermindMissionHost?.auth;
                    if (!auth) return;
                    const signingOut =
                      authState.acquisition ||
                      authState.content ||
                      authState.status === "signing_in";
                    if (signingOut) {
                      setWindowDocument(null);
                      setMission(
                        unavailableMission(
                          selection,
                          "AUTHENTICATION_REQUIRED",
                        ),
                      );
                    }
                    try {
                      const request = signingOut
                        ? auth.signOut()
                        : auth.signIn();
                      request.catch(() =>
                        setNotice(
                          "Sign-in could not complete. Please try again.",
                        ),
                      );
                    } catch {
                      setNotice(
                        "Sign-in could not complete. Please try again.",
                      );
                    }
                  }}
                >
                  {authState.status === "signing_in"
                    ? "Cancel sign in"
                    : authState.acquisition || authState.content
                      ? "Sign out"
                      : "Sign in"}
                </button>
              </div>
            ) : null}
          </div>
        </header>
        <div className="notice" role="status">
          {visibleNotice}
        </div>
        {build ? (
          <details className="build-details">
            <summary>Build details</summary>
            <dl>
              <dt>Version</dt>
              <dd>{build.version}</dd>
              <dt>Source revision</dt>
              <dd>
                <code>{build.source_revision}</code>
              </dd>
              <dt>Build identity</dt>
              <dd>
                <code>{build.build_identity}</code>
              </dd>
              {build.native_client_ref ? (
                <>
                  <dt>Native client reference</dt>
                  <dd>
                    <code>{build.native_client_ref}</code>
                  </dd>
                </>
              ) : null}
              <dt>Transport</dt>
              <dd>{`${build.transport} / ${build.state}`}</dd>
            </dl>
          </details>
        ) : null}
        {content}
        {d && missionNavigation.includes(active) && !conversationActive && (
          <section className="card">
            <h2>Missingness and source state</h2>
            {d.missingness.length ? (
              <ul className="missing">
                {d.missingness.map((x, i) => (
                  <li key={i}>
                    <State value={x.missingness_class} />{" "}
                    <code>{x.target_field}</code> — {x.reason}
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>
                No missingness facts were projected. This adds no freshness
                claim.
              </Empty>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
