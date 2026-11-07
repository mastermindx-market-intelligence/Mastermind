"""Train/dev window admission for the GLT T15/T16 harness (no outcome reads).

``WindowGuard`` is built ONLY from the frozen T14 preregistration card.  It
admits forward-return rows into the train or dev fold and refuses -- never
clips -- any row whose anchor or outcome window reaches the card's reserved
window.  Every refusal is counted and kept with its reason so a run can quote
``refused_count``.  Nothing here reads data, records a look, or touches the
``ForwardLedger`` custodian; looks belong to T20/T24.

The T13 horizon-counting rule ("declared-calendar sessions from the card
govern; an estimator horizon counted on supplied closes is admissible only when
every declared session in the window is supplied, otherwise the outcome is
immature and never shifted") is enforced here when the caller supplies the
declared and supplied session sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from brain.liquidity_lab.contracts import ContractError
from brain.liquidity_lab.preregistration import card_hash

FOLDS = ("train", "dev")


class ReservedWindowTouched(ContractError):
    """A row's anchor or outcome window reaches the card's reserved window."""


@dataclass(frozen=True, slots=True)
class WindowRefusal:
    shock_id: str
    target_id: str
    horizon_bdays: int
    anchor_session: date
    exit_session: date
    fold: str
    reason: str


def _card_mapping(card: Any) -> Mapping[str, Any]:
    payload = getattr(card, "payload", None)
    if payload is not None:
        return payload
    if isinstance(card, Mapping):
        return card
    raise TypeError("expected a PreregistrationCard or a card mapping")


def _parse(value: Any, name: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ContractError(f"card window {name} is not an ISO date: {value!r}") from exc


@dataclass
class WindowGuard:
    """Fold admission from the card windows; refusals are recorded, never clipped."""

    card_hash: str
    train_start: date
    train_end: date
    dev_start: date
    dev_end: date
    reserved_start: date
    purge_sessions: int
    refused_count: int = 0
    admitted_count: int = 0
    refusals: list[WindowRefusal] = field(default_factory=list)

    @classmethod
    def from_card(cls, card: Any) -> "WindowGuard":
        mapping = _card_mapping(card)
        recorded = mapping.get("card_hash")
        computed = card_hash(mapping)
        if recorded != computed:
            raise ContractError(
                f"card_hash mismatch: recorded {recorded!r} != computed {computed}"
            )
        windows = mapping.get("windows")
        if not isinstance(windows, Mapping):
            raise ContractError("card has no windows block")
        guard = cls(
            card_hash=computed,
            train_start=_parse(windows.get("train_start"), "train_start"),
            train_end=_parse(windows.get("train_end"), "train_end"),
            dev_start=_parse(windows.get("dev_start"), "dev_start"),
            dev_end=_parse(windows.get("dev_end"), "dev_end"),
            reserved_start=_parse(windows.get("reserved_start"), "reserved_start"),
            purge_sessions=int(windows.get("purge_sessions", 0)),
        )
        if not (
            guard.train_start <= guard.train_end < guard.dev_start <= guard.dev_end
            < guard.reserved_start
        ):
            raise ContractError("card windows are not ordered train < dev < reserved")
        return guard

    # ------------------------------------------------------------------ checks
    def _reason(self, row: Any, fold: str) -> str | None:
        anchor: date = row.anchor_session
        exit_: date = row.exit_session
        if anchor >= self.reserved_start or exit_ >= self.reserved_start:
            return "reserved_window"
        if anchor < self.train_start:
            return "before_train_start"
        if fold == "train":
            if anchor > self.train_end:
                return "anchor_after_train_end"
            if exit_ >= self.dev_start:
                return "outcome_matures_in_dev"
        elif fold == "dev":
            if anchor > self.dev_end:
                return "anchor_after_dev_end"
        else:
            raise ContractError(f"unknown fold {fold!r}; expected one of {FOLDS}")
        return None

    @staticmethod
    def _counting_reason(
        row: Any,
        declared_sessions: Sequence[date] | None,
        supplied_sessions: Mapping[str, Iterable[date]] | None,
    ) -> str | None:
        if declared_sessions is None:
            return None
        declared = sorted(set(declared_sessions))
        window = [d for d in declared if row.anchor_session < d <= row.exit_session]
        if row.anchor_session not in set(declared):
            return "anchor_not_a_declared_session"
        if len(window) != int(row.horizon_bdays):
            return f"horizon_count_mismatch:declared={len(window)}"
        if supplied_sessions is not None:
            supplied = set(supplied_sessions.get(row.target_id, ()))
            missing = [d for d in [row.anchor_session, *window] if d not in supplied]
            if missing:
                return f"immature_outcome:missing_sessions={len(missing)}"
        return None

    def admit(
        self,
        observations: Iterable[Any],
        *,
        fold: str = "dev",
        declared_sessions: Sequence[date] | None = None,
        supplied_sessions: Mapping[str, Iterable[date]] | None = None,
    ) -> list[Any]:
        """Return only admissible rows for ``fold`` and record every refusal.

        ``fold="train"``: train_start <= anchor <= train_end and exit < dev_start.
        ``fold="dev"`` (the walk-forward development set, train + dev windows):
        train_start <= anchor <= dev_end and exit < reserved_start.
        """

        if fold not in FOLDS:
            raise ContractError(f"unknown fold {fold!r}; expected one of {FOLDS}")
        admitted: list[Any] = []
        for row in observations:
            reason = self._reason(row, fold) or self._counting_reason(
                row, declared_sessions, supplied_sessions
            )
            if reason is None:
                admitted.append(row)
                continue
            self.refused_count += 1
            self.refusals.append(
                WindowRefusal(
                    shock_id=row.shock_id,
                    target_id=row.target_id,
                    horizon_bdays=int(row.horizon_bdays),
                    anchor_session=row.anchor_session,
                    exit_session=row.exit_session,
                    fold=fold,
                    reason=reason,
                )
            )
        self.admitted_count += len(admitted)
        return admitted

    def assert_no_reserved(self, observations: Iterable[Any]) -> None:
        """Raise ``ReservedWindowTouched`` if any anchor or exit reaches reserved_start."""

        touched = [
            (row.shock_id, row.target_id, int(row.horizon_bdays))
            for row in observations
            if row.anchor_session >= self.reserved_start
            or row.exit_session >= self.reserved_start
        ]
        if touched:
            raise ReservedWindowTouched(
                f"{len(touched)} row(s) reach reserved_start {self.reserved_start.isoformat()}: "
                f"{sorted(touched)[:5]}"
            )

    def receipt(self) -> dict[str, object]:
        reasons: dict[str, int] = {}
        for refusal in self.refusals:
            reasons[refusal.reason] = reasons.get(refusal.reason, 0) + 1
        return {
            "card_hash": self.card_hash,
            "admitted_count": self.admitted_count,
            "refused_count": self.refused_count,
            "refused_by_reason": dict(sorted(reasons.items())),
        }
