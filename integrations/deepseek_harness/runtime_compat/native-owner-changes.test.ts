/** Real native change records through the original Connection and Session policy owner. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import RemoteAccessService,{type RemoteAccessBinding} from "@deepseek-ai/dsh-api-remote-access";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import TypertGatewayService from "@deepseek-ai/dsh-api-gateway";
import {apply as applyConnection,inject as connectionInject} from "@deepseek-ai/dsh-client-connection";
import {provideBrowserCredentials} from "mmx-native-browser-credentials";
import {mountAgentLoopTestDependencies} from "@deepseek-ai/dsh-agent-loop-testkit";
import LocalFileSystem from "@deepseek-ai/dsh-fs-local";
import LocalSubprocessRuntime from "@deepseek-ai/dsh-subprocess-local";
import * as WorkspaceChanges from "@deepseek-ai/dsh-workspace-changes";
import {SessionId} from "@deepseek-ai/dsh-session";
import {createSessionTestController} from "mmx-native-test-remote";
import {registerPresentOpen} from "mmx-native-present-open";
import {startTurn,endTurn,mutate,settle} from "mmx-native-changes-support";
import {mkdtemp,rm,writeFile} from "node:fs/promises";
import {tmpdir} from "node:os";
import {join} from "node:path";

const cleanup:(()=>Promise<unknown>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
async function fixture(admitted=true){
  const root=await mkdtemp(join(tmpdir(),"mmx-native-changes-"));cleanup.push(()=>rm(root,{recursive:true,force:true}));
  const ctx=new Context();cleanup.push(()=>ctx.fiber.dispose());ctx.provide("remoteAccessOwnerRestricted",true);
  await ctx.plugin(TypertRegistry);await ctx.plugin(RemoteAccessService);await ctx.plugin(TypertGatewayService);
  provideBrowserCredentials(ctx);await ctx.plugin({inject:[...connectionInject],apply:applyConnection});
  await mountAgentLoopTestDependencies(ctx);await ctx.plugin(LocalFileSystem,{cwd:root});
  await ctx.plugin(LocalSubprocessRuntime);
  vi.spyOn(ctx.subprocess,"resolveExecutable").mockRejectedValue(Error("Fixture uses original file captures without git"));
  await ctx.plugin(WorkspaceChanges,{});
  createSessionTestController(ctx,{defaultModelSelection:()=>({provider:"fixture",model:"fixture"}),cwd:root});
  await ctx.plugin({inject:["connection","sessionController","workspaceChanges"],apply:registerPresentOpen});
  const session=ctx.sessions.create(SessionId("changes-owned"),{meta:{cwd:root}});
  await writeFile(join(root,"owned.txt"),"before\n");
  startTurn(session,1);await settle(ctx,session);
  await mutate(ctx,session,1,"edit",{file_path:"owned.txt",old_string:"before",new_string:"after"},
    "owned.txt",()=>writeFile(join(root,"owned.txt"),"after\n"));
  endTurn(session,1);await settle(ctx,session);
  const event=session.snapshotEvents().filter(event=>event.type==="workspace/changes").at(-1);
  if(!event)throw Error("Original native recorder did not announce its change");
  const seq=event.seq,state={current:true,allowed:true,coordinates:true,index:0};
  const abort=new AbortController();
  const bindings=():RemoteAccessBinding[]=>state.allowed?[{resource:{kind:"session",id:session.id},
    role:{name:"native-changes-read",resource:"session",actions:["changes/summary","changes/diff"]},
    condition:({args})=>{
      const request=args?.request as {seq?:number;index?:number}|undefined;
      return !state.coordinates||(request?.seq===seq&&(request.index===undefined||request.index===state.index))
        ?{kind:"allow"}:{kind:"deny",reason:"change-coordinates-withdrawn"};
    }}]:[];
  const source={signal:abort.signal,requireCurrent:()=>{if(!state.current)throw Error("retired");},policy:{bindings}};
  let retire=admitted?ctx.remoteAccess.registerOwnerRestriction(source):()=>{};
  const replace=()=>{retire();retire=ctx.remoteAccess.registerOwnerRestriction(source);};
  const peer=ctx.connection.browserPeer,handler=ctx.connection.createSharedFetchHandler("/api");
  const fetch=(path:string,method="GET")=>handler.fetch(new Request("http://native"+path,{method}),peer);
  const read=(id:string=session.id,sequence:number=seq)=>fetch("/api/changes.summary?sessionId="+encodeURIComponent(id)+"&seq="+sequence);
  const diff=(index=0)=>fetch("/api/changes.diff?sessionId="+encodeURIComponent(session.id)+"&seq="+seq+"&index="+index);
  return{ctx,root,session,seq,state,abort,peer,fetch,read,diff,replace};
}
it("serves only the original announced summary and captured before/after comparison",async()=>{
  const h=await fixture(),summary=await h.read(),comparison=await h.diff();
  expect(summary.status).toBe(200);expect(comparison.status).toBe(200);
  const value=await summary.json();
  expect(value).toMatchObject({turn:1,total:1,files:[{path:"owned.txt"}]});
  expect(value).not.toHaveProperty("cwd");expect(value).not.toHaveProperty("snapshot");
  expect(await comparison.json()).toMatchObject({kind:"text",path:"owned.txt",hunks:[{lines:["-before","+after"]}]});
  h.state.coordinates=false;
  expect((await h.read(h.session.id,h.seq+1)).status).toBe(404);
  expect((await h.diff(1)).status).toBe(404);
  h.ctx.emit("session/disposed",h.session);
  expect((await h.read()).status).toBe(404);
});
it.each(["missing","foreign","coordinates"] as const)("refuses %s authority before consulting native change storage",async(kind)=>{
  const h=await fixture(kind!=="missing"),summary=vi.spyOn(h.ctx.workspaceChanges,"summary"),diff=vi.spyOn(h.ctx.workspaceChanges,"diff");
  const response=kind==="foreign"?await h.read("foreign"):kind==="coordinates"?await h.diff(1):await h.read();
  expect(response.status).toBe(403);expect(summary).not.toHaveBeenCalled();expect(diff).not.toHaveBeenCalled();
});
it.each(["guard","bindings","coordinates","replacement","signal"] as const)("withholds a completed native comparison when %s retires during the read",async(kind)=>{
  const h=await fixture(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const original=h.ctx.workspaceChanges.diff.bind(h.ctx.workspaceChanges);let observedSignal:AbortSignal|undefined;
  vi.spyOn(h.ctx.workspaceChanges,"diff").mockImplementationOnce(async(...args)=>{
    observedSignal=args[3];const value=await original(...args);entered.resolve();await release.promise;return value;
  });
  const pending=h.diff();
  await Promise.race([entered.promise,pending.then(()=>{throw Error("Change read did not enter the original recorder");})]);
  if(kind==="guard")h.state.current=false;
  else if(kind==="bindings")h.state.allowed=false;
  else if(kind==="coordinates")h.state.index=1;
  else if(kind==="replacement")h.replace();
  else h.abort.abort(Error("retired"));
  if(kind==="signal")expect(observedSignal?.aborted).toBe(true);
  release.resolve();const response=await pending;expect(response.status).toBe(403);
  expect(await response.text()).not.toContain("after");
  if(kind==="replacement")expect((await h.diff()).status).toBe(200);
});
it("keeps path-only reads and native desktop effects outside the change-read grant",async()=>{
  const h=await fixture(),open=vi.spyOn(h.ctx.sessionController,"openWorkspacePath");
  for(const [path,method] of [
    ["/api/file?path="+encodeURIComponent(join(h.root,"owned.txt")),"GET"],
    ["/api/changes.open?sessionId="+h.session.id+"&seq="+h.seq+"&index=0","POST"],
    ["/api/present.open?sessionId="+h.session.id+"&seq="+h.seq+"&index=0","POST"],
  ])expect((await h.fetch(path!,method!)).status).toBe(403);
  expect(open).not.toHaveBeenCalled();
});
