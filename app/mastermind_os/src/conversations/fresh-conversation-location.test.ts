import {expect,it,vi} from "vitest";
import {readFreshConversationLocation as read,writeFreshConversationLocation as write} from "./fresh-conversation-location";
const selected={work_ref:"WS:Qualified.Project",operation_key:"mmos-conversation-create-"+"a".repeat(40)};
it("roundtrips only the original work/key lookup without carrying private input or previous Mission identity",()=>{
 const out=write("https://mcp.mastermind-x.com/os/?message=PRIVATE&work_ref=WS:OTHER&root_job_id=JOB-1#PRIVATE",selected);
 expect(read(out)).toEqual({valid:true,open:true,selection:selected});
 expect(new URL(out).searchParams.size).toBe(3);expect(out).not.toContain("PRIVATE");expect(out).not.toContain("JOB-1");
});
it("keeps blank entry and closed list distinct without minting an original key",()=>{
 expect(read(write("https://mcp.mastermind-x.com/os/",null))).toEqual({valid:true,open:true,selection:null});
 expect(read(write("https://mcp.mastermind-x.com/os/?private=1",null,false))).toEqual({valid:true,open:false,selection:null});
});
it.each(["new_conversation=0","new_conversation=1&new_conversation=1","conversation_work_ref=WS:ONE",
 "conversation_operation_key=mmos-conversation-create-"+"b".repeat(40),"conversation_work_ref=WS:ONE&conversation_operation_key=foreign"])("refuses malformed/incomplete lookup %s",query=>{
 expect(read("https://mcp.mastermind-x.com/os/?"+query)).toEqual({valid:false,open:false,selection:null});
});
it("rejects foreign record versions, descriptors and credential URLs without exposing or executing input",()=>{
 const getter=vi.fn(()=>selected.work_ref),input=Object.defineProperty({operation_key:selected.operation_key},"work_ref",{get:getter,enumerable:true});
 for(const value of [input,{...selected,operation_key:"mmos-launch-"+"a".repeat(40)},{...selected,extra:true}])
  expect(()=>write("https://mcp.mastermind-x.com/os/",value as never)).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
 expect(getter).not.toHaveBeenCalled();
 expect(()=>write("https://user:PRIVATE@mcp.mastermind-x.com/os/",selected)).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
});

it("preserves the native custom-scheme host/path and rejects a contradictory closed original lookup",()=>{
 const out=write("tauri://localhost/os/?message=PRIVATE#PRIVATE",selected);
 const url=new URL(out);expect(url.protocol).toBe("tauri:");expect(url.host).toBe("localhost");expect(url.pathname).toBe("/os/");
 expect(read(out)).toEqual({valid:true,open:true,selection:selected});expect(out).not.toContain("PRIVATE");
 expect(()=>write("https://mcp.mastermind-x.com/os/",selected,false)).toThrow("FRESH_CONVERSATION_LOCATION_INVALID");
});
