/** Original-code contract doubles. These tests do NOT mount DSH/Cordis. */
import assert from 'node:assert/strict';
import test from 'node:test';

const producerUrl = new URL('../../experiments/harness_convergence/dsh_native/observe.ts', import.meta.url);
const hostUrl = new URL('../../experiments/harness_convergence/dsh_native/fixture_host.ts', import.meta.url);
export const digest = (letter: string) => `sha256:${letter.repeat(64)}`;
export function fixture() {
  const agent = {session: {id: 'native-fixture-1'}};
  const definition = (name: string) => ({name, description: `In-memory ${name}`,
    parameters: {type: 'object', additionalProperties: false},
    output: {schema: {type: 'string'}, render: (_: unknown, value: unknown) => [{type: 'text', text: String(value)}]},
    execute: async () => 'fixture-only'});
  const defs = [definition('fixture_read'), definition('fixture_note')];
  let live = true;
  const modules = [{id:'core', options:{name:'@deepseek-ai/dsh-tools'}, disabled:false, fiber:{state:2}}];
  const selection = {current:{provider:'fixture', model:'fixture-model'}, assembled:undefined};
  const ctx: any = {
    agents:{get:(id: string) => live && id===agent.session.id ? agent : undefined},
    tools:{schemas:(scope: unknown) => {assert.equal(scope, agent, 'must use exact Agent'); return defs.map(({name,description,parameters})=>({name,description,parameters}));},
      get:(name: string, scope: unknown) => {assert.equal(scope,agent);return defs.find(d=>d.name===name);}},
    loader:{entries:()=>modules},
    llm:{resolveCallConfig:async (value: any)=>({...value,maxTokens:64})},
  };
  const owner: any = {
    binding:{attempt_id:'attempt-fixture',worker_id:'worker-fixture',process_generation_id:'generation-fixture',native_session_id:agent.session.id},
    recipe_digest:digest('a'),
    modules:[{entry_id:'core',module:'@deepseek-ai/dsh-tools',module_digest:digest('b')}],
    definitions:defs.map(definition=>({definition,implementation_digest:digest('c')})),
    extension_policy:'N0_CLOSED_FIXTURE_NO_EXTERNAL_CAPABILITIES',
  };
  return {agent,defs,ctx,selection,owner,handle:{agent,dispose:async()=>{live=false;}},kill:()=>{live=false;}};
}
export async function emitFixtureObservation() {
  const {createObserver}=await import(producerUrl.href);
  const f=fixture();return await createObserver(f.ctx,f.handle,f.selection,f.owner).capture();
}
if(process.argv.includes('--emit')) {
  console.log(await emitFixtureObservation());
} else {
  test('positive: exact-scope observation is bounded JSON with no execution grant',async()=>{
    const p=JSON.parse(await emitFixtureObservation());
    assert.equal(p.format,'dsh-native-observation/n0');
    assert.equal(p.tools.length,2);assert.equal(p.binding.native_session_id,'native-fixture-1');
    assert.equal(p.model.model,'fixture-model');assert.equal(p.presentation,'native');
    assert.equal(p.extension_policy,'N0_CLOSED_FIXTURE_NO_EXTERNAL_CAPABILITIES');
    assert.equal('allow' in p,false);assert.equal('authenticated' in p,false);
  });
  const refusals: [string,(f:any)=>void,string][] = [
    ['extra scoped tool',(f)=>{f.defs.push({...f.defs[0],name:'ambient_write'});},'TOOL_CENSUS_MISMATCH'],
    ['same schema replaced implementation',(f)=>{f.defs[0]={...f.defs[0],execute:async()=> 'changed'};},'TOOL_IMPLEMENTATION_DRIFT'],
    ['in-place executable replacement',(f)=>{f.defs[0].execute=async()=> 'changed';},'TOOL_IMPLEMENTATION_DRIFT'],
    ['schema description drift',(f)=>{f.defs[0].description='changed';},'TOOL_SCHEMA_DRIFT'],
    ['tool order drift',(f)=>{f.defs.reverse();},'TOOL_CENSUS_MISMATCH'],
    ['PTC transport',(f)=>{f.defs.push({...f.defs[0],name:'run_code'});},'PRESENTATION_NOT_NATIVE'],
    ['unknown inventory',(f)=>{f.ctx.tools.schemas=()=>undefined;},'OBSERVATION_UNAVAILABLE'],
    ['extra module',(f)=>{f.ctx.loader.entries=()=>[{id:'alien',options:{name:'alien'},disabled:false,fiber:{state:2}}];},'COMPOSITION_MISMATCH'],
    ['pending module',(f)=>{f.ctx.loader.entries=()=>[{id:'core',options:{name:'@deepseek-ai/dsh-tools'},disabled:false,fiber:{state:0}}];},'COMPOSITION_UNSETTLED'],
    ['disposed generation',(f)=>f.kill(),'NATIVE_IDENTITY_STALE'],
    ['session identity drift',(f)=>{f.agent.session.id='other';},'NATIVE_IDENTITY_STALE'],
  ];
  for(const [name,change,code] of refusals) test(`refuses ${name}`,async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();
    const o=createObserver(f.ctx,f.handle,f.selection,f.owner);change(f);
    await assert.rejects(()=>o.capture(),(e:any)=>e.code===code && e.message===code);
  });
  test('late scope change during model resolution refuses',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();
    f.ctx.llm.resolveCallConfig=async(v:any)=>{f.defs[0]={...f.defs[0],execute:async()=> 'late'};return v;};
    await assert.rejects(()=>createObserver(f.ctx,f.handle,f.selection,f.owner).capture(),(e:any)=>e.code==='TOOL_IMPLEMENTATION_DRIFT');
  });
  test('late selection change refuses',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();
    f.ctx.llm.resolveCallConfig=async(v:any)=>{f.selection.current.model='changed';return v;};
    await assert.rejects(()=>createObserver(f.ctx,f.handle,f.selection,f.owner).capture(),(e:any)=>e.code==='MODEL_SELECTION_DRIFT');
  });
  test('cancellation is checked again after async resolver',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();const c=new AbortController();
    f.ctx.llm.resolveCallConfig=async(v:any)=>{c.abort();return v;};
    await assert.rejects(()=>createObserver(f.ctx,f.handle,f.selection,f.owner).capture(c.signal),(e:any)=>e.code==='CANCELLED');
  });
  test('resolver failures never echo supplied exception text',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();
    f.ctx.llm.resolveCallConfig=async()=>{throw Error('sensitive-fixture-marker');};
    await assert.rejects(()=>createObserver(f.ctx,f.handle,f.selection,f.owner).capture(),(e:any)=>e.code==='OBSERVATION_UNAVAILABLE'&&!e.message.includes('sensitive'));
  });
  test('owner mutation does not change sealed binding',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();const o=createObserver(f.ctx,f.handle,f.selection,f.owner);
    f.owner.binding.worker_id='changed';f.owner.modules[0].module_digest=digest('d');
    const p=JSON.parse(await o.capture());assert.equal(p.binding.worker_id,'worker-fixture');assert.equal(p.composition[0].module_digest,digest('b'));
  });
  test('deep and oversized schema refuse rather than truncate',async()=>{
    const {createObserver}=await import(producerUrl.href);
    for(const huge of [()=> 'x'.repeat(70000),()=>{let v:any={};for(let i=0;i<40;i++)v={child:v};return v;}]) {
      const f=fixture();f.defs[0].parameters=huge() as any;
      assert.throws(()=>createObserver(f.ctx,f.handle,f.selection,f.owner),(e:any)=>e.code==='OBSERVATION_LIMIT');
    }
  });
  test('fixture coordinator always disposes and rejects late observations',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();let disposed=0;
    f.handle.dispose=async()=>{disposed++;f.kill();};
    const result=await withOwnedFixture(async()=>({ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner}));
    assert.equal(disposed,1);assert.equal(result.cleanup,'SETTLED');assert.equal(result.scope,'N0_SOURCE_CONFORMANCE');
    assert.equal(result.provider_turns_started,0);assert.equal(JSON.parse(result.observation).tools.length,2);
  });
  test('cleanup failure cannot publish successful fixture result',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();f.handle.dispose=async()=>{throw Error('private');};
    await assert.rejects(()=>withOwnedFixture(async()=>({ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner})),(e:any)=>e.code==='CLEANUP_UNSETTLED'&&e.message==='CLEANUP_UNSETTLED');
  });
  test('capture failure still disposes the owned handle',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();let disposed=0;
    f.ctx.tools.schemas=()=>undefined;f.handle.dispose=async()=>{disposed++;f.kill();};
    await assert.rejects(()=>withOwnedFixture(async()=>({ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner})));
    assert.equal(disposed,1);
  });

  test('setup receives the caller cancellation signal',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();const c=new AbortController();
    await withOwnedFixture(async(signal:any)=>{assert.equal(signal,c.signal);return {ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner};},c.signal);
  });
  test('cancellation during setup disposes the returned handle',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();const c=new AbortController();let disposed=0;
    f.handle.dispose=async()=>{disposed++;f.kill();};
    await assert.rejects(()=>withOwnedFixture(async()=>{c.abort();return {ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner};},c.signal),(e:any)=>e.code==='CANCELLED');
    assert.equal(disposed,1);
  });
  test('unexpected owner-read failure is sanitized after disposal',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();let disposed=0;
    Object.defineProperty(f.owner,'binding',{get(){throw Error('sensitive-owner-marker');}});
    f.handle.dispose=async()=>{disposed++;f.kill();};
    await assert.rejects(()=>withOwnedFixture(async()=>({ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner})),(e:any)=>e.code==='OBSERVATION_UNAVAILABLE'&&!e.message.includes('sensitive'));
    assert.equal(disposed,1);
  });
  test('public native factory composes before observation and disposes once',async()=>{
    const {nativeFixtureFactory,withOwnedFixture}=await import(hostUrl.href);const f=fixture();const order:string[]=[];
    f.ctx.agents.create=async(options:any)=>{
      assert.equal(options.sessionId,f.agent.session.id);f.defs.length=0;
      await options.setup({tools:{presentAs:(mode:string)=>{assert.equal(mode,'native');order.push('native');},register:(d:any)=>{order.push(d.name);f.defs.push(d);}}});
      order.push('created');return f.handle;
    };
    const make=nativeFixtureFactory(f.ctx,f.owner.binding,{recipe_digest:digest('a'),modules:f.owner.modules,implementation_digest:digest('c')},(_ctx:any,s:any)=>{assert.equal(s.current.model,'fixture-model');order.push('selection');});
    const result=await withOwnedFixture(make);
    assert.deepEqual(order,['selection','native','fixture_read','fixture_note','created']);
    assert.equal(JSON.parse(result.observation).model.model,'fixture-model');
    assert.equal(result.provider_calls_observed,null,'unmeasured upstream calls must not be reported as zero');
  });
  test('observer never reads process environment',async()=>{
    const {createObserver}=await import(producerUrl.href);const f=fixture();const old=process.env;
    try {process.env=new Proxy(old,{get(){throw Error('ambient env read');},ownKeys(){throw Error('ambient env enumeration');}});await createObserver(f.ctx,f.handle,f.selection,f.owner).capture();}
    finally {process.env=old;}
  });

  test('cancellation during teardown cannot publish success',async()=>{
    const {withOwnedFixture}=await import(hostUrl.href);const f=fixture();const c=new AbortController();
    f.handle.dispose=async()=>{c.abort();f.kill();};
    await assert.rejects(()=>withOwnedFixture(async()=>({ctx:f.ctx,handle:f.handle,selection:f.selection,owner:f.owner}),c.signal),(e:any)=>e.code==='CANCELLED');
  });

  test('owner digest rejects coercion and trailing newline',async()=>{
    const {createObserver}=await import(producerUrl.href);
    for(const bad of [digest('a')+'\n',{toString:()=>digest('a')}]) {
      const f=fixture();f.owner.recipe_digest=bad;
      assert.throws(()=>createObserver(f.ctx,f.handle,f.selection,f.owner),(e:any)=>e.code==='OWNER_SEAL_INVALID');
    }
  });
  test('factory seals caller binding and recipe before native setup awaits',async()=>{
    const {nativeFixtureFactory,withOwnedFixture}=await import(hostUrl.href);const f=fixture();
    const recipe={recipe_digest:digest('a'),modules:f.owner.modules,implementation_digest:digest('c')};
    f.ctx.agents.create=async(options:any)=>{
      f.owner.binding.worker_id='changed-worker';recipe.recipe_digest=digest('e');f.defs.length=0;
      await options.setup({tools:{presentAs:()=>{},register:(d:any)=>f.defs.push(d)}});return f.handle;
    };
    const result=await withOwnedFixture(nativeFixtureFactory(f.ctx,f.owner.binding,recipe,()=>{}));
    const value=JSON.parse(result.observation);assert.equal(value.binding.worker_id,'worker-fixture');assert.equal(value.recipe_digest,digest('a'));
  });
}
