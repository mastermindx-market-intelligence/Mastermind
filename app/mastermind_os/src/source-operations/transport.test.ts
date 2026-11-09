import { expect, it, vi } from "vitest";
import {
  createSourceOperationTransport,
  sourceOperationRequest,
} from "./transport";

const id = "mmos-project-adopt-" + "a".repeat(40);
const lookup = {
  schema: "mastermind.workspace_source_operation_lookup.v1" as const,
  action: "ADOPT_PLAN" as const,
  request_id: id,
  work_ref: "WS:TEST",
};
const witness = {
  original_input: {
    schema: "mastermind.terminal_original_input_reference.v1",
    input_ref: "terminal-input:" + "b".repeat(64),
    artifact_sha256: "c".repeat(64),
    payload_sha256: "d".repeat(64),
  },
  recipe_fingerprint_sha256: "e".repeat(64),
};
it("maps the same original identity to fixed read and four explicit POST targets", async () => {
  const call = vi.fn(async (_method: string, _path: string) => null),
    port = createSourceOperationTransport(call),
    signal = new AbortController().signal;
  await port.prepareSourceOperation(
    {
      action: lookup.action,
      request: { request_id: id, work_ref: lookup.work_ref },
    },
    signal,
  );
  await port.readSourceOperation(lookup, signal);
  await port.submitSourceOperation(
    {
      action: lookup.action,
      request_id: id,
      work_ref: lookup.work_ref,
      preview_witness: witness,
    },
    signal,
  );
  await port.reconcileSourceOperation(lookup, signal);
  await port.advanceSourceOperation(
    {
      ...lookup,
      schema: "mastermind.workspace_source_operation_advance.v1",
      phase_receipt_digest: "f".repeat(64),
    },
    signal,
  );
  expect(call.mock.calls.map(([method, path]) => [method, path])).toEqual([
    ["prepare", "/workspace/source-operation/prepare"],
    [
      "read",
      `/workspace/source-operation/operation?action=ADOPT_PLAN&request_id=${id}&work_ref=WS%3ATEST`,
    ],
    ["submit", "/workspace/source-operation/submit"],
    ["reconcile", "/workspace/source-operation/reconcile"],
    ["advance", "/workspace/source-operation/advance"],
  ]);
  expect(call).toHaveBeenCalledTimes(5);
});
it("detaches input, never invokes accessors, and sanitizes reflective failures", () => {
  const input = { ...lookup };
  const result = sourceOperationRequest("read", input);
  input.work_ref = "WS:OTHER";
  expect(result.work_ref).toBe("WS:TEST");
  let calls = 0;
  const getter = { ...lookup };
  Object.defineProperty(getter, "request_id", {
    get() {
      calls++;
      return id;
    },
    enumerable: true,
  });
  for (const value of [
    getter,
    new Proxy(lookup, {
      getPrototypeOf() {
        throw Error("PRIVATE_CANARY");
      },
    }),
  ])
    expect(() => sourceOperationRequest("read", value)).toThrow(
      "SOURCE_OPERATION_REQUEST_INVALID",
    );
  expect(calls).toBe(0);
});
it.each([
  ["read", { ...lookup, principal: "caller" }],
  ["read", { ...lookup, work_ref: "WS:TEST\n" }],
  ["read", { ...lookup, request_id: "mmos-project-create-" + "a".repeat(40) }],
  [
    "read",
    {
      ...lookup,
      action: "add_project_file",
      request_id: "mmos-project-file-add-" + "a".repeat(40),
      source_ref: "opaque",
      expected_revision: "b".repeat(40),
      target: "x",
    },
  ],
  [
    "prepare",
    { action: "ADOPT_PLAN", request: { request_id: id, work_ref: null } },
  ],
  [
    "prepare",
    {
      action: "ADOPT_PLAN",
      request: {
        request_id: id,
        work_ref: "WS:TEST",
        private: "x".repeat(32768),
      },
    },
  ],
  [
    "submit",
    {
      action: "ADOPT_PLAN",
      request_id: id,
      work_ref: "WS:TEST",
      preview_witness: { ...witness, principal: "caller" },
    },
  ],
  [
    "advance",
    {
      ...lookup,
      schema: "mastermind.workspace_source_operation_advance.v1",
      phase_receipt_digest: "f".repeat(64) + "\n",
    },
  ],
] as const)(
  "refuses malformed or unqualified %s input before I/O",
  async (method, value) => {
    const call = vi.fn(async () => null),
      port = createSourceOperationTransport(call);
    const invoke = (
      {
        read: port.readSourceOperation,
        prepare: port.prepareSourceOperation,
        submit: port.submitSourceOperation,
        advance: port.advanceSourceOperation,
      } as const
    )[method];
    await expect(
      invoke(value as never, new AbortController().signal),
    ).rejects.toThrow("SOURCE_OPERATION_REQUEST_INVALID");
    expect(call).not.toHaveBeenCalled();
  },
);

