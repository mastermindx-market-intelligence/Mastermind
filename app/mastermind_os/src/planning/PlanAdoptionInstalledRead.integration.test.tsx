// @vitest-environment jsdom
// Actual temp-Git installed ADOPT owner output from test_installed_plan_adoption:
// fixed captured a5 compiler + nominal DATA/private Events + real Git CAS +
// inert upstream/PR/grants/root seal fixtures. This is source composition,
// never company adoption, enrolled capability or a live installed receipt.
import {afterEach,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import actual from '../fixtures/plan-adoption-installed-owner.json';
import {decodeProjectPlan} from './project-plan';
import {ProjectPlanContinuity} from './ProjectPlanContinuity';
import {validateProjectDataObservation} from '../knowledge/library/project-data-observation';
import {planAdoptionRequestFromRead} from './plan-adoption-from-read';
afterEach(cleanup);
const selection={work_ref:'WS:PLAN-TEST'};
it('joins the actual final ADOPTION witness to the reopened pinned CODE / current DATA plan',()=>{
 const read=decodeProjectPlan(actual.body,selection);
 const witness=validateProjectDataObservation(actual.witness,{workRef:selection.work_ref,
   canonicalDataCommit:read.source!.commit,executableMacroCommit:actual.witness.executable_macro_commit});
 expect(witness.source_operation?.selection).toEqual(actual.status.selection);
 expect(witness.source_operation?.sources).toHaveLength(3);
 expect(witness.canonical_data_commit).not.toBe(witness.executable_macro_commit);
 expect(read.availability).toBe('AVAILABLE');
 if(read.schema!=='mastermind.workspace_project_plan.v2'||read.availability!=='AVAILABLE')throw Error('actual read unavailable');
 expect(read.continuity.adoption.state).toBe('AVAILABLE');
 const row=read.continuity.proposals.state==='AVAILABLE'?read.continuity.proposals.items[0]:null;
 expect(row?.state==='RECORDED_PROPOSAL'&&row.adoption_relation).toBe('CURRENT_DECISION_REFERENCES_PROPOSAL');
 expect(()=>planAdoptionRequestFromRead(actual.body,selection,'PLAN-PROPOSAL','mmos-project-adopt-'+'a'.repeat(40))).toThrow('PLAN_ADOPTION_PREPARATION_UNAVAILABLE');
});
it('renders actual current decision/predecessor comparison without offering the recorded proposal as a new adoption',()=>{
 const read=decodeProjectPlan(actual.body,selection);
 if(read.schema!=='mastermind.workspace_project_plan.v2'||read.availability!=='AVAILABLE')throw Error('actual read unavailable');
 const view=render(<ProjectPlanContinuity data={read.continuity}/>);
 const compare=screen.getByText('Compare plans').closest('details')!;
 fireEvent.click(compare.querySelector('summary')!);
 expect(compare.open).toBe(true);
 expect(screen.getAllByText('DEC:PLAN-ADOPTION-'+'9'.repeat(40)).length).toBeGreaterThan(0);
 expect(view.container.textContent).toContain('DEC:PLAN-FIRST');
 expect(view.container.textContent).toContain('Compared against the recorded predecessor plan.');
 expect(Array.from(view.container.querySelectorAll('pre')).some(x=>x.textContent?.includes('Qualified planning wave'))).toBe(true);
 expect(screen.queryByRole('button',{name:'Adopt this plan'})).toBeNull();
});
