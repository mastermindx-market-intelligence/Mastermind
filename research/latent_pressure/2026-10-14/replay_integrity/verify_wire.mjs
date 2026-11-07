// Consume the actual Python-produced fixture snapshots using JavaScript JSON parsing.
// This validates transport representation, not a deployed browser or live data feed.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
const directory = process.argv[2];
if (!directory) throw new Error('Usage: node verify_wire.mjs <replay_integrity-directory>');
const pending = JSON.parse(readFileSync(resolve(directory, 'EXAMPLE_PENDING.json'), 'utf8'));
const committed = JSON.parse(readFileSync(resolve(directory, 'EXAMPLE_COMMITTED.json'), 'utf8'));
const lagged = JSON.parse(readFileSync(resolve(directory, 'EXAMPLE_COVERAGE_LAG.json'), 'utf8'));
const expectedStart = (2n ** 60n) + 2n;
for (const record of pending.records) {
  const episode = record.recovery.sides.bid.pending;
  assert.equal(typeof episode.start_ns, 'string');
  assert.equal(BigInt(episode.start_ns), expectedStart);
  assert.equal(BigInt(episode.start_sequence), expectedStart);
  assert.equal(record.forecast_probability, null);
  assert.equal(record.recovery.forecast_probability, null);
  assert(Object.values(record.authority).every(value => value === false));
}
assert.equal(committed.records[0].recovery.sides.bid.past_recoveries, 1);
assert.equal(committed.records[0].recovery.sides.bid.past_level_depletions, 0);
assert.equal(committed.records[1].recovery.sides.bid.past_level_depletions, 1);
for (const record of lagged.records) {
  assert.equal(record.state, 'COVERAGE_NOT_PROVEN_TO_REQUESTED_CUTOFF');
  assert.equal(BigInt(record.measurement_cutoff_ns), (2n ** 60n) + 6n);
  assert.equal(BigInt(record.requested_cutoff_ns), (2n ** 60n) + 7n);
}
console.log(JSON.stringify({
  status: 'PASSED_PYTHON_TO_JAVASCRIPT_JSON_ROUNDTRIP',
  node_version: process.version,
  exact_large_integer_clocks_and_sequences: true,
  completed_outcomes_match_committed_snapshot: true,
  lagged_coverage_not_extrapolated: true,
  forecast_probabilities_null: true,
  all_action_authorities_false: true,
  origin: 'SYNTHETIC_FIXTURE_NOT_REAL_MARKET_VALIDATION'
}, null, 2));
