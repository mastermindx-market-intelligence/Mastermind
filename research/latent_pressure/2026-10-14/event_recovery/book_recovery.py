"""Research recovery engine for EXPLICIT normalized synthetic order events.

No DEEP+ semantic decoder, source admission, network or forecast authority.
An atomic batch must be supplied by an independently qualified source adapter; equal
message timestamps do NOT prove atomicity. Depletion means displayed quantity at a
price disappeared, not that a trade-price breakdown or informed selling occurred.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, asdict
from fractions import Fraction
import math
from typing import Any, Iterable

MAX_SIGNED = 2**63 - 1
MAX_UNSIGNED = 2**64 - 1
MAX_JSON_SAFE = 2**53 - 1


def _integer(value: Any, name: str, *, minimum: int = 0, maximum: int = MAX_SIGNED) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an exact integer in [{minimum}, {maximum}]')
    return value


def _wire(value: Any) -> Any:
    """Preserve large integer identity/clock values in ordinary JSON consumers."""
    if type(value) is int and abs(value) > MAX_JSON_SAFE:
        return str(value)
    if isinstance(value, dict):
        return {k: _wire(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(v) for v in value]
    return value


def median_duration_ns(values: list[int]) -> int | float | str | None:
    """Exact median duration, including large half-nanosecond averages."""
    if not values:
        return None
    a = sorted(values)
    n = len(a)
    if n % 2:
        return a[n // 2]
    twice = a[n // 2 - 1] + a[n // 2]
    if twice % 2 == 0:
        return twice // 2
    if twice > 2 * MAX_JSON_SAFE:
        return f'{twice // 2}.5'
    return twice / 2


@dataclass(frozen=True)
class Event:
    sequence: int
    received_ns: int
    kind: str  # ADD, MODIFY, DELETE, EXECUTE; explicitly normalized meanings only
    order_id: int
    side: int  # +1 resting bid, -1 resting ask
    price: int  # integer ticks; referenced resting price on DELETE/EXECUTE
    quantity: int  # total remaining on ADD/MODIFY; consumed quantity on EXECUTE


@dataclass
class Response:
    side: int
    level: int
    start_ns: int
    start_sequence: int
    original_depth: int
    shock_quantity: int
    initial_remaining: int
    state: str = 'PENDING'
    completed_ns: int | None = None
    completion_sequence: int | None = None
    outcome_observed_ns: int | None = None


class RecoveryBook:
    """One instrument/session's explicit normalized displayed-book state.

    apply() preserves the original single-observation contract. apply_batch() instead
    exposes only the committed result of a declared atomic observation. It stages all
    order changes and validates them before mutating either orders or measurements.
    No queue priority, hidden liquidity or exchange reset semantics are inferred.
    """
    def __init__(self, *, horizon_ns: int = 10_000_000_000, shock_fraction: float = .5):
        _integer(horizon_ns, 'horizon_ns', minimum=1)
        if type(shock_fraction) not in (int, float) or not math.isfinite(shock_fraction) or not 0 < shock_fraction <= 1:
            raise ValueError('shock_fraction must be a finite number in (0, 1]')
        self.horizon_ns = horizon_ns
        self.shock_fraction = shock_fraction
        self._threshold = Fraction(str(shock_fraction))
        self.orders: dict[int, tuple[int, int, int]] = {}
        self.pending: dict[int, Response] = {}
        self.history: list[Response] = []
        self.sequence = -1
        self.time = -1
        self.valid = True
        self.skipped_immediate_depletions = 0
        self.same_batch_resolved_shocks = 0
        self.atomic_batches = 0

    def depth(self, side: int, price: int) -> int:
        return sum(q for s, p, q in self.orders.values() if s == side and p == price)

    def best(self, side: int) -> int | None:
        prices = [p for s, p, q in self.orders.values() if s == side and q > 0]
        return (max(prices) if side == 1 else min(prices)) if prices else None

    def _finish(self, side: int, state: str, event_time: int, sequence: int,
                *, observed_ns: int | None = None) -> None:
        r = self.pending.pop(side)
        r.state = state
        r.completed_ns = event_time
        r.completion_sequence = sequence
        r.outcome_observed_ns = event_time if observed_ns is None else observed_ns
        self.history.append(r)

    def _expire(self, timestamp: int, sequence: int) -> None:
        for side, r in list(self.pending.items()):
            deadline = r.start_ns + self.horizon_ns
            # A recovery exactly on the deadline remains eligible.
            if timestamp > deadline:
                self._finish(side, 'HORIZON_ENDED_UNRECOVERED', deadline, sequence,
                             observed_ns=timestamp)

    def invalidate(self) -> None:
        self.valid = False
        for side in list(self.pending):
            self._finish(side, 'SOURCE_GAP_CENSORED', self.time, self.sequence)

    def apply(self, event: Event) -> None:
        if not isinstance(event, Event):
            raise ValueError('normalized Event required')
        self.apply_batch([event], available_ns=event.received_ns)

    def apply_batch(self, events: Iterable[Event], *, available_ns: int) -> None:
        if not self.valid:
            raise ValueError('source invalidated; no continuing inference')
        _integer(available_ns, 'available_ns')
        if available_ns < self.time:
            raise ValueError('commit clock moved backward')
        items = list(events)
        if not items:
            raise ValueError('empty batch is not a qualified source-coverage heartbeat')
        staged = self.orders.copy()
        previous_sequence, previous_time = self.sequence, self.time
        initial_best = {side: self.best(side) for side in (-1, 1)}
        initial_depth = {side: self.depth(side, price) if price is not None else 0
                         for side, price in initial_best.items()}
        executed = {-1: 0, 1: 0}
        prior_pending = set(self.pending)
        for e in items:
            if not isinstance(e, Event):
                raise ValueError('normalized Event required')
            _integer(e.sequence, 'sequence', minimum=1, maximum=MAX_UNSIGNED)
            _integer(e.received_ns, 'received_ns')
            _integer(e.order_id, 'order_id', minimum=1, maximum=MAX_UNSIGNED)
            _integer(e.price, 'price', minimum=1)
            _integer(e.quantity, 'quantity')
            if type(e.side) is not int or e.side not in (-1, 1):
                raise ValueError('side must be exactly -1 or +1')
            if e.sequence <= previous_sequence or e.received_ns < previous_time:
                raise ValueError('out-of-order observation')
            if e.received_ns > available_ns:
                raise ValueError('an event is received after the declared complete batch')
            previous_sequence, previous_time = e.sequence, e.received_ns
            old = staged.get(e.order_id)
            if e.kind == 'ADD':
                if old is not None or e.quantity <= 0:
                    raise ValueError('duplicate/empty add')
                staged[e.order_id] = (e.side, e.price, e.quantity)
            elif e.kind in ('MODIFY', 'DELETE', 'EXECUTE'):
                if old is None:
                    raise ValueError('unknown order; source cannot be reconstructed')
                if old[0] != e.side:
                    raise ValueError('side mutation is outside the normalized contract')
                if e.kind in ('DELETE', 'EXECUTE') and old[1] != e.price:
                    raise ValueError('price reference mismatch')
                if e.kind == 'MODIFY':
                    if e.quantity:
                        staged[e.order_id] = (e.side, e.price, e.quantity)
                    else:
                        del staged[e.order_id]
                elif e.kind == 'DELETE':
                    if e.quantity:
                        raise ValueError('delete quantity must be zero')
                    del staged[e.order_id]
                else:
                    if not 0 < e.quantity <= old[2]:
                        raise ValueError('overexecution or empty execution')
                    if e.price == initial_best[e.side]:
                        executed[e.side] += e.quantity
                    remaining = old[2] - e.quantity
                    if remaining:
                        staged[e.order_id] = (old[0], old[1], remaining)
                    else:
                        del staged[e.order_id]
            else:
                raise ValueError('unknown normalized kind')
        # All validation has completed; no invalid tail can mutate earlier state.
        last_sequence = items[-1].sequence
        self._expire(available_ns, last_sequence)
        self.orders = staged
        for side, r in list(self.pending.items()):
            depth = self.depth(side, r.level)
            if depth == 0:
                self._finish(side, 'LEVEL_DEPLETED', available_ns, last_sequence)
            elif depth >= r.original_depth:
                self._finish(side, 'RECOVERED', available_ns, last_sequence)
        for side in (-1, 1):
            depth = initial_depth[side]
            consumed = executed[side]
            if side in prior_pending or not depth or not consumed:
                continue
            # Exact arithmetic matters for quantities larger than floating-point integers.
            if consumed * self._threshold.denominator < depth * self._threshold.numerator:
                continue
            level = initial_best[side]
            assert level is not None
            remaining = self.depth(side, level)
            if remaining == 0:
                self.skipped_immediate_depletions += 1
            elif remaining >= depth:
                self.same_batch_resolved_shocks += 1
            else:
                self.pending[side] = Response(side, level, available_ns, last_sequence,
                                              depth, consumed, remaining)
        self.sequence = last_sequence
        self.time = available_ns
        self.atomic_batches += 1

    def snapshot(self, cutoff_ns: int) -> dict[str, Any]:
        _integer(cutoff_ns, 'cutoff_ns')
        if cutoff_ns < self.time:
            raise ValueError('past snapshot requires replay of the original prefix')
        # The normalized fixture caller declares coverage. The replay adapter separately
        # rejects cutoffs without a known coverage watermark; no real feed is implied.
        b = deepcopy(self)
        b._expire(cutoff_ns, b.sequence)
        sides = {}
        for side in (1, -1):
            done = [x for x in b.history if x.side == side][-20:]
            recovered = [x for x in done if x.state == 'RECOVERED']
            r = b.pending.get(side)
            sides['bid' if side == 1 else 'ask'] = {
                'pending': asdict(r) if r else None,
                'elapsed_ns': cutoff_ns - r.start_ns if r else None,
                'current_level_depth': b.depth(side, r.level) if r else None,
                'past_recoveries': len(recovered),
                'past_level_depletions': sum(x.state == 'LEVEL_DEPLETED' for x in done),
                'right_censored': sum(x.state in ('HORIZON_ENDED_UNRECOVERED', 'SOURCE_GAP_CENSORED') for x in done),
                'median_completed_recovery_ns': median_duration_ns([x.completed_ns - x.start_ns for x in recovered]),
            }
        return _wire({
            'schema': 'research_snapshot_not_production', 'cutoff_ns': str(cutoff_ns),
            'last_received_ns': str(b.time), 'last_sequence': str(b.sequence),
            'input_origin': 'SYNTHETIC_NORMALIZED_FIXTURE', 'source_integrity': b.valid,
            'sides': sides, 'immediate_depletions_not_predicted': b.skipped_immediate_depletions,
            'same_batch_resolved_shocks_not_predicted': b.same_batch_resolved_shocks,
            'committed_batches': b.atomic_batches,
            'inferred_institution': None, 'forecast_probability': None,
            'forecast_authority': 'NONE',
        })


def decode_iex_book_event(*args, **kwargs):
    raise NotImplementedError('DEEPPLUS_BOOK_FIELDS_UNVERIFIED: no guessing side/modify/delete semantics. Use only the separately qualified L-only research path.')
