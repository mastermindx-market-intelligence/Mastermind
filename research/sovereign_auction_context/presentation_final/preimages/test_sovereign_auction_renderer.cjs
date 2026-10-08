// Renderer unit test against the actual page script; not browser/e2e acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(path.join(root, 'app/static/market_view.html'), 'utf8');
const script = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x => x[1]).find(x => x.includes('function renderAuctions'));
assert.ok(script, 'actual auction renderer present');
let lang = 'en';
const sandbox = { URL, document: { getElementById: () => ({}), documentElement: { getAttribute: () => lang } } };
vm.createContext(sandbox);
const prefix = script.slice(0, script.indexOf('  fetch("/api/market_view"'));
vm.runInContext(prefix + '\nglobalThis.renderAuctions = renderAuctions;\n})();', sandbox);
const wrapper = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/sovereign_auction_context/event_calendar.json'), 'utf8'));
const original = wrapper.sovereign_auction_context;
const context = { ...structuredClone(original), available: true };
const html = sandbox.renderAuctions({ sovereign_auction_context: context });
assert.ok(html.includes('Sovereign auctions — observed context'));
assert.ok(html.includes('Freshness unassessed'));
assert.ok(html.includes('Importance: Not scored'));
assert.ok(html.includes('Results not observed'));
assert.ok(html.includes('Observed at: 2026-10-08T22:12:22.414829+00:00'));
for (const row of context.events) {
  assert.ok(html.includes(row.episode_id));
  assert.ok(html.includes(row.offering_amount_usd));
  assert.ok(html.includes(row.competitive_deadline_utc));
}
// More than forty prior rows must never bury the three actual upcoming auctions.
const oldRows = Array.from({length: 43}, (_, i) => ({...structuredClone(context.events[0]),
  episode_id: `past-${i}`, label: `Past result ${i}`, auction_date: '2026-10-01', physical_state: 'RESULT_OBSERVED',
  source_state: 'RESULT_OBSERVED', result: { nominal_yield_pct: '3.2' }}));
context.events = [...oldRows, ...context.events];
const grouped = sandbox.renderAuctions({ sovereign_auction_context: context });
assert.ok(grouped.indexOf('Scheduled auctions (3)') < grouped.indexOf('Observed results (43)'));
assert.ok(grouped.indexOf(original.events[2].episode_id) < grouped.indexOf('Past result 0'));
assert.ok(grouped.includes('Show remaining 38'));
const awaiting = {...structuredClone(original.events[0]), physical_state: 'AWAITING_RESULT',
  competitive_deadline_utc: null, time_et: null, offering_amount_usd: null};
const unknown = sandbox.renderAuctions({sovereign_auction_context: {...context, events: [awaiting]}});
assert.ok(unknown.includes('Awaiting results (1)'));
assert.ok(unknown.includes('Competitive deadline (UTC): Unknown'));
assert.ok(unknown.includes('Offering amount (USD): Unknown'));
const hostile = {...structuredClone(original.events[0]), label: '<img src=x onerror="alert(1)">',
  episode_id: '<script>bad</script>', null_reasons: ['<svg onload="bad()">'],
  source_url: 'https://www.treasurydirect.gov/path?q=" onclick="alert(2)'};
const escaped = sandbox.renderAuctions({sovereign_auction_context: {...context, events: [hostile]}});
assert.ok(!escaped.includes('<img src=x'));
assert.ok(!escaped.includes('<script>bad'));
assert.ok(!escaped.includes('<svg onload='));
assert.ok(escaped.includes('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'));
assert.ok(escaped.includes('q=&quot; onclick=&quot;alert(2)'));
const invalidLink = {...hostile, source_url: 'javascript:alert(1)'};
assert.ok(!sandbox.renderAuctions({sovereign_auction_context: {...context, events: [invalidLink]}}).includes('href="javascript:'));
lang = 'zh';
const chinese = sandbox.renderAuctions({ sovereign_auction_context: {...context, events: original.events} });
assert.ok(chinese.includes('国债拍卖 — 已观察背景'));
assert.ok(chinese.includes('新鲜度未评估'));
assert.ok(chinese.includes('尚未观察到结果'));
assert.ok(chinese.includes('重要性：未评分'));
assert.ok(sandbox.renderAuctions({}).includes('不可用：生产方背景未发布'));
lang = 'en';
assert.ok(sandbox.renderAuctions({sovereign_auction_context: {available: false, note: '<bad>'}}).includes('Unavailable: &lt;bad&gt;'));
assert.ok(page.includes('var(--panel)'));
assert.ok(page.includes('overflow-wrap: anywhere'));
console.log('Actual renderer unit assertions passed: real clocks/amounts, EN/ZH, 43 past + 3 scheduled grouping/count/expand, awaiting/null, escaped upstream text and source href, unavailable.');