function knowledgeLookup(preference=false) {
  return {action:preference?'set_project_communication_preference' as const:'add_project_file' as const,
    request_id:(preference?'mmos-project-preference-set-':'mmos-project-file-add-')+'a'.repeat(40),
    work_ref:'WS:TEST',source_commit:'b'.repeat(40),base_revision:'c'.repeat(64),
    request_sha256:'d'.repeat(64),expected_preference_revision:preference?'e'.repeat(64):null};
}
it.each([false,true])('preserves the exact Knowledge seven-field lookup and fixed null wire %s',async preference=>{
  const call=vi.fn(async(_method:string,_path:string,_body:Record<string,unknown>,_signal:AbortSignal)=>({})),port=createSourceOperationTransport(call),input=knowledgeLookup(preference);
  const signal=new AbortController().signal;
  await port.readSourceOperation(input,signal);await port.reconcileSourceOperation(input,signal);
  const url=new URL(call.mock.calls[0][1],'https://app.mastermind-x.com');
  expect(url.pathname).toBe('/workspace/source-operation/operation');
  expect(Object.fromEntries(url.searchParams)).toEqual(Object.fromEntries(Object.entries(input).map(([key,value])=>[key,String(value)])));
  expect(call.mock.calls[1][0]).toBe('reconcile');expect(call.mock.calls[1][2]).toEqual(input);
  expect(call.mock.calls[1][2].expected_preference_revision).toBe(preference?'e'.repeat(64):null);
});
it('refuses malformed Knowledge variants without falling back to another action or basic selector',()=>{
  const original=knowledgeLookup();
  const variants=[{...original,schema:'mastermind.workspace_source_operation_lookup.v1'},
    {...original,action:'ADOPT_PLAN',request_id:'mmos-project-adopt-'+'a'.repeat(40)},
    {...original,source_commit:'B'.repeat(40)},{...original,base_revision:'short'},
    {...original,request_sha256:'d'.repeat(64)+'\n'},{...original,expected_preference_revision:'e'.repeat(64)},
    {...original,principal_scope:'f'.repeat(64)},{...original,source_path:'/private/file'},
    {...original,work_ref:'WS:OTHER\n'},{...original,request_id:'mmos-project-preference-set-'+'a'.repeat(40)},
    {...original,expected_preference_revision:undefined}];
  const hidden={...original};Object.defineProperty(hidden,'source_commit',{value:original.source_commit,enumerable:false});variants.push(hidden);
  for(const input of variants)for(const method of ['read','reconcile'] as const)
    expect(()=>sourceOperationRequest(method,input)).toThrow('SOURCE_OPERATION_REQUEST_INVALID');
  expect(()=>sourceOperationRequest('read',{schema:'mastermind.workspace_source_operation_lookup.v1',action:original.action,request_id:original.request_id,work_ref:original.work_ref})).toThrow();
});

it('accepts actual UTF8 JSON envelopes for maximum allowed files and rejects one decoded byte over',()=>{
 const measurements:number[]=[];
 for(const unit of ['"','\\','\r','\n','\t','中文😀','"\\\r\n\t中文😀']){
  const width=new TextEncoder().encode(unit).length;
  const content=unit.repeat(Math.floor(32768/width))+'x'.repeat(32768%width);
  const body={action:'add_project_file',request:{schema:'mastermind.project_file_add_request.v1',
   request_id:'mmos-project-file-add-'+'a'.repeat(40),work_ref:'WS:'+'A'.repeat(64),source_commit:'b'.repeat(40),base_revision:'c'.repeat(64),
   file:{display_name:'"'.repeat(125)+'.MD',media_type:'text/markdown',content_utf8:content}}};
  const selected=sourceOperationRequest('prepare',body);
  const encoded=JSON.stringify(selected),bytes=new TextEncoder().encode(encoded).length;
  measurements.push(bytes);
  expect(bytes).toBeGreaterThan(32768);expect(bytes).toBeLessThanOrEqual(98304);
  expect(JSON.parse(encoded).request.file.content_utf8).toBe(content);
  expect(()=>sourceOperationRequest('prepare',{...body,request:{...body.request,file:{...body.request.file,content_utf8:content+'x'}}})).toThrow();
  expect(()=>sourceOperationRequest('prepare',{action:'ADOPT_PLAN',request:{request_id:'mmos-project-adopt-'+'a'.repeat(40),work_ref:'WS:TEST',body:content}})).toThrow();
 } console.info('KNOWLEDGE_FILE_ENVELOPE_UTF8 '+JSON.stringify({file_bytes:32768,case_bytes:measurements,max_json_bytes:Math.max(...measurements),cap:98304,max_display_name_bytes:128,max_work_key_chars:64}));
});

it('refuses a hostile Proxy that changes the preflight file action during detachment before any call',async()=>{
 let reads=0;
 const target={action:'ADOPT_PLAN' as const,request:{schema:'mastermind.project_file_add_request.v1',
  request_id:'mmos-project-adopt-'+'a'.repeat(40),work_ref:'WS:TEST',source_commit:'b'.repeat(40),base_revision:'c'.repeat(64),
  file:{display_name:'notes.md',media_type:'text/markdown',content_utf8:'"'.repeat(32768)}}};
 const hostile=new Proxy(target,{getOwnPropertyDescriptor(object,key){
  const descriptor=Reflect.getOwnPropertyDescriptor(object,key);
  return key==='action'&&++reads===1?{...descriptor!,value:'add_project_file'}:descriptor;
 }});
 const call=vi.fn(async()=>({}));const port=createSourceOperationTransport(call);
 await expect(port.prepareSourceOperation(hostile,new AbortController().signal)).rejects.toThrow('SOURCE_OPERATION_REQUEST_INVALID');
 expect(call).not.toHaveBeenCalled();
});
