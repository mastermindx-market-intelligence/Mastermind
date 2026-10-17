"""EAF A5 — point-in-time calibration harness (report-only).

F0G §15: *point-in-time or it does not count*.  At replay time ``t`` the
evaluator may use only facts observable at ``t``.  Later outcomes and
corrections may **label** an episode but can never become contemporaneous
inputs, and unreconstructable data is an explicit gap rather than a silent
default.

This module is the instrument, not the verdict.  It computes the F0G §15
metric families over an episode set and reports a promotion verdict against the
hard zero-violation laws.  It never promotes anything itself, writes nothing,
and holds no state between calls.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from control_plane.executive_attention_frontier import (
    AttentionClass,
    AttentionDemand,
    AuthorityRequirement,
    ProjectionRelation,
    Serviceability,
    compute_attention_frontier,
)

SCHEMA = "mastermind.executive_attention_calibration.v1"

__all__ = [
    "SCHEMA",
    "Episode",
    "CalibrationReport",
    "evaluate_episodes",
    "measure_baseline_scanning_burden",
]


class HindsightLeak(RuntimeError):
    """Raised when an episode would feed post-decision truth into the decision."""


@dataclasses.dataclass(frozen=True, slots=True)
class Episode:
    """One point-in-time decision boundary plus its later, separate labels.

    ``demands`` are the facts observable at ``decision_at``.  ``severe_labels``
    are the demand ids a later adjudication accepted as genuinely needing an
    interrupt.  Labels are evaluation-only and are never passed to the engine.
    """

    episode_id: str
    decision_at: str
    demands: tuple[AttentionDemand, ...]
    severe_labels: frozenset[str] = frozenset()
    authority_labels: Mapping[str, str] = dataclasses.field(default_factory=dict)
    unreplayable_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for demand in self.demands:
            observed = demand.admission_source.observed_at
            if observed is not None and observed > self.decision_at:
                raise HindsightLeak(
                    f"{self.episode_id}: demand {demand.demand_id} carries a source "
                    f"observed at {observed}, after the decision boundary "
                    f"{self.decision_at}"
                )


@dataclasses.dataclass(frozen=True, slots=True)
class CalibrationReport:
    schema: str
    episodes: int
    severe_interrupt_misses: tuple[str, ...]
    false_severe_interrupts: tuple[str, ...]
    authority_escalations: tuple[str, ...]
    suppressed_independent_interrupts: tuple[str, ...]
    semantic_suppressions: tuple[str, ...]
    truthful_unknown_rate: float
    valid_waits_preserved: int
    invented_waits: tuple[str, ...]
    fairness_debt: int
    baseline_scan_items: int
    frontier_scan_items: int
    interruption_volume: int
    unreplayable_gaps: tuple[str, ...]
    promotion_verdict: str
    promotion_blockers: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def measure_baseline_scanning_burden(work_cards: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Baseline: what the executive must scan today, with no attention split.

    The honest baseline is the raw card count the Control Room presents plus
    how many of those carry any explicit attention obligation at all — a card
    with none cannot be triaged without reading it.
    """
    total = len(work_cards)
    with_obligation = sum(1 for c in work_cards if c.get("attention_ids"))
    return {
        "cards_presented": total,
        "cards_with_explicit_attention_obligation": with_obligation,
        "cards_requiring_manual_read": total - with_obligation,
    }


