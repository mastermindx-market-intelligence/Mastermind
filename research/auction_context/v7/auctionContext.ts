/** Research integration spike. No network, storage, ordering, auth or trading authority.
 * Existing market-data owner MUST select the input vintage and canonical identity.
 * Existing Terminal analytics is imported unchanged; no second profile implementation.
 */
import { calculateFixedRangeVolumeProfile, type DrawingAnalyticsBar,
  type FixedRangeVolumeProfile } from './terminal_analytics_pinned.js';

export type SourceIdentity = Readonly<{
  provider: string; instrument: string; venue: string;
  priceUnit: string; volumeUnit: string; vintage: string;
  timeBasis: 'utc_epoch_seconds'; calendar: '24x7_utc';
}>;
export type Candle = Readonly<{
  start: number; open: number; high: number; low: number; close: number;
  volume: number; observedAt?: number;
}>;
export type Feed = Readonly<{
  source: SourceIdentity; seconds: number; rows: readonly Candle[];
}>;
export type Request = Readonly<{
  source: SourceIdentity; decisionAt: number;
  evidenceMode: 'selected_historical_vintage' | 'observed_by_cutoff';
  analysisSeconds: number; lookback: number; bins: number;
  valueAreaFraction: number; balancePeriods: number;
}>;
export type State = 'ready' | 'missing_source' | 'source_mismatch' | 'invalid_input'
  | 'conflicting_bars' | 'unavailable_by_cutoff' | 'incomplete_window'
  | 'zero_volume' | 'point_mass' | 'unknown_polarity' | 'inconsistent_children';
export type Component<T> = Readonly<{
  state: State; reason: string; value: T | null;
  expected: number; present: number; lastCompleteEnd: number | null;
}>;
export type ProfileContext = {
  method: 'terminal_candle_overlap_v1'; sourceSeconds: number;
  pocZone: readonly [number, number]; pocCenter: number;
  valueArea: readonly [number, number]; binWidth: number;
  pocVolumeShare: number; representedVolume: number;
  profile: FixedRangeVolumeProfile;
};
export type FlowContext = {
  method: 'minute_polarity_volume_estimate_v1'; childSeconds: 60;
  latestDeltaPct: number; balanceDeltaPct: number; balancePeriods: number;
  proxyOnly: true; polarityInitialization: 'unknown_until_observed_price_direction';
};
export type Snapshot = Readonly<{
  usage: 'descriptive_research_only'; source: SourceIdentity;
  decisionAt: number; analysisSeconds: number; windowStart: number; windowEnd: number;
  evidenceMode: Request['evidenceMode']; claimsOriginalLiveFeed: false;
  construction: Readonly<{ lookback: number; bins: number; valueAreaFraction: number; balancePeriods: number }>;
  profile: Component<ProfileContext>; flow: Component<FlowContext>;
}>;
const identityKeys = ['provider', 'instrument', 'venue', 'priceUnit', 'volumeUnit',
  'vintage', 'timeBasis', 'calendar'] as const;
const finite = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const integer = (x: unknown): x is number => finite(x) && Number.isSafeInteger(x);
const positiveInt = (x: unknown): x is number => integer(x) && x > 0;
const sourceValid = (x: SourceIdentity): boolean => !!x && identityKeys.every(k =>
  typeof x[k] === 'string' && x[k].length > 0) &&
  x.timeBasis === 'utc_epoch_seconds' && x.calendar === '24x7_utc';
const sameSource = (a: SourceIdentity, b: SourceIdentity): boolean =>
  sourceValid(a) && sourceValid(b) && identityKeys.every(k => a[k] === b[k]);
