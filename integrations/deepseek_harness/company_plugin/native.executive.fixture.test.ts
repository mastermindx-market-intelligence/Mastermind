/** Cross-process fixture, entered only by test_deepseek_native_read.py.
 * This test-owned socket pair is not an installed launcher handoff.
 */
import {expect,it,vi} from "vitest";
import {Socket} from "node:net";
import {readFile,writeFile} from "node:fs/promises";
import {attachExecutiveReadPort,type InstalledNativeReadAssociation} from "./src/executive-read-port";
import {attachNativeTestPort,disk,nativeFixture,digest} from "./native.read-fixture";

const specPath=process.env.MMX_DSH_NATIVE_READ_FIXTURE;
it.skipIf(!specPath)("serves the original native history to the actual Python Runtime/private bridge",async()=>{
  const spec=JSON.parse(await readFile(specPath!,"utf8")) as {
    fd:number;association:InstalledNativeReadAssociation;ready:string;report:string;
    answer?:string;question?:string;laterAnswer?:string;runtimeContext?:boolean;
  };
  expect(Number.isSafeInteger(spec.fd)&&spec.fd>=3).toBe(true);
  const h=await nativeFixture(spec.answer,{sessionId:spec.association.native_session_id,
    question:spec.question,laterAnswer:spec.laterAnswer,runtimeContext:spec.runtimeContext}),
    port=new Socket({fd:spec.fd,readable:true,writable:true});
  const ownerLife=new AbortController();
  const create=vi.spyOn(h.ctx.agents,"create"),resume=vi.spyOn(h.ctx.agents,"resume");
  const open=vi.spyOn(h.ctx.sessionPersistence,"open");
  const invoke=vi.spyOn(h.ctx.typertGateway,"invoke");
  const closed=new Promise<void>(resolve=>port.once("close",resolve));
  const owner=await attachNativeTestPort(h.ctx,port,{
    association:spec.association,signal:ownerLife.signal,requireCurrent:()=>{},
  });
  try {
    await writeFile(spec.ready,JSON.stringify({ready:true,donor:spec.association.donor_sha,
      session_id:h.id,message_id:h.originalMessage.id,through_seq:h.originalRecords.at(-1)!.seq,
      records_sha256:digest({records:h.originalRecords})})+"\n");
    await closed;await owner.dispose();
    const after=await disk(h.root);
    expect(after).toEqual(h.before);expect(create).not.toHaveBeenCalled();expect(resume).not.toHaveBeenCalled();
    expect(open.mock.calls.length).toBeGreaterThan(0);
    expect(open.mock.calls.every(call=>call[0]===h.id&&call[1]==="read")).toBe(true);
    expect(h.ctx.sessions.get(h.id)).toBeUndefined();expect(h.ctx.agents.get(h.id)).toBeUndefined();
    await writeFile(spec.report,JSON.stringify({
      schema:"mastermind.dsh.native_read_fixture.v1",original_writer_held:true,
      native_files_before:h.before,native_files_after:after,native_read_calls:open.mock.calls.length,
      gateway_methods:invoke.mock.calls.map(([call])=>call.method),
      agent_create_calls:create.mock.calls.length,agent_resume_calls:resume.mock.calls.length,
      native_session_promoted:false,port_closed:port.closed,provider_calls:0,installed:false,
    },null,2)+"\n");
  } finally {await owner.dispose();await h.close();}
},45000);
