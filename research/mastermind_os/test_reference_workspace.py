"""Browser acceptance for the offline OS reference; never production proof."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from playwright.sync_api import expect, sync_playwright

HTML = Path(__file__).with_name('reference_workspace.html')
ROUTES = ('today', 'program', 'workspace', 'connections', 'evidence', 'ask', 'advanced')


def test_reference_exists():
    assert HTML.is_file(), 'The integrated reference workspace has not been built'


@pytest.fixture(scope='session')
def reference_url():
    # A finite test-only origin serves the authored document, never directories.
    # This honors environments that disallow file: navigation without changing policy.
    content = HTML.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/reference_workspace.html':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/reference_workspace.html'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.fixture(scope='session')
def browser():
    with sync_playwright() as p:
        executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
        browser = p.chromium.launch(headless=True, executable_path=executable)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, reference_url):
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.set_default_timeout(3000)
    errors, network = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: network.append(request.url) if request.url != reference_url else None)
    try:
        page.goto(reference_url)
        yield page
        assert not errors, errors
        assert not network, network
    finally:
        context.close()


def test_default_explains_reference_and_unknown_coverage(page):
    expect(page.get_by_text('Recorded reference · not connected', exact=True)).to_be_visible()
    expect(page.get_by_text('Current Chairman action cannot be established from this recorded view.', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='See the company. Understand the next move.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Send instruction', exact=True)).to_have_count(0)


def test_program_to_workspace(page):
    page.get_by_role('button', name='Open Mastermind OS', exact=True).click()
    expect(page.get_by_role('heading', name='Mastermind OS', exact=True)).to_be_visible()
    page.get_by_role('button', name='Open execution workspace', exact=True).click()
    expect(page.get_by_role('heading', name='Execution Fabric', exact=True)).to_be_visible()
    expect(page.get_by_text('Conversation is not connected', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Send instruction', exact=True)).to_be_disabled()


def test_connections_preserve_same_nodes_in_list(page):
    page.goto(page.url.split('#')[0] + '#connections')
    graph_ids = page.locator('[data-node]').evaluate_all('(nodes) => nodes.map(n => n.dataset.node).sort()')
    assert len(graph_ids) == 6 and len(set(graph_ids)) == 6
    page.get_by_role('button', name='List view', exact=True).click()
    list_ids = page.locator('[data-node]').evaluate_all('(nodes) => nodes.map(n => n.dataset.node).sort()')
    assert list_ids == graph_ids
    expect(page.get_by_text('Design dependencies — not an admitted execution graph.', exact=True)).to_be_visible()


def test_unknown_effect_never_enables_send(page):
    page.get_by_label('Reference scenario', exact=True).select_option('effect_unknown')
    expect(page.get_by_text('Synthetic scenario · outcome unknown', exact=True)).to_be_visible()
    page.goto(page.url.split('#')[0] + '#workspace')
    expect(page.get_by_role('button', name='Send instruction', exact=True)).to_be_disabled()
    expect(page.locator('.callout.bad').get_by_text('Reconcile the original operation. Do not resend.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Inspect reconciliation contract', exact=True)).to_be_enabled()


def test_missing_source_retains_known_evidence_without_false_zero(page):
    page.get_by_label('Reference scenario', exact=True).select_option('source_missing')
    expect(page.get_by_text('Synthetic scenario · source unavailable', exact=True)).to_be_visible()
    expect(page.get_by_text('Known records remain visible. Live totals are withheld.', exact=True)).to_be_visible()
    expect(page.locator('[data-runtime-total]')).to_have_text('Unknown')
    page.get_by_role('button', name='Programs', exact=True).click()
    expect(page.get_by_role('heading', name='Mastermind OS', exact=True)).to_be_visible()


def test_correction_is_explicit_across_routes(page):
    page.get_by_label('Reference scenario', exact=True).select_option('corrected')
    expect(page.get_by_text('Synthetic scenario · evidence corrected', exact=True)).to_be_visible()
    expect(page.get_by_text('An earlier supported claim has been withdrawn. Recheck its evidence.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Programs', exact=True).click()
    expect(page.get_by_text('Synthetic scenario · evidence corrected', exact=True)).to_be_visible()


def test_keyboard_known_navigation(page):
    button = page.get_by_role('button', name='Programs', exact=True)
    button.focus()
    button.press('Enter')
    expect(page.get_by_role('heading', name='Mastermind OS', exact=True)).to_be_visible()
    expect(page.locator('main h1')).to_be_focused()


def test_inspector_closes_and_restores_known_focus(page):
    trigger = page.get_by_role('button', name='Inspect delivery boundary', exact=True)
    trigger.click()
    dialog = page.get_by_role('dialog')
    expect(dialog).to_be_visible()
    page.get_by_role('button', name='Close inspector', exact=True).press('Escape')
    expect(dialog).not_to_be_visible()
    expect(trigger).to_be_focused()


def test_hostile_search_is_text_not_markup(page):
    hostile = '<img src=x onerror="window.__injected=1">'
    page.get_by_label('Search recorded evidence', exact=True).fill(hostile)
    expect(page.get_by_text(f'No recorded item matches “{hostile}”.', exact=True)).to_be_visible()
    assert page.locator('img[src="x"]').count() == 0
    assert page.evaluate('typeof window.__injected') == 'undefined'


def test_search_opens_exact_record(page):
    page.get_by_label('Search recorded evidence', exact=True).fill('autonomy')
    page.get_by_role('button', name='Web CEO autonomy contract', exact=True).click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.get_by_role('link', name='Open canonical source', exact=True)).to_have_attribute('href', re.compile(r'/pull/612$'))


def test_ask_sol_does_not_simulate_a_live_model(page):
    page.goto(page.url.split('#')[0] + '#ask')
    expect(page.get_by_text('No reasoning service is connected', exact=True)).to_be_visible()
    expect(page.locator('textarea')).to_have_count(0)
    expect(page.get_by_role('button', name='Inspect evidence', exact=True)).to_be_enabled()


def test_unknown_hash_does_not_interpret_source_text(page):
    page.goto(page.url.split('#')[0] + '#%3Cscript%3Ealert(1)%3C/script%3E')
    expect(page.get_by_role('heading', name='See the company. Understand the next move.', exact=True)).to_be_visible()


def test_no_persistent_company_state(page):
    page.get_by_role('button', name='Programs', exact=True).click()
    assert page.evaluate('localStorage.length') == 0
    assert page.evaluate('sessionStorage.length') == 0
    assert page.evaluate('document.cookie') == ''


def test_graph_node_opens_source_and_not_a_command(page):
    page.goto(page.url.split('#')[0] + '#connections')
    page.locator('[data-node="fabric"]').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    expect(page.get_by_role('link', name='Open canonical source', exact=True)).to_have_attribute('href', re.compile(r'/pull/600$'))
    expect(page.get_by_text('This is a recorded/design relationship, not current runtime execution.', exact=True)).to_be_visible()


def test_csp_is_content_bound_and_no_dynamic_egress():
    text = HTML.read_text()
    csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)"', text).group(1)
    assert "connect-src 'none'" in csp and "form-action 'none'" in csp
    blocks = re.findall(r'<(style|script)(?: [^>]*)?>(.*?)</\1>', text, re.S)
    assert blocks, 'The actual inline application sources must be present'
    for _tag, value in blocks:
        digest = base64.b64encode(hashlib.sha256(value.encode()).digest()).decode()
        assert "'sha256-" + digest + "'" in csp
    assert "'unsafe-inline'" not in csp
    assert len(text.encode()) < 192000
    for forbidden in ('fetch(', 'XMLHttpRequest', 'WebSocket(', 'EventSource(', 'sendBeacon(', 'localStorage.', 'sessionStorage.', 'setInterval(', 'serviceWorker'):
        assert forbidden not in text, forbidden
    for private in ('/Users/', '/Volumes/', 'Authorization:', 'sk-proj-'):
        assert private not in text


@pytest.mark.parametrize('route', ROUTES)
@pytest.mark.parametrize('viewport', [(1440, 1000), (1024, 768), (390, 844)])
def test_responsive_routes_have_no_horizontal_overflow(page, route, viewport):
    width, height = viewport
    page.set_viewport_size({'width': width, 'height': height})
    page.goto(page.url.split('#')[0] + '#' + route)
    expect(page.locator('main h1')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), (route, viewport)


# These run the exact pure presentation module in Node, not a browser or a DOM.
# They cannot establish CSS/layout, native dialog, CSP enforcement or accessibility.
def run_presentation_expression(expression: str):
    text = HTML.read_text()
    found = re.search(r'<script data-purpose="presentation-model">(.*?)</script>', text, re.S)
    assert found is not None, 'The shared executable relationship/focus model is missing'
    node = shutil.which('node')
    assert node is not None, 'Node is required for the source-only model checks'
    driver = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const context = vm.createContext({});
vm.runInContext(input.source, context, { timeout: 1000 });
const result = vm.runInContext(input.expression, context, { timeout: 1000 });
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        [node, '-e', driver],
        input=json.dumps({'source': found.group(1), 'expression': expression}),
        text=True, capture_output=True, timeout=5, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_presentation_model_has_real_typed_edges():
    model = run_presentation_expression('ReferencePresentation.graph()')
    assert {n['id'] for n in model['nodes']} == {'os', 'admission', 'fabric', 'consumer', 'continuity', 'proof'}
    pairs = {(e['from'], e['to'], e['kind']) for e in model['edges']}
    assert pairs == {
        ('os', 'fabric', 'product_scope'), ('os', 'consumer', 'product_scope'),
        ('admission', 'fabric', 'prerequisite'), ('fabric', 'consumer', 'observation'),
        ('fabric', 'continuity', 'return_path'), ('consumer', 'proof', 'user_journey'),
        ('continuity', 'proof', 'consumption'),
    }
    assert all(e['label'] and e['source'] and e['path'].startswith('M ') for e in model['edges'])
    assert model['authority'] == 'DESIGN_REFERENCE_ONLY'


def test_presentation_model_edges_touch_real_node_boundaries():
    model = run_presentation_expression('ReferencePresentation.graph()')
    nodes = {n['id']: n for n in model['nodes']}
    for edge in model['edges']:
        for point, identity in [(edge['start'], edge['from']), (edge['end'], edge['to'])]:
            n = nodes[identity]
            assert n['x'] <= point['x'] <= n['x'] + n['width']
            assert n['y'] <= point['y'] <= n['y'] + n['height']
            assert point['x'] in (n['x'], n['x'] + n['width']) or point['y'] in (n['y'], n['y'] + n['height'])
    assert all(0 <= n['x'] and 0 <= n['y'] and n['x'] + n['width'] <= model['width'] and n['y'] + n['height'] <= model['height'] for n in nodes.values())


@pytest.mark.parametrize('mutation', [
    "edges[0].to = 'missing'",
    "edges.push({...edges[0]})",
    "edges[0].kind = 'runtime_admission'",
    "nodes.push({...nodes[0]})",
])
def test_presentation_model_rejects_ambiguous_design_relationships(mutation):
    expression = """(() => {
      const base = ReferencePresentation.graph();
      const nodes = base.nodes.map(n => ({...n}));
      const edges = base.edges.map(e => ({...e}));
      %s;
      try { ReferencePresentation.compose(nodes, edges); return false; }
      catch (error) { return error.message === 'INVALID_DESIGN_RELATIONSHIPS'; }
    })()""" % mutation
    assert run_presentation_expression(expression) is True


def test_presentation_model_is_pure_and_repeatable():
    assert run_presentation_expression("""(() => {
      const base = ReferencePresentation.graph();
      const before = JSON.stringify(base);
      const a = ReferencePresentation.compose(base.nodes, base.edges);
      const b = ReferencePresentation.compose(base.nodes, base.edges);
      return JSON.stringify(a) === JSON.stringify(b) && before === JSON.stringify(base);
    })()""") is True


@pytest.mark.parametrize('origin_valid,fallback_valid,expected', [
    (True, True, 'origin'), (False, True, 'fallback'), (False, False, None),
])
def test_presentation_model_selects_connected_focus_return(origin_valid, fallback_valid, expected):
    # Minimal inputs test a pure choice, not mocked DOM focus behavior.
    result = run_presentation_expression("""(() => {
      const origin = { name: 'origin', isConnected: %s, focus() {} };
      const fallback = { name: 'fallback', isConnected: %s, focus() {} };
      const selected = ReferencePresentation.focusTarget(origin, fallback);
      return selected === null ? null : selected.name;
    })()""" % (json.dumps(origin_valid), json.dumps(fallback_valid)))
    assert result == expected


def test_presentation_model_does_not_choose_disabled_return_control():
    assert run_presentation_expression("""(() => {
      const origin = { isConnected: true, disabled: true, focus() {} };
      const fallback = { isConnected: true, focus() {} };
      return ReferencePresentation.focusTarget(origin, fallback) === fallback;
    })()""") is True


def test_graph_and_list_render_same_relationships(page):
    page.goto(page.url.split('#')[0] + '#connections')
    paths = page.locator('path[data-edge]')
    expect(paths).to_have_count(7)
    graph_ids = sorted(paths.evaluate_all('(rows) => rows.map(r => r.dataset.edge)'))
    list_ids = sorted(page.locator('button[data-relation]').evaluate_all('(rows) => rows.map(r => r.dataset.relation)'))
    assert graph_ids == list_ids
    page.get_by_role('button', name='List view', exact=True).click()
    expect(page.locator('path[data-edge]')).to_have_count(0)
    assert sorted(page.locator('button[data-relation]').evaluate_all('(rows) => rows.map(r => r.dataset.relation)')) == graph_ids
    expect(page.get_by_role('button', name='List view', exact=True)).to_be_focused()


def test_skip_link_preserves_current_workspace(page):
    page.goto(page.url.split('#')[0] + '#workspace')
    skip = page.get_by_role('link', name='Skip to main content', exact=True)
    skip.focus()
    skip.press('Enter')
    assert page.url.endswith('#workspace')
    expect(page.get_by_role('heading', name='Execution Fabric', exact=True)).to_be_focused()


def test_search_inspector_restores_search_input_not_removed_result(page):
    search = page.get_by_label('Search recorded evidence', exact=True)
    search.fill('autonomy')
    page.get_by_role('button', name='Web CEO autonomy contract', exact=True).click()
    page.get_by_role('button', name='Close inspector', exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    expect(search).to_be_focused()


def test_narrow_connections_default_to_readable_equivalent_list(page):
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(page.url.split('#')[0] + '#connections')
    expect(page.locator('path[data-edge]')).to_have_count(0)
    expect(page.locator('button[data-relation]')).to_have_count(7)
    expect(page.locator('[data-node]')).to_have_count(6)
    expect(page.get_by_role('button', name='Graph view', exact=True)).to_be_disabled()


def test_application_focus_calls_are_centralized_through_connected_guard():
    text = HTML.read_text()
    scripts = re.findall(r'<script(?: [^>]*)?>(.*?)</script>', text, re.S)
    assert len(scripts) == 2
    app = scripts[1]
    assert 'function focusConnected(' in app
    assert 'ReferencePresentation.focusTarget' in app
    # There must be exactly one actual DOM focus invocation: inside focusConnected.
    assert app.count('.focus(') == 1


def test_acceptance_environment_is_epoch_qualified():
    record = json.loads(Path(__file__).with_name('reference_acceptance.json').read_text())
    current = record['environment']
    native = record['native_source_checks']
    assert current['scope'] == 'current_native_source_check_environment'
    assert current['python'] == native['python']
    assert current['node'] == native['node']
    historical = record['historical_environment']
    assert historical['scope'] == 'pre_recovery_original_reference_checkpoint'
    assert historical['python'] == '3.13.5'
    assert historical['node'] == 'v22.16.0'
