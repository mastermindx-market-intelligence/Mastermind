"""Actual API response -> shipped browser qualifier; synthetic snapshots only."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from app import portfolio_scenarios as api
from tests.test_portfolio_scenarios_api import (
    HEADERS, client, isolated_owners, payload,
)

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / 'app/static/portfolio_scenarios.js'
NODE = shutil.which('node')


def evaluate(response, packet, expression='lab.validateResponse(input.response,input.packet)'):
    if not NODE:
        pytest.skip('Node required for shipped browser-source execution')
    program = '''const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const context={window:{},document:{getElementById:()=>null},URL,Date,Map,Set,Object,Number,JSON,TextDecoder};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const lab=context.window.MastermindScenarioLab;
process.stdout.write(JSON.stringify(''' + expression + '''));'''
    run = subprocess.run([NODE, '-e', program, str(JS)],
                         input=json.dumps({'response': response, 'packet': packet}, allow_nan=False),
                         capture_output=True, text=True, timeout=10, check=True)
    return json.loads(run.stdout)


def response_for(client, data=None):
    packet = payload() if data is None else data
    response = client.post(api.PATH, json=packet, headers=HEADERS)
    assert response.status_code == 200
    return response.json(), packet


def test_actual_native_http_response_survives_browser_qualification(client):
    data, packet = response_for(client)
    assert evaluate(data, packet) == {'ok': True, 'empty': False}
    assert data['result']['comparison']['hold_baseline']['source'] == 'unchanged_supplied_book'


def test_partial_scenario_and_missing_hold_are_not_zero(client):
    packet = payload()
    del packet['scenarios'][0]['returns']['AAPL']
    data, packet = response_for(client, packet)
    assert data['status'] == 'PARTIAL'
    assert evaluate(data, packet) == {'ok': True, 'empty': False}
    row = data['result']['comparison']['alternatives'][0]['relative_to_hold']
    assert row['status'] == 'UNAVAILABLE'


def test_positive_delta_never_overrides_concentration_constraint(client):
    packet = payload();packet['mandate']['constraints']['max_instrument_weight'] = .2
    data, packet = response_for(client, packet)
    assert evaluate(data, packet)['ok']
    rows = {r['alternative_id']:r for r in data['result']['comparison']['alternatives']}
    assert rows['rotation']['status'] == 'INELIGIBLE'
    assert rows['rotation']['relative_to_hold']['scenarios'][0]['net_return_delta'] > 0


def test_explicit_all_cash_without_instruments_is_supported(client):
    from tests.test_global_scenario_account import digest
    packet = payload();packet['account']['positions'] = {};packet['prices'] = {};packet['price_evidence'] = {}
    packet['snapshot']['account_sha256'] = digest(packet['account']);packet['universe'] = []
    packet['alternatives'] = [packet['alternatives'][1]];packet['scenarios'][0]['returns'] = {}
    data, packet = response_for(client, packet)
    assert evaluate(data, packet) == {'ok': True, 'empty': False}


def test_missing_native_price_is_an_empty_unavailable_response(client):
    packet = payload();packet['prices'] = {}
    data, packet = response_for(client, packet)
    assert data['result']['comparison'] is None
    assert evaluate(data, packet) == {'ok': True, 'empty': True}


def test_invalid_core_alternative_preserves_unavailable_row(client):
    packet = payload();packet['alternatives'][2]['cash_weight'] = .1
    data, packet = response_for(client, packet)
    assert evaluate(data, packet)['ok']
    row = next(r for r in data['result']['comparison']['alternatives'] if r['alternative_id']=='rotation')
    assert row['status'] == 'UNAVAILABLE'


@pytest.mark.parametrize('path,value', [
    (('authority','can_trade'), True),
    (('result','authority','can_rank'), True),
    (('result','comparison','authority','can_size'), True),
    (('live_account_read',), True),
    (('account_ownership_verified',), True),
    (('historical_original_availability_proven',), True),
    (('input_basis',), 'verified_current_account'),
    (('result','comparison','book','book_id'), 'hk'),
    (('result','comparison','book','base_currency'), 'HKD'),
    (('analysis_as_of',), '2026-11-06T22:00:00Z'),
    (('result','comparison','as_of'), '2026-11-06T22:00:00Z'),
    (('result','scenario_window','end'), '2026-12-05T22:00:00Z'),
    (('result','scenario_window','end'), '2026-11-31T22:00:00Z'),
    (('result','comparison','input_digest'), 'unverified'),
    (('result','comparison','method_version'), 'new-unaccepted-method'),
    (('result','comparison','hold_baseline','source'), 'caller_named_hold'),
    (('result','comparison','hold_baseline','one_time_cost_fraction'), .02),
    (('result','comparison','hold_baseline','scenario_results',0,'one_time_cost'), .02),
    (('result','comparison','alternatives',0,'target_cash_fraction'), True),
    (('result','comparison','alternatives',0,'scenario_results',0,'net_return'), None),
    (('result','comparison','alternatives',0,'relative_to_hold','paired_scenarios'), 999),
    (('result','comparison','alternatives',0,'relative_to_hold','scenarios',0,'hold_net_return'), .8),
])
def test_unsafe_or_mismatched_response_is_withdrawn(client, path, value):
    data, packet = response_for(client)
    target = data
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    assert evaluate(data, packet)['ok'] is False


def test_unknown_or_duplicated_alternative_cannot_replace_requested_set(client):
    data, packet = response_for(client)
    data['result']['comparison']['alternatives'][1]['alternative_id'] = 'cash'
    assert not evaluate(data, packet)['ok']


def test_formatting_never_converts_null_or_boolean_to_zero(client):
    data, packet = response_for(client)
    out = evaluate(data, packet,
        '[lab.formatPercent(null),lab.formatPercent(false),lab.formatPercent(0),'
        'lab.formatPoints(.06024),lab.formatPercent(NaN),lab.formatPercent(Infinity)]')
    assert out == ['\u2014','\u2014','0.000%','+6.024','\u2014','\u2014']


def test_actual_assets_have_no_private_state_or_credential_store(client):
    for url, part in [('/portfolio-scenarios.js', 'MastermindScenarioLab'),('/portfolio-scenarios.css','#portfolio-scenario-lab')]:
        r = client.get(url)
        assert r.status_code == 200 and part in r.text
        assert 'public, max-age=300' == r.headers['Cache-Control']
    source = JS.read_text()
    for forbidden in ('localStorage', 'sessionStorage', 'innerHTML', 'console.log', 'eval(', 'document.cookie'):
        assert forbidden not in source
    assert "body: raw" in source and "redirect: 'error'" in source
    assert "new URL(PATH, window.location.origin)" in source
    assert "token.value = ''" in source
    assert "mine !== generation" in source
    assert 'reader.cancel()' in source
    assert client.get('/portfolio-scenarios.js/../../account.json').status_code == 404


def test_mount_uses_existing_managed_opportunities_shell():
    text = (ROOT/'app/static/index.html').read_text()
    assert text.count('id="portfolio-scenario-lab"') == 1
    assert text.count('src="/portfolio-scenarios.js"') == 1
    assert text.count('href="/portfolio-scenarios.css"') == 1
    assert '<div class="mm-section" data-mm-views="opportunities">\n  <div id="portfolio-scenario-lab">' in text


def test_retained_browser_captures_bind_current_panel_assets_not_unrelated_app_edits():
    import hashlib
    base = ROOT/'research/evidence/multiasset_scenario_browser_20261106'
    receipt = json.loads((base/'receipt.json').read_text())
    assert receipt['scope'] == 'local_synthetic_http_not_production'
    assert receipt['production'] is False and receipt['account_io'] is False
    assert receipt['total_matrices'] == 6 and receipt['total_behavior_assertions'] >= 90
    assert all(not row['page_errors'] for row in receipt['matrices'])
    # Bind only this owned panel. Unrelated edits to the large app shell/auth
    # must not force this feature to regenerate unchanged screenshots.
    for name in ('app/static/portfolio_scenarios.js','app/static/portfolio_scenarios.css'):
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == receipt['source_hashes'][name]
    assert len(receipt['captures']) == 12
    for row in receipt['captures']:
        assert '/' not in row['file'] and row['file'].endswith('.png')
        raw = (base/row['file']).read_bytes()
        assert raw[:8] == b'\x89PNG\r\n\x1a\n'
        assert len(raw) == row['bytes']
        assert hashlib.sha256(raw).hexdigest() == row['sha256']
