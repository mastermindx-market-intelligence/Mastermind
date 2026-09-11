// Offline behavior contracts; synthetic fixtures, not historical market outcomes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const target = process.env.TARGET_MODULE || './compiled/auctionContext.js';
const {computeAsOfAuctionContext: compute, snapshotMatchesRequest: matches} = require(target);
const {calculateFixedRangeVolumeProfile: profile} = require('./compiled/terminal_analytics_pinned.js');
const T = 1788825600;
const source = {provider:'fixture',instrument:'BTC-USD',venue:'fixture-venue',priceUnit:'USD',
 volumeUnit:'BTC',vintage:'fixture-vintage',timeBasis:'utc_epoch_seconds',calendar:'24x7_utc'};
const r0 = {source,decisionAt:T+99*180,analysisSeconds:180,lookback:99,bins:24,valueAreaFraction:.7,
 balancePeriods:20,evidenceMode:'selected_historical_vintage'};
const clone = x => JSON.parse(JSON.stringify(x));
const tests=[];const test=(name,fn)=>{try{fn();tests.push({name,status:'PASS'});}catch(e){tests.push({name,status:'FAIL',error:e.stack});}};
function fixture(parents=99, mode='up'){
 const cs=[];
 for(let i=0;i<parents*3;i++){
  const o=100+(i%11)*.25,c=mode==='flat'?o:o+(mode==='down'?-.1:.1);
  cs.push({start:T+i*60,open:o,high:Math.max(o,c)+.2,low:Math.min(o,c)-.2,close:c,
   volume:1+i%7,observedAt:T+(i+1)*60});
 }
 return fromChildren(cs);
}
function fromChildren(cs){
 const ps=[];
 for(let i=0;i<cs.length;i+=3){const q=cs.slice(i,i+3);if(q.length!==3)continue;
  ps.push({start:q[0].start,open:q[0].open,high:Math.max(...q.map(x=>x.high)),low:Math.min(...q.map(x=>x.low)),
   close:q[2].close,volume:q.reduce((s,x)=>s+x.volume,0),observedAt:q[2].start+60});}
 return{p:{source:clone(source),seconds:180,rows:ps},c:{source:clone(source),seconds:60,rows:cs}};
}
function run(f=fixture(),r=r0){return compute(r,f.p,f.c);}
function frozen(x){Object.freeze(x);for(const v of Object.values(x))if(v&&typeof v==='object')frozen(v);return x;}

test('exact_existing_profile_source_blob',()=>{const b=fs.readFileSync('./source/terminal_analytics_pinned.ts');
 assert.equal(crypto.createHash('sha1').update(Buffer.concat([Buffer.from('blob '+b.length+'\0'),b])).digest('hex'),
  'dd6abc4e177ff4870d2b64b927c73d7ea430e2a3');});
test('complete_context_has_two_ready_components',()=>{const s=run();assert.equal(s.profile.state,'ready');assert.equal(s.flow.state,'ready');});
test('exact_profile_reuse_not_new_math',()=>{const f=fixture(),s=run(f);const bs=f.p.rows.map(x=>({time:String(x.start),o:x.open,h:x.high,l:x.low,c:x.close,v:x.volume}));
 assert.deepEqual(s.profile.value.profile,profile(bs,Math.min(...bs.map(x=>x.l)),Math.max(...bs.map(x=>x.h))));});
test('all_positive_polarity_is_100',()=>{const v=run().flow.value;assert.equal(v.latestDeltaPct,100);assert.equal(v.balanceDeltaPct,100);});
test('all_negative_polarity_is_minus100',()=>{const v=run(fixture(99,'down')).flow.value;assert.equal(v.latestDeltaPct,-100);assert.equal(v.balanceDeltaPct,-100);});
test('latest_ratio_and_rolling_balance_are_different',()=>{const f=fixture();for(const c of f.c.rows.slice(-3)){c.close=c.open-.1;c.high=c.open+.2;c.low=c.close-.2;}
 const s=run(fromChildren(f.c.rows));assert.equal(s.flow.value.latestDeltaPct,-100);assert.ok(s.flow.value.balanceDeltaPct>0);});
test('window_is_anchored_at_requested_cutoff',()=>{const s=run();assert.equal(s.windowStart,T);assert.equal(s.windowEnd,r0.decisionAt);});
test('future_extremes_do_not_change_past_profile',()=>{const a=fixture(),b=fixture(110);for(const x of b.p.rows.slice(99)){x.high=1e9;}
 assert.deepEqual(run(a),run(b));});
