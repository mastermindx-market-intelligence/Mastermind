import { useId, useMemo, useState } from "react";
import type { ControlRoomState } from "./control-room";
import type { ProgramCard } from "./mission";
import "./control-room.css";

type Props = {
  state: ControlRoomState;
  canRefresh: boolean;
  onRefresh: () => void;
  onOpen: (workRef: string, rootJobId: string) => void;
};
type Filter = "all" | "attention" | "linked";
const human = (text: string | null) =>
  text ? text.replaceAll("_", " ").toLowerCase() : "Not reported";
const attention = (p: Readonly<ProgramCard>) =>
  p.rootState !== "RESOLVED" ||
  /blocked|hold|conflict|needs.?review|waiting.?external/i.test(p.state ?? "");
function Observed({ value }: { value: string | null }) {
  if (!value) return <>Observation time not supplied</>;
  return (
    <time dateTime={value}>
      {new Intl.DateTimeFormat("en-GB", {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "UTC",
      }).format(new Date(value))}{" "}
      UTC
    </time>
  );
}
function RefreshIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
    >
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M5 8a7.5 7.5 0 0 1 13-2l2 3M4 15l2 3a7.5 7.5 0 0 0 13-2" />
    </svg>
  );
}

/** Presentation only. Read owner and auth epoch stay in the original App host.
 * Every mission navigation uses its exact projected root; controls do not mint
 * an OAuth grant, worker status, pending operation or second programme cache.
 */
