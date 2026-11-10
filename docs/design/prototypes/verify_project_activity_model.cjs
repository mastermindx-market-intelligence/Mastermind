'use strict';
// Pure presentation checks. No DOM, browser, network or production owner is used.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, 'project-activity.html'), 'utf8');
const source = html.split('// BEGIN PRESENTATION MODEL')[1]?.split('// END PRESENTATION MODEL')[0];
assert.ok(source, 'The actual inline presentation model must be present.');
const model = vm.runInNewContext('// BEGIN PRESENTATION MODEL' + source + '\n({states, describeObservation})', {}, {timeout:1000});
const expected = {
  active:       {card:'activity', run:true,  operation:true,  history:2, continue:false, animate:true},
  result:       {card:'result',   run:true,  operation:true,  history:2, continue:true,  animate:true},
  stale:        {card:'activity', run:true,  operation:true,  history:2, continue:false, animate:false},
  disconnected: {card:'activity', run:true,  operation:true,  history:2, continue:false, animate:false},
  partial:      {card:'activity', run:true,  operation:true,  history:2, continue:false, animate:false},
  unreadable:   {card:'state',    run:true,  operation:true,  history:2, continue:false, animate:false},
  unknown:      {card:'state',    run:false, operation:true,  history:1, continue:false, animate:false},
  loading:      {card:'state',    run:false, operation:false, history:0, continue:false, animate:false},
  empty:        {card:'state',    run:false, operation:false, history:0, continue:false, animate:false}
};
assert.deepEqual(Object.keys(model.states).sort(), Object.keys(expected).sort());
let cases = 0;
for (const [state, contract] of Object.entries(expected)) {
  for (const mode of ['attended','durable','unavailable']) {
    const view = model.describeObservation(state,mode);
    assert.equal(view.data.kind,contract.card,state);
    assert.equal(view.hasRun,contract.run,state);
    assert.equal(view.showOperation,contract.operation,state);
    assert.equal(view.historyCount,contract.history,state);
    assert.equal(view.canContinue,contract.continue,state);
    assert.equal(view.canAnimate,contract.animate,state);
    if (['loading','empty','unknown','result','unreadable'].includes(state)) {
      assert.equal(view.consequence,'',state + ' must not promise active execution.');
      assert.doesNotMatch(view.announcement,/Keep this session open|Continues after/);
    }
    if (['stale','disconnected'].includes(state)) {
      assert.match(view.announcement,/Last observed:/);
      assert.match(view.inspectorMode,/Last observed:/);
      assert.equal(view.historyRunState,'Last observed working');
    }
    if (['result','unreadable'].includes(state)) {
      assert.equal(view.historyRunState,'Result returned');
      assert.match(view.inspectorMode,/Recorded for completed run:/);
    }
    if (!contract.run) assert.equal(view.inspectorMode,'');
    if (state === 'partial') assert.equal(view.historyRunState,'Working');
    if (state === 'empty') {
      assert.equal(view.inspectorTitle,'Reader coverage');
      assert.equal(view.historyCurrent,false);
      assert.equal(view.historyPrevious,false);
      assert.match(view.historyNote,/No runs returned by this reader/);
    }
    if (state === 'unknown') {
      assert.equal(view.inspectorTitle,'Original request');
      assert.equal(view.historyCurrent,false);
      assert.match(view.coverage,/no run identity is asserted/);
    }
    assert.doesNotMatch(view.historyRunState,/Read disconnected|Partial activity|No runs returned/);
    cases += 1;
  }
}
assert.equal(model.describeObservation('active','unavailable').consequence,'Execution mode unavailable');
assert.throws(() => model.describeObservation('invented','attended'));
assert.throws(() => model.describeObservation('active','invented'));
console.log(JSON.stringify({
  status:'PASS',
  observation_mode_cases:cases,
  checks:['truthful card and history projection','unknown request without invented run','state-qualified continuity announcements','completed result distinct from active execution','continuation and motion eligibility'],
  browser_rendering:'NOT_VERIFIED',
  production_acceptance:false
},null,2));
