"""Censoring-aware descriptive summaries for the synthetic recovery prototype.

Aalen-Johansen competing-outcome estimates, not validated forecast probabilities.
Displayed-level depletion is not a trade-price breakdown. No real-book adapter.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable

def _median_duration(values: list[int]):
    # Integer order statistics; do not round a large half-integer through float.
    if not values:
        return None
    a = sorted(values); n = len(a)
    if n % 2:
        return a[n // 2]
    twice = a[n // 2 - 1] + a[n // 2]
    if twice % 2 == 0:
        return twice // 2
    return f'{twice // 2}.5' if twice > 2 * (2**53 - 1) else twice / 2


EVENTS = {'RECOVERED', 'LEVEL_DEPLETED'}
CENSORS = {'PENDING', 'HORIZON_ENDED_UNRECOVERED', 'SOURCE_GAP_CENSORED'}


@dataclass(frozen=True)
class Episode:
    duration_ns: int
    status: str

    def __post_init__(self):
        if type(self.duration_ns) is not int or self.duration_ns < 0:
            raise ValueError('nonnegative exact integer duration required')
        if self.status not in EVENTS | CENSORS:
            raise ValueError('unknown outcome/censoring state')


def competing_incidence(episodes: Iterable[Episode]) -> dict[str, Any]:
    """Process tied events before tied censoring, with risk sets fixed before either.

    Noninformative censoring is an interpretation assumption, not established by code.
    No extrapolation beyond observed follow-up is returned.
    """
    data = list(episodes)
    if any(not isinstance(e, Episode) for e in data):
        raise TypeError('Episode inputs required')
    n = len(data)
    if not n:
        return {'n': 0, 'curve': [], 'terminal_estimate': None,
                'median_completed_recovery_ns': None, 'median_recovery_incidence_ns': None,
                'followup_end_ns': None, 'status': 'NO_OBSERVED_EPISODES'}
    groups: dict[int, list[Episode]] = {}
    for e in data:
        groups.setdefault(e.duration_ns, []).append(e)
    risk = n
    survival = 1.0
    recovered = depleted = 0.0
    crossing = None
    curve = []
    for time in sorted(groups):
        group = groups[time]
        dr = sum(e.status == 'RECOVERED' for e in group)
        dd = sum(e.status == 'LEVEL_DEPLETED' for e in group)
        dc = len(group) - dr - dd
        if risk < len(group) or risk <= 0:
            raise ValueError('incoherent risk set')
        before = survival
        recovered += before * dr / risk
        depleted += before * dd / risk
        survival *= 1.0 - (dr + dd) / risk
        if abs(recovered + depleted + survival - 1.0) > 1e-12:
            raise ArithmeticError('competing-outcome probability mass lost')
        if crossing is None and recovered >= .5:
            crossing = time
        curve.append({'duration_ns': time, 'at_risk_before': risk,
                      'recoveries': dr, 'level_depletions': dd, 'censored': dc,
                      'recovery_incidence': recovered, 'depletion_incidence': depleted,
                      'unresolved_survival_estimate': survival})
        risk -= len(group)
    done = [e.duration_ns for e in data if e.status == 'RECOVERED']
    return {
        'n': n, 'curve': curve,
        'terminal_estimate': {'recovery_incidence': recovered, 'depletion_incidence': depleted,
                              'unresolved_survival_estimate': survival},
        'median_completed_recovery_ns': _median_duration(done),
        'median_recovery_incidence_ns': crossing, 'followup_end_ns': max(groups),
        'observed_counts': {'recovered': len(done),
                            'depleted': sum(e.status == 'LEVEL_DEPLETED' for e in data),
                            'censored': sum(e.status in CENSORS for e in data)},
        'status': 'DESCRIPTIVE_ESTIMATES_NOT_CALIBRATED_FORECASTS',
        'limitations': ['Independent/noninformative censoring is not established',
                        'Episodes can be dependent; no confidence interval or population inference',
                        'Unresolved tail mass is not proof that no future event will occur',
                        'Displayed-level depletion is not a traded-price breakdown'],
    }


def summarize_book(book: Any, cutoff_ns: int) -> dict[str, Any]:
    """Consume an existing synthetic RecoveryBook prefix without mutating it.

    The cutoff is a claimed observed clock for the normalized fixture, not evidence
    that a real source was online until that time. Future-state historical queries fail.
    """
    if type(cutoff_ns) is not int or cutoff_ns < 0 or cutoff_ns < book.time:
        raise ValueError('historical query requires original event-prefix replay')
    if type(book.horizon_ns) is not int or book.horizon_ns <= 0:
        raise ValueError('exact positive horizon required')
    records: dict[int, list[Episode]] = {1: [], -1: []}
    identities = set()
    for r in list(book.history) + list(book.pending.values()):
        if type(r.start_ns) is not int or r.start_ns < 0 or r.start_ns > cutoff_ns or r.side not in records:
            raise ValueError('invalid observed episode')
        key = (r.side, r.start_sequence)
        if key in identities:
            raise ValueError('duplicate episode identity')
        identities.add(key)
        if r.state in EVENTS | {'HORIZON_ENDED_UNRECOVERED', 'SOURCE_GAP_CENSORED'}:
            if type(r.completed_ns) is not int or not r.start_ns <= r.completed_ns <= cutoff_ns:
                raise ValueError('future or invalid completion passed to as-of summary')
            duration, status = r.completed_ns - r.start_ns, r.state
        elif r.state == 'PENDING':
            duration = min(cutoff_ns - r.start_ns, book.horizon_ns)
            status = 'HORIZON_ENDED_UNRECOVERED' if duration >= book.horizon_ns else 'PENDING'
        else:
            raise ValueError('unsupported episode state')
        records[r.side].append(Episode(duration, status))
    return {
        'schema': 'synthetic_recovery_competing_outcomes.v1_RESEARCH_ONLY',
        'cutoff_ns': str(cutoff_ns), 'last_received_ns': str(book.time),
        'source_integrity': bool(book.valid), 'input_origin': 'SYNTHETIC_NORMALIZED_EVENTS_ONLY',
        'bid': competing_incidence(records[1]), 'ask': competing_incidence(records[-1]),
        'forecast_probability': None, 'institutional_inventory': None,
        'real_DEEPplus_book_adapter': 'UNVERIFIED_FAIL_CLOSED_UNCHANGED',
        'authority': {'rotation_call_write': False, 'live_alert': False, 'rank': False, 'size': False},
    }