const numberKeys = ['open', 'high', 'low', 'close', 'volume'] as const;
function validCandle(c: Candle): boolean {
  return numberKeys.every(k => finite(c[k])) && c.low > 0 &&
    c.low <= Math.min(c.open, c.close) && Math.max(c.open, c.close) <= c.high && c.volume >= 0;
}
function sameCandle(a: Candle, b: Candle): boolean {
  return numberKeys.every(k => a[k] === b[k]) && a.observedAt === b.observedAt;
}
function failure<T>(state: State, reason: string, expected: number, present = 0,
  lastCompleteEnd: number | null = null): Component<T> {
  return { state, reason, expected, present, lastCompleteEnd, value: null };
}
type Selected = { issue: Component<never> | null; rows: Candle[] };
function select(feed: Feed | null | undefined, r: Request, seconds: number,
  from: number, to: number): Selected {
  const expected = (to - from) / seconds;
  const bad = (state: State, reason: string, present = 0): Selected =>
    ({ issue: failure(state, reason, expected, present), rows: [] });
  if (!feed) return bad('missing_source', 'Required feed is absent.');
  if (!sameSource(feed.source, r.source) || feed.seconds !== seconds)
    return bad('source_mismatch', 'Provider/instrument/venue/units/vintage/cadence must match.');
  if (!Array.isArray(feed.rows)) return bad('invalid_input', 'Rows must be an array.');
  const found = new Map<number, Candle>();
  let notYetKnown = 0;
  for (const c of feed.rows) {
    // Unknown identity/time cannot safely be classified as outside the window.
    if (!c || !integer(c.start) || c.start % seconds !== 0)
      return bad('invalid_input', 'Bar start must be aligned safe-integer UTC seconds.');
    if (c.start < from || c.start + seconds > to) continue;
    if (r.evidenceMode === 'observed_by_cutoff') {
      if (!integer(c.observedAt)) return bad('unavailable_by_cutoff', 'Observation clock is absent or invalid.');
      if (c.observedAt > r.decisionAt) { notYetKnown++; continue; }
      if (c.observedAt < c.start + seconds)
        return bad('invalid_input', 'Final bar was marked observed before it closed.');
    }
    if (!validCandle(c)) return bad('invalid_input', 'Invalid OHLCV in the eligible window.');
    const old = found.get(c.start);
    if (old && !sameCandle(old, c))
      return bad('conflicting_bars', 'The existing source owner must select one unambiguous vintage.');
    found.set(c.start, { ...c });
  }
  const rows = [...found.values()].sort((a, b) => a.start - b.start);
  let lastCompleteEnd: number | null = null;
  if (rows.length) lastCompleteEnd = rows[rows.length - 1].start + seconds;
  const contiguous = rows.length === expected && rows.every((c, i) => c.start === from + i * seconds);
  return { rows, issue: contiguous ? null : failure(notYetKnown ? 'unavailable_by_cutoff' : 'incomplete_window',
    'The exact requested window is incomplete; old rows are not shifted forward.',
    expected, rows.length, lastCompleteEnd) };
}
function requestValid(r: Request): boolean {
  return !!r && typeof r === 'object' && sourceValid(r.source) && integer(r.decisionAt) && r.decisionAt >= 0 &&
    positiveInt(r.analysisSeconds) && r.analysisSeconds % 60 === 0 && r.analysisSeconds <= 86400 &&
    positiveInt(r.lookback) && r.lookback <= 2000 &&
    positiveInt(r.bins) && r.bins >= 4 && r.bins <= 200 &&
    finite(r.valueAreaFraction) && r.valueAreaFraction >= 0.01 && r.valueAreaFraction <= 1 &&
    positiveInt(r.balancePeriods) && r.balancePeriods <= r.lookback &&
    ['selected_historical_vintage', 'observed_by_cutoff'].includes(r.evidenceMode);
}
function profileContext(parents: Selected, r: Request): Component<ProfileContext> {
  if (parents.issue) return parents.issue;
  const b = parents.rows;
  const lo = Math.min(...b.map(x => x.low)), hi = Math.max(...b.map(x => x.high));
  const total = b.reduce((s, x) => s + x.volume, 0);
  if (!finite(total)) return failure('invalid_input', 'Aggregate volume overflows.', r.lookback, b.length);
  if (total === 0) return failure('zero_volume', 'No represented volume; no POC invented.', r.lookback, b.length);
  if (lo === hi) return failure('point_mass', 'Single-price distribution; a multi-row profile is undefined.', r.lookback, b.length);
  const input: DrawingAnalyticsBar[] = b.map(x => ({ time: String(x.start), o: x.open,
    h: x.high, l: x.low, c: x.close, v: x.volume }));
  const p = calculateFixedRangeVolumeProfile(input, lo, hi, r.bins, r.valueAreaFraction);
  if (!p) return failure('invalid_input', 'Existing profile function could not compute finite output.', r.lookback, b.length);
  const finiteProfile = [p.totalVolume, p.pocPrice, p.valueAreaLow, p.valueAreaHigh,
    ...p.bins.flatMap(x => [x.low, x.high, x.midpoint, x.volume])].every(finite);
  if (!finiteProfile)
    return failure('invalid_input', 'Existing profile arithmetic produced a nonfinite value.', r.lookback, b.length);
  const bin = p.bins[p.pocIndex];
  return { state: 'ready', reason: 'Candle-derived estimate, not observed trade-at-price volume.',
    expected: r.lookback, present: b.length, lastCompleteEnd: b[b.length - 1].start + r.analysisSeconds,
    value: { method: 'terminal_candle_overlap_v1', sourceSeconds: r.analysisSeconds,
      pocZone: [bin.low, bin.high], pocCenter: p.pocPrice, valueArea: [p.valueAreaLow, p.valueAreaHigh],
      binWidth: bin.high - bin.low, pocVolumeShare: bin.volume / p.totalVolume,
      representedVolume: p.totalVolume, profile: p } };
}
function flowContext(parents: Selected, children: Selected, r: Request): Component<FlowContext> {
  if (parents.issue) return failure(parents.issue.state, 'Parent window is not valid for source-parity checking.',
    r.lookback, parents.rows.length, parents.issue.lastCompleteEnd);
  if (children.issue) return children.issue;
  const ratio = r.analysisSeconds / 60;
  let previous: Candle | null = null, sign: number | null = null;
  const deltas: (number | null)[] = [];
  const childTotals: number[] = [];
  for (let i = 0; i < parents.rows.length; i++) {
    const p = parents.rows[i], cs = children.rows.slice(i * ratio, (i + 1) * ratio);
    let sum = 0, known = true;
    for (const c of cs) {
      if (c.close !== c.open) sign = c.close > c.open ? 1 : -1;
      else if (previous && c.close !== previous.close) sign = c.close > previous.close ? 1 : -1;
      if (c.volume > 0) { if (sign === null) known = false; else sum += sign * c.volume; }
      previous = c;
    }
    // Same canonical selection, not approximate cross-feed matching.
    const equal = (a: number, b: number): boolean => Math.abs(a - b) <= Math.max(1e-12, Math.abs(a) * 1e-10);
    const volume = cs.reduce((s, c) => s + c.volume, 0);
    if (!finite(volume) || !finite(sum))
      return failure('invalid_input', 'Child-volume arithmetic overflows.', r.lookback, parents.rows.length);
    if (p.open !== cs[0].open || p.close !== cs[cs.length - 1].close ||
      p.high !== Math.max(...cs.map(c => c.high)) || p.low !== Math.min(...cs.map(c => c.low)) ||
      !equal(p.volume, volume))
      return failure('inconsistent_children', 'Parent OHLCV does not reconcile with same-source children.', r.lookback, parents.rows.length);
    deltas.push(known ? sum : null);
    childTotals.push(volume);
  }
  const dd = deltas.slice(-r.balancePeriods), bb = parents.rows.slice(-r.balancePeriods);
  if (dd.some(d => d === null)) return failure('unknown_polarity', 'Initial positive-volume dojis lack a known direction.', r.balancePeriods);
  const volumes = childTotals.slice(-r.balancePeriods);
  const volume = volumes.reduce((s, v) => s + v, 0), latest = bb[bb.length - 1];
  const latestVolume = volumes[volumes.length - 1];
  if (volume === 0 || latestVolume === 0)
    return failure('zero_volume', 'A percentage denominator is zero, not neutral pressure.', r.balancePeriods, bb.length);
  const d = dd.reduce<number>((s, x) => s + (x as number), 0);
  if (!finite(volume) || !finite(d)) return failure('invalid_input', 'Rolling arithmetic overflows.', r.balancePeriods, bb.length);
  return { state: 'ready', reason: 'Intrabar candle-polarity proxy; not actual aggressor-side flow.',
    expected: r.balancePeriods, present: bb.length, lastCompleteEnd: latest.start + r.analysisSeconds,
    value: { method: 'minute_polarity_volume_estimate_v1', childSeconds: 60,
      latestDeltaPct: 100 * ((dd[dd.length - 1] as number) / latestVolume),
      balanceDeltaPct: 100 * (d / volume), balancePeriods: r.balancePeriods,
      proxyOnly: true, polarityInitialization: 'unknown_until_observed_price_direction' } };
}
export function computeAsOfAuctionContext(r: Request, parentFeed: Feed | null,
  minuteFeed?: Feed | null): Snapshot {
  if (!requestValid(r)) throw new TypeError('Invalid explicit analysis/source/cutoff contract.');
  const end = Math.floor(r.decisionAt / r.analysisSeconds) * r.analysisSeconds;
  const start = end - r.lookback * r.analysisSeconds;
  const parents = select(parentFeed, r, r.analysisSeconds, start, end);
  const children = select(minuteFeed, r, 60, start, end);
  return { usage: 'descriptive_research_only', source: { ...r.source }, decisionAt: r.decisionAt,
    analysisSeconds: r.analysisSeconds, windowStart: start, windowEnd: end,
    evidenceMode: r.evidenceMode, claimsOriginalLiveFeed: false,
    construction: { lookback: r.lookback, bins: r.bins, valueAreaFraction: r.valueAreaFraction, balancePeriods: r.balancePeriods },
    profile: profileContext(parents, r), flow: flowContext(parents, children, r) };
}

/** Pure comparison for the existing render owner's stale-result guard. No new queue or cache. */
export function snapshotMatchesRequest(s: Snapshot | null, r: Request): boolean {
  if (!s || !requestValid(r) || !s.construction) return false;
  return sameSource(s.source, r.source) && s.decisionAt === r.decisionAt &&
    s.analysisSeconds === r.analysisSeconds && s.evidenceMode === r.evidenceMode &&
    s.construction.lookback === r.lookback && s.construction.bins === r.bins &&
    s.construction.valueAreaFraction === r.valueAreaFraction &&
    s.construction.balancePeriods === r.balancePeriods;
}
