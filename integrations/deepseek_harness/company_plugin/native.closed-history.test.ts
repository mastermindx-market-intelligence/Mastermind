/** Actual cold donor owner: no provider, browser auth, Agent or Session admission. */
import {afterEach,expect,it,vi} from "vitest";
import {Context} from "@deepseek-ai/cordis";
import SessionStore from "@deepseek-ai/dsh-session";
import {TypertGatewayService} from "@deepseek-ai/dsh-api-gateway";
import {Duplex,PassThrough} from "node:stream";
import {cp,mkdtemp,rm,readFile,chown} from "node:fs/promises";
import {spawn} from "node:child_process";
import {createHash} from "node:crypto";
import {tmpdir} from "node:os";
import {join,dirname} from "node:path";
import {openClosedNativeHistory} from "./src/executive-read-port";
import {canonical,disk,nativeFixture,request,testAssociation} from "./native.read-fixture";

const cleanup:(()=>Promise<void>)[]=[];
afterEach(async()=>{while(cleanup.length)await cleanup.pop()!();vi.restoreAllMocks();});
function pair(){
  const input=new PassThrough(),output=new PassThrough();
  const host=Duplex.from({readable:input,writable:output}),client=Duplex.from({readable:output,writable:input});
  host.on("error",()=>{});client.on("error",()=>{});return {host,client};
}
function receive(port:Duplex):Promise<any>{
  return new Promise((resolve,reject)=>{
    let bytes=Buffer.alloc(0);
    const done=()=>{port.off("data",data);port.off("close",closed);port.off("error",error);};
    const closed=()=>{done();reject(Error("closed"));},error=(e:Error)=>{done();reject(e);};
    const data=(chunk:Buffer)=>{bytes=Buffer.concat([bytes,chunk]);if(bytes.includes(10)){done();resolve(JSON.parse(bytes.toString("utf8")));}};
    port.on("data",data);port.once("close",closed);port.once("error",error);
  });
}
async function fixture(){
  const seed=await nativeFixture("Original closed answer — 原样", {laterAnswer:"Different later answer"});
  const home=await mkdtemp(join(tmpdir(),"mmx-cold-native-home-"));
  await cp(seed.root,join(home,"sessions"),{recursive:true});
  const id=seed.id,records=seed.originalRecords,message=seed.originalMessage;
  await seed.close();
  cleanup.push(()=>rm(home,{recursive:true,force:true}));
  const before=await disk(home),ports=pair(),life=new AbortController();
  let current=true;
  const prepare=vi.spyOn(SessionStore.prototype,"prepare"),enter=vi.spyOn(SessionStore.prototype,"enter");
  const invoke=vi.spyOn(TypertGatewayService.prototype,"invoke");
  const association=testAssociation({native_session_id:id});
  const owner=await openClosedNativeHistory(home,ports.host,{
    association,signal:life.signal,requireCurrent(){if(!current)throw Error("retired");},
  });
  cleanup.push(async()=>{await owner.dispose();ports.client.destroy();});
  const claim={schema:"mastermind.dsh.native_prompt_claim.v1",operationId:"original-closed-result",
    requestId:7,sessionId:id,messageId:message.id,nativeTurn:1,throughSeq:0};
  const last=records.at(-1)!;
  const terminal={schema:"mastermind.dsh.native_prompt_terminal.v1",operationId:claim.operationId,
    requestId:claim.requestId,claim,throughSeq:last.seq,observedLastTurn:(last.data as any).turn,
    observedTurnCount:records.filter(row=>row.type==="turn/start").length};
  const read={kind:"result",claim,terminal,offset_bytes:0,expected_sha256:null};
  const send=async(value=request(association,{read}))=>{
    const response=receive(ports.client);ports.client.write(canonical(value)+"\n");return response;
  };
  return {...ports,home,before,life,owner,enter,invoke,association,read,send,
    get root(){return (prepare.mock.contexts[0] as any).ctx.root as Context;},
    retire(){current=false;}};
}
it("recovers the sealed original answer after the original context and writer are gone",async()=>{
  const h=await fixture(),value=await h.send();
  expect(value.status).toBe("READ");expect(value.data.state).toBe("CONTENT");
  const bytes=Buffer.from(value.data.content.data,"base64").toString("utf8");
  expect(bytes).toContain("Original closed answer — 原样");expect(bytes).not.toContain("Different later answer");
  expect(h.invoke.mock.calls.every(([call])=>call.namespace==="session"&&call.method==="page")).toBe(true);
  expect(h.enter).not.toHaveBeenCalled();
  for(const service of ["agents","connection","browserAuth","webServer","llm"])
    expect(h.root.get(service as any)).toBeUndefined();
  expect(h.root.sessions.get(h.association.native_session_id as any)).toBeUndefined();
  await h.owner.dispose();expect(await disk(h.home)).toEqual(h.before);
});
it.each(["expired","wrong-session","wrong-principal","snapshot"] as const)(
  "withholds closed history on %s without changing native storage",async(fault)=>{
    const h=await fixture(),value=request(h.association,{read:structuredClone(h.read)}) as any;
    if(fault==="expired"){value.principal.issued_at-=500;value.principal.expires_at=value.principal.issued_at+1;}
    if(fault==="wrong-session")value.read.claim.sessionId="foreign";
    if(fault==="wrong-principal")value.principal.principal_scope="9".repeat(64);
    if(fault==="snapshot")value.read={kind:"snapshot"};
    expect(await h.send(value)).toMatchObject({status:"UNAVAILABLE",data:null});
    expect(h.enter).not.toHaveBeenCalled();expect(await disk(h.home)).toEqual(h.before);
  });
