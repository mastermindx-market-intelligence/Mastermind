import { useId } from "react";
import type { MissionSelection } from "./mission";
import {
  resolveWorkMissionLink,
  type WorkMissionLinkInput,
  type WorkMissionLinkReason,
} from "./work-mission-link";

export interface WorkMissionLinkProps extends WorkMissionLinkInput {
  /** Navigation only; the incumbent Mission reader rechecks the exact pair. */
  onOpenMission: (selection: MissionSelection) => void;
}

const unavailableCopy: Record<WorkMissionLinkReason, string> = {
  ACQUISITION_UNAVAILABLE:
    "Mission access is unavailable. The selected work stays visible.",
  WORK_UNAVAILABLE:
    "The selected Work observation is no longer available. Read it again before opening a Mission.",
  PROGRAMS_UNAVAILABLE:
    "The Programs source is unavailable. No Mission link was guessed.",
  PROGRAMS_INVALID:
    "The Programs relationship could not be qualified. No Mission link was guessed.",
  ROOT_UNJOINED: "No qualified Program match is available for this root.",
  ROOT_CONFLICT:
    "The Programs view contains a conflicting relationship for this root.",
};

/**
 * N9's selected-root navigation leaf, not a Work feed or action authority.
 * No reads, effects, selection store, timer, or source-freshness inference.
 */
export function WorkMissionLink(props: WorkMissionLinkProps) {
  const descriptionId = useId();
  const resolution = resolveWorkMissionLink(props);
  const resolved = resolution.state === "RESOLVED";
  const open = () => {
    // Recheck current input, and never silently retarget an already-painted
    // button if the owning data structure changed without a React render.
    const current = resolveWorkMissionLink(props);
    if (current.state !== "RESOLVED" || resolution.state !== "RESOLVED") return;
    if (
      current.selection.workRef !== resolution.selection.workRef ||
      current.selection.rootJobId !== resolution.selection.rootJobId
    )
      return;
    props.onOpenMission(current.selection);
  };
  return (
    <section className="card" aria-label="Selected work Mission link">
      <div className="section-title">
        <div>
          <p className="eyebrow">SELECTED ROOT</p>
          <code>{props.rootJobId}</code>
        </div>
      </div>
      <h2>
        {resolved && resolution.title ? resolution.title : "Selected work"}
      </h2>
      <p className="muted" id={descriptionId}>
        {resolved
          ? "One qualified Program match in the returned view. Work and Programs are separate observations."
          : unavailableCopy[resolution.reason]}
      </p>
      <button
        type="button"
        className="primary"
        disabled={!resolved}
        aria-describedby={descriptionId}
        onClick={open}
      >
        {resolved ? "Open Mission" : "Mission unavailable"}
      </button>
      <p className="muted">
        Navigation only. The Mission reader checks access again; opening this
        view starts no work.
      </p>
    </section>
  );
}
