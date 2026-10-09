// Renderer unit test against the actual page script; not browser/e2e acceptance.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(path.join(root, 'app/static/market_view.html'), 'utf8');
// Bind to the owned page's exact renderer and stop before its network call.
// This is strict source selection, not HTML parsing or sanitization. A changed,
// missing or duplicate boundary requires review instead of selecting other code.
const ownedStart = '<script>\n(function () {\n  "use strict";\n\n  var root = document.getElementById("mv-root");';
const ownedEnd = '\n})();\n</script>';
const ownedFetch = '  fetch("/api/market_view", { headers: { "Accept": "application/json" } })';
function ownedRendererPrefix(source) {
  const uniqueIndex = marker => {
    const at = source.indexOf(marker);
    assert.ok(at >= 0 && source.indexOf(marker, at + marker.length) === -1, 'Owned renderer boundary missing or duplicated');
    return at;
  };
  const start = uniqueIndex(ownedStart);
  const end = uniqueIndex(ownedEnd);
  const stop = uniqueIndex(ownedFetch);
  assert.ok(start < stop && stop < end, 'Owned renderer boundaries out of order');
  // HTML closes a script even when the closing tag appears inside a JS comment
  // or string. Reject an earlier close rather than testing code the browser skips.
  const body = source.slice(start + '<script>\n'.length, end);
  assert.ok(!body.toLowerCase().includes('</script'), 'Unexpected early script close in owned renderer');
  const prefix = source.slice(start + '<script>\n'.length, stop);
  assert.ok(prefix.includes('function renderAuctions'), 'actual auction renderer present');
  return prefix;
}
const prefix = ownedRendererPrefix(page);
assert.equal(ownedRendererPrefix('<SCRIPT>unrelated_bootstrap()</SCRIPT>\n' + page), prefix);
assert.throws(() => ownedRendererPrefix(page + ownedStart), /boundary missing or duplicated/);
assert.throws(() => ownedRendererPrefix(page.replace(ownedStart, ownedStart.replace('<script>', '<SCRIPT>'))), /boundary missing or duplicated/);
assert.throws(() => ownedRendererPrefix(page.replace(ownedEnd, '')), /boundary missing or duplicated/);
assert.throws(() => ownedRendererPrefix(page.replace(ownedFetch, '')), /boundary missing or duplicated/);
assert.throws(() => ownedRendererPrefix(ownedFetch + page.replace(ownedFetch, '')), /boundaries out of order/);
for (const close of ['</script>', '</ScRiPt >', '</SCRIPT\t>']) {
  assert.throws(() => ownedRendererPrefix(page.replace(ownedStart, ownedStart + '\n  // ' + close)), /Unexpected early script close/);
}
let lang = 'en';
const sandbox = { URL, document: { getElementById: () => ({}), documentElement: { getAttribute: () => lang } } };
vm.createContext(sandbox);
vm.runInContext(prefix + '\nglobalThis.renderAuctions = renderAuctions; globalThis.renderAuctionRow = renderAuctionRow; globalThis.auctionDollars = auctionDollars; globalThis.statusPill = statusPill;\n})();', sandbox);
const hostileStatus = 'advisory" onmouseover="alert(1)\'&<>';
const escapedStatus = 'advisory&quot; onmouseover=&quot;alert(1)&#39;&amp;&lt;&gt;';
assert.equal(sandbox.statusPill({status: hostileStatus, freshness: {stale: true}}),
  '<span class="pill ' + escapedStatus + '">' + escapedStatus + '</span> <span class="pill stale">stale</span>');
assert.equal(sandbox.statusPill({status: 'validated'}), '<span class="pill validated">validated</span>');
assert.equal(sandbox.statusPill({raw: {artifact_present: false}, status: hostileStatus}), '<span class="pill none">absent</span>');
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
  const rendered = sandbox.renderAuctionRow(row);
  const summary = rendered.match(/<div class="auction-row-summary">([\s\S]*?)<\/div><details class="auction-source-details">/)[1];
  assert.ok(summary.includes(sandbox.auctionDollars(row.offering_amount_usd)));
  assert.ok(!summary.includes(row.episode_id));
  assert.ok(!summary.includes(row.known_at));
  assert.ok(!summary.includes('ANNOUNCED'));
  assert.ok(rendered.includes('<summary>Source details</summary>'));
  assert.ok(rendered.includes('Known at: ' + row.known_at));
}
assert.ok(html.includes('6-week Treasury bill'));
assert.ok(html.includes('95,000,000,000 USD'));
for (const [raw, expected] of [['0', '0 USD'], ['95000000000.1250000000000001', '95,000,000,000.1250000000000001 USD'],
  ['9007199254740993.0100', '9,007,199,254,740,993.0100 USD'], ['-1234.0050', '-1,234.0050 USD']]) {
  assert.equal(sandbox.auctionDollars(raw), expected);
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
assert.ok(unknown.includes('Offering amount: <span class="auction-amount">Unknown'));
assert.ok(unknown.includes('Competitive deadline: Unknown'));
assert.ok(unknown.includes('Awaiting observed results'));
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
assert.ok(chinese.includes('6周 短期国债'));
assert.ok(chinese.includes('<summary>来源详情</summary>'));
assert.ok(sandbox.renderAuctions({}).includes('不可用：生产方背景未发布'));
lang = 'en';
assert.ok(sandbox.renderAuctions({sovereign_auction_context: {available: false, note: '<bad>'}}).includes('Unavailable: &lt;bad&gt;'));
assert.ok(page.includes('var(--panel)'));
assert.ok(page.includes('overflow-wrap: anywhere'));
console.log('Actual renderer assertions passed: exact grouped decimals, readable EN/ZH lifecycle, raw evidence under Source details, 43 past + 3 scheduled grouping/expand, unknowns, safe escaping/links and unavailable.');