it("drains an aborted original cold page before disposing persistence",async()=>{
  const h=await fixture(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  h.invoke.mockRestore();
  const invoke=TypertGatewayService.prototype.invoke;
  vi.spyOn(TypertGatewayService.prototype,"invoke").mockImplementation(async function(args){
    const result=await invoke.call(this,args);entered.resolve();await release.promise;return result;
  });
  const pending=h.send().then(value=>({value}),error=>({error}));
  await entered.promise;h.life.abort();
  let finished=false;const disposal=h.owner.dispose().then(()=>{finished=true;});
  await Promise.resolve();expect(finished).toBe(false);release.resolve();
  await disposal;expect(await pending).toHaveProperty("error");
  expect(await disk(h.home)).toEqual(h.before);
});

it("rejects a promise-valued original guard before composing a cold owner",async()=>{
  const ports=pair(),life=new AbortController(),prepare=vi.spyOn(SessionStore.prototype,"prepare");
  try{
    await expect(openClosedNativeHistory("/unused",ports.host,{
      association:testAssociation(),signal:life.signal,
      requireCurrent:(()=>Promise.resolve()) as unknown as ()=>void,
    })).rejects.toThrow("unavailable");
    expect(prepare).not.toHaveBeenCalled();
  }finally{ports.host.destroy();ports.client.destroy();}
});

it.skipIf(!process.env.MMX_DSH_NATIVE_HISTORY_ENTRY)(
  "uses the qualified packaged Worker entry for the original closed answer",async()=>{
    const h=await fixture();
    await h.owner.dispose();h.client.destroy();
    const entry=process.env.MMX_DSH_NATIVE_HISTORY_ENTRY!;
    const release=dirname(entry);
    const config=JSON.parse(await readFile(join(release,"app.json"),"utf8"));
    const association={...h.association,native_package_sha256:createHash("sha256")
      .update(await readFile(join(release,"package-manifest.json"))).digest("hex")};
    // This test-owned home must satisfy the original enrolled realm's uid/gid
    // law even when macOS's temporary parent supplies a different inherited gid.
    await chown(h.home,process.getuid!(),process.getgid!());
    const child=spawn(config.node,[entry,"--read-history"],{
      cwd:h.home,env:{PATH:"/usr/bin:/bin:/usr/sbin:/sbin",HOME:process.env.HOME!,
        DSH_HOME:h.home,LANG:"C.UTF-8",MMX_NATIVE_COMPANY_FD:"3",
        MMX_NATIVE_HISTORY_ASSOCIATION:canonical(association)},
      stdio:["ignore","pipe","pipe","pipe"],
    });
    const port=child.stdio[3] as Duplex;
    let diagnostic="";
    child.stderr!.on("data",chunk=>{if(diagnostic.length<8192)diagnostic+=String(chunk);});
    child.stdout!.resume();port.on("error",()=>{});
    const finished=new Promise<{code:number|null;signal:string|null}>((resolve,reject)=>{
      child.once("error",reject);child.once("exit",(code,signal)=>resolve({code,signal}));
    });
    const response=receive(port);
    try{
      port.write(canonical(request(association,{read:h.read}))+"\n");
      const value=await response.catch(error=>{throw Error(String(error)+" "+diagnostic);});
      expect(value.status).toBe("READ");expect(value.data.state).toBe("CONTENT");
      const bytes=Buffer.from(value.data.content.data,"base64").toString("utf8");
      expect(bytes).toContain("Original closed answer — 原样");
      expect(bytes).not.toContain("Different later answer");
      port.end();
      expect(await finished).toEqual({code:0,signal:null});
      expect(await disk(h.home)).toEqual(h.before);
    }finally{
      port.destroy();
      // This finite fixture owns only this child. No service or original Session
      // process is signalled; await its actual exit on every failure path.
      if(child.exitCode===null&&child.signalCode===null)child.kill("SIGTERM");
      await finished;
    }
  },15000);
