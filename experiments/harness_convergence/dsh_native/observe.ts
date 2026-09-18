/**
 * Original N0 exact-Agent observer. No DSH loader, model turn or company admission.
 * The caller is the admitted native fixture owner, NOT an arbitrary RPC client.
 * Structural ports below name public APIs at the pinned upstream commit. Real
 * native compatibility requires the separately qualified mounted-DSH fixture.
 */
import {createHash} from 'node:crypto';
import type {ToolDefinition} from '@deepseek-ai/dsh-tools';
import type {ModelSelection} from '@deepseek-ai/dsh-agent';
export const UPSTREAM_COMMIT = '0d1f50007f9bca3f52b06e1c3074fa14d5fb0720';
export const EXTENSION_POLICY = 'N0_CLOSED_FIXTURE_NO_EXTERNAL_CAPABILITIES';
export const MAX_BYTES = 65536;
export class ObservationError extends Error {
  code: string;
  constructor(code: string) {super(code);this.name='ObservationError';this.code=code;}
}
function refuse(code: string): never {throw new ObservationError(code);}
type Json = null|boolean|number|string|Json[]|{[key:string]:Json};
export type Binding = Readonly<{attempt_id:string;worker_id:string;process_generation_id:string;native_session_id:string}>;
export type Agent = {session:{id:string}};
export type Definition = ToolDefinition;
export type Handle = {agent:Agent;dispose():Promise<void>};
export type Selection = ModelSelection;
export type NativeContext = {
  agents:{get(id:string):Agent|undefined};
  tools:{schemas(agent:Agent):unknown;get(name:string,agent:Agent):Definition|undefined};
  loader:{entries():Iterable<{id:string;options:{name:string;group?:boolean|null|undefined};disabled:boolean;fiber?:{state:number}|undefined}>};
  llm:{resolveCallConfig(selection:Selection,signal?:AbortSignal):Promise<Selection & {maxTokens?:number}>};
};
export type ModuleIdentity = Readonly<{entry_id:string;module:string;module_digest:string}>;
export type OwnerSeal = {
  binding:Binding;recipe_digest:string;modules:readonly ModuleIdentity[];
  definitions:readonly {definition:Definition;implementation_digest:string}[];
  extension_policy:typeof EXTENSION_POLICY;
};

/** Snapshot lossless bounded JSON without invoking accessors or custom serializers. */
export function snapshot(value:unknown):Json {
  let nodes=0;
  const seen=new Set<object>();
  function walk(v:unknown,depth:number):Json {
    if(depth>32 || ++nodes>4096) refuse('OBSERVATION_LIMIT');
    if(v===null || typeof v==='boolean') return v;
    if(typeof v==='string') {
      if(v.length>8192 || /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(v)) refuse('OBSERVATION_LIMIT');
      return v;
    }
    if(typeof v==='number') {if(!Number.isSafeInteger(v) || Object.is(v,-0)) refuse('OBSERVATION_SHAPE');return v;}
    if(typeof v!=='object' || seen.has(v)) refuse('OBSERVATION_SHAPE');
    seen.add(v);
    try {
      if(Array.isArray(v)) {
        if(v.length>128) refuse('OBSERVATION_LIMIT');
        const keys=Reflect.ownKeys(v);
        if(keys.length!==v.length+1) refuse('OBSERVATION_SHAPE');
        const result:Json[]=[];
        for(let i=0;i<v.length;i++) {
          const d=Object.getOwnPropertyDescriptor(v,String(i));
          if(!d || !('value' in d)) refuse('OBSERVATION_SHAPE');
          result.push(walk(d.value,depth+1));
        }
        return result;
      }
      if(Object.getPrototypeOf(v)!==Object.prototype && Object.getPrototypeOf(v)!==null) refuse('OBSERVATION_SHAPE');
      const result:{[key:string]:Json}=Object.create(null);
      const keys=Reflect.ownKeys(v);
      if(keys.length>128 || keys.some(k=>typeof k!=='string')) refuse('OBSERVATION_LIMIT');
      for(const key of (keys as string[]).sort()) {
        if(!/^[\x20-\x7e]{1,128}$/.test(key) || ['__proto__','prototype','constructor'].includes(key)) refuse('OBSERVATION_SHAPE');
        const d=Object.getOwnPropertyDescriptor(v,key);
        if(!d || !('value' in d) || !d.enumerable) refuse('OBSERVATION_SHAPE');
        result[key]=walk(d.value,depth+1);
      }
      return result;
    } finally {seen.delete(v);}
  }
  const result=walk(value,0);
  if(Buffer.byteLength(JSON.stringify(result),'utf8')>MAX_BYTES) refuse('OBSERVATION_LIMIT');
  return result;
}
export function canonical(value:unknown):string {return JSON.stringify(snapshot(value));}
export function digest(value:unknown):string {return 'sha256:'+createHash('sha256').update(canonical(value)).digest('hex');}
function hex(value:string):string {if(typeof value!=='string' || value.length!==71 || !/^sha256:[a-f0-9]{64}$/.test(value)) refuse('OWNER_SEAL_INVALID');return value;}
function schema(d:Definition) {return {name:d.name,description:d.description,parameters:d.parameters};}