test('unfinished_parent_excluded',()=>{const a=run(fixture(100),{...r0,decisionAt:r0.decisionAt+179});assert.equal(a.profile.present,99);assert.equal(a.windowEnd,r0.decisionAt);});
test('later_cutoff_requires_new_complete_bucket',()=>{const s=run(fixture(99),{...r0,decisionAt:r0.decisionAt+180});assert.equal(s.profile.state,'incomplete_window');assert.equal(s.profile.present,98);});
test('missing_trailing_bars_not_silently_shifted',()=>{const f=fixture(100);f.p.rows.pop();const s=run(f,{...r0,decisionAt:T+100*180});assert.equal(s.profile.state,'incomplete_window');assert.equal(s.profile.value,null);});
test('missing_middle_parent_not_neutral',()=>{const f=fixture();f.p.rows.splice(50,1);assert.equal(run(f).profile.state,'incomplete_window');});
test('missing_child_does_not_hide_valid_profile',()=>{const f=fixture();f.c.rows.splice(240,1);const s=run(f);assert.equal(s.profile.state,'ready');assert.equal(s.flow.state,'incomplete_window');assert.equal(s.flow.value,null);});
test('absent_optional_child_feed_is_explicit',()=>{const f=fixture();const s=compute(r0,f.p,null);assert.equal(s.profile.state,'ready');assert.equal(s.flow.state,'missing_source');});
test('absent_parent_feed_is_explicit',()=>{assert.equal(compute(r0,null).profile.state,'missing_source');});
for(const key of ['provider','instrument','venue','priceUnit','volumeUnit','vintage']){
 test('child_'+key+'_mismatch_not_silently_mixed',()=>{const f=fixture();f.c.source[key]='different';const s=run(f);assert.equal(s.profile.state,'ready');assert.equal(s.flow.state,'source_mismatch');});
 test('parent_'+key+'_mismatch_not_silently_mixed',()=>{const f=fixture();f.p.source[key]='different';assert.equal(run(f).profile.state,'source_mismatch');});
}
test('wrong_child_cadence_rejected',()=>{const f=fixture();f.c.seconds=180;assert.equal(run(f).flow.state,'source_mismatch');});
test('untrusted_display_epoch_contract_rejected',()=>{assert.throws(()=>run(fixture(),{...r0,source:{...source,timeBasis:'display_epoch'}}),TypeError);});
test('unsupported_equity_calendar_rejected',()=>{assert.throws(()=>run(fixture(),{...r0,source:{...source,calendar:'NYSE'}}),TypeError);});
test('identical_duplicates_are_idempotent',()=>{const f=fixture();f.p.rows.push(clone(f.p.rows[10]));f.c.rows.push(clone(f.c.rows[10]));assert.deepEqual(run(f),run());});
test('conflicting_selected_bars_refused',()=>{const f=fixture();f.p.rows.push({...f.p.rows[10],volume:33});assert.equal(run(f).profile.state,'conflicting_bars');});
test('child_conflict_does_not_mutate_profile',()=>{const f=fixture();f.c.rows.push({...f.c.rows[10],volume:33});const s=run(f);assert.equal(s.profile.state,'ready');assert.equal(s.flow.state,'conflicting_bars');});
test('input_order_does_not_change_result',()=>{const f=fixture();f.p.rows.reverse();f.c.rows.reverse();assert.deepEqual(run(f),run());});
test('input_and_output_do_not_alias',()=>{const f=fixture(),r=clone(r0),s=run(f,r);f.p.rows[0].volume=999;r.source.venue='new';assert.equal(s.source.venue,'fixture-venue');assert.notEqual(s.profile.value.representedVolume,999);});
test('deep_frozen_inputs_accepted',()=>{const f=frozen(fixture()),r=frozen(clone(r0));assert.equal(run(f,r).profile.state,'ready');});
test('display_timeframe_does_not_change_analysis',()=>{assert.deepEqual(run(fixture(),{...r0,displaySeconds:60}),run(fixture(),{...r0,displaySeconds:3600}));});
test('changing_analysis_timeframe_requires_matching_feed',()=>{assert.equal(run(fixture(),{...r0,analysisSeconds:300}).profile.state,'source_mismatch');});
test('late_observation_does_not_become_eligible',()=>{const f=fixture();f.p.rows[10].observedAt=r0.decisionAt+1;
 const s=run(f,{...r0,evidenceMode:'observed_by_cutoff'});assert.equal(s.profile.state,'unavailable_by_cutoff');});
