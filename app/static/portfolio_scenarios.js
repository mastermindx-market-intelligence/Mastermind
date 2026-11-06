/* Private, non-persistent consumer of the existing portfolio scenario API.
 * No account/quote acquisition, trade action, recommendation, or financial math.
 * Imported bytes go unchanged to the server, including duplicate JSON keys.
 */
(function () {
  'use strict';
  const LIMIT = 1000000;
  const PATH = '/api/portfolio/scenarios/compare';
  const SAFETY = ['can_rank', 'can_gate', 'can_size', 'can_trade', 'can_rebalance'];
  const STATES = ['AVAILABLE', 'PARTIAL', 'INELIGIBLE', 'UNAVAILABLE'];
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const label = x => typeof x === 'string' && x.length > 0 && x.length <= 128 && x.trim() === x;
  const reasons = x => Array.isArray(x) && x.length <= 50 && x.every(label);
  const safe = x => object(x) && x.display_only === true && x.hypothetical_only === true &&
    x.no_predictive_claim === true && object(x.authority) &&
    Object.keys(x.authority).length === SAFETY.length && SAFETY.every(k => x.authority[k] === false);
  function instant(x) {
    if (typeof x !== 'string' || x.length > 64 ||
        !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(x)) return null;
    const day = x.slice(0, 10), d = new Date(day + 'T00:00:00Z'), stamp = Date.parse(x);
    return Number.isFinite(stamp) && Number.isFinite(d.valueOf()) &&
      d.toISOString().slice(0, 10) === day ? stamp : null;
  }
  const formatPercent = x => finite(x) ? (x * 100).toFixed(3) + '%' : '\u2014';
  const formatPoints = x => finite(x) ? (x > 0 ? '+' : '') + (x * 100).toFixed(3) : '\u2014';
  function identities(rows, field) {
    if (!Array.isArray(rows) || !rows.length || rows.length > 30 ||
        rows.some(r => !object(r) || !label(r[field]))) return null;
    const ids = rows.map(r => r[field]);
    return new Set(ids).size === ids.length ? ids.sort() : null;
  }
  const sameIds = (a, b) => a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);
  function validScenario(row) {
    if (!object(row) || !label(row.scenario_id)) return false;
    if (row.status === 'UNAVAILABLE') return reasons(row.reasons) && row.reasons.length > 0;
    return row.status === 'HYPOTHETICAL' && finite(row.gross_return) && finite(row.net_return) &&
      finite(row.one_time_cost) && row.one_time_cost >= 0 && label(row.assumption_ref);
  }
  function validateResponse(data, packet) {
    const bad = () => ({ok: false, empty: true});
    if (!object(packet) || !safe(data) || data.schema !== 'mastermind.global_scenario_response/v1' ||
        !['AVAILABLE', 'PARTIAL', 'UNAVAILABLE'].includes(data.status) ||
        data.input_basis !== 'operator_supplied_snapshot' || data.account_ownership_verified !== false ||
        data.historical_original_availability_proven !== false || data.live_account_read !== false ||
        data.account_mutation !== false || !safe(data.result)) return bad();
    const r = data.result, at = instant(packet.as_of);
    if (at === null || instant(data.analysis_as_of) !== at || instant(r.as_of) !== at ||
        instant(data.received_at) === null || instant(data.received_at) < at ||
        r.schema !== 'mastermind.global_scenario_account/v1' || r.status !== data.status) return bad();
    if (r.comparison === null) return r.status === 'UNAVAILABLE' && reasons(r.reasons) ? {ok: true, empty: true} : bad();
    const c = r.comparison, sids = identities(packet.scenarios, 'scenario_id');
    const aids = identities(packet.alternatives, 'alternative_id');
    if (!safe(c) || c.schema !== 'mastermind.portfolio_global_scenario_context/v1' ||
        c.method_version !== 'fully_funded_read_only_counterfactual.v1' || instant(c.as_of) !== at ||
        c.status !== r.status || !sids || !aids) return bad();
    if (!c.book) return c.status === 'UNAVAILABLE' && reasons(c.reasons) &&
      Array.isArray(c.alternatives) && c.alternatives.length === 0 ? {ok: true, empty: true} : bad();
    if (!object(c.book) || c.book.book_id !== packet.portfolio_id ||
        c.book.base_currency !== packet.mandate.currency || r.base_currency !== packet.mandate.currency ||
        !label(c.book.book_revision) || typeof c.input_digest !== 'string' || !/^[a-f0-9]{64}$/.test(c.input_digest) ||
        !object(r.scenario_window) || instant(r.scenario_window.start) !== at ||
        instant(r.scenario_window.end) === null || instant(r.scenario_window.end) <= at ||
        packet.scenarios.some(s => instant(s.period_start) !== at || instant(s.period_end) !== instant(r.scenario_window.end)) ||
        !sameIds(identities(c.alternatives, 'alternative_id'), aids)) return bad();
    const b = c.hold_baseline;
    if (!object(b) || !STATES.includes(b.status) || b.source !== 'unchanged_supplied_book' ||
        !reasons(b.constraints_breached) || !reasons(b.reasons) || !Array.isArray(b.scenario_results) ||
        b.scenario_results.some(x => !validScenario(x)) ||
        (b.scenario_results.length && !sameIds(identities(b.scenario_results, 'scenario_id'), sids)) ||
        (b.one_time_cost_fraction !== null && b.one_time_cost_fraction !== 0) ||
        b.scenario_results.some(x => x.status === 'HYPOTHETICAL' && x.one_time_cost !== 0)) return bad();
    const base = new Map(b.scenario_results.map(x => [x.scenario_id, x]));
    for (const row of c.alternatives) {
      if (!STATES.includes(row.status) || !reasons(row.reasons) || !Array.isArray(row.scenario_results) ||
          row.scenario_results.some(x => !validScenario(x)) ||
          (row.scenario_results.length && !sameIds(identities(row.scenario_results, 'scenario_id'), sids))) return bad();
      if (row.status !== 'UNAVAILABLE' && (!finite(row.target_cash_fraction) || row.target_cash_fraction < 0 ||
          row.target_cash_fraction > 1 || !finite(row.one_time_cost_fraction) || row.one_time_cost_fraction < 0 ||
          !reasons(row.constraints_breached))) return bad();
      if (row.status === 'INELIGIBLE' && !row.constraints_breached.length) return bad();
      const paired = row.relative_to_hold;
      if (!object(paired) || !['AVAILABLE', 'PARTIAL', 'UNAVAILABLE'].includes(paired.status) ||
          !sameIds(identities(paired.scenarios, 'scenario_id'), sids) || paired.requested_scenarios !== sids.length) return bad();
      const candidates = new Map(row.scenario_results.map(x => [x.scenario_id, x]));
      let count = 0;
      for (const pair of paired.scenarios) {
        if (pair.status === 'UNAVAILABLE') {
          if (!label(pair.reason)) return bad();
          continue;
        }
        const original = candidates.get(pair.scenario_id), hold = base.get(pair.scenario_id);
        if (pair.status !== 'HYPOTHETICAL' || !original || !hold || original.status !== 'HYPOTHETICAL' ||
            hold.status !== 'HYPOTHETICAL' || !finite(pair.net_return_delta) ||
            pair.candidate_net_return !== original.net_return || pair.hold_net_return !== hold.net_return ||
            pair.candidate_one_time_cost !== original.one_time_cost) return bad();
        count++;
      }
      if (paired.paired_scenarios !== count || paired.status !== (count === sids.length ? 'AVAILABLE' : count ? 'PARTIAL' : 'UNAVAILABLE')) return bad();
    }
    return {ok: true, empty: false};
  }
  // The public surface is pure formatting/qualification, never imported state or credentials.
  window.MastermindScenarioLab = Object.freeze({validateResponse, formatPercent, formatPoints});
  const root = document.getElementById('portfolio-scenario-lab');
  if (!root) return;
  let raw = null, packet = null, response = null, state = 'empty', generation = 0, pending = null;
  let selected = '', timer = null;
  const translated = [];
  const zh = () => document.documentElement.getAttribute('data-lang') === 'zh';
  const t = (en, cn) => zh() ? cn : en;
  function node(tag, text, cls) {
    const e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function words(e, en, cn) { translated.push([e, en, cn]); e.textContent = t(en, cn); return e; }
  function field(parent, id, en, cn, type) {
    const box = node('div', undefined, 'scenario-field');
    const l = words(node('label'), en, cn); l.htmlFor = id;
    const input = node('input'); input.id = id; input.type = type;
    box.append(l, input); parent.append(box); return input;
  }
  const details = node('details', undefined, 'scenario-panel');
  const summary = words(node('summary'), 'Portfolio scenario lab', '\u7ec4\u5408\u60c5\u666f\u5206\u6790');
  const intro = words(node('p', undefined, 'scenario-muted'),
    'Compare cash, hold and rotation under explicit assumptions. Nothing here changes an account or places an order.',
    '\u5728\u660e\u786e\u5047\u8bbe\u4e0b\u6bd4\u8f83\u73b0\u91d1\u3001\u6301\u6709\u548c\u8f6e\u6362\u3002\u672c\u529f\u80fd\u4e0d\u4f1a\u4fee\u6539\u8d26\u6237\u6216\u4e0b\u5355\u3002');
  const privacy = words(node('p', undefined, 'scenario-note'),
    'Imported snapshot only: this is not connected to the account displayed above. Use an authorized native-book JSON packet. Inputs and credentials are not saved by this panel.',
    '\u4ec5\u5206\u6790\u5bfc\u5165\u7684\u5feb\u7167\uff0c\u4e0d\u8fde\u63a5\u4e0a\u65b9\u663e\u793a\u7684\u8d26\u6237\u3002\u8bf7\u9009\u62e9\u5df2\u6388\u6743\u7684\u539f\u751f\u7ec4\u5408 JSON \u6587\u4ef6\u3002\u672c\u9762\u677f\u4e0d\u4fdd\u5b58\u8f93\u5165\u6216\u51ed\u8bc1\u3002');
  const form = node('div', undefined, 'scenario-form');
  const file = field(form, 'scenario-file', 'Authorized scenario packet (.json)', '\u5df2\u6388\u6743\u7684\u60c5\u666f\u6587\u4ef6 (.json)', 'file');
  file.accept = '.json,application/json';
  const token = field(form, 'scenario-token', 'Operator credential (never saved)', '\u64cd\u4f5c\u5458\u51ed\u8bc1\uff08\u4e0d\u4fdd\u5b58\uff09', 'password');
  token.autocomplete = 'off'; token.spellcheck = false;
  token.setAttribute('aria-describedby', 'scenario-credential-help');
  const help = words(node('p', undefined, 'scenario-muted'),
    'Use the existing operator credential, never a broker key. It is sent only to this site\u2019s scenario API and cleared before the response.',
    '\u4ec5\u4f7f\u7528\u73b0\u6709\u64cd\u4f5c\u5458\u51ed\u8bc1\uff0c\u4e0d\u662f\u5238\u5546\u5bc6\u94a5\u3002\u51ed\u8bc1\u4ec5\u53d1\u9001\u81f3\u672c\u7ad9\u60c5\u666f API\uff0c\u5e76\u5728\u8fd4\u56de\u7ed3\u679c\u524d\u6e05\u9664\u3002');
  help.id = 'scenario-credential-help';
  const preview = node('p', undefined, 'scenario-input-summary'); preview.id = 'scenario-input-summary';
  const actions = node('div', undefined, 'scenario-actions');
  const run = words(node('button'), 'Compare scenarios', '\u6bd4\u8f83\u60c5\u666f'); run.id = 'scenario-run'; run.type = 'button';
  const clear = words(node('button'), 'Clear private inputs', '\u6e05\u9664\u79c1\u5bc6\u8f93\u5165'); clear.id = 'scenario-clear'; clear.type = 'button';
  actions.append(run, clear);
  const status = node('p'); status.id = 'scenario-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const results = node('div'); results.id = 'scenario-results'; results.setAttribute('role', 'region');
  results.setAttribute('aria-label', 'Hypothetical scenario comparison');
  details.append(summary, intro, privacy, form, help, preview, actions, status, results); root.append(details);
  const messages = {
    empty: ['Choose an authorized packet to begin. No account has been loaded.', '\u9009\u62e9\u5df2\u6388\u6743\u7684\u6587\u4ef6\u5f00\u59cb\u3002\u672a\u8bfb\u53d6\u4efb\u4f55\u8d26\u6237\u3002'],
    reading: ['Reading the selected file locally\u2026', '\u6b63\u5728\u672c\u5730\u8bfb\u53d6\u9009\u5b9a\u6587\u4ef6\u2026'],
    ready: ['Ready for an explicit, private comparison.', '\u53ef\u8fdb\u884c\u9700\u624b\u52a8\u786e\u8ba4\u7684\u79c1\u5bc6\u6bd4\u8f83\u3002'],
    busy: ['Evaluating the supplied assumptions\u2026 Previous results are withdrawn.', '\u6b63\u5728\u8bc4\u4f30\u5bfc\u5165\u7684\u5047\u8bbe\u2026\u4e0a\u6b21\u7ed3\u679c\u5df2\u64a4\u56de\u3002'],
    complete: ['Hypothetical comparison complete. This is not a forecast or permission to trade.', '\u5047\u8bbe\u60c5\u666f\u6bd4\u8f83\u5b8c\u6210\u3002\u8fd9\u4e0d\u662f\u9884\u6d4b\u6216\u4ea4\u6613\u6388\u6743\u3002'],
    invalid: ['The packet is invalid or exceeds the input limit. No request was sent.', '\u6587\u4ef6\u65e0\u6548\u6216\u8d85\u51fa\u8f93\u5165\u9650\u5236\u3002\u672a\u53d1\u9001\u8bf7\u6c42\u3002'],
    credential: ['Enter the existing operator credential to submit.', '\u8bf7\u8f93\u5165\u73b0\u6709\u64cd\u4f5c\u5458\u51ed\u8bc1\u4ee5\u63d0\u4ea4\u3002'],
    denied: ['Authentication or operator access was refused. No result is shown.', '\u8eab\u4efd\u9a8c\u8bc1\u6216\u64cd\u4f5c\u5458\u8bbf\u95ee\u88ab\u62d2\u7edd\u3002\u4e0d\u663e\u793a\u7ed3\u679c\u3002'],
    limited: ['Request limit reached. Nothing will be retried automatically.', '\u8bf7\u6c42\u5df2\u8fbe\u9650\u989d\u3002\u4e0d\u4f1a\u81ea\u52a8\u91cd\u8bd5\u3002'],
    unqualified: ['The server could not qualify these inputs. No zero-return substitute is used.', '\u670d\u52a1\u5668\u65e0\u6cd5\u786e\u8ba4\u8fd9\u4e9b\u8f93\u5165\u3002\u4e0d\u4f1a\u7528\u96f6\u6536\u76ca\u66ff\u4ee3\u3002'],
    unsafe: ['The response did not match the read-only contract. Results were withdrawn.', '\u54cd\u5e94\u4e0d\u7b26\u5408\u53ea\u8bfb\u5408\u540c\u3002\u7ed3\u679c\u5df2\u64a4\u56de\u3002'],
    error: ['The comparison is unavailable. No automatic retry or account action occurred.', '\u6bd4\u8f83\u6682\u4e0d\u53ef\u7528\u3002\u672a\u81ea\u52a8\u91cd\u8bd5\u6216\u6267\u884c\u8d26\u6237\u64cd\u4f5c\u3002']
  };
  const stateName = s => ({AVAILABLE: t('Hypothetical', '\u5047\u8bbe\u60c5\u666f'), PARTIAL: t('Partial coverage', '\u90e8\u5206\u8986\u76d6'),
    INELIGIBLE: t('Outside mandate', '\u8d85\u51fa\u7ec4\u5408\u9650\u5236'), UNAVAILABLE: t('Unavailable', '\u4e0d\u53ef\u7528')})[s] || t('Unavailable', '\u4e0d\u53ef\u7528');
  function reasonLabel(code) {
    const labels = {
      turnover_ceiling: ['Turnover limit exceeded', '\u6362\u624b\u7387\u8d85\u51fa\u9650\u5236'],
      cash_floor: ['Below the cash minimum', '\u4f4e\u4e8e\u6700\u4f4e\u73b0\u91d1\u6bd4\u4f8b'],
      instrument_weight_ceiling: ['Position concentration limit exceeded', '\u5355\u4e00\u6301\u4ed3\u8d85\u51fa\u96c6\u4e2d\u5ea6\u9650\u5236'],
      risk_key_weight_ceiling: ['Shared-risk concentration limit exceeded', '\u5171\u540c\u98ce\u9669\u8d85\u51fa\u96c6\u4e2d\u5ea6\u9650\u5236'],
      scenario_coverage_incomplete: ['Some scenarios lack evidence', '\u90e8\u5206\u60c5\u666f\u8bc1\u636e\u4e0d\u8db3'],
      instrument_return_missing: ['Instrument return assumption missing', '\u7f3a\u5c11\u6807\u7684\u6536\u76ca\u5047\u8bbe'],
      fx_ancestry_unqualified: ['Currency evidence not qualified', '\u6c47\u7387\u8bc1\u636e\u4e0d\u7b26\u5408\u8981\u6c42'],
      candidate_or_hold_scenario_unavailable: ['Candidate or unchanged-book comparison unavailable', '\u65b9\u6848\u6216\u539f\u6301\u4ed3\u7f3a\u5c11\u6bd4\u8f83\u8bc1\u636e'],
      alternative_not_fully_funded: ['Alternative is not fully funded', '\u65b9\u6848\u7684\u8d44\u91d1\u672a\u5b8c\u6574\u914d\u7f6e']
    };
    return labels[code] ? t.apply(null, labels[code]) : t('Evidence unavailable', '\u8bc1\u636e\u4e0d\u53ef\u7528');
  }
  function paint() {
    translated.forEach(([e, en, cn]) => { e.textContent = t(en, cn); });
    run.disabled = !packet || state === 'busy' || state === 'reading';
    root.setAttribute('aria-busy', String(state === 'busy'));
    status.textContent = t.apply(null, messages[state] || messages.error);
    preview.textContent = packet ? t('Imported: ', '\u5bfc\u5165\uff1a') + packet.portfolio_id + ' \u00b7 ' + packet.mandate.currency + ' \u00b7 ' + packet.as_of : '';
    results.replaceChildren();
    if (!response) return;
    const verified = validateResponse(response, packet);
    if (!verified.ok) { response = null; state = 'unsafe'; paint(); return; }
    if (verified.empty) { results.append(node('p', t('No qualified comparison. Missing evidence is not zero risk.', '\u6ca1\u6709\u5408\u683c\u7684\u6bd4\u8f83\u3002\u8bc1\u636e\u7f3a\u5931\u4e0d\u7b49\u4e8e\u96f6\u98ce\u9669\u3002'))); return; }
    const r = response.result, c = r.comparison, ids = packet.scenarios.map(x => x.scenario_id).sort();
    if (!ids.includes(selected)) selected = ids[0];
    results.append(node('p', t('Hypothetical only. Costs are already included; favorable deltas do not override constraints.', '\u4ec5\u4e3a\u5047\u8bbe\u60c5\u666f\u3002\u6210\u672c\u5df2\u8ba1\u5165\uff1b\u6b63\u5411\u5dee\u989d\u4e0d\u4f1a\u8986\u76d6\u7ec4\u5408\u9650\u5236\u3002'), 'scenario-note'));
    results.append(node('p', c.book.base_currency + ' \u00b7 ' + r.scenario_window.start + ' \u2192 ' + r.scenario_window.end, 'scenario-muted'));
    const pick = node('label', t('Scenario assumption', '\u60c5\u666f\u5047\u8bbe')); pick.htmlFor = 'scenario-select';
    const select = node('select'); select.id = 'scenario-select';
    ids.forEach(id => { const option = node('option', id); option.value = id; select.append(option); });
    select.value = selected;
    select.addEventListener('change', () => { selected = select.value; paint(); root.querySelector('#scenario-select').focus(); });
    const controls = node('div', undefined, 'scenario-pick'); controls.append(pick, select); results.append(controls);
    const baseline = c.hold_baseline, held = baseline.scenario_results.find(x => x.scenario_id === selected);
    results.append(node('p', t('Unchanged holdings: ', '\u4fdd\u6301\u5f53\u524d\u6301\u4ed3\uff1a') +
      formatPercent(held && held.status === 'HYPOTHETICAL' ? held.net_return : null) + ' \u00b7 ' + stateName(baseline.status), 'scenario-baseline'));
    if (baseline.constraints_breached.length) results.append(node('p', t('Existing constraints: ', '\u73b0\u6709\u9650\u5236\uff1a') + baseline.constraints_breached.map(reasonLabel).join(', '), 'scenario-warning'));
    const wrap = node('div', undefined, 'scenario-table-wrap'); wrap.tabIndex = 0;
    wrap.setAttribute('aria-label', t('Scenario results, scroll horizontally on narrow screens', '\u60c5\u666f\u7ed3\u679c\uff0c\u7a84\u5c4f\u53ef\u6c34\u5e73\u6eda\u52a8'));
    const table = node('table'), head = node('thead'), tr = node('tr');
    [[ 'Alternative', '\u65b9\u6848' ], ['Net return', '\u51c0\u6536\u76ca'], ['Versus held (pp)', '\u76f8\u5bf9\u6301\u4ed3\uff08\u767e\u5206\u70b9\uff09'],
      ['One-time cost', '\u4e00\u6b21\u6027\u6210\u672c'], ['Cash', '\u73b0\u91d1'], ['Qualification', '\u8bc1\u636e\u4e0e\u9650\u5236']].forEach(pair => {
      const th = node('th', t.apply(null, pair)); th.scope = 'col'; tr.append(th);
    });
    head.append(tr); table.append(head); const body = node('tbody');
    c.alternatives.slice().sort((a, b) => a.alternative_id.localeCompare(b.alternative_id)).forEach(alt => {
      const ar = alt.scenario_results.find(x => x.scenario_id === selected);
      const delta = alt.relative_to_hold.scenarios.find(x => x.scenario_id === selected);
      const row = node('tr'); if (alt.status === 'INELIGIBLE') row.className = 'scenario-ineligible';
      const id = node('th', alt.alternative_id); id.scope = 'row'; row.append(id);
      const values = [formatPercent(ar && ar.status === 'HYPOTHETICAL' ? ar.net_return : null),
        formatPoints(delta && delta.status === 'HYPOTHETICAL' ? delta.net_return_delta : null),
        formatPercent(alt.one_time_cost_fraction), formatPercent(alt.target_cash_fraction)];
      const labels = [t('Net return', '\u51c0\u6536\u76ca'), t('Versus held (pp)', '\u76f8\u5bf9\u6301\u4ed3\uff08\u767e\u5206\u70b9\uff09'),
        t('One-time cost', '\u4e00\u6b21\u6027\u6210\u672c'), t('Cash', '\u73b0\u91d1')];
      values.forEach((v, i) => { const cell = node('td', v); cell.dataset.label = labels[i]; row.append(cell); });
      const qualification = node('td', stateName(alt.status));
      qualification.dataset.label = t('Qualification', '\u8bc1\u636e\u4e0e\u9650\u5236');
      const why = [].concat(alt.constraints_breached || [], alt.reasons || [], ar && ar.status === 'UNAVAILABLE' ? ar.reasons : [],
        delta && delta.status === 'UNAVAILABLE' ? [delta.reason] : []);
      if (why.length) { const codes = Array.from(new Set(why)); const note = node('small', codes.map(reasonLabel).join(' \u00b7 ')); note.title = codes.join(', '); qualification.append(note); }
      row.append(qualification); body.append(row);
    });
    table.append(body); wrap.append(table); results.append(wrap);
  }
  function abort() {
    generation++;
    if (pending) pending.abort(); pending = null;
    if (timer !== null) clearTimeout(timer); timer = null;
    response = null;
  }
  function reset() { abort(); token.value = ''; file.value = ''; raw = null; packet = null; selected = ''; state = 'empty'; paint(); }
  clear.addEventListener('click', reset);
  window.addEventListener('pagehide', reset);
  file.addEventListener('change', async () => {
    abort(); token.value = ''; raw = null; packet = null; selected = '';
    const mine = generation, f = file.files && file.files[0];
    if (!f) { state = 'empty'; paint(); return; }
    state = 'reading'; paint();
    try {
      if (f.size > LIMIT || f.size === 0) throw new Error('input');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await f.arrayBuffer());
      const value = JSON.parse(text);
      if (!object(value) || value.schema !== 'mastermind.global_scenario_request/v1' ||
          !['autonomous', 'china', 'hk'].includes(value.portfolio_id) || instant(value.as_of) === null ||
          !object(value.mandate) || !['USD', 'CNY', 'HKD'].includes(value.mandate.currency) ||
          !identities(value.scenarios, 'scenario_id') || !identities(value.alternatives, 'alternative_id')) throw new Error('input');
      if (mine !== generation) return;
      raw = text; packet = value; state = 'ready';
    } catch (_) { if (mine !== generation) return; state = 'invalid'; }
    paint();
  });
  async function boundedResponse(res) {
    if (Number(res.headers.get('content-length') || 0) > LIMIT || !res.body) throw new Error('response');
    const reader = res.body.getReader(), chunks = []; let bytes = 0;
    try {
      for (;;) {
        const item = await reader.read(); if (item.done) break;
        bytes += item.value.byteLength;
        if (bytes > LIMIT) { await reader.cancel(); throw new Error('response'); }
        chunks.push(item.value);
      }
    } finally { reader.releaseLock(); }
    const joined = new Uint8Array(bytes); let offset = 0;
    chunks.forEach(chunk => { joined.set(chunk, offset); offset += chunk.byteLength; });
    return new TextDecoder('utf-8', {fatal: true}).decode(joined);
  }
  run.addEventListener('click', async () => {
    if (!packet || state === 'busy') return;
    let credential = token.value.trim();
    if (!credential) { state = 'credential'; paint(); token.focus(); return; }
    abort(); const mine = generation, controller = new AbortController(); pending = controller;
    state = 'busy'; token.value = ''; paint();
    timer = setTimeout(() => controller.abort(), 25000);
    try {
      const request = fetch(new URL(PATH, window.location.origin).href, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + credential},
        body: raw, signal: controller.signal, cache: 'no-store', redirect: 'error', credentials: 'omit'
      });
      credential = '';
      const res = await request;
      if (mine !== generation) return;
      if (!res.ok) {
        state = [401, 403].includes(res.status) ? 'denied' : res.status === 429 ? 'limited' :
          [400, 413, 415, 422].includes(res.status) ? 'unqualified' : 'error';
      } else {
        const text = await boundedResponse(res);
        const value = JSON.parse(text);
        if (mine !== generation) return;
        if (!validateResponse(value, packet).ok) state = 'unsafe';
        else { response = value; state = 'complete'; }
      }
    } catch (_) { if (mine === generation) state = 'error'; }
    finally {
      credential = '';
      if (mine === generation) { if (timer !== null) clearTimeout(timer); timer = null; pending = null; paint(); }
    }
  });
  new MutationObserver(paint).observe(document.documentElement, {attributes: true, attributeFilter: ['data-lang']});
  paint();
}());
