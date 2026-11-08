/** Actual Gateway/JSONL history through the finite inherited-port component. */
import {afterEach, expect, it, vi} from "vitest";
import {Duplex, PassThrough} from "node:stream";
import {setImmediate} from "node:timers/promises";
import {attachExecutiveReadPort, type InstalledNativeReadSource} from "./src/executive-read-port";
import {attachNativeTestPort, canonical, disk, nativeFixture, request, testAssociation} from "./native.read-fixture";

const cleanup: (()=>Promise<void>)[] = [];
afterEach(async()=>{while(cleanup.length) await cleanup.pop()!(); vi.restoreAllMocks();});
function pair() {
  const toHost = new PassThrough(), fromHost = new PassThrough();
  const host=Duplex.from({readable:toHost,writable:fromHost}),
    client=Duplex.from({readable:fromHost,writable:toHost});
  // Duplex.from propagates an expected abort to the opposite test endpoint.
  // Production owns a net.Socket; both fixture halves must consume closure.
  host.on("error",()=>{});client.on("error",()=>{});
  return {host,client};
}
async function harness(answer?:string, options?: Parameters<typeof nativeFixture>[1]) {
  const h = await nativeFixture(answer, options); cleanup.push(h.close);
  const ports = pair(), generation = new AbortController();
  let current = true;
  const source: InstalledNativeReadSource = {association:testAssociation(),signal:generation.signal,
    requireCurrent:()=>{if(!current) throw Error("fixture source retired");}};
  const attached = await attachNativeTestPort(h.ctx, ports.host, source);
  cleanup.push(async()=>{await attached.dispose(); ports.client.destroy();});
  return {...h,...ports,generation,source,attached,setCurrent:(value:boolean)=>{current=value;}};
}
function read(port:Duplex):Promise<any> {
  return new Promise((resolve,reject)=>{
    let data=Buffer.alloc(0);
    const done=()=>{port.off("data",onData);port.off("close",onClose);port.off("error",onError);};
    const onClose=()=>{done();reject(Error("port closed"));},onError=(error:Error)=>{done();reject(error);};
    const onData=(chunk:Buffer)=>{data=Buffer.concat([data,chunk]);if(data.includes(10)){done();resolve(JSON.parse(data.toString("utf8")));}};
    port.on("data",onData);port.once("close",onClose);port.once("error",onError);
  });
}
async function send(h:Awaited<ReturnType<typeof harness>>,value= request(h.source.association)) {
  const response=read(h.client); h.client.write(canonical(value)+"\n");
  const result=await response; await setImmediate(); return result;
}

it("reads the exact cold native session twice while its original writer and stream bytes remain intact",async()=>{
  const h=await harness(), create=vi.spyOn(h.ctx.agents,"create"),resume=vi.spyOn(h.ctx.agents,"resume");
  const open=vi.spyOn(h.ctx.sessionPersistence,"open");
  const first=await send(h),second=await send(h);
  expect(first.status).toBe("READ");expect(first.data).toEqual(second.data);
  expect(first.data.page.records.map((row:any)=>row.event.seq)).toEqual([0,1,2,3,4,5]);
  expect(JSON.stringify(first.data)).toContain("原始问题");
  expect(JSON.stringify(first.data)).toContain('"texts":["Native answer"," retained"," — 原样保留"]');
  expect(open.mock.calls.every(call=>call[0]===h.id&&call[1]==="read")).toBe(true);
  expect(create).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();
  expect(h.ctx.sessions.get(h.id)).toBeUndefined();expect(h.ctx.agents.get(h.id)).toBeUndefined();
  expect(await disk(h.root)).toEqual(h.before);
});

it.each(["foreign-principal","foreign-association","expired","future"] as const)(
  "refuses %s before the native storage owner is entered",async(fault)=>{
    const h=await harness(),open=vi.spyOn(h.ctx.sessionPersistence,"open"),value=request(h.source.association);
    if(fault==="foreign-principal")value.principal.principal_scope="9".repeat(64);
    if(fault==="foreign-association")value.association_sha256="9".repeat(64);
    if(fault==="expired"){value.principal.issued_at-=900;value.principal.expires_at=value.principal.issued_at+1;}
    if(fault==="future"){value.principal.issued_at+=100;value.principal.expires_at+=200;}
    expect(await send(h,value)).toMatchObject({status:"UNAVAILABLE",data:null});
    expect(open).not.toHaveBeenCalled();expect(await disk(h.root)).toEqual(h.before);
  });