test('missing_observation_clock_not_as_known_live',()=>{const f=fixture();delete f.p.rows[0].observedAt;assert.equal(run(f,{...r0,evidenceMode:'observed_by_cutoff'}).profile.state,'unavailable_by_cutoff');});
test('known_observations_ready_but_not_original_feed_proof',()=>{const s=run(fixture(),{...r0,evidenceMode:'observed_by_cutoff'});assert.equal(s.profile.state,'ready');assert.equal(s.claimsOriginalLiveFeed,false);});
test('historical_vintage_does_not_masquerade_as_live',()=>{const f=fixture();for(const b of f.p.rows)b.observedAt=r0.decisionAt+1000;const s=run(f);assert.equal(s.profile.state,'ready');assert.equal(s.evidenceMode,'selected_historical_vintage');assert.equal(s.claimsOriginalLiveFeed,false);});
test('future_corrected_version_cannot_break_known_past',()=>{const f=fixture();f.p.rows.push({...f.p.rows[0],volume:1,observedAt:r0.decisionAt+5});assert.equal(run(f,{...r0,evidenceMode:'observed_by_cutoff'}).profile.state,'ready');});
test('eligible_conflict_cannot_hide_behind_newer_winner',()=>{const f=fixture();f.p.rows.push({...f.p.rows[0],volume:1});f.p.rows.reverse();assert.equal(run(f).profile.state,'conflicting_bars');});
test('final_bar_observed_before_close_refused',()=>{const f=fixture();f.p.rows[0].observedAt=T;assert.equal(run(f,{...r0,evidenceMode:'observed_by_cutoff'}).profile.state,'invalid_input');});
test('null_volume_is_not_zero',()=>{const f=fixture();f.p.rows[0].volume=null;assert.equal(run(f).profile.state,'invalid_input');});
test('boolean_volume_is_not_one',()=>{const f=fixture();f.p.rows[0].volume=true;assert.equal(run(f).profile.state,'invalid_input');});
test('nonfinite_volume_refused',()=>{for(const value of [NaN,Infinity,-Infinity]){const f=fixture();f.p.rows[0].volume=value;assert.equal(run(f).profile.state,'invalid_input');}});
test('negative_volume_refused',()=>{const f=fixture();f.p.rows[0].volume=-1;assert.equal(run(f).profile.state,'invalid_input');});
test('invalid_high_low_not_repaired_by_swapping',()=>{const f=fixture();f.p.rows[0].low=f.p.rows[0].high+1;assert.equal(run(f).profile.state,'invalid_input');});
test('zero_volume_does_not_create_profile_or_neutral_flow',()=>{const f=fixture();for(const b of [...f.p.rows,...f.c.rows])b.volume=0;const s=run(f);assert.equal(s.profile.state,'zero_volume');assert.equal(s.flow.state,'zero_volume');});
test('flat_single_price_distribution_is_explicit',()=>{const f=fixture();for(const b of [...f.p.rows,...f.c.rows])b.open=b.high=b.low=b.close=100;assert.equal(run(f).profile.state,'point_mass');});
test('unclassified_initial_dojis_remain_unknown',()=>{const cs=fixture().c.rows;for(const b of cs){b.open=b.close=100;b.high=101;b.low=99;}const s=run(fromChildren(cs));assert.equal(s.flow.state,'unknown_polarity');assert.equal(s.flow.value,null);});
test('late_initial_ambiguity_does_not_poison_later_balance',()=>{const cs=fixture().c.rows;cs[0].close=cs[0].open;const s=run(fromChildren(cs));assert.equal(s.flow.state,'ready');});
test('parent_volume_reconciles_with_children',()=>{const f=fixture();f.p.rows[0].volume+=1;assert.equal(run(f).flow.state,'inconsistent_children');});
test('parent_price_reconciles_with_children',()=>{const f=fixture();f.p.rows[0].high+=.01;assert.equal(run(f).flow.state,'inconsistent_children');});
test('tiny_float_volume_roundoff_tolerated',()=>{const f=fixture();f.p.rows[0].volume+=1e-12;assert.equal(run(f).flow.state,'ready');});
test('future_bad_ohlcv_does_not_poison_past',()=>{const f=fixture(100);f.p.rows[99].volume=NaN;assert.equal(run(f).profile.state,'ready');});
test('misaligned_clock_refused',()=>{const f=fixture();f.p.rows[0].start++;assert.equal(run(f).profile.state,'invalid_input');});
test('unsafe_integer_clock_refused',()=>{assert.throws(()=>run(fixture(),{...r0,decisionAt:Number.MAX_SAFE_INTEGER+1}),TypeError);});
test('request_parameters_not_silently_clamped',()=>{for(const patch of [{bins:1},{lookback:0},{valueAreaFraction:0},{analysisSeconds:90},{balancePeriods:100},{bins:24.5}])assert.throws(()=>run(fixture(),{...r0,...patch}),TypeError);});
test('nonfinite_aggregate_volume_refused',()=>{const f=fixture();for(const b of f.p.rows)b.volume=1e308;assert.equal(run(f).profile.state,'invalid_input');});
test('all_output_numbers_are_finite',()=>{const s=run();function walk(v){if(typeof v==='number')assert.ok(Number.isFinite(v));else if(v&&typeof v==='object')Object.values(v).forEach(walk);}walk(s);});
test('no_trade_or_probability_authority',()=>{const s=run();assert.equal(s.usage,'descriptive_research_only');for(const k of ['signal','trade','forecastProbability','size','ranking'])assert.equal(k in s,false);});

