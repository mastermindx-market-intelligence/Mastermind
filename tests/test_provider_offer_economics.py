"""Temporal quotes: fixtures do not authorize a model, account or live request."""
from dataclasses import replace
from decimal import Decimal
import pytest
from control_plane.provider_model_economics import ApiRateCard, ProviderModelCatalog, ModelEconomicsError
from control_plane.provider_offer_economics import ReviewedApiOffer, TimeBoundRate, quote_temporal_offer, require_current_quote

D = Decimal
DIGEST = 'a' * 64
BODY = 'b' * 64
START = '2026-09-01T00:00:00Z'
END = '2026-10-01T00:00:00Z'
PEAK = tuple((d * 1440 + s, d * 1440 + e) for d in range(5) for s, e in ((60, 240), (360, 600)))

def complement(windows):
    result, previous = [], 0
    for start, end in windows:
        if previous < start:
            result.append((previous, start))
        previous = end
    if previous < 10080:
        result.append((previous, 10080))
    return tuple(result)


def rate(name='base', inp='.15', out='.6', lo=0, hi=None, windows=((0, 10080),), start=START, end=END, cached='.003', write=None):
    return TimeBoundRate(ApiRateCard(name, 'opencode_go', lo, hi, D(inp), None if cached is None else D(cached), None if write is None else D(write), D(out)), start, end, windows)


def offer(*rates):
    return ReviewedApiOffer('opencode.deepseek-v4.1-flash', 'opencode', 'deepseek-v4.1-flash', 'opencode_go', DIGEST, END, rates or (rate(),))


def quote(value=None, **kwargs):
    fields = dict(expected_offer_digest=DIGEST, expected_model_key='opencode.deepseek-v4.1-flash', expected_surface='opencode_go', request_digest=BODY, now='2026-09-14T12:00:00Z', context_tokens=1000, input_tokens=1000, output_tokens=100)
    fields.update(kwargs)
    return quote_temporal_offer(value or offer(), **fields)


def check(q, **kwargs):
    fields = dict(now='2026-09-14T12:00:01Z', request_digest=BODY, offer_digest=DIGEST, model_key='opencode.deepseek-v4.1-flash', surface='opencode_go')
    fields.update(kwargs)
    require_current_quote(q, **fields)


def test_uses_existing_calculator_exactly_once(monkeypatch):
    calls = []
    original = ProviderModelCatalog.estimate_api_cash_usd
    def observe(self, *args, **kwargs):
        calls.append(kwargs)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(ProviderModelCatalog, 'estimate_api_cash_usd', observe)
    result = quote()
    assert result.estimated_usage_usd == D('.00021')
    assert len(calls) == 1
    assert result.scope == 'estimate_only_not_capacity_or_execution_authority'


@pytest.mark.parametrize('now,expected', [
    ('2026-09-14T00:59:59.999999Z', 'off'),
    ('2026-09-14T01:00:00Z', 'peak'),
    ('2026-09-14T03:59:59Z', 'peak'),
    ('2026-09-14T04:00:00Z', 'off'),
    ('2026-09-14T05:59:59Z', 'off'),
    ('2026-09-14T06:00:00Z', 'peak'),
    ('2026-09-14T10:00:00Z', 'off'),
    ('2026-09-19T02:00:00Z', 'off'),
    ('2026-09-20T23:59:59Z', 'off'),
    ('2026-09-13T18:00:00-07:00', 'peak'),
])
def test_explicit_utc_schedule(now, expected):
    value = offer(rate('peak', '.3', '1.2', windows=PEAK), rate('off', windows=complement(PEAK)))
    result = quote(value, now=now)
    assert result.rate_id == expected
    assert result.estimated_usage_usd == D('.00042' if expected == 'peak' else '.00021')


def test_quote_expires_at_next_peak_boundary():
    value = offer(rate('peak', '.3', '1.2', windows=PEAK), rate('off', windows=complement(PEAK)))
    result = quote(value, now='2026-09-14T00:59:59Z')
    assert result.valid_until == '2026-09-14T01:00:00Z'
    check(result, now='2026-09-14T00:59:59.999Z')
    with pytest.raises(ModelEconomicsError, match='expired'):
        check(result, now='2026-09-14T01:00:00Z')


@pytest.mark.parametrize('context,expected', [(0, 'short'), (256000, 'short'), (256001, 'long'), (1000000, 'long')])
def test_explicit_integer_context_threshold(context, expected):
    value = offer(rate('short', '.4', '1.6', hi=256000), rate('long', '1.2', '4.8', lo=256001, hi=1000000))
    assert quote(value, context_tokens=context, input_tokens=0).rate_id == expected


def test_context_and_time_bands_compose():
    rates = tuple(rate(f'{n}-{t}', inp, out, lo, hi, windows=win) for n, lo, hi in [('short', 0, 200000), ('long', 200001, 1000000)] for t, inp, out, win in [('peak', '.3', '1.2', PEAK), ('off', '.15', '.6', complement(PEAK))])
    assert quote(offer(*rates), context_tokens=200001, now='2026-09-14T02:00:00Z').rate_id == 'long-peak'