it.each(["session-selector","duplicate-key","bom","oversized","pipeline"] as const)(
  "retires malformed %s without entering native storage",async(fault)=>{
    const h=await harness(),open=vi.spyOn(h.ctx.sessionPersistence,"open");
    const value=request(h.source.association);let raw=canonical(value)+"\n";
    if(fault==="session-selector")raw=canonical({...value,read:{kind:"snapshot",session_id:"foreign"}})+"\n";
    if(fault==="duplicate-key")raw=raw.replace('"read":','"read":{},"read":');
    if(fault==="bom")raw="\ufeff"+raw;
    if(fault==="oversized")raw=" ".repeat(8193);
    if(fault==="pipeline")raw+=raw;
    h.client.write(raw);await vi.waitFor(()=>expect(h.host.destroyed).toBe(true));
    expect(open).not.toHaveBeenCalled();
  });

it("withholds a late real native read after original source retirement and cannot revive it",async()=>{
  const h=await harness(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const invoke=h.ctx.typertGateway.invoke.bind(h.ctx.typertGateway);
  vi.spyOn(h.ctx.typertGateway,"invoke").mockImplementation(async args=>{
    const result=await invoke(args);entered.resolve();await release.promise;return result;
  });
  const response=send(h).then(value=>({value}),error=>({error}));
  await entered.promise;h.setCurrent(false);release.resolve();
  await vi.waitFor(()=>expect(h.host.destroyed).toBe(true));
  h.setCurrent(true);expect(h.host.destroyed).toBe(true);
  h.client.destroy();expect(await response).toHaveProperty("error");
  expect(await disk(h.root)).toEqual(h.before);
});

it("refuses an oversized whole native page without truncating or exposing a partial transcript",async()=>{
  const h=await harness("界".repeat(15000));
  const value=await send(h);expect(value).toMatchObject({status:"PAGE_TOO_LARGE",data:null});
  expect(Buffer.byteLength(JSON.stringify(value)+"\n")).toBeLessThan(32768);
  expect(await disk(h.root)).toEqual(h.before);
});

it("retires both the pending read and port on concurrent input instead of queuing another read",async()=>{
  const h=await harness(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const invoke=h.ctx.typertGateway.invoke.bind(h.ctx.typertGateway);
  const calls=vi.spyOn(h.ctx.typertGateway,"invoke").mockImplementation(async args=>{
    entered.resolve();await release.promise;return invoke(args);
  });
  h.client.write(canonical(request(h.source.association))+"\n");await entered.promise;
  h.client.write(canonical(request(h.source.association))+"\n");
  await vi.waitFor(()=>expect(h.host.destroyed).toBe(true));release.resolve();
  await h.attached.dispose();expect(calls).toHaveBeenCalledTimes(1);
});

it("releases only its original port scope and permits a newly qualified attachment in the surviving native Context",async()=>{
  const h=await harness();
  expect((await send(h)).status).toBe("READ");
  await h.attached.dispose();
  expect(h.host.closed).toBe(true);
  const next=pair(),generation=new AbortController();
  const owner=await attachNativeTestPort(h.ctx,next.host,{
    association:h.source.association,signal:generation.signal,requireCurrent:()=>{},
  });
  cleanup.push(async()=>{await owner.dispose();next.client.destroy();});
  const value=read(next.client);next.client.write(canonical(request(h.source.association))+"\n");
  expect(await value).toMatchObject({status:"READ"});
  expect(h.ctx.sessions.get(h.id)).toBeUndefined();expect(await disk(h.root)).toEqual(h.before);
});

it("refuses an already-retired source before leaving a native policy behind",async()=>{
  const h=await nativeFixture();cleanup.push(h.close);
  const first=pair(),retired=new AbortController();retired.abort();
  expect(()=>attachExecutiveReadPort(h.ctx,first.host,{
    association:testAssociation(),signal:retired.signal,requireCurrent:()=>{},
  })).toThrow("unavailable");
  first.host.destroy();first.client.destroy();
  const next=pair(),live=new AbortController();
  const owner=await attachNativeTestPort(h.ctx,next.host,{
    association:testAssociation(),signal:live.signal,requireCurrent:()=>{},
  });
  cleanup.push(async()=>{await owner.dispose();next.client.destroy();});
  const value=read(next.client);next.client.write(canonical(request())+"\n");
  expect(await value).toMatchObject({status:"READ"});
});

it("preserves the original native before-first-event history cursor",async()=>{
  const h=await harness(),value=request(h.source.association,{
    read:{kind:"page",through_seq:-1,before_seq:0,max_messages:1},
  });
  const response=await send(h,value);
  expect(response.status).toBe("READ");expect(response.data.page.records).toEqual([]);
  expect(await disk(h.root)).toEqual(h.before);
});


function resultRead(h: Awaited<ReturnType<typeof harness>>) {
  const claim = {schema:"mastermind.dsh.native_prompt_claim.v1",
    operationId:"original-result",requestId:7,sessionId:h.id,messageId:h.originalMessage.id,
    nativeTurn:1,throughSeq:0};
  const last = h.originalRecords[h.originalRecords.length - 1];
  const terminal = {schema:"mastermind.dsh.native_prompt_terminal.v1",
    operationId:claim.operationId,requestId:claim.requestId,claim,
    throughSeq:last.seq,observedLastTurn:(last.data as any).turn,
    observedTurnCount:h.originalRecords.filter(row=>row.type==="turn/start").length};
  return {kind:"result",claim,terminal,offset_bytes:0,expected_sha256:null as string|null};
}

it("reconstructs an oversized original answer through the real cold owner without substituting a later turn",async()=>{
  const answer=" \n"+"界🪐".repeat(20000)+"  \n",h=await harness(answer,{laterAnswer:"THIS IS A DIFFERENT TURN"});
  const create=vi.spyOn(h.ctx.agents,"create"),resume=vi.spyOn(h.ctx.agents,"resume");
  const selected=resultRead(h),chunks:Buffer[]=[];
  let nativeReadFailure:unknown;
  const invoke=h.ctx.typertGateway.invoke.bind(h.ctx.typertGateway);
  vi.spyOn(h.ctx.typertGateway,"invoke").mockImplementation(async args=>{
    try {return await invoke(args);}
    catch(error){nativeReadFailure=error;throw error;}
  });
  let originalDigest:string|undefined, metadata:any;
  for(let count=0;count<256;count++){
    const value=await send(h,request(h.source.association,{read:selected}));
    if(value.status!=="READ" && nativeReadFailure)throw nativeReadFailure;
    expect(value.status).toBe("READ");
    expect(Buffer.byteLength(JSON.stringify(value)+"\n")).toBeLessThan(32768);
    const data=value.data,part=data.content;
    expect(data.state).toBe("CONTENT");
    expect(data.claim).toEqual(selected.claim);expect(data.terminal).toEqual(selected.terminal);
    expect(data.user_message_seq).toBeGreaterThan(selected.claim.throughSeq);
    expect(data.turn_start_seq).toBe(0);expect(data.turn_end_seq).toBe(5);
    expect(data.assistant_message_seqs).toEqual([3]);
    expect(part.offset_bytes).toBe(selected.offset_bytes);
    expect(part.encoding).toBe("base64");
    const chunk=Buffer.from(part.data,"base64");expect(chunk.byteLength).toBeGreaterThan(0);
    expect(chunk.byteLength).toBeLessThanOrEqual(4096);chunks.push(chunk);
    if(originalDigest===undefined){originalDigest=part.sha256;metadata=part;}
    expect(part.sha256).toBe(originalDigest);
    if(part.next_offset_bytes===null)break;
    selected.offset_bytes=part.next_offset_bytes;selected.expected_sha256=part.sha256;
  }
  const bytes=Buffer.concat(chunks);
  expect(bytes.byteLength).toBe(metadata.total_bytes);
  expect(bytes.byteLength).toBeGreaterThan(131072);
  const {createHash}=await import("node:crypto");
  expect(createHash("sha256").update(bytes).digest("hex")).toBe(originalDigest);
  const content=JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(bytes));
  expect(content.records.map((row:any)=>row.event.seq)).toEqual([0,1,2,3,4,5]);
  expect(content.records[3].event.data.message.content[0].text).toBe(answer);
  expect(content.records[3].event.data.stream[0].texts).toEqual(["Native answer"," retained"," — 原样保留"]);
  expect(bytes.toString("utf8")).not.toContain("THIS IS A DIFFERENT TURN");
  expect(create).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();
  expect(h.ctx.sessions.get(h.id)).toBeUndefined();expect(h.ctx.agents.get(h.id)).toBeUndefined();
  expect(await disk(h.root)).toEqual(h.before);
});

it("returns explicit no-answer for the original blocked pre-step claim",async()=>{
  const h=await harness(undefined,{blocked:true}),selected=resultRead(h);
  const value=await send(h,request(h.source.association,{read:selected}));
  expect(value).toMatchObject({status:"READ",data:{kind:"result",state:"NO_ANSWER",
    turn_start_seq:0,turn_end_seq:1,user_message_seq:null,assistant_message_seqs:[],content:null}});
  expect(await disk(h.root)).toEqual(h.before);
});

it.each(["message","session","digest","offset"] as const)(
  "withholds original result bytes after %s substitution",async(fault)=>{
    const h=await harness(),selected=resultRead(h);
    if(fault==="message"){selected.claim.messageId="foreign-message";}
    if(fault==="session"){selected.claim.sessionId="foreign-session";}
    if(fault==="digest"){selected.expected_sha256="0".repeat(64);}
    if(fault==="offset"){selected.offset_bytes=4000000;selected.expected_sha256="0".repeat(64);}
    const value=await send(h,request(h.source.association,{read:selected}));
    expect(value).toMatchObject({status:"UNAVAILABLE",data:null});
    expect(await disk(h.root)).toEqual(h.before);
  });

it("withdraws result content when the original read authority changes during the cold page",async()=>{
  const h=await harness(),entered=Promise.withResolvers<void>(),release=Promise.withResolvers<void>();
  const invoke=h.ctx.typertGateway.invoke.bind(h.ctx.typertGateway);
  vi.spyOn(h.ctx.typertGateway,"invoke").mockImplementation(async args=>{
    const result=await invoke(args);entered.resolve();await release.promise;return result;
  });
  const response=send(h,request(h.source.association,{read:resultRead(h)})).then(value=>({value}),error=>({error}));
  await entered.promise;h.setCurrent(false);release.resolve();
  expect(await response).toHaveProperty("error");
  expect(h.host.destroyed).toBe(true);expect(await disk(h.root)).toEqual(h.before);
});


it("retains native runtime-context records without confusing them with the claimed user message",async()=>{
  const h=await harness(undefined,{runtimeContext:true}),selected=resultRead(h);
  const value=await send(h,request(h.source.association,{read:selected}));
  expect(value.status).toBe("READ");expect(value.data.state).toBe("CONTENT");
  expect(value.data.user_message_seq).toBe(2);expect(value.data.assistant_message_seqs).toEqual([4]);
  expect(value.data.content.next_offset_bytes).toBeNull();
  const records=JSON.parse(Buffer.from(value.data.content.data,"base64").toString("utf8")).records;
  const users=records.filter((row:any)=>row.event.type==="user/message");
  expect(users).toHaveLength(2);
  expect(users[0].event.data.id).toBe(selected.claim.messageId);
  expect(users[1].event.data.source.kind).toBe("runtime-context");
  expect(users[1].event.data.content[0].text).toBe("Actual native runtime context");
  expect(await disk(h.root)).toEqual(h.before);
});

it.each(["completed","aborted"] as const)("reports the exact closed empty %s original turn without inventing text",async emptyReason=>{
  const h=await harness(undefined,{emptyReason}),selected=resultRead(h);
  const value=await send(h,request(h.source.association,{read:selected}));
  expect(value).toMatchObject({status:"READ",data:{kind:"result",state:"NO_ANSWER",
    turn_start_seq:0,turn_end_seq:emptyReason==="aborted"?3:1,
    user_message_seq:null,assistant_message_seqs:[],content:null}});
  expect(await disk(h.root)).toEqual(h.before);
});