test('balance_uses_volume_not_average_percentages',()=>{const f=fixture(2);for(let i=0;i<6;i++){const c=f.c.rows[i];c.volume=i<3?1:9;c.close=c.open+(i<3?.1:-.1);c.high=c.open+.2;c.low=c.open-.2;}
 const v=run(fromChildren(f.c.rows),{...r0,lookback:2,balancePeriods:2,decisionAt:T+360}).flow.value;
 assert.equal(v.latestDeltaPct,-100);assert.equal(v.balanceDeltaPct,-80);});
test('normalized_delta_does_not_overflow',()=>{const cs=fixture().c.rows;for(const c of cs.slice(-3))c.volume=1e307;const v=run(fromChildren(cs)).flow.value;
 assert.equal(v.latestDeltaPct,100);assert.equal(v.balanceDeltaPct,100);});
test('accepted_parent_roundoff_does_not_distort_child_delta',()=>{const f=fixture();for(const b of f.p.rows)b.volume*=1-1e-11;const v=run(f).flow.value;
 assert.equal(v.latestDeltaPct,100);assert.equal(v.balanceDeltaPct,100);});

test('current_result_matches_current_request',()=>{assert.equal(matches(run(),r0),true);});
test('earlier_result_does_not_match_new_cutoff',()=>{assert.equal(matches(run(),{...r0,decisionAt:r0.decisionAt+180}),false);});
test('same_cutoff_different_bins_is_stale',()=>{assert.equal(matches(run(),{...r0,bins:48}),false);});
test('same_cutoff_different_value_area_is_stale',()=>{assert.equal(matches(run(),{...r0,valueAreaFraction:.8}),false);});
test('same_cutoff_different_flow_window_is_stale',()=>{assert.equal(matches(run(),{...r0,balancePeriods:10}),false);});
test('same_cutoff_different_knowledge_mode_is_stale',()=>{assert.equal(matches(run(),{...r0,evidenceMode:'observed_by_cutoff'}),false);});
test('same_cutoff_different_source_vintage_is_stale',()=>{assert.equal(matches(run(),{...r0,source:{...source,vintage:'changed'}}),false);});
test('absent_result_cannot_match',()=>{assert.equal(matches(null,r0),false);});
test('display_only_change_does_not_invalidate_same_analysis',()=>{assert.equal(matches(run(),{...r0,displaySeconds:3600}),true);});

test('nonfinite_profile_output_refused',()=>{const f=fixture();for(const b of f.p.rows){b.open=1e308;b.low=1e308;b.high=1.1e308;b.close=1.05e308;}const s=compute(r0,f.p,null);assert.equal(s.profile.state,'invalid_input');assert.equal(s.profile.value,null);});
test('subminimum_value_area_refused',()=>{assert.throws(()=>run(fixture(),{...r0,valueAreaFraction:.001}),TypeError);});

const report={scope:'New TypeScript adapter, unchanged existing profile dependency, synthetic offline behavior tests only',
 status:tests.every(t=>t.status==='PASS')?'PASS':'FAIL',total:tests.length,passed:tests.filter(t=>t.status==='PASS').length,
 failed:tests.filter(t=>t.status==='FAIL').length,tests};
const dest=process.env.REPORT_PATH||'./results/context_contract.json';fs.writeFileSync(dest,JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({status:report.status,total:report.total,passed:report.passed,failed:report.failed,failures:tests.filter(t=>t.status==='FAIL')},null,2));
process.exitCode=report.failed?1:0;
