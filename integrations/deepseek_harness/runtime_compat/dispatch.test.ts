import {expect,it} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import Stock from "./.cache/pristine/packages/core/tools/src/index";
import Patched,{TOOL_RUNTIME_SCHEDULER} from "./.cache/patched/packages/core/tools/src/index";
import {qualifyLoadedDispatchRuntime} from "../../acp_worker/dsh_dispatch_preflight.mjs";

async function runtime(patched=true, strict=true) {
 const ctx=new Context();
 await ctx.plugin(SystemPrompt);
 await ctx.plugin(patched?Patched:Stock,{strictDispatchBinding:strict});
 return ctx;
}
const input=(signal:AbortSignal)=>({signal,name:"fixture_read",callId:"fixture",arguments:{}});
const definition=(execute:()=>Promise<string>,label="original")=>({
 name:"fixture_read",description:"In-memory qualification fixture",parameters:{},
 output:{schema:{type:"string"},render:(_:unknown,value:string)=>[{type:"text",text:label+":"+value}]},execute,
});

it("the actual stock donor fails the existing late-revocation discriminator",async()=>{
 const ctx=await runtime(false);
 try {await expect(qualifyLoadedDispatchRuntime(ctx,{signal:new AbortController().signal}))
   .rejects.toMatchObject({code:"DSH_DISPATCH_PREFLIGHT_REFUSED",check:"revocation"});}
 finally {await ctx.fiber.dispose();}
});
it("the patched full-app runtime passes the unchanged four-check admission preflight",async()=>{
 const ctx=await runtime();
 try {
   const receipt=await qualifyLoadedDispatchRuntime(ctx,{signal:new AbortController().signal});
   expect(receipt.verified).toBe(true);
   expect(receipt.checks.map((check:any)=>check.name)).toEqual(["positive","revocation","replacement","result-owner"]);
 } finally {await ctx.fiber.dispose();}
});
it.each(["revocation","replacement"])("the native staged scheduler rejects queued %s",async(change)=>{
 const ctx=await runtime();
 let body=0,replacement=0,allowed=true;
 let unregister=ctx.tools.register(definition(async()=>{body++;return "value";}));
 const removeGuard=ctx.tools.guard(()=>allowed?undefined:"REVOKED");
 try {
   const scheduler=ctx.tools[TOOL_RUNTIME_SCHEDULER];
   const ready=await scheduler.prepare(input(new AbortController().signal));
   expect(ready.kind).toBe("dispatch");
   await Promise.resolve();
   if(change==="revocation")allowed=false;
   else {unregister();unregister=ctx.tools.register(definition(async()=>{replacement++;return "other";},"replacement"));}
   const dispatched=await scheduler.dispatch((ready as any).exec);
   const result=dispatched.kind==="post-result"?await scheduler.finalize((ready as any).exec,dispatched.result)
     :scheduler.finish((ready as any).exec,dispatched.result);
   expect(result.isError).toBe(true);expect(body).toBe(0);expect(replacement).toBe(0);
 } finally {removeGuard();unregister();await ctx.fiber.dispose();}
});
it("post-execute values retain the original definition after its body replaces the registry",async()=>{
 const ctx=await runtime();let body=0,replacement=0;
 let unregister=()=>{};
 unregister=ctx.tools.register(definition(async()=>{
   body++;await Promise.resolve();unregister();
   unregister=ctx.tools.register(definition(async()=>{replacement++;return "other";},"replacement"));
   return "value";
 }));
 const remove=ctx.on("tools/post-execute",async()=>({kind:"accept",value:"rewritten"}));
 try {
   const result=await ctx.tools.execute(input(new AbortController().signal));
   expect(body).toBe(1);expect(replacement).toBe(0);expect(result.isError).toBe(false);
   expect(result.content).toEqual([{type:"text",text:"original:rewritten"}]);
 } finally {remove();unregister();await ctx.fiber.dispose();}
});
it.each(["before","during"])("cancellation %s the body stays on the original dispatch",async(when)=>{
 const ctx=await runtime();const controller=new AbortController();let body=0,settled=false;
 const unregister=ctx.tools.register(definition(async()=>{
   body++;await Promise.resolve();controller.abort();settled=true;return "value";
 }));
 const remove=ctx.on("tools/execute",async(_exec:any,next:any)=>{
   if(when==="before"){await Promise.resolve();controller.abort();}
   return next();
 });
 try {
   const result=await ctx.tools.execute(input(controller.signal));
   expect(body).toBe(when==="before"?0:1);expect(settled).toBe(when==="during");
   expect(result.isError).toBe(true);expect(result.error?.info?.code).toBe(when==="before"?"ABORTED_BEFORE_DISPATCH":"ABORTED");
 } finally {remove();unregister();await ctx.fiber.dispose();}
});
it("the patch leaves non-opted-in dispatch behavior unchanged",async()=>{
 const ctx=await runtime(true,false);let allowed=true,body=0;
 const unregister=ctx.tools.register(definition(async()=>{body++;return "value";}));
 const guard=ctx.tools.guard(()=>allowed?undefined:"REVOKED");
 const remove=ctx.on("tools/execute",async(_exec:any,next:any)=>{await Promise.resolve();allowed=false;return next();});
 try {const result=await ctx.tools.execute(input(new AbortController().signal));expect(body).toBe(1);expect(result.isError).toBe(false);}
 finally {remove();guard();unregister();await ctx.fiber.dispose();}
});