def test_refuses_context_rates_that_overlap_at_the_same_instant():
    value = offer(
        rate('first', windows=((0, 120),)),
        rate('second', lo=500, windows=((60, 180),)),
    )
    with pytest.raises(ModelEconomicsError, match='overlapping time/context rate variants'):
        quote(value)


def test_explicit_promotion_cutover_not_guessed_from_prose():
    cutover = '2026-09-20T04:00:00Z'  # Fictional reviewed fixture, not vendor time.
    value = offer(rate('promo', end=cutover), rate('baseline', '.3', '1.2', start=cutover))
    early = quote(value, now='2026-09-20T03:59:59Z')
    assert early.rate_id == 'promo' and early.valid_until == cutover
    assert quote(value, now=cutover).rate_id == 'baseline'
    with pytest.raises(ModelEconomicsError, match='expired'):
        check(early, now=cutover)


def test_owner_lease_caps_even_all_week_rate():
    value = replace(offer(), valid_until='2026-09-14T12:00:30Z')
    assert quote(value).valid_until == value.valid_until
    with pytest.raises(ModelEconomicsError, match='expired'):
        quote(value, now=value.valid_until)


def test_nonzero_cache_usage_with_unknown_rate_refuses():
    with pytest.raises(ModelEconomicsError, match='no cached price'):
        quote(offer(rate(cached=None)), input_tokens=900, cached_input_tokens=100)
    with pytest.raises(ModelEconomicsError, match='no write price'):
        quote(input_tokens=900, cache_write_tokens=100)


def test_disjoint_cache_input_and_output_no_double_count():
    value = offer(rate(write='.375'))
    result = quote(value, input_tokens=100, cached_input_tokens=800, cache_write_tokens=100, output_tokens=100)
    assert result.estimated_usage_usd == D('.0001149')
    with pytest.raises(ModelEconomicsError, match='exceed context'):
        quote(value, input_tokens=1000, cached_input_tokens=800)


@pytest.mark.parametrize('kwargs', [{'input_tokens': True}, {'context_tokens': None}, {'output_tokens': -1}, {'input_tokens': 1.5}, {'context_tokens': 1000000001}])
def test_invalid_estimates(kwargs):
    with pytest.raises(ModelEconomicsError):
        quote(**kwargs)


@pytest.mark.parametrize('field,value', [('expected_offer_digest', 'c'*64), ('expected_model_key', 'other.model'), ('expected_surface', 'other_surface'), ('request_digest','bad')])
def test_quote_requires_exact_binding(field, value):
    with pytest.raises(ModelEconomicsError):
        quote(**{field:value})


@pytest.mark.parametrize('kwargs', [{'request_digest':'c'*64}, {'offer_digest':'c'*64}, {'model_key':'other.model'}, {'surface':'other'}, {'now':'2026-09-14T11:59:59Z'}])
def test_saved_quote_rebinding_or_future_refuses(kwargs):
    with pytest.raises(ModelEconomicsError):
        check(quote(), **kwargs)


@pytest.mark.parametrize('value', [
    offer(rate('one'),rate('two')),
    offer(rate('same',hi=100),rate('same',lo=101)),
    offer(rate(windows=())),
    offer(rate(windows=((60,240),(200,400)))),
    offer(rate(windows=((100,60),))),
    offer(rate(windows=((False,100),))),
    offer(rate(start=END,end=START)),
    offer(rate(inp='NaN')),
    offer(rate(inp='-1')),
    offer(rate(hi=-1)),
])
def test_invalid_or_ambiguous_schedule_rejected(value):
    with pytest.raises(ModelEconomicsError):
        quote(value)


def test_no_applicable_variant_is_not_free_or_fallback():
    with pytest.raises(ModelEconomicsError, match='no unique'):
        quote(offer(rate(windows=PEAK)))
    with pytest.raises(ModelEconomicsError, match='no unique'):
        quote(offer(rate(hi=999)))


def test_quote_digest_stable_and_changes_with_body_and_token_estimates():
    first = quote()
    assert quote() == first
    assert quote(request_digest='c'*64).quote_digest != first.quote_digest
    assert quote(input_tokens=999).quote_digest != first.quote_digest


def test_expiry_requires_real_datetime_with_timezone():
    with pytest.raises(ModelEconomicsError, match='timestamp'):
        quote(replace(offer(),valid_until='Ends Sep 20'))
    with pytest.raises(ModelEconomicsError, match='timezone'):
        quote(replace(offer(),valid_until='2026-09-20T00:00:00'))


@pytest.mark.parametrize("changes", [{"estimated_usage_usd":D("0")}, {"input_tokens":0}, {"valid_until":END}, {"scope":"authorized"}])
def test_quote_fields_cannot_change_after_quote(changes):
    q = quote(offer(rate(end="2026-09-14T13:00:00Z")))
    with pytest.raises(ModelEconomicsError, match="integrity"):
        check(replace(q, **changes))
