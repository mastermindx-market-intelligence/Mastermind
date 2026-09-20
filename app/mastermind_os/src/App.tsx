import { useEffect, useMemo, useRef, useState } from "react";
import {
  allEvidence,
  decodeMission,
  normalizeSelection,
  programsFromControlRoom,
  relationshipsForMission,
  selectionFromLocation,
  unavailableMission,
  type MissionDocument,
  type MissionRead,
  type MissionSelection,
  type UnavailableMission,
} from "./mission";
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
    MastermindMissionHost?: {
      readMission?: MissionRead;
      selection?: unknown;
      controlRoom?: unknown;
    };
  }
}
const display = (v: unknown, f = "Not established") =>
  typeof v === "string" && v ? v : f;
const label = (v: unknown) => display(v, "UNKNOWN").replaceAll("_", " ");
const isDoc = (v: MissionDocument | UnavailableMission): v is MissionDocument =>
  !("kind" in v);
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
export function App() {
  const native = "__TAURI_INTERNALS__" in window,
    initial = useMemo(
      () =>
        normalizeSelection(window.MastermindMissionHost?.selection) ??
        selectionFromLocation(),
      [],
    ),
    index = useMemo(
      () => programsFromControlRoom(window.MastermindMissionHost?.controlRoom),
      [],
    ),
    [selection, setSelection] = useState<MissionSelection | null>(initial),
    [active, setActive] = useState<View>("Today"),
    [mission, setMission] = useState<MissionDocument | UnavailableMission>(() =>
      unavailableMission(
        initial,
        initial ? "SOURCE_NOT_READ" : "EXACT_SELECTION_REQUIRED",
      ),
    ),
    [notice, setNotice] = useState("A qualified source has not been read."),
    [build, setBuild] = useState<BuildReceipt | null>(null),
    request = useRef(0);
  useEffect(() => {
    let attached = true;
    const current = ++request.current,
      controller = new AbortController();
    if (native) {
      setMission(
        unavailableMission(selection, "NATIVE_TRANSPORT_UNCONFIGURED"),
      );
      setNotice("Workspace connection unavailable. Current work was not read.");
      import("@tauri-apps/api/core")
        .then(({ invoke }) => invoke<BuildReceipt>("readiness"))
        .then((r) => {
          if (attached && request.current === current) setBuild(r);
        })
        .catch(() => {
          if (attached && request.current === current)
            setNotice(
              "Native readiness receipt unavailable. No source request was attempted.",
            );
        });
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
    const read = window.MastermindMissionHost?.readMission ?? null;
    if (!read) {
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
    read({ ...selection, signal: controller.signal })
      .then((raw) => {
        if (!attached || request.current !== current) return;
        const decoded = decodeMission(raw, selection);
        if (decoded) {
          setMission(decoded);
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
          request.current === current &&
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
  }, [selection, native]);
  const candidate = isDoc(mission) ? mission : null,
    d =
      candidate &&
      selection &&
      candidate.program.work_ref === selection.workRef &&
      (candidate.mission.root_job_id === null ||
        candidate.mission.root_job_id === selection.rootJobId)
        ? candidate
        : null,
    open = (w: string, r: string | null) => {
      if (r) {
        setMission(
          unavailableMission(
            { workRef: w, rootJobId: r },
            "SOURCE_READ_PENDING",
          ),
        );
        setNotice("Reading the exact selected mission pair…");
        setSelection({ workRef: w, rootJobId: r });
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
          <State value={index.state} />
        </div>
        {index.programs.length ? (
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
        ) : (
          <Empty>
            {window.MastermindMissionHost?.controlRoom == null
              ? "Workspace connection unavailable. Programs will appear when an approved source is available."
              : `The supplied Programs source did not match the required contract (${index.reason}).`}
          </Empty>
        )}
      </section>
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
  else if (active === "Mission Workspace") content = <Mission d={d} />;
  else if (active === "Connections") content = <Connections d={d} />;
  else if (active === "Evidence") content = <Evidence d={d} />;
  else
    content = (
      <section className="card">
        <div className="section-title">
          <h2>Conversation</h2>
          <State value={d.conversation.state} />
        </div>
        <p className="muted">{d.conversation.reason_codes.join(" · ")}</p>
        <Empty>
          No qualified Steward endpoint, viewer grant, connected reader,
          lifecycle control, or content store is installed. Existing owner and
          effect boundaries remain unchanged.
        </Empty>
      </section>
    );
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
            <h1>{active}</h1>
            <p>
              {d
                ? d.mission.root_job_id && d.read_state.state === "CURRENT"
                  ? "A bounded rendering of one exact source-qualified mission."
                  : d.mission.root_job_id
                    ? `This mission projection is ${label(d.read_state.state)}; source qualification is not current.`
                    : "A qualified reconciliation state; no mission root is established."
                : "No producer document is currently admitted."}
            </p>
          </div>
          <State value={d?.read_state.state ?? "UNAVAILABLE"} />
        </header>
        <div className="notice" role="status">
          {notice}
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
        {d && (
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
