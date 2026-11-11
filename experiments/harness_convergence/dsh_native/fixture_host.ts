/**
 * One-handle N0 coordinator, not an executable installer or an Agent loop.
 * The qualified native owner supplies its already-composed DSH Context/factory.
 * Unit contract doubles exercise this original code, not DSH itself.
 */
import type {Context} from '@deepseek-ai/cordis';
import type {CreateAgentOptions, ModelSelectionRef} from '@deepseek-ai/dsh-agent';
import {createObserver,ObservationError,EXTENSION_POLICY,canonical} from './observe.ts';
import type {NativeContext,Handle,OwnerSeal,Selection,Definition,Binding,ModuleIdentity} from './observe.ts';
export type NativeCreateOptions = Omit<CreateAgentOptions, 'sessionId'|'setup'> & {
  sessionId:string; setup:(ctx:Context)=>Promise<void>;
};
export type NativeFactoryContext = NativeContext & {
  agents:NativeContext['agents'] & {create(options:NativeCreateOptions):Promise<Handle>};
};
export type OwnedFixture = {ctx:NativeContext;handle:Handle;selection:{current:Selection|undefined};owner:OwnerSeal};

export async function withOwnedFixture(factory:(signal?:AbortSignal)=>Promise<OwnedFixture>,signal?:AbortSignal) {
  if(signal?.aborted) throw new ObservationError('CANCELLED');
  let fixture:OwnedFixture;
  try {fixture=await factory(signal);} catch {throw new ObservationError('SETUP_FAILED_EFFECT_UNRESOLVED');}
  let observer:ReturnType<typeof createObserver>|undefined;
  let observation:string|undefined;
  let captureFailure:unknown;
  try {
    observer=createObserver(fixture.ctx,fixture.handle,fixture.selection,fixture.owner);
    observation=await observer.capture(signal);
  } catch(error) {captureFailure=error;}
  // No observation escapes until owned-Agent disposal settles. A failed cleanup
  // dominates a capture result; never replace that uncertainty with a success.
  observer?.invalidate();
  try {
    await fixture.handle.dispose();
    if(fixture.ctx.agents.get(fixture.handle.agent.session.id)===fixture.handle.agent) throw Error('still-live');
  } catch {throw new ObservationError('CLEANUP_UNSETTLED');}
  if(captureFailure) throw captureFailure instanceof ObservationError ? captureFailure : new ObservationError('OBSERVATION_UNAVAILABLE');
  if(signal?.aborted) throw new ObservationError('CANCELLED');
  if(observation===undefined) throw new ObservationError('OBSERVATION_UNAVAILABLE');
  return Object.freeze({scope:'N0_SOURCE_CONFORMANCE',observation,cleanup:'SETTLED',
    cleanup_scope:'OWNED_AGENT_HANDLE_ONLY',provider_turns_started:0,
    provider_calls_observed:null,native_runtime_qualification:'SEPARATE_OWNER_EVIDENCE_REQUIRED'});
}

/**
 * Adapter for the pinned public agents.create/setup API. Caller passes the real
 * installModelSelection export and an already provisioned provider-free Context.
 * There is no package lookup, loader, credential access, model prompt or spawn.
 * Module closure, fixture LLM adapter and process fencing belong to that caller.
 */
export function nativeFixtureFactory(
  ctx:NativeFactoryContext,
  binding:Binding,
  recipe:Readonly<{recipe_digest:string;modules:readonly ModuleIdentity[];implementation_digest:string}>,
  installModelSelection:(ctx:Context,selection:ModelSelectionRef)=>void,
) {
  const fixedBinding=JSON.parse(canonical(binding)) as Binding;
  const fixedRecipe=JSON.parse(canonical(recipe)) as typeof recipe;
  return async (signal?:AbortSignal):Promise<OwnedFixture> => {
    const selection={current:{provider:'fixture',model:'fixture-model'} as Selection|undefined,assembled:undefined};
    const definitions:Definition[]=['fixture_read','fixture_note'].map(name=>({
      name,description:`In-memory ${name}`,parameters:{type:'object',additionalProperties:false},
      output:{schema:{type:'string'},render:(_args:unknown,value:unknown)=>[{type:'text',text:String(value)}]},
      execute:async()=> 'fixture-only',
    }));
    const handle=await ctx.agents.create({sessionId:fixedBinding.native_session_id,...(signal ? {signal} : {}),
      agentOptions:{provider:'fixture',model:'fixture-model'},
      setup:async (agentCtx:Context)=>{
        installModelSelection(agentCtx,selection);
        agentCtx.tools.presentAs('native');
        for(const definition of definitions) agentCtx.tools.register(definition);
      }});
    return {ctx,handle,selection,owner:{binding:fixedBinding,recipe_digest:fixedRecipe.recipe_digest,modules:fixedRecipe.modules,
      definitions:definitions.map(definition=>({definition,implementation_digest:fixedRecipe.implementation_digest})),
      extension_policy:EXTENSION_POLICY}};
  };
}
