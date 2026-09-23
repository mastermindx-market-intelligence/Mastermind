import type { AuthState, MissionHost } from "./host";
import type {
  ObservedMissionAssociation,
  WindowDocument,
} from "./workspace-contract";
import { observedMissionAssociation } from "./workspace-contract";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
export const navigation = [
  "Today",
  "Programs",
  "Mission Workspace",
  "Connections",
  "Evidence",
  "Conversation",
] as const;
type View = (typeof navigation)[number];
interface BuildReceipt {
  version: string;
  source_revision: string;
  build_identity: string;
  transport: string;
  state: string;
}
declare global {
  interface Window {
    MastermindMissionHost?: MissionHost;
  }
}
type ProgramIndex =
  | ReturnType<typeof programsFromControlRoom>
  | { programs: []; state: "PENDING"; reason: "SOURCE_READ_PENDING" };
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
    [index, setIndex] = useState<ProgramIndex>({
      programs: [],
      state: "PENDING",
      reason: "SOURCE_READ_PENDING",
    }),
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
    previousAuth = useRef<string | null>(
      authState ? JSON.stringify(authState) : null,
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
    missionSelectionState =
      native && !window.MastermindMissionHost?.readPrograms
        ? "NATIVE"
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
  const resultContext = useMemo(
    () => ({ selection, authRevision, missionV3 }),
    [selection, authRevision, missionV3],
  );
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
    previousView = useRef(active);
  useLayoutEffect(() => {
    if (previousView.current === active) return;
    previousView.current = active;
    // A removed content action leaves focus on body. Preserve connected
    // controls (including navigation), and never move focus for data refreshes.
    if (!document.activeElement || document.activeElement === document.body)
      routeHeading.current?.focus();
  }, [active]);
  useEffect(
    () =>
      window.MastermindMissionHost?.auth?.subscribe((state) => {
        const serialized = JSON.stringify(state);
        if (serialized === previousAuth.current) return;
        previousAuth.current = serialized;
        bumpInvalidation();
        setAuthState(state);
        setAuthRevision((n) => n + 1);
        setWindowDocument(null);
        setAssociation(null);
        setMissionV3(null);
        setResultState({ kind: "IDLE" });
        if (!state.acquisition)
          setMission(unavailableMission(null, "AUTHENTICATION_REQUIRED"));
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
    if (active !== "Conversation")
      return () => {
        attached = false;
        controller.abort();
      };
    const run = async () => {
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
      } catch {
        if (!stillCurrent()) return;
        setWindowDocument(null);
        setAssociation(null);
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
    if (native && !window.MastermindMissionHost?.readPrograms) {
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
    if (typeof read !== "function") {
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
      .then(() => read({ signal: controller.signal }))
      .then((raw) => {
        if (attached && programRequest.current === current)
          setIndex(programsFromControlRoom(raw));
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
  }, [native, authRevision, authState?.acquisition]);
  useEffect(() => {
    const restoreSelection = () => {
      const next = selectionFromLocation();
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
      setActive("Mission Workspace");
    };
    window.addEventListener("popstate", restoreSelection);
    return () => window.removeEventListener("popstate", restoreSelection);
  }, []);
  useEffect(() => {
    let attached = true;
    const current = ++missionRequest.current,
      controller = new AbortController();
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
    conversationActive = active === "Conversation",
    conversationState = windowPending
      ? "SOURCE_READ_PENDING"
      : association
        ? "OBSERVED_MISSION_ASSOCIATION"
        : windowDocument && authState?.content
          ? "UNBOUND"
          : "UNAVAILABLE",
    headerState = conversationActive
      ? conversationState
      : (d?.read_state.state ?? "UNAVAILABLE"),
    headerSummary = conversationActive
      ? association
        ? "Observed window for this Mission from separately authorized owner observations."
        : windowDocument && authState?.content
          ? "A global current permitted window. No relationship to the selected Mission is proven."
          : "No Mission-linked conversation is currently established."
      : d
        ? d.mission.root_job_id && d.read_state.state === "CURRENT"
          ? "A bounded source-qualified mission, current as of its owner observation."
          : d.mission.root_job_id
            ? `This mission projection is ${label(d.read_state.state)}; source qualification is not current.`
            : "A qualified reconciliation state; no mission root is established."
        : "No producer document is currently admitted.",
    visibleNotice = conversationActive
      ? association
        ? "Observed window for this Mission. Independent owner observations."
        : windowDocument && authState?.content
          ? "This current permitted window is not linked to the selected Mission."
          : windowPending
            ? "Reading the current permitted window…"
            : "No Mission-linked conversation is currently established."
      : notice,
    open = (w: string, r: string | null) => {
      if (r) {
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
        setActive("Mission Workspace");
      }
    };
  let content: React.ReactNode;
  if (active === "Today")
    content = (
      <section className="card">
        <h2>Today</h2>
        <p className="muted">
          Open Programs to choose a mission. Current work will appear when an
          approved workspace source is available.
        </p>
        <button className="primary" onClick={() => setActive("Programs")}>
          Open Programs
        </button>
      </section>
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
  else if (active === "Conversation")
    content = (
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
  else if (active === "Connections") content = <Connections d={d} />;
  else if (active === "Evidence") content = <Evidence d={d} />;
  else content = <Conversation />;
  return (
    <div className="shell">
      <a className="skip" href="#content">
        Skip to workspace
      </a>
      <aside>
        <div className="brand">
          ▦{" "}
          <span>
            MASTERMIND<small>OPERATING SYSTEM</small>
          </span>
        </div>
        <nav aria-label="Workspace navigation">
          {navigation.map((x) => (
            <button
              key={x}
              className={active === x ? "active" : ""}
              aria-current={active === x ? "page" : undefined}
              onClick={() => setActive(x)}
            >
              {x}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <b>Read-only workspace</b>
          <br />
          Source, execution, review, transport, acceptance and posture remain
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
              <dt>Transport</dt>
              <dd>{`${build.transport} / ${build.state}`}</dd>
            </dl>
          </details>
        ) : null}
        {content}
        {d && !conversationActive && (
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