export function createObserver(ctx:NativeContext,handle:Handle,selection:{current:Selection|undefined},owner:OwnerSeal) {
  // Capture independent trusted materialization facts before any asynchronous read.
  const binding=JSON.parse(canonical(owner.binding)) as Binding;
  const modules=JSON.parse(canonical(owner.modules)) as ModuleIdentity[];
  const recipeDigest=hex(owner.recipe_digest);
  if(owner.extension_policy!==EXTENSION_POLICY || modules.length===0 || modules.length>128 || owner.definitions.length===0 || owner.definitions.length>64) refuse('OWNER_SEAL_INVALID');
  for(const row of modules) hex(row.module_digest);
  if(new Set(modules.map(m=>m.entry_id)).size!==modules.length) refuse('OWNER_SEAL_INVALID');
  const definitions=owner.definitions.map(row=>({definition:row.definition,
    execute:row.definition.execute,render:row.definition.output.render,finalize:row.definition.finalizeContent,
    outputSchema:canonical(row.definition.output.schema),schema:canonical(schema(row.definition)),
    name:row.definition.name,implementation_digest:hex(row.implementation_digest)}));
  if(new Set(definitions.map(d=>d.name)).size!==definitions.length) refuse('OWNER_SEAL_INVALID');
  let invalid=false;
  function checkLive(signal?:AbortSignal) {
    if(signal?.aborted) refuse('CANCELLED');
    if(invalid || handle.agent.session.id!==binding.native_session_id || ctx.agents.get(binding.native_session_id)!==handle.agent) refuse('NATIVE_IDENTITY_STALE');
  }
  function readTools() {
    const rows=ctx.tools.schemas(handle.agent);
    if(!Array.isArray(rows)) refuse('OBSERVATION_UNAVAILABLE');
    if(rows.some(r=>r?.name==='run_code')) refuse('PRESENTATION_NOT_NATIVE');
    if(rows.length>64) refuse('OBSERVATION_LIMIT');
    if(rows.length!==definitions.length || rows.some((r,i)=>r?.name!==definitions[i]?.name)) refuse('TOOL_CENSUS_MISMATCH');
    return rows.map((r,i)=>{
      const sealed=definitions[i];
      if(!sealed) refuse('TOOL_CENSUS_MISMATCH');
      const actual=ctx.tools.get(sealed.name,handle.agent);
      if(actual!==sealed.definition || actual.execute!==sealed.execute || actual.output.render!==sealed.render || actual.finalizeContent!==sealed.finalize || canonical(actual.output.schema)!==sealed.outputSchema) refuse('TOOL_IMPLEMENTATION_DRIFT');
      if(canonical(r)!==sealed.schema || canonical(schema(actual))!==sealed.schema) refuse('TOOL_SCHEMA_DRIFT');
      return {...JSON.parse(sealed.schema),implementation_digest:sealed.implementation_digest};
    });
  }
  function readComposition() {
    const rows=[];
    for(const entry of ctx.loader.entries()) {
      if(rows.length>=128) refuse('OBSERVATION_LIMIT');
      // N0 admits a flat explicit fixture recipe; no inherited conditional groups.
      if(entry.options.group || entry.disabled!==false || entry.fiber?.state!==2) refuse('COMPOSITION_UNSETTLED');
      const expected:ModuleIdentity|undefined=modules[rows.length];
      if(!expected || entry.id!==expected.entry_id || entry.options.name!==expected.module) refuse('COMPOSITION_MISMATCH');
      rows.push({...expected});
    }
    if(rows.length!==modules.length) refuse('COMPOSITION_MISMATCH');
    return rows;
  }
  return Object.freeze({
    invalidate(){invalid=true;},
    async capture(signal?:AbortSignal):Promise<string> {
      try {
        checkLive(signal);
        const tools=readTools(),composition=readComposition();
        if(!selection.current) refuse('OBSERVATION_UNAVAILABLE');
        const selected=canonical(selection.current);
        const resolved=await ctx.llm.resolveCallConfig(JSON.parse(selected),signal);
        checkLive(signal);
        if(!selection.current || selected!==canonical(selection.current)) refuse('MODEL_SELECTION_DRIFT');
        if(canonical(tools)!==canonical(readTools()) || canonical(composition)!==canonical(readComposition())) refuse('COMPOSITION_MISMATCH');
        const effective=JSON.parse(canonical(resolved));
        if(Object.keys(effective).some(k=>!['provider','model','reasoningEffort','maxTokens'].includes(k)) || typeof effective.provider!=='string' || typeof effective.model!=='string') refuse('MODEL_OBSERVATION_INVALID');
        const requestedSelection=JSON.parse(selected);
        if(effective.provider!==requestedSelection.provider || effective.model!==requestedSelection.model) refuse('MODEL_SELECTION_DRIFT');
        if(effective.reasoningEffort!==undefined && typeof effective.reasoningEffort!=='string') refuse('MODEL_OBSERVATION_INVALID');
        if(effective.maxTokens!==undefined && (!Number.isSafeInteger(effective.maxTokens)||effective.maxTokens<=0)) refuse('MODEL_OBSERVATION_INVALID');
        return canonical({format:'dsh-native-observation/n0',upstream_commit:UPSTREAM_COMMIT,binding,recipe_digest:recipeDigest,
          extension_policy:EXTENSION_POLICY,presentation:'native',
          model:{provider:effective.provider,model:effective.model,reasoning_effort:effective.reasoningEffort??null,max_tokens:effective.maxTokens??null},
          tools,composition});
      } catch(error) {
        if(error instanceof ObservationError) throw error;
        throw new ObservationError('OBSERVATION_UNAVAILABLE');
      }
    },
  });
}
