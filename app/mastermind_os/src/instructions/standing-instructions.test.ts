// @vitest-environment node
import {describe,expect,it} from 'vitest';
import fixture from './fixtures/standing-instructions-owner.json';
import {decodeStandingInstructions,validStandingInstructionSelection} from './standing-instructions';
const selection={work_ref:'WS:ONE'};
const current=()=>structuredClone(fixture.cases.supplied);
describe('canonical standing instruction content',()=>{
 it('consumes actual owner cases while keeping absent/empty/unavailable distinct',()=>{
  for(const body of Object.values(fixture.cases))expect(decodeStandingInstructions(body,selection)).toEqual(body);
  expect(fixture.cases.absent.declaration).toBe('NOT_DECLARED');expect(fixture.cases.empty.declaration).toBe('SUPPLIED');
  expect(fixture.cases.unavailable.instructions).toBeNull();
  expect(fixture.cases.supplied.instructions[0].text).toBe('复查项目 🎯');
 });
 it('returns detached content and never adds state, permission, title or clock',()=>{
  const body=current(),decoded=decodeStandingInstructions(body,selection)!;
  body.instructions[0].text='edited input';expect(decoded).not.toEqual(body);
  expect(Object.keys(decoded).sort()).toEqual(['availability','declaration','instructions','reason_codes','schema','selection','source']);
  if(decoded.availability!=='AVAILABLE')throw Error('available owner body was withheld');
  expect(Object.keys(decoded.instructions[0]).sort()).toEqual(['instruction_ref','revision','text']);
 });
 it.each(['schema','selection','availability','source','declaration','instructions','reason_codes'])('rejects a missing %s',(key)=>{
  const body:Record<string,unknown>=current();delete body[key];expect(decodeStandingInstructions(body,selection)).toBeNull();
 });
 it.each(['WS:A','WS:one','WS:ONE\n','WS:ONE--TWO','WS:ONE_TWO','WS:'+'A'.repeat(65)])('requires exact canonical project identity %s',(work_ref)=>{
  expect(validStandingInstructionSelection({work_ref})).toBe(false);expect(decodeStandingInstructions(current(),{work_ref})).toBeNull();
 });
 it.each(['WS:AA','WS:PROJECT-ONE','WS:'+'A'.repeat(64)])('accepts canonical project bounds %s',(work_ref)=>expect(validStandingInstructionSelection({work_ref})).toBe(true));
 it.each(['commit','content_sha256','path','repository'])('rejects foreign or malformed canonical source %s',(field)=>{
  const body=current();(body.source as Record<string,unknown>)[field]=String((body.source as Record<string,unknown>)[field])+'\n';expect(decodeStandingInstructions(body,selection)).toBeNull();
 });
 it('withholds unknown fields, foreign selection and unavailable partial facts',()=>{
  expect(decodeStandingInstructions({...current(),state:'ACTIVE'},selection)).toBeNull();
  expect(decodeStandingInstructions({...current(),selection:{work_ref:'WS:OTHER'}},selection)).toBeNull();
  expect(decodeStandingInstructions({...fixture.cases.unavailable,instructions:[]},selection)).toBeNull();
  expect(decodeStandingInstructions({...fixture.cases.unavailable,reason_codes:['NEW_REASON']},selection)).toBeNull();
  expect(decodeStandingInstructions({...fixture.cases.absent,instructions:current().instructions},selection)).toBeNull();
 });
 it.each(['',' \t\n','\u0085','\u0000task','\u007f','\ud800','\udc00','x'.repeat(4097)])('rejects blank, control, malformed Unicode or overbound literal text',text=>{
  const body=current();body.instructions[0].text=text;expect(decodeStandingInstructions(body,selection)).toBeNull();
 });
 it('uses Unicode codepoints, preserves permitted whitespace and follows Python blank semantics',()=>{
  for(const text of ['🎯'.repeat(4096),'\t\n保留文字\r','\ufeff']){
   const body=current();body.instructions[0].text=text;expect(decodeStandingInstructions(body,selection)).not.toBeNull();
  }
 });
 it('rejects duplicate references and full-string digest/ref errors',()=>{
  const body=current();body.instructions.push(structuredClone(body.instructions[0]));expect(decodeStandingInstructions(body,selection)).toBeNull();
  for(const field of ['instruction_ref','revision']){
   const changed=current();(changed.instructions[0] as Record<string,unknown>)[field]+='\n';expect(decodeStandingInstructions(changed,selection)).toBeNull();
  }
 });
 it('refuses the whole overbound UTF8 envelope without truncation and caps row count',()=>{
  const body=current(),row=body.instructions[0];body.instructions=Array.from({length:2},(_,i)=>({...row,instruction_ref:`INS:ITEM-${i}`,text:'漢'.repeat(4096)}));
  expect(decodeStandingInstructions(body,selection)).not.toBeNull();body.instructions.push({...row,instruction_ref:'INS:ITEM-2',text:'漢'.repeat(4096)});
  expect(decodeStandingInstructions(body,selection)).toBeNull();
  body.instructions=Array.from({length:17},(_,i)=>({...row,instruction_ref:`INS:ITEM-${i}`}));expect(decodeStandingInstructions(body,selection)).toBeNull();
 });
 it('rejects accessors, hidden/symbol fields, holes, cycles and foreign prototypes without invoking getters',()=>{
  let invoked=0;
  const getter=current();Object.defineProperty(getter,'availability',{get(){invoked++;return 'AVAILABLE';},enumerable:true});expect(decodeStandingInstructions(getter,selection)).toBeNull();
  const index=current();Object.defineProperty(index.instructions,'0',{get(){invoked++;return current().instructions[0];},enumerable:true});expect(decodeStandingInstructions(index,selection)).toBeNull();
  for(const mutate of [(x:Record<string,unknown>)=>Object.defineProperty(x,'hidden',{value:true}),(x:Record<string,unknown>)=>Object.defineProperty(x,Symbol('extra'),{value:true}),(x:Record<string,unknown>)=>Object.setPrototypeOf(x,{foreign:true})]){
   const body=current();mutate(body);expect(decodeStandingInstructions(body,selection)).toBeNull();
  }
  const hole=current();delete (hole.instructions as unknown[])[0];expect(decodeStandingInstructions(hole,selection)).toBeNull();
  const cycle=current();(cycle as Record<string,unknown>).source=cycle;expect(decodeStandingInstructions(cycle,selection)).toBeNull();
  expect(invoked).toBe(0);
 });
 it('contains hostile reflection failures and never calls toJSON',()=>{
  expect(decodeStandingInstructions(new Proxy(current(),{ownKeys(){throw Error('private');}}),selection)).toBeNull();
  const body=current();let invoked=0;Object.assign(body,{toJSON(){invoked++;throw Error();}});expect(decodeStandingInstructions(body,selection)).toBeNull();expect(invoked).toBe(0);
 });
});
