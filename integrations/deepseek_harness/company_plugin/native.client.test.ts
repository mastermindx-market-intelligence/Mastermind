import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {expect,it,vi} from "vitest";
import * as React from "react";
import * as Store from "@deepseek-ai/dsh-client-store";
import {SlotTestRuntime} from "@deepseek-ai/dsh-client-test-runtime";
import {COMPANY_SCHEMA} from "./src/protocol";

it("mounts the compiled company plugin through native Cordis slots and clears revoked context",async()=>{
 const runtime=await SlotTestRuntime.create();
 const tokens=vi.fn(()=>()=>{}),theme=vi.fn(),locale=vi.fn();
 runtime.ctx.provide("theme",{overrideTokens:tokens,setTheme:theme});
 // This test exercises native slot/rendering machinery. No business Host or provider is present.
 runtime.ctx.provide("locale",{setLocale:locale});
 const nonce="325154ad-b82d-4a19-8814-f59d9bce1c38";
 let plugin:any;
 const previous=(window as any).__ModuleLoader__;
 (window as any).__ModuleLoader__={load:({id,factory}:any)=>{
   expect(id).toBe("@mastermind/dsh-company");
   plugin=factory((name:string)=>{
     if(name==="react")return React;
     if(name==="@deepseek-ai/dsh-client-store")return Store;
     throw new Error("Unexpected runtime dependency "+name);
   });
 }};
 try {
   new Function(readFileSync(resolve(process.cwd(),"lib/client.js"),"utf8"))();
   await runtime.declare({
     main:{kind:"keyed",scope:"root"},
     "sidebar.panellist":{kind:"list",scope:"root"},
     "sidebar.brand.mark":{kind:"single",scope:"root"},
     "sidebar.brand.name":{kind:"single",scope:"root"},
   } as never);
   await runtime.mount(plugin);
   const {view}=runtime.renderSlot("main",{}, {entryKey:"mastermind-projects"} as never);
   expect(view.getByText("Your projects")).toBeTruthy();
   expect(view.getByText("Open chat from Mastermind OS to connect your projects.")).toBeTruthy();
   const send=(data:unknown)=>window.dispatchEvent(new MessageEvent("message",{source:window,origin:"https://mcp.mastermind-x.com",data}));
   await React.act(async()=>{
     send({schema:COMPANY_SCHEMA,type:"connect",nonce});
     send({schema:COMPANY_SCHEMA,type:"context",nonce,view:{
       generation:1,state:"CURRENT",locale:"en",theme:"dark",selectedProject:"WS:CHAT",
       projects:[{workRef:"WS:CHAT",title:"DeepSeek integration"}],
     }});
   });
   expect(view.getByRole("button",{name:"Open project: DeepSeek integration"})).toBeTruthy();
   expect(theme).toHaveBeenCalledWith("dark");
   expect(tokens).toHaveBeenCalledOnce();
   await React.act(async()=>{
     send({schema:COMPANY_SCHEMA,type:"context",nonce,view:{
       generation:2,state:"SIGNED_OUT",locale:"en",theme:"dark",selectedProject:null,projects:[],
     }});
   });
   expect(view.queryByText("DeepSeek integration")).toBeNull();
   expect(view.getByText("Sign in to Mastermind OS to see your projects.")).toBeTruthy();
 } finally {
   await runtime.dispose();
   (window as any).__ModuleLoader__=previous;
 }
 expect(document.querySelector('style[data-plugin="@mastermind/dsh-company"]')).toBeNull();
});