def evaluate_episodes(episodes: Sequence[Episode]) -> CalibrationReport:
    """Run report-only point-in-time evaluation over an episode set."""
    misses: list[str] = []
    false_severe: list[str] = []
    escalations: list[str] = []
    suppressed: list[str] = []
    semantic: list[str] = []
    invented_waits: list[str] = []
    gaps: list[str] = []
    unknown_flagged = 0
    total_items = 0
    waits = 0
    debt = 0
    baseline_scan = 0
    frontier_scan = 0
    interruptions = 0

    for episode in episodes:
        gaps.extend(f"{episode.episode_id}:{g}" for g in episode.unreplayable_gaps)
        result = compute_attention_frontier(
            episode.demands, snapshot_identity=episode.decision_at
        )
        visible = result.visible()
        baseline_scan += len(episode.demands)
        frontier_scan += len(visible)

        interrupt_ids = {
            i.demand_id
            for i in result.items
            if i.attention_class is AttentionClass.INTERRUPT_NOW
        }
        visible_ids = {i.demand_id for i in visible}
        interruptions += len(interrupt_ids)

        # A severe episode that the frontier did not raise as an interrupt at all.
        for label in sorted(episode.severe_labels):
            if label not in interrupt_ids:
                misses.append(f"{episode.episode_id}:{label}")
            elif label not in visible_ids:
                # Raised but not renderable anywhere — a hidden interrupt.
                suppressed.append(f"{episode.episode_id}:{label}")

        for i in result.items:
            total_items += 1
            if i.issues:
                unknown_flagged += 1
            if i.attention_class is AttentionClass.VALID_WAIT:
                waits += 1
            if i.attention_class is AttentionClass.INTERRUPT_NOW:
                if episode.severe_labels and i.demand_id not in episode.severe_labels:
                    false_severe.append(f"{episode.episode_id}:{i.demand_id}")
            # Authority escalation: the engine claimed more authority than the
            # adjudicated label allows.
            expected = episode.authority_labels.get(i.demand_id)
            if expected is not None and i.authority_requirement.value != expected:
                if i.authority_requirement is AuthorityRequirement.CHAIRMAN:
                    escalations.append(
                        f"{episode.episode_id}:{i.demand_id}"
                        f" -> CHAIRMAN (labelled {expected})"
                    )
            # A wait the engine asserted with no authored wait fact behind it.
            if (
                i.attention_class is AttentionClass.VALID_WAIT
                and i.wait_context is None
            ):
                invented_waits.append(f"{episode.episode_id}:{i.demand_id}")

        for authority, entry in (
            result.coverage_summary.get("fairness_debt_by_authority") or {}
        ).items():
            debt += int(entry.get("deferred_ordinary", 0))

        # Semantic suppression: anything omitted without an exact receipt.
        omitted = {
            i.demand_id
            for i in result.items
            if i.projection_relation is not ProjectionRelation.ROOT_VISIBLE
        }
        receipted = {o.demand_id for o in result.omissions}
        semantic.extend(
            f"{episode.episode_id}:{d}" for d in sorted(omitted - receipted)
        )

    blockers: list[str] = []
    if misses:
        blockers.append(f"{len(misses)} accepted severe-interrupt miss(es)")
    if escalations:
        blockers.append(f"{len(escalations)} priority-driven authority escalation(s)")
    if suppressed:
        blockers.append(f"{len(suppressed)} independent-interrupt suppression(s)")
    if semantic:
        blockers.append(f"{len(semantic)} omission(s) without an exact receipt")
    if invented_waits:
        blockers.append(f"{len(invented_waits)} invented wait(s)")
    if gaps:
        blockers.append(f"{len(gaps)} unreplayable input gap(s)")
    if baseline_scan and frontier_scan >= baseline_scan:
        blockers.append("no reduction in executive scanning versus baseline")

    verdict = "PROMOTABLE" if not blockers else "NOT_PROMOTABLE"
    return CalibrationReport(
        schema=SCHEMA,
        episodes=len(episodes),
        severe_interrupt_misses=tuple(misses),
        false_severe_interrupts=tuple(false_severe),
        authority_escalations=tuple(escalations),
        suppressed_independent_interrupts=tuple(suppressed),
        semantic_suppressions=tuple(semantic),
        truthful_unknown_rate=(unknown_flagged / total_items) if total_items else 0.0,
        valid_waits_preserved=waits,
        invented_waits=tuple(invented_waits),
        fairness_debt=debt,
        baseline_scan_items=baseline_scan,
        frontier_scan_items=frontier_scan,
        interruption_volume=interruptions,
        unreplayable_gaps=tuple(gaps),
        promotion_verdict=verdict,
        promotion_blockers=tuple(blockers),
    )
