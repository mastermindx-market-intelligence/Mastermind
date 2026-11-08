/** Native ceilings in the original tool, sandbox, approval and skill owners. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import {createScope} from "@deepseek-ai/dsh-scope";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import ToolRuntime,{type ToolDefinition} from "@deepseek-ai/dsh-tools";
import SandboxPolicy,{setSandboxMode} from "@deepseek-ai/dsh-sandbox-policy";
import Approval,{setApprovalPolicy} from "@deepseek-ai/dsh-user-approval";
import Skills from "@deepseek-ai/dsh-skill";
import Projections from "@deepseek-ai/dsh-session-projection";
import {Session,SessionId} from "@deepseek-ai/dsh-session";
import {ToolCallId} from "@deepseek-ai/dsh-llm";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
const definition=(name:string,execute=vi.fn(async()=>"read")):ToolDefinition=>({
  name,description:name,parameters:{type:"object",properties:{}},
  output:{schema:{type:"string"},render:(_args,value)=>[{type:"text",text:value as string}]},execute,
});
async function toolHost(native=true){
  const ctx=new Context(),generation=new AbortController(),state={current:true,check:undefined as any};
  cleanup.push(()=>ctx.fiber.dispose());
  const admission={signal:generation.signal,check:(facts:any)=>state.check?state.check(facts):state.current&&facts.definition.name==="read"};
  if(native)ctx.provide("nativeToolAdmission",admission);
  await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime);
  const body=vi.fn(async()=>"original read"),read=definition("read",body);
  const dispose=ctx.tools.register(read);
  const run=(agent?:any)=>ctx.tools.execute({signal:new AbortController().signal,callId:ToolCallId("call-1"),
    name:"read",arguments:{},...agent?{agent}:{}});
  return{ctx,generation,state,admission,body,read,dispose,run};
}
const outcome=(p:Promise<any>)=>p.then(value=>({value}),error=>({error}));

it("filters same-scope registrations through the original native view",async()=>{
  const h=await toolHost();let scope:any;const agent:any={id:"native-scope"};
  await h.ctx.plugin({inject:["tools","systemPrompt"],apply(ctx:Context){scope=createScope(ctx,agent);}});
  scope.ctx.tools.register(definition("shell"));
  expect(h.ctx.tools.schemas(agent).map(x=>x.name)).toEqual(["read"]);
  expect(h.ctx.tools.get("shell",agent)).toBeUndefined();
  expect((await h.run(agent)).isError).not.toBe(true);expect(h.body).toHaveBeenCalledTimes(1);
});

it("same definition in two layers retains two exact registration identities",async()=>{
  const h=await toolHost(),global=h.ctx.tools.observeRegistration("read")!;
  let scope:any;const agent:any={id:"native-scope"};
  await h.ctx.plugin({inject:["tools","systemPrompt"],apply(ctx:Context){scope=createScope(ctx,agent);}});
  const remove=scope.ctx.tools.register(h.read),local=h.ctx.tools.observeRegistration("read",agent)!;
  expect(local.definition).toBe(global.definition);
  expect(local.registrationIdentity).not.toBe(global.registrationIdentity);
  expect(global.assertCurrent()).toBe(true);expect(local.assertCurrent()).toBe(true);
  remove();expect(()=>local.assertCurrent()).toThrow();expect(global.assertCurrent()).toBe(true);
  expect(h.ctx.tools.observeRegistration("read",agent)!.registrationIdentity).toBe(global.registrationIdentity);
});

it.each(["withdraw","abort","replacement","callback","authority"] as const)(
  "checks %s after an awaiting around-wrapper and before the body",async change=>{
    const h=await toolHost(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
    const witness=h.ctx.tools.observeRegistration("read")!;
    h.state.check=(facts:any)=>h.state.current&&facts.registrationIdentity===witness.registrationIdentity;
    h.ctx.on("tools/execute",async(_exec,next)=>{entered.resolve();await release.promise;return next();});
    const pending=outcome(h.run());await entered.promise;
    if(change==="withdraw")h.state.current=false;
    if(change==="abort")h.generation.abort();
    if(change==="replacement"){h.dispose();h.ctx.tools.register(definition("read"));}
    if(change==="callback")h.read.execute=vi.fn(async()=>"replacement");
    if(change==="authority")h.ctx.nativeToolAdmission={signal:h.generation.signal,check:()=>true};
    release.resolve();const result=await pending;
    expect("error" in result||result.value.isError===true).toBe(true);expect(h.body).not.toHaveBeenCalled();
  });

it("rejects native callback accessors before inserting a registration",async()=>{
  const h=await toolHost(),bad=definition("bad"),getter=vi.fn(()=>h.body);
  Object.defineProperty(bad,"execute",{get:getter,enumerable:true});
  expect(()=>h.ctx.tools.register(bad)).toThrow("own data property");
  expect(getter).not.toHaveBeenCalled();
  expect(()=>h.ctx.tools.register(definition("bad"))).not.toThrow();
});
it("keeps ordinary registration lazy for an execute accessor",async()=>{
  const h=await toolHost(false),bad=definition("ordinary"),getter=vi.fn(()=>{throw Error("read only at execution");});
  Object.defineProperty(bad,"execute",{get:getter,enumerable:true});
  expect(()=>h.ctx.tools.register(bad)).not.toThrow();expect(getter).not.toHaveBeenCalled();
});
it.each(["parameters","name","output"] as const)("invalidates an in-place %s contract change",async field=>{
  const h=await toolHost(),seen=h.ctx.tools.observeRegistration("read")!;
  expect(seen.assertCurrent()).toBe(true);
  if(field==="name")h.read.name="other";
  if(field==="parameters")(h.read.parameters as any).properties={path:{type:"string"}};
  if(field==="output")(h.read.output.schema as any).type="number";
  expect(()=>seen.assertCurrent()).toThrow();
});
it("contains a reentrant native callback before the original body",async()=>{
  const h=await toolHost();
  h.state.check=(facts:any)=>{if(facts.phase==="dispatch")h.generation.abort();return true;};
  const result=await outcome(h.run());
  expect("error" in result||result.value.isError===true).toBe(true);expect(h.body).not.toHaveBeenCalled();
});

async function policies(){
  const ctx=new Context(),generation=new AbortController(),check=()=>{generation.signal.throwIfAborted();return true as const;};
  cleanup.push(()=>ctx.fiber.dispose());
  ctx.provide("nativeSandboxCeiling",{mode:"read-only",signal:generation.signal,assertCurrent:check});
  ctx.provide("nativeApprovalCeiling",{policy:"never",signal:generation.signal,assertCurrent:check});
  ctx.provide("nativeSkillCeiling",{mode:"disabled",signal:generation.signal,assertCurrent:check});
  await ctx.plugin(Projections);await ctx.plugin(SandboxPolicy,{mode:"danger-full-access",workspaceRoot:"/original"});
  await ctx.plugin(Approval,{policy:"ask"});await ctx.plugin(Skills);
  const session=Session.create(SessionId("original-policy"));return{ctx,generation,session};
}
it("clamps actual session and explicit sandbox overrides in the original owner",async()=>{
  const h=await policies();setSandboxMode(h.session,"danger-full-access");
  expect(h.ctx.sandboxPolicy.resolve({session:h.session,mode:"workspace-write"}).mode).toBe("read-only");
  h.generation.abort();expect(()=>h.ctx.sandboxPolicy.resolve({session:h.session})).toThrow();
});
it("keeps never approval in the original decision and settlement path",async()=>{
  const h=await policies();setApprovalPolicy(h.session,"ask");const answer=vi.fn(async()=>"allowed-once" as const);
  h.ctx.on("approval/request",answer);
  expect(h.ctx.approval.policyFor(h.session)).toBe("never");
  expect(()=>h.ctx.approval.setPolicy({session:h.session} as any,"ask")).toThrow();
  h.session.append("turn/start",{turn:1});
  expect(await h.ctx.approval.request({agent:{session:h.session} as any,toolName:"read",signal:new AbortController().signal})).toBe("rejected");
  expect(answer).not.toHaveBeenCalled();
  const events=h.session.snapshotEvents();
  expect(events.slice(-2).map(x=>x.type)).toEqual(["approval/asked","approval/decided"]);
});
it("reports enforced empty skills without starting provider discovery",async()=>{
  const h=await policies(),list=vi.fn(async()=>[]),get=vi.fn();
  h.ctx.skills.registerProvider(()=>({name:"unadmitted",list,get}));
  expect(await h.ctx.skills.snapshot({cwd:"/original"})).toEqual({skills:[],complete:true});
  expect(await h.ctx.skills.get("unadmitted")).toBeUndefined();
  expect(list).not.toHaveBeenCalled();expect(get).not.toHaveBeenCalled();
  h.generation.abort();await expect(h.ctx.skills.snapshot()).rejects.toThrow();
});

it("native dispatch exposes the original caller cancellation through an around-wrapper",async()=>{
  const h=await toolHost(),caller=new AbortController(),wrapper=new AbortController(),facts:any[]=[];
  h.state.check=(value:any)=>{if(value.phase==="dispatch")facts.push(value);return true;};
  h.ctx.on("tools/execute",async(exec,next)=>{const old=exec.signal;exec.signal=wrapper.signal;
    try{return await next();}finally{exec.signal=old;}});
  const result=await h.ctx.tools.execute({signal:caller.signal,callId:ToolCallId("bound-call"),name:"read",arguments:{}});
  expect(result.isError).not.toBe(true);expect(facts).toHaveLength(1);
  expect(facts[0].originalCallerSignal).toBe(caller.signal);expect(h.body).toHaveBeenCalledTimes(1);
});
