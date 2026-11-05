"""Trading Lab read-only decision preflight. No execution, storage or model calls.

Candidate adapter for the existing Self-Directed and private trade-episode owners.
All Context data is server-owned; never populate it from a browser request.
A binding digest is a change detector, NOT a signed authorization or order token.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_EVEN
import hashlib
import json
import re
from typing import Literal

D = Decimal
ZERO = D('0')
CENT = D('0.01')
MAX_NUMBER = D('1000000000000')
PLAN_FIELDS = frozenset({'instrument_id', 'side', 'unit', 'amount', 'horizon',
                         'thesis', 'trigger', 'invalidation', 'counter_case'})


class ContractError(ValueError):
    """A malformed or contradictory trusted input must never produce a green view."""


def number(value: object, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ContractError('Numbers must be decimal strings, integers or Decimal, not floats/bools.')
    if len(str(value)) > 64:
        raise ContractError('Number exceeds representation bound.')
    try:
        out = D(value)
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise ContractError('Invalid number.') from exc
    if not out.is_finite() or out < 0 or out > MAX_NUMBER:
        raise ContractError('Number must be finite, nonnegative and bounded.')
    if positive and out <= 0:
        raise ContractError('Number must be positive.')
    if out.as_tuple().exponent < -12 or out.as_tuple().exponent > 12:
        raise ContractError('Unsupported decimal precision.')
    return out


def stamp(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError('An explicit timezone is required.')
    return value.astimezone(timezone.utc)


def ident(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:._-]{0,95}', value):
        raise ContractError('Invalid identifier.')
    return value


def cash_text(v: Decimal) -> str:
    return format(v.quantize(CENT, rounding=ROUND_HALF_EVEN), '.2f')


def decimal_text(v: Decimal) -> str:
    return format(v.normalize(), 'f')


def digest(value: object) -> str:
    def encode(v):
        if isinstance(v, Decimal):
            return decimal_text(v)
        if isinstance(v, datetime):
            return stamp(v).isoformat()
        raise TypeError(type(v).__name__)
    wire = json.dumps(value, default=encode, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(wire).hexdigest()


@dataclass(frozen=True)
class Plan:
    instrument_id: str
    side: Literal['buy', 'sell']
    unit: Literal['shares', 'dollars']
    amount: Decimal
    horizon: Literal['intraday', 'swing', 'investment']
    thesis: str = ''
    trigger: str = ''
    invalidation: str = ''
    counter_case: str = ''

    @classmethod
    def from_payload(cls, raw: dict) -> 'Plan':
        if not isinstance(raw, dict) or set(raw) - PLAN_FIELDS:
            raise ContractError('Unknown plan fields. Server evidence is not client-editable.')
        needed = {'instrument_id', 'side', 'unit', 'amount', 'horizon'}
        if needed - set(raw):
            raise ContractError('Missing plan fields.')
        if raw['side'] not in ('buy', 'sell') or raw['unit'] not in ('shares', 'dollars'):
            raise ContractError('Unsupported side or unit.')
        if raw['horizon'] not in ('intraday', 'swing', 'investment'):
            raise ContractError('Unsupported horizon.')
        text = {}
        for name in ('thesis', 'trigger', 'invalidation', 'counter_case'):
            s = raw.get(name, '')
            if not isinstance(s, str) or len(s) > 4000 or any(ord(c) < 32 and c not in '\n\t' for c in s):
                raise ContractError('Invalid plan text.')
            text[name] = s.strip()
        return cls(ident(raw['instrument_id']), raw['side'], raw['unit'],
                   number(raw['amount'], positive=True), raw['horizon'], **text)

    @property
    def fingerprint(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Position:
    instrument_id: str
    shares: Decimal
    reserved_shares: Decimal
    mark: Decimal | None
    mark_valid_until: datetime | None


@dataclass(frozen=True)
class Context:
    principal_id: str
    account_id: str
    mode: str
    account_version: int
    account_state: str
    cash: Decimal
    reserved_cash: Decimal
    currency: str
    positions: tuple[Position, ...]
    instrument_id: str
    quote_id: str
    quote_bid: Decimal | None
    quote_ask: Decimal | None
    quote_observed_at: datetime
    quote_received_at: datetime
    quote_valid_until: datetime
    quote_currency: str
    session: str
    share_step: Decimal
    policy_id: str
    policy_version: int
    policy_mode: str
    max_name_weight: Decimal | None
    market_generation: str
    market_horizon: str
    market_valid_until: datetime
    evidence_generation: str
    review_state: str
    reviewed_binding: str | None
    review_valid_until: datetime | None
    review_is_fixture: bool = False

    def validate(self) -> None:
        for value in (self.principal_id, self.account_id, self.instrument_id,
                      self.quote_id, self.policy_id, self.market_generation,
                      self.evidence_generation):
            ident(value)
        for value in (self.account_version, self.policy_version):
            if type(value) is not int or not 0 <= value <= 2**63-1:
                raise ContractError('Invalid version.')
        if self.mode not in ('PAPER', 'REAL', 'REPLAY', 'SYNTHETIC'):
            raise ContractError('Invalid mode.')
        if self.account_state not in ('verified', 'reconcile_required', 'unavailable'):
            raise ContractError('Invalid account state.')
        if self.policy_mode not in ('advisory', 'deliberate_practice'):
            raise ContractError('Invalid policy mode.')
        if self.session not in ('regular', 'closed', 'halted', 'unknown'):
            raise ContractError('Invalid session.')
        if self.review_state not in ('not_connected', 'pending', 'complete', 'failed'):
            raise ContractError('Invalid review state.')
        if self.market_horizon not in ('intraday', 'swing', 'investment'):
            raise ContractError('Invalid market horizon.')
        if self.currency != 'USD' or self.quote_currency != 'USD':
            raise ContractError('This bounded vertical supports USD only.')
        if type(self.review_is_fixture) is not bool or not isinstance(self.positions, tuple):
            raise ContractError('Context must be immutable and explicitly qualified.')
        numeric_values = (self.cash, self.reserved_cash, self.share_step)
        if any(not isinstance(v, Decimal) for v in numeric_values):
            raise ContractError('Server monetary inputs must be Decimal.')
        for v in (self.quote_bid, self.quote_ask, self.max_name_weight):
            if v is not None and not isinstance(v, Decimal):
                raise ContractError('Server monetary inputs must be Decimal.')
        cash = number(self.cash)
        if number(self.reserved_cash) > cash:
            raise ContractError('Cash reservations exceed cash.')
        number(self.share_step, positive=True)
        if self.max_name_weight is not None and number(self.max_name_weight, positive=True) > 1:
            raise ContractError('Invalid user-selected concentration limit.')
        if self.quote_bid is not None:
            number(self.quote_bid, positive=True)
        if self.quote_ask is not None:
            number(self.quote_ask, positive=True)
        if self.quote_bid is not None and self.quote_ask is not None and self.quote_bid > self.quote_ask:
            raise ContractError('Crossed quote.')
        if not stamp(self.quote_observed_at) <= stamp(self.quote_received_at) <= stamp(self.quote_valid_until):
            raise ContractError('Invalid quote chronology.')
        stamp(self.market_valid_until)
        if self.review_valid_until is not None:
            stamp(self.review_valid_until)
        seen = set()
        for p in self.positions:
            if not isinstance(p, Position) or not isinstance(p.shares, Decimal) or not isinstance(p.reserved_shares, Decimal):
                raise ContractError('Invalid typed position.')
            if p.mark is not None and not isinstance(p.mark, Decimal):
                raise ContractError('Server marks must be Decimal.')
            ident(p.instrument_id)
            if p.instrument_id in seen:
                raise ContractError('Duplicate position identity.')
            seen.add(p.instrument_id)
            if number(p.reserved_shares) > number(p.shares):
                raise ContractError('Share reservations exceed holdings.')
            if p.mark is not None:
                number(p.mark, positive=True)
            if p.mark_valid_until is not None:
                stamp(p.mark_valid_until)


def review_binding(plan: Plan, ctx: Context) -> str:
    """Thesis/context-only review. Quantity and price are NOT thesis judgments.

    The review owner supplies this binding. Never treat this hash as an approval
    signature. Account identity prevents cross-account reuse; evidence and policy
    generations bind substantive meaning. Cash/marks/quote/quantity are checked
    on EVERY preflight, without spending another slow thesis-review call.
    """
    thesis = {k: v for k, v in asdict(plan).items() if k not in ('amount', 'unit')}
    context = {k: getattr(ctx, k) for k in (
        'principal_id', 'account_id', 'mode', 'instrument_id',
        'policy_id', 'policy_version', 'policy_mode',
        'market_generation', 'market_horizon', 'evidence_generation')}
    return digest({'scope': 'thesis_and_context.v1', 'plan': thesis, 'context': context})


def preview_binding(plan: Plan, ctx: Context) -> str:
    """Fast economic preview binds ALL trusted facts, including review state.

    Changes to price, amount, reservations, ownership, policy or evidence discard
    a previous preview. This changes no order or review state and is not an
    execution capability. Production must revalidate within its account lock.
    """
    return digest({'scope': 'economic_preview.v1', 'plan': asdict(plan),
                   'context': asdict(ctx)})


def evaluate(plan: Plan, ctx: Context, *, now: datetime) -> dict:
    """Compute one safe view. Always returns execution_authority=False.

    This checks structural completeness and economic/freshness constraints. It
    cannot judge thesis truth, forecast success or issue a binding market policy.
    """
    # Re-validate even callers constructing a Plan directly rather than parsing JSON.
    if not isinstance(plan, Plan) or not isinstance(plan.amount, Decimal):
        raise ContractError('Use Plan.from_payload to canonicalize the intent.')
    normalized = Plan.from_payload(asdict(plan))
    if normalized != plan:
        raise ContractError('Plan must be canonicalized before evaluation.')
    ctx.validate()
    now = stamp(now)
    checks: list[dict] = []
    def add(code, severity, title, detail, action, field=None):
        checks.append(dict(code=code, severity=severity, title=title, detail=detail,
                           next_action=action, field=field))

    if ctx.mode != 'PAPER':
        add('WRONG_MODE', 'block', 'Paper account required',
            'Real, replay and synthetic accounts never use this live-paper preview.', 'select_paper_account')
    if ctx.account_state != 'verified':
        add('ACCOUNT_UNVERIFIED', 'block', 'Account needs reconciliation',
            'No fresh-account fallback or cash estimate replaces missing account truth.', 'reconcile_account')
    if plan.instrument_id != ctx.instrument_id:
        add('INSTRUMENT_MISMATCH', 'block', 'Quote belongs to a different security',
            'Refresh the exact instrument before previewing.', 'refresh_quote')
    if ctx.quote_received_at > now or ctx.quote_observed_at > now:
        add('FUTURE_QUOTE', 'block', 'Quote time is invalid', 'Future observations cannot price an order.', 'refresh_quote')
    elif now >= ctx.quote_valid_until:
        add('QUOTE_EXPIRED', 'block', 'Price needs a refresh', 'The quote has expired; no stale fill price is implied.', 'refresh_quote')
    if ctx.session != 'regular':
        add('SESSION_NOT_EXECUTABLE', 'block', 'Market is not executable now',
            'Closed, halted and unknown sessions are not a next-open fill promise.', 'wait_for_session')

    price = ctx.quote_ask if plan.side == 'buy' else ctx.quote_bid
    if price is None:
        add('NO_EXECUTABLE_QUOTE', 'block', 'Executable quote unavailable',
            'This vertical does not silently substitute a last trade for bid or ask.', 'refresh_quote')
    pos = next((p for p in ctx.positions if p.instrument_id == plan.instrument_id), None)
    held = pos.shares if pos else ZERO
    held_reserved = pos.reserved_shares if pos else ZERO
    free_cash = ctx.cash - ctx.reserved_cash
    quantity = None
    value = None
    if price is not None:
        raw_qty = plan.amount if plan.unit == 'shares' else plan.amount / price
        quantity = (raw_qty / ctx.share_step).to_integral_value(rounding=ROUND_DOWN) * ctx.share_step
        if quantity <= 0:
            add('BELOW_SHARE_INCREMENT', 'block', 'Amount is below the supported share increment',
                'Choose a supported quantity; nothing is silently submitted.', 'edit_amount', 'amount')
        if quantity != raw_qty:
            if plan.unit == 'shares':
                add('INVALID_SHARE_INCREMENT', 'block', 'Share quantity is not supported',
                    'Share-sized orders must match the instrument increment.', 'edit_amount', 'amount')
            else:
                add('NOTIONAL_ROUNDING', 'info', 'Dollar order rounds down',
                    'The preview explicitly shows the resulting shares and unused dollars.', 'review_quantity')
        value = (quantity * price).quantize(CENT, rounding=ROUND_HALF_EVEN)
        if value <= 0:
            add('BELOW_CASH_PRECISION', 'block', 'Order is below cash precision',
                'A positive share amount must not round into a free fill.', 'edit_amount', 'amount')
        if plan.side == 'buy' and value > free_cash:
            add('INSUFFICIENT_CASH', 'block', 'Not enough unreserved cash',
                f'Available: ${cash_text(free_cash)}. This order is not resized for you.', 'edit_amount', 'amount')
        if plan.side == 'sell' and quantity > held - held_reserved:
            add('INSUFFICIENT_SHARES', 'block', 'Not enough unreserved shares',
                'Existing sell reservations count. No short or oversell is permitted.', 'edit_amount', 'amount')

    # Mark coverage is explicit. Never use average cost as a current mark.
    missing = [p.instrument_id for p in ctx.positions if p.shares > 0 and
               (p.mark is None or p.mark_valid_until is None or now >= p.mark_valid_until)]
    equity = None if missing else ctx.cash + sum((p.shares * p.mark for p in ctx.positions if p.shares > 0), ZERO)
    after_equity = None
    after_weight = None
    after_cash = None
    after_shares = None
    if missing:
        add('INCOMPLETE_VALUATION', 'warning', 'Portfolio value is incomplete',
            'Missing or expired marks hide total value and concentration; cash remains separately readable.', 'refresh_marks')
    if quantity is not None and value is not None:
        after_cash = ctx.cash - value if plan.side == 'buy' else ctx.cash + value
        after_shares = held + quantity if plan.side == 'buy' else held - quantity
        if equity is not None and after_cash >= 0 and after_shares >= 0:
            # Retain the same valuation basis before/after. Existing position mark
            # is not overwritten with the simulated execution quote.
            marking_price = pos.mark if pos is not None and pos.shares > 0 else price
            prior_mv = held * marking_price
            new_mv = after_shares * marking_price
            after_equity = equity + (after_cash - ctx.cash) + new_mv - prior_mv
            if after_equity > 0:
                after_weight = new_mv / after_equity
    if plan.side == 'buy' and ctx.max_name_weight is not None:
        if after_weight is None:
            add('LIMIT_NOT_EVALUABLE', 'block', 'Your concentration limit cannot be checked',
                'Complete marks are required for this chosen rule.', 'refresh_marks')
        elif after_weight > ctx.max_name_weight:
            add('NAME_LIMIT', 'block', 'Order exceeds your chosen position limit',
                'This is your practice rule, not a market forecast or AI risk recommendation.', 'edit_amount', 'amount')

    # Only new risk is subject to slow thesis/AI requirements. A reduction still
    # requires all exact account, position, quote and session checks above.
    if plan.side == 'buy':
        for name, label in [('thesis', 'What is your idea?'), ('trigger', 'Why enter now?'),
                            ('invalidation', 'What would change your mind?'), ('counter_case', 'What is the strongest counter-case?')]:
            if not getattr(plan, name):
                add('MISSING_' + name.upper(), 'process', label,
                    'Record your own view before reading the AI review.', 'edit_plan', name)
        if now >= ctx.market_valid_until or plan.horizon != ctx.market_horizon:
            add('MARKET_CONTEXT_UNFIT', 'warning', 'Market context is stale or for a different horizon',
                'A swing-market label must not silently stand in for an intraday or investment assessment.', 'refresh_context')

    thesis_binding = review_binding(plan, ctx)
    binding = preview_binding(plan, ctx)
    review_valid = (ctx.review_state == 'complete' and ctx.reviewed_binding == thesis_binding and
                    ctx.review_valid_until is not None and now < ctx.review_valid_until)
    if plan.side == 'buy' and not review_valid:
        code = 'REVIEW_INVALIDATED' if ctx.review_state == 'complete' else 'REVIEW_UNAVAILABLE'
        add(code, 'review' if ctx.policy_mode == 'deliberate_practice' else 'warning',
            'Evidence review needs attention',
            'No matching completed review exists. A checklist or model outage is not AI approval.', 'request_review')
    if ctx.review_is_fixture:
        add('FIXTURE_REVIEW', 'info', 'Illustrative review only',
            'The demonstration review is a fixture, not a model response.', 'inspect_limits')

    structural_complete = all(getattr(plan, k) for k in ('thesis', 'trigger', 'invalidation', 'counter_case'))
    if any(x['severity'] == 'block' for x in checks):
        state = 'BLOCKED'
    elif any(x['severity'] == 'process' for x in checks):
        state = 'PLAN_INCOMPLETE'
    elif any(x['severity'] == 'review' for x in checks):
        state = 'REVIEW_NEEDED'
    elif plan.side == 'sell':
        state = 'REDUCTION_PREVIEW'
    elif review_valid:
        state = 'PREVIEW_READY'
    else:
        state = 'UNREVIEWED_PREVIEW'
    priority = {'block': 0, 'process': 1, 'review': 2, 'warning': 3, 'info': 4}
    checks.sort(key=lambda x: priority[x['severity']])
    expires = min(ctx.quote_valid_until, now + timedelta(seconds=30))
    if review_valid:
        expires = min(expires, ctx.review_valid_until)
    return {
        'schema': 'trading_lab.preflight.v1', 'state': state,
        'execution_authority': False, 'order_submitted': False,
        'next_action': checks[0]['next_action'] if checks and checks[0]['severity'] in ('block', 'process', 'review') else 'review_preview',
        'checks': checks, 'plan_fields_complete': bool(structural_complete),
        'thesis_quality': 'NOT_ASSESSED_BY_THIS_ENGINE',
        'forecast_probability': None,
        'evidence_review': 'fixture_complete' if review_valid and ctx.review_is_fixture else 'complete' if review_valid else 'not_current',
        'review_scope': 'thesis_and_context_only',
        'review_binding': thesis_binding,
        'economic_checks_recomputed': True,
        'quote_id': ctx.quote_id, 'binding': binding,
        'binding_is_authorization': False,
        'account_version': ctx.account_version, 'policy_version': ctx.policy_version,
        'expires_at': expires.isoformat(),
        'valuation': {'complete': not missing, 'missing_instruments': missing,
                      'equity': cash_text(equity) if equity is not None else None,
                      'available_cash': cash_text(free_cash)},
        'preview': {'shares': decimal_text(quantity) if quantity is not None else None,
                    'price': decimal_text(price) if price is not None else None,
                    'value': cash_text(value) if value is not None else None,
                    'cash_after': cash_text(after_cash) if after_cash is not None and after_cash >= 0 else None,
                    'shares_after': decimal_text(after_shares) if after_shares is not None and after_shares >= 0 else None,
                    'position_weight_after': decimal_text(after_weight) if after_weight is not None else None,
                    'equity_after': cash_text(after_equity) if after_equity is not None else None,
                    'assumptions': ['Zero explicit fees in this preview', 'Liquidity depth and market impact not modeled',
                                    'No fill, reservation or order is created']}}


def verify_preview(prior: dict, plan: Plan, ctx: Context, *, now: datetime) -> bool:
    """Read-only TOCTOU check. Even True grants no order or execution permission."""
    ctx.validate()
    try:
        expiry = stamp(datetime.fromisoformat(prior['expires_at']))
        now = stamp(now)
        fresh = evaluate(plan, ctx, now=now)
        return (prior.get('schema') == 'trading_lab.preflight.v1' and
                prior.get('binding') == preview_binding(plan, ctx) and now < expiry and
                fresh['state'] not in ('BLOCKED', 'PLAN_INCOMPLETE', 'REVIEW_NEEDED'))
    except (KeyError, TypeError, ValueError):
        return False
