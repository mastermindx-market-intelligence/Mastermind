"""Synthetic demonstration inputs only. No live prices, users or provider calls."""
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal as D
from backend.preflight import Context, Position, Plan, review_binding

NOW = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
SAMPLE_PLAN = {
    'instrument_id': 'DEMO:ASTER', 'side': 'buy', 'unit': 'shares', 'amount': '250', 'horizon': 'swing',
    'thesis': 'Order growth may improve if the new product gains adoption. I need a second independent source.',
    'trigger': 'Wait for the planned price condition and sustained participation, not a single strong candle.',
    'invalidation': 'The next operating update contradicts the adoption assumption.',
    'counter_case': 'The expected growth may already be reflected in the price.'}
CASES = ('current', 'reviewed_example', 'quote_expired', 'missing_marks', 'account_error', 'market_closed', 'advisory')


def context(case='current'):
    if case not in CASES:
        raise ValueError('Unknown fixture case')
    c = Context('demo-user', 'demo-paper', 'PAPER', 7, 'verified', D('70000'), D('5000'), 'USD', (
        Position('DEMO:ASTER', D('1000'), D('100'), D('20'), NOW+timedelta(minutes=1)),
        Position('DEMO:ORION', D('100'), D('0'), D('100'), NOW+timedelta(minutes=1))),
        'DEMO:ASTER', 'demo-quote-7', D('20'), D('20.10'), NOW-timedelta(seconds=2),
        NOW-timedelta(seconds=1), NOW+timedelta(seconds=30), 'USD', 'regular', D('1'),
        'demo-practice-policy', 2, 'deliberate_practice', D('0.35'),
        'demo-market-12', 'swing', NOW+timedelta(minutes=5), 'demo-evidence-3',
        'not_connected', None, None)
    if case == 'reviewed_example':
        c = replace(c, review_state='complete', reviewed_binding=review_binding(Plan.from_payload(SAMPLE_PLAN), c),
                    review_valid_until=NOW+timedelta(seconds=20), review_is_fixture=True)
    elif case == 'quote_expired':
        c = replace(c, quote_observed_at=NOW-timedelta(minutes=2), quote_received_at=NOW-timedelta(minutes=2),
                    quote_valid_until=NOW-timedelta(seconds=1))
    elif case == 'missing_marks':
        c = replace(c, positions=(c.positions[0], replace(c.positions[1], mark=None)))
    elif case == 'account_error':
        c = replace(c, account_state='reconcile_required')
    elif case == 'market_closed':
        c = replace(c, session='closed')
    elif case == 'advisory':
        c = replace(c, policy_mode='advisory')
    return c
