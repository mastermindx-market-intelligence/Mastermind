"""Finite, source-independent synthetic replay through the existing recovery engine.

This module is a research adapter, not a new runtime/identity/collection service.
BATCH and WATERMARK are explicit fixture declarations, never inferred exchange rules.
The real DEEP+ semantic adapter remains disabled. No network, predictions or writes
other than explicitly requested local report files are part of this reader.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'event_recovery'))
sys.path.insert(0, str(ROOT / 'clock_pause'))
from book_recovery import Event, RecoveryBook, MAX_SIGNED, MAX_UNSIGNED, _wire
from recovery_incidence import summarize_book

ORIGIN = 'SYNTHETIC_NORMALIZED_FIXTURE'
AUTHORITY = {'rotation_call_write': False, 'live_alert': False, 'rank': False, 'size': False}


def exact(value: Any, name: str, *, minimum: int = 0, maximum: int = MAX_SIGNED) -> int:
    """Accept integers or their canonical decimal strings, never floats or booleans."""
    if isinstance(value, str):
        if not re.fullmatch(r'0|[1-9][0-9]*', value):
            raise ValueError(f'{name}: canonical nonnegative decimal string required')
        value = int(value)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name}: exact integer out of range')
    return value


def label(value: Any, name: str, *, synthetic_symbol: bool = False) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value):
        raise ValueError(f'{name}: invalid bounded fixture label')
    if synthetic_symbol and not value.startswith('SYN-'):
        raise ValueError('real-security mapping is not admitted by this synthetic adapter')
    return value


class Replay:
    """In-memory computation for one finite normalized fixture; no durable state plane."""
    def __init__(self, *, horizon_ns: int = 20, shock_fraction: float = .5):
        self.parameters = {'horizon_ns': horizon_ns, 'shock_fraction': shock_fraction}
        RecoveryBook(**self.parameters)  # Validate parameters even before the first session.
        self.books: dict[str, RecoveryBook] = {}
        self.sessions: dict[str, str] = {}
        self.coverage: dict[str, int] = {}
        self.sealed: dict[str, int] = {}
        self.retired: list[dict[str, Any]] = []
        self.observed_ns = -1
        self.frame_count = 0

    def apply_frame(self, frame: dict[str, Any]) -> None:
        # Stage the complete state so an invalid reset/frame cannot partially mutate it.
        candidate = deepcopy(self)
        candidate._apply(frame)
        self.__dict__.update(candidate.__dict__)

    def _apply(self, frame: dict[str, Any]) -> None:
        if not isinstance(frame, dict) or frame.get('origin') != ORIGIN:
            raise ValueError('only explicit synthetic normalized fixture frames are supported')
        observed = exact(frame.get('observed_ns'), 'observed_ns')
        if observed < self.observed_ns:
            raise ValueError('frame receipt clock moved backward')
        symbol = label(frame.get('symbol'), 'symbol', synthetic_symbol=True)
        session = label(frame.get('session'), 'session')
        kind = frame.get('kind')
        if kind == 'START':
            if symbol in self.books:
                raise ValueError('existing symbol/session must end with an explicit RESET')
            self.books[symbol] = RecoveryBook(**self.parameters)
            self.sessions[symbol] = session
            self.coverage[symbol] = observed
            self.sealed[symbol] = observed
        elif kind == 'RESET':
            if symbol not in self.books or self.sessions[symbol] == session:
                raise ValueError('RESET requires an existing symbol and a different declared session')
            previous = self.books[symbol]
            previous.time = max(previous.time, self.coverage[symbol])
            previous.invalidate()
            self.retired.append({'symbol': symbol, 'session': self.sessions[symbol],
                                 'ended_observed_ns': str(observed),
                                 'last_verified_ns': str(self.coverage[symbol]),
                                 'responses': _wire([asdict(r) for r in previous.history]),
                                 'forecast_probability': None})
            self.books[symbol] = RecoveryBook(**self.parameters)
            self.sessions[symbol] = session
            self.coverage[symbol] = observed
            self.sealed[symbol] = observed
        else:
            if symbol not in self.books or self.sessions[symbol] != session:
                raise ValueError('missing or mismatched explicit session')
            book = self.books[symbol]
            if kind == 'GAP':
                # Censor at the last proven receipt/coverage time, not at detection time.
                if not book.valid:
                    raise ValueError('source already invalidated')
                book.time = max(book.time, self.coverage[symbol])
                book.invalidate()
            elif kind == 'WATERMARK':
                if not book.valid:
                    raise ValueError('invalid source cannot declare continuing coverage')
                through = exact(frame.get('complete_through_ns'), 'complete_through_ns')
                sequence = exact(frame.get('last_sequence'), 'last_sequence', maximum=MAX_UNSIGNED)
                if sequence != max(0, book.sequence):
                    raise ValueError('watermark does not match the known decoded prefix')
                if not self.coverage[symbol] <= through <= observed:
                    raise ValueError('coverage moves backward or exceeds its receipt')
                self.coverage[symbol] = through
                self.sealed[symbol] = through
            elif kind == 'BATCH':
                if not book.valid:
                    raise ValueError('source gap requires an explicit new-session reset')
                if frame.get('complete') is not True:
                    raise ValueError('partial normalized batch cannot be published')
                raw = frame.get('events')
                if not isinstance(raw, list) or not 1 <= len(raw) <= 10000:
                    raise ValueError('bounded nonempty event list required')
                events = []
                fields = {'sequence', 'received_ns', 'kind', 'order_id', 'side', 'price', 'quantity'}
                for item in raw:
                    if not isinstance(item, dict) or set(item) != fields:
                        raise ValueError('normalized event field set must be exact')
                    received = exact(item['received_ns'], 'received_ns')
                    if received <= self.sealed[symbol]:
                        raise ValueError('late event contradicts a previously complete watermark')
                    side = item['side']
                    if type(side) is not int or side not in (-1, 1):
                        raise ValueError('side must be the declared exact normalized sign')
                    events.append(Event(exact(item['sequence'], 'sequence', minimum=1, maximum=MAX_UNSIGNED),
                                        received, item['kind'],
                                        exact(item['order_id'], 'order_id', minimum=1, maximum=MAX_UNSIGNED),
                                        side, exact(item['price'], 'price', minimum=1),
                                        exact(item['quantity'], 'quantity')))
                book.apply_batch(events, available_ns=observed)
                self.coverage[symbol] = observed
            else:
                raise ValueError('unsupported normalized fixture frame')
        self.observed_ns = observed
        self.frame_count += 1

    def snapshot(self, cutoff_ns: int) -> dict[str, Any]:
        cutoff_ns = exact(cutoff_ns, 'cutoff_ns')
        if cutoff_ns < self.observed_ns:
            raise ValueError('past cutoff requires replay of its original received prefix')
        result = []
        for symbol in sorted(self.books):
            book = self.books[symbol]
            verified = min(cutoff_ns, self.coverage[symbol])
            if not book.valid:
                state = 'SOURCE_GAP_CENSORED'
            elif verified < cutoff_ns:
                state = 'COVERAGE_NOT_PROVEN_TO_REQUESTED_CUTOFF'
            else:
                state = 'SYNTHETIC_PREFIX_OBSERVED_TO_CUTOFF'
            # Use only the coverage actually present in the fixture. No wall-clock
            # extrapolation can make a missing-feed interval look like market silence.
            measurement = book.snapshot(verified)
            incidence = summarize_book(book, verified)
            result.append({'symbol': symbol, 'session': self.sessions[symbol], 'state': state,
                           'requested_cutoff_ns': str(cutoff_ns), 'measurement_cutoff_ns': str(verified),
                           'observation_age_ns': cutoff_ns - verified,
                           'recovery': measurement, 'descriptive_competing_outcomes': incidence,
                           'forecast_probability': None, 'pressure_direction': None,
                           'institutional_inventory': None, 'authority': dict(AUTHORITY)})
        return _wire({'schema': 'normalized_recovery_replay.v1_RESEARCH_ONLY', 'origin': ORIGIN,
                      'requested_cutoff_ns': str(cutoff_ns), 'frames_received': self.frame_count,
                      'records': result, 'retired_sessions': deepcopy(self.retired),
                      'real_DEEPplus_adapter': 'UNVERIFIED_FAIL_CLOSED_UNCHANGED',
                      'authority': dict(AUTHORITY),
                      'interpretation': 'Synthetic measurement and data-integrity examples, not real-market probabilities.'})


def replay(frames: Iterable[dict[str, Any]], cutoff_ns: int, **parameters) -> dict[str, Any]:
    cutoff = exact(cutoff_ns, 'cutoff_ns')
    engine = Replay(**parameters)
    for frame in frames:
        if not isinstance(frame, dict):
            raise ValueError('fixture frame must be an object')
        # Do not inspect a future frame's events or outcome to answer an earlier cutoff.
        at = exact(frame.get('observed_ns'), 'observed_ns')
        if at > cutoff:
            break
        engine.apply_frame(frame)
    return engine.snapshot(cutoff)


def from_file(path: Path, cutoff_ns: int, **parameters) -> dict[str, Any]:
    if path.stat().st_size > 8_000_000:
        raise ValueError('finite synthetic fixture size limit exceeded')
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict) or payload.get('origin') != ORIGIN or not isinstance(payload.get('frames'), list):
        raise ValueError('expected explicit normalized synthetic fixture envelope')
    output = replay(payload['frames'], cutoff_ns, **parameters)
    output['fixture_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--at', required=True, help='exact normalized available-time cutoff in nanoseconds')
    parser.add_argument('--horizon-ns', type=int, default=20)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    result = from_file(args.fixture, exact(args.at, 'at'), horizon_ns=args.horizon_ns)
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.out:
        with args.out.open('x') as f:
            f.write(text)
    else:
        print(text, end='')