export function ControlRoomPanel({
  state,
  canRefresh,
  onRefresh,
  onOpen,
}: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const id = useId();
  const available = state.state === "AVAILABLE";
  const programs = available ? state.programs : [];
  const linked = programs.filter(
    (p) => p.rootState === "RESOLVED" && p.rootJobId !== null,
  ).length;
  const review = programs.filter(attention).length;
  const visible = useMemo(() => {
    const search = query.trim().toLocaleLowerCase();
    return programs
      .filter(
        (p) =>
          (filter !== "attention" || attention(p)) &&
          (filter !== "linked" ||
            (p.rootState === "RESOLVED" && p.rootJobId !== null)) &&
          (!search ||
            [p.title, p.workRef, p.state, p.nextAction].some((v) =>
              v?.toLocaleLowerCase().includes(search),
            )),
      )
      .map((p, index) => ({ p, index }))
      .sort(
        (a, b) =>
          Number(attention(b.p)) - Number(attention(a.p)) || a.index - b.index,
      )
      .map(({ p }) => p);
  }, [programs, query, filter]);
  const pending = state.state === "PENDING" || state.refreshPending === true;
  return (
    <section
      className="ccr-workspace"
      aria-label="Control Room workspace"
      aria-busy={pending}
    >
      <header className="ccr-hero">
        <div className="ccr-hero-copy">
          <span className="ccr-eyebrow">PRIORITIES & PROGRESS</span>
          <h2>Company overview</h2>
          <p>
            See what needs attention. Open the exact mission. Keep the source in
            view.
          </p>
        </div>
        <div className="ccr-hero-actions">
          <span className="ccr-source-pill">
            <span aria-hidden="true" />
            {available
              ? "Source observed"
              : pending
                ? "Reading source"
                : "Source unavailable"}
          </span>
          <button
            type="button"
            className="ccr-refresh"
            aria-label="Refresh Control Room"
            disabled={!canRefresh || pending}
            onClick={onRefresh}
          >
            <RefreshIcon />
            {pending ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {available ? (
        <>
          <div className="ccr-stats" aria-label="Observed programme coverage">
            <div>
              <span>Programmes observed</span>
              <strong>{programs.length}</strong>
              <small>In this bounded source</small>
            </div>
            <div>
              <span>Exact mission links</span>
              <strong>{linked}</strong>
              <small>Navigation, not worker liveness</small>
            </div>
            <div className={review ? "ccr-stat-attention" : ""}>
              <span>Needs review</span>
              <strong>{review}</strong>
              <small>Blocked or missing a clear root</small>
            </div>
          </div>
          <section className="ccr-cross-plane" aria-label="Cross-plane source evidence">
            <div className="ccr-cross-plane-head">
              <div>
                <h3>Cross-plane source evidence</h3>
                <p>Read-only source attribution. A merge or green check is not completion proof.</p>
              </div>
              <span>Execution not projected</span>
            </div>
            {state.crossPlane.state === "UNAVAILABLE" ? (
              <p role="status" className="ccr-cross-plane-unavailable">
                {state.crossPlane.reason === "NOT_INSTALLED"
                  ? "Session Truth is not connected to this installed Control Room."
                  : "Session Truth owner sources are unavailable; no healthy result was inferred."}
              </p>
            ) : (
              <>
                <p className="ccr-cross-plane-meta">
                  {state.crossPlane.viewState === "DEGRADED" ? "Incomplete source evidence" : "Source evidence composed"}
                  {" · "}{state.crossPlane.unknownCount} unknowns
                  {" · "}{state.crossPlane.unavailableCount} unavailable sources
                  {" · "}{state.crossPlane.digestVerified ? "Receipt digest verified" : "Receipt digest unverified"}
                </p>
                {state.crossPlane.cards.length === 0 ? (
                  <p className="ccr-cross-plane-unavailable">No source-authorized workstream attribution was established.</p>
                ) : state.crossPlane.cards.map((card) => (
                  <div className="ccr-cross-plane-card" key={card.workstream}>
                    <h4>{card.workstream}</h4>
                    {card.pullRequests.map((pr) => (
                      <p key={`${pr.repository}#${pr.number}`}>
                        <code>{pr.repository}#{pr.number}</code>
                        {" · "}Delivery: {pr.delivery}; CI: {pr.ci}
                        {" · "}Declared completion: {pr.declaredCompletion ?? "not established"}
                        {" · "}Proof state: {pr.proofState ?? "not established"}
                        {" · "}Native Linear link: {pr.linkedIssue ?? "not established"}
                      </p>
                    ))}
                    {card.issues.map((issue) => (
                      <p key={issue.issueId}>{issue.issueId}: {issue.status} (projection, not execution)</p>
                    ))}
                    {!card.pullRequests.length && !card.issues.length && (
                      <p>Neither an exact PR nor an exact Linear relationship was established.</p>
                    )}
                  </div>
                ))}
              </>
            )}
          </section>
          <div className="ccr-toolbar">
            <div
              className="ccr-filters"
              role="group"
              aria-label="Filter programmes"
            >
              {(
                [
                  ["all", "All programmes"],
                  ["attention", "Needs attention"],
                  ["linked", "Linked missions"],
                ] as const
              ).map(([value, title]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={filter === value}
                  onClick={() => setFilter(value)}
                >
                  {title}
                </button>
              ))}
            </div>
            <div className="ccr-search">
              <label htmlFor={id} className="ccr-sr-only">
                Find a programme
              </label>
              <svg
                viewBox="0 0 24 24"
                width="17"
                height="17"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
                aria-hidden="true"
              >
                <circle cx="10.5" cy="10.5" r="6.5" />
                <path d="m16 16 5 5" />
              </svg>
              <input
                id={id}
                type="search"
                value={query}
                maxLength={160}
                placeholder="Find a programme…"
                onChange={(e) => setQuery(e.currentTarget.value)}
                autoComplete="off"
              />
              {query && (
                <button
                  type="button"
                  aria-label="Clear search"
                  onClick={() => setQuery("")}
                >
                  ×
                </button>
              )}
            </div>
          </div>
          <div className="ccr-list-heading">
            <h3>Programme overview</h3>
            <span aria-live="polite">
              {visible.length} of {programs.length} shown
            </span>
          </div>
          <div
            className="ccr-programmes"
            role="region"
            aria-label="Programme overview"
          >
            {visible.map((p) => (
              <article className="ccr-programme" key={p.workRef}>
                <div className="ccr-programme-leading" aria-hidden="true">
                  {attention(p) ? "!" : "↗"}
                </div>
                <div className="ccr-programme-content">
                  <div className="ccr-programme-title">
                    <h4>{p.title || p.workRef}</h4>
                    <span
                      className={
                        attention(p) ? "ccr-badge ccr-badge-warn" : "ccr-badge"
                      }
                    >
                      {human(p.state)}
                    </span>
                  </div>
                  <code>{p.workRef}</code>
                  <p className="ccr-next-action">
                    <span>Next step</span>
                    {p.nextAction ||
                      (p.nextActionWithheld
                        ? "Next action withheld by the source."
                        : "The owner has not supplied a next action.")}
                  </p>
                  <details className="ccr-programme-source">
                    <summary>Source and mission link</summary>
                    <dl>
                      <div>
                        <dt>Root qualification</dt>
                        <dd>{human(p.rootState)}</dd>
                      </div>
                      <div>
                        <dt>Exact mission</dt>
                        <dd>{p.rootJobId || "Not established"}</dd>
                      </div>
                    </dl>
                  </details>
                </div>
                <div className="ccr-programme-action">
                  {p.rootState === "RESOLVED" && p.rootJobId ? (
                    <button
                      type="button"
                      onClick={() => onOpen(p.workRef, p.rootJobId!)}
                      aria-label={`View qualified Mission for ${p.title || p.workRef}`}
                    >
                      View mission <span aria-hidden="true">↗</span>
                    </button>
                  ) : (
                    <span className="ccr-link-withheld">
                      {p.rootState === "CONFLICT"
                        ? "Resolve competing mission links"
                        : "Waiting for an exact mission link"}
                    </span>
                  )}
                </div>
              </article>
            ))}
            {!visible.length && (
              <div className="ccr-empty">
                <h4>
                  {programs.length
                    ? "No programmes match your search."
                    : "No programmes in this observation."}
                </h4>
                <p>
                  {programs.length
                    ? "Try a different name or clear your filters."
                    : "This bounded source is empty; it does not prove there is no company work."}
                </p>
                {(query || filter !== "all") && (
                  <button
                    onClick={() => {
                      setQuery("");
                      setFilter("all");
                    }}
                  >
                    Clear filters
                  </button>
                )}
              </div>
            )}
          </div>
          <footer className="ccr-observation">
            <span>
              {programs.length} source-qualified Programs ·{" "}
              <Observed value={state.observedAt} />
            </span>
            <span>
              {state.freshness === "UNKNOWN"
                ? "Freshness not supplied"
                : `Source publication ${state.publicationSeq}`}
            </span>
            {state.refreshInFlight && <span>Source refresh in progress</span>}
          </footer>
        </>
      ) : (
        <div className="ccr-unavailable" role="status">
          <div className="ccr-unavailable-symbol" aria-hidden="true">
            {pending ? "◌" : "—"}
          </div>
          <h3>
            {pending
              ? "Reading your workspace"
              : "The source is not available yet"}
          </h3>
          <p>
            {pending
              ? "Checking the existing authenticated Control Room source."
              : "The signed Control Room read is unavailable. No programme state or action authority is inferred."}
          </p>
          <small>
            {pending
              ? "A read does not submit work or start a worker."
              : "Sign in with an enrolled workspace account, then refresh. Missing data is not an empty queue."}
          </small>
        </div>
      )}

      <details className="ccr-access">
        <summary>
          <span>Workspace access and controls</span>
          <span className="ccr-access-status">
            {available ? "Signed member READ" : "Authentication required"}
          </span>
        </summary>
        <div className="ccr-access-content">
          <p>
            <strong>
              All authenticated workspace members are intended to have access.
            </strong>{" "}
            The designated main account is <span>admin@mastermind-x.com</span>.
            An account name on this screen is not an identity or permission
            proof.
          </p>
          <p>
            Discovery and Open, Bind, Unbind, and Refresh builds are not
            connected in this source build. They require the existing verified
            account and action owners; a workspace read permission alone does
            not enable them.
          </p>
          <p>
            No new cache, worker control, or privileged TCP listener is created
            by this screen. Installation and worker activation remain separate
            operations.
          </p>
        </div>
      </details>
    </section>
  );
}
