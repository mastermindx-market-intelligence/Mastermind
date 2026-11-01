import { normalizeResultReferencesSelection } from "./result-references";

// Explicit read-only choice among validated programme root candidates for one
// workspace. Choosing a root only opens that root's retained result history;
// it never starts, switches or accepts a current Mission and never touches a
// current action. The parent mounts this as a bounded utility inset in the
// existing projects view (not a new dashboard) and keys/clears it on its
// auth/host/source identity epoch, so this component keeps no state of its
// own: selection authority is the parent's selectedRootJobId prop, never the
// URL, and no candidate is ever auto-selected, newest-first or otherwise.

// Presentation copy only. Root identifiers stay verbatim; every string below
// has an exact zh-CN counterpart so both locales show the same information.
const ROOT_TITLE = "Choose work and review history";
const ROOT_CANDIDATES_LABEL = "Available missions";
const UNKNOWN_NOTICE =
  "The programme root source state is unknown, so no root can be chosen.";
const INVALID_NOTICE =
  "The reported programme root list is invalid, so no root can be chosen.";
const RESOLVED_EXPLANATION = "Read retained work and review results for this mission.";
const CONFLICT_EXPLANATION =
  "Multiple missions are linked to this project. Choose one to read retained " +
  "work and review results; the current Mission stays unresolved.";
const SELECTED_LABEL = "Selected";
const UNLISTED_NOTICE =
  "The recorded root is not among the reported candidates.";
const MORE_LABEL = "More missions";

const STATIC_ZH: Record<string, string> = {
  [ROOT_TITLE]: "选择工作和审阅历史",
  [ROOT_CANDIDATES_LABEL]: "可用任务",
  [UNKNOWN_NOTICE]: "项目根来源状态未知，因此无法选择根。",
  [INVALID_NOTICE]: "报告的项目根列表无效，因此无法选择根。",
  [RESOLVED_EXPLANATION]:
    "读取此任务保留的工作和审阅结果。",
  [CONFLICT_EXPLANATION]:
    "此项目关联多个任务。选择其中一个以读取保留的工作和审阅结果；当前任务仍未确定。",
  [SELECTED_LABEL]: "已选择",
  [UNLISTED_NOTICE]: "记录的根不在报告的候选列表中。",
  [MORE_LABEL]: "更多任务",
};

const MAX_CANDIDATES = 50;
const VISIBLE_CHOICES = 8;

export interface RetainedRootChoiceProps {
  workRef: string;
  rootCandidates: string[];
  rootState: "RESOLVED" | "CONFLICT" | "UNKNOWN";
  selectedRootJobId: string | null;
  locale: "en" | "zh-CN";
  onChooseRoot: (selection: { workRef: string; rootJobId: string }) => void;
}

/** Candidate vectors are accepted only when every entry is a valid job token
 * and the vector is bounded and duplicate-free. State and vector must also
 * agree: RESOLVED carries exactly one candidate, CONFLICT at least two, and
 * UNKNOWN never offers a choice. Rejected input renders a bounded notice
 * with no buttons and no callback; nothing is trimmed into validity. */
function normalizeRootCandidates(value: unknown, workRef: string): string[] | null {
  if (!Array.isArray(value)) return null;
  if (value.length < 1 || value.length > MAX_CANDIDATES) return null;
  const seen = new Set<string>();
  for (const item of value) {
    if (!normalizeResultReferencesSelection({ workRef, rootJobId: item })) return null;
    if (seen.has(item)) return null;
    seen.add(item);
  }
  return value;
}

export function RetainedRootChoice(props: RetainedRootChoiceProps) {
  const {
    workRef,
    rootCandidates,
    rootState,
    selectedRootJobId,
    locale,
    onChooseRoot,
  } = props;
  const t = (value: string) =>
    locale === "zh-CN" ? STATIC_ZH[value] ?? value : value;
  const candidates = normalizeRootCandidates(rootCandidates, workRef);

  const notice = (text: string) => (
    <section className="card" aria-label={t(ROOT_TITLE)}>
      <h2 className="section-title">{t(ROOT_TITLE)}</h2>
      <p className="muted" role="status">
        {text}
      </p>
    </section>
  );

  if (rootState !== "RESOLVED" && rootState !== "CONFLICT") return notice(t(UNKNOWN_NOTICE));
  if (candidates === null) return notice(t(INVALID_NOTICE));
  if (rootState === "RESOLVED" && candidates.length !== 1)
    return notice(t(INVALID_NOTICE));
  if (rootState === "CONFLICT" && candidates.length < 2)
    return notice(t(INVALID_NOTICE));

  const renderChoice = (rootJobId: string) => {
    const selected = selectedRootJobId === rootJobId;
    return (
      <li key={rootJobId}>
        <button
          type="button"
          className="button"
          aria-pressed={selected}
          onClick={() => onChooseRoot({ workRef, rootJobId })}
        >
          {rootJobId}
        </button>
        {selected ? <small className="muted">{t(SELECTED_LABEL)}</small> : null}
      </li>
    );
  };

  return (
    <section className="card" aria-label={t(ROOT_TITLE)}>
      <h2 className="section-title">{t(ROOT_TITLE)}</h2>
      <p className="muted">
        {rootState === "CONFLICT"
          ? t(CONFLICT_EXPLANATION)
          : t(RESOLVED_EXPLANATION)}
      </p>
      {selectedRootJobId !== null && !candidates.includes(selectedRootJobId) ? (
        <p className="muted">{t(UNLISTED_NOTICE)}</p>
      ) : null}
      <ul className="items" aria-label={t(ROOT_CANDIDATES_LABEL)}>
        {candidates.slice(0, VISIBLE_CHOICES).map(renderChoice)}
      </ul>
      {candidates.length > VISIBLE_CHOICES ? (
        <details>
          <summary>
            {t(MORE_LABEL)} ({candidates.length - VISIBLE_CHOICES})
          </summary>
          <ul className="items">
            {candidates.slice(VISIBLE_CHOICES).map(renderChoice)}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
