import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {TextOutputPager,OUTPUT_PAGE_TOOL} from './output-budget.mjs';
const size=x=>Buffer.byteLength(JSON.stringify(x));
const body=x=>JSON.parse(x.content[0].text);
const result=(text,extra={})=>({content:[{type:'text',text}],...extra});
const make=extra=>new TextOutputPager({responseBytes:2048,...extra});
function reconstruct(pager,receipt){let offset=0,chunks=[];
  for(let n=0;n<1000;n++){const response=pager.read({receipt_id:receipt.receipt_id,offset});
    assert.ok(size(response)<=2048);const p=body(response);assert.equal(p.status,'OUTPUT_PAGE');
    assert.equal(p.offset,offset);assert.equal(p.sha256,receipt.sha256);
    assert.equal(Buffer.byteLength(p.text),p.next_offset-offset);chunks.push(p.text);
    if(p.done){const text=chunks.join('');assert.equal(Buffer.byteLength(text),receipt.source_bytes);
      assert.equal(createHash('sha256').update(text).digest('hex'),receipt.sha256);return JSON.parse(text);}
    assert.ok(p.next_offset>offset);offset=p.next_offset;
  }assert.fail('paging failed to terminate');
}
test('small results preserve exact object and fields',()=>{
  const r=result('ok',{isError:false,_meta:{source:'backend'}});assert.equal(make().project(r),r);
});
test('large results are bounded and reconstruct byte-exactly',()=>{
  const p=make(),r=result('BEGIN\n'+'x'.repeat(85000)+'\nEND',{_meta:{ref:'exact'}});
  const out=p.project(r,{toolName:'read_process_output'});assert.ok(size(out)<=2048);
  assert.equal(body(out).source_tool,'read_process_output');assert.deepEqual(reconstruct(p,body(out)),r);
});
test('Unicode and JSON escaping count serialized payload bytes',()=>{
  const p=make(),r=result(('🧠漢字\n\t\\\"\u0000').repeat(1300)),out=p.project(r);
  assert.ok(size(out)<=2048);assert.deepEqual(reconstruct(p,body(out)),r);
});
test('backend error truth and tail failures survive paging',()=>{
  const p=make(),r=result('log'.repeat(8000)+'\nFAIL: exit 17',{isError:true}),out=p.project(r);
  assert.equal(out.isError,true);assert.equal(body(out).backend_is_error,true);
  assert.match(body(out).preview.tail,/FAIL: exit 17/);assert.deepEqual(reconstruct(p,body(out)),r);
});
test('reading pages cannot call or retry the backend',()=>{
  let calls=0;const backend=()=>{calls++;return result('x'.repeat(5000));};const p=make();
  const id=body(p.project(backend())).receipt_id;for(let i=0;i<3;i++)p.read({receipt_id:id,offset:0});assert.equal(calls,1);
});
test('foreign owner cannot read another owner receipt',()=>{
  const a=make(),b=make(),id=body(a.project(result('private'.repeat(2000)))).receipt_id;
  const out=b.read({receipt_id:id,offset:0});assert.equal(out.isError,true);
  assert.equal(body(out).status,'OUTPUT_NOT_AVAILABLE');assert.doesNotMatch(JSON.stringify(out),/private/);
});
test('entry ceiling evicts oldest without replay',()=>{
  const p=make({maxEntries:2}),ids=Array.from({length:3},(_,i)=>body(p.project(result(String(i).repeat(5000)))).receipt_id);
  assert.equal(p.size,2);assert.equal(body(p.read({receipt_id:ids[0],offset:0})).status,'OUTPUT_NOT_AVAILABLE');
  assert.equal(body(p.read({receipt_id:ids[2],offset:0})).status,'OUTPUT_PAGE');
});
test('aggregate byte ceiling is enforced',()=>{
  const p=make({retainedBytes:12000});for(let i=0;i<4;i++)p.project(result('x'.repeat(5000)));
  assert.ok(p.retainedBytes<=12000);assert.equal(p.size,2);
});
test('unretainable output has no invented receipt or false tool verdict',()=>{
  const p=make({retainedBytes:4096}),out=p.project(result('x'.repeat(10000),{isError:false}));
  assert.ok(size(out)<=2048);assert.equal(body(out).status,'OUTPUT_NOT_RETAINED');
  assert.equal(body(out).receipt_id,undefined);assert.equal(out.isError,false);assert.equal(p.size,0);
  assert.match(body(out).notice,/[Nn]ever repeat/);
});
test('owner closure clears bytes and forbids late-result retention',()=>{
  const p=make(),id=body(p.project(result('x'.repeat(5000)))).receipt_id;p.clear();p.clear();
  assert.equal(p.size,0);assert.equal(p.retainedBytes,0);
  assert.equal(body(p.read({receipt_id:id,offset:0})).status,'OUTPUT_NOT_AVAILABLE');
  assert.equal(body(p.project(result('x'.repeat(5000)))).status,'OUTPUT_NOT_RETAINED');
});
test('native and mixed media pass through unchanged',()=>{
  const p=make(),image={content:[{type:'image',mimeType:'image/png',data:'a'.repeat(10000)}]};
  assert.equal(p.project(image),image);const mixed={content:[...result('x'.repeat(5000)).content,...image.content]};
  assert.equal(p.project(mixed),mixed);
});
test('strict output schema is not rewritten',()=>{
  const r=result('x'.repeat(5000),{structuredContent:{value:'y'.repeat(5000)}});
  assert.equal(make().project(r,{hasOutputSchema:true}),r);
});
test('untyped structured duplication is retained once and reconstructs',()=>{
  const p=make(),r=result('x'.repeat(5000),{structuredContent:{value:'x'.repeat(5000)}}),out=p.project(r);
  assert.equal(out.structuredContent,undefined);assert.deepEqual(reconstruct(p,body(out)),r);
});
test('invalid arguments fail closed without leaking supplied fields',()=>{
  const p=make();for(const a of [null,[],{},{receipt_id:'../../secret',offset:0},{receipt_id:'a'.repeat(100000),offset:0},
    {receipt_id:'0'.repeat(36),offset:-1},{receipt_id:'0'.repeat(36),offset:0.5},{receipt_id:'0'.repeat(36),offset:0,command:'not executed'}]){
    const out=p.read(a);assert.equal(out.isError,true);assert.ok(size(out)<=2048);assert.doesNotMatch(JSON.stringify(out),/secret|not executed/);}
});
test('UTF-8 interior and out-of-range offsets are refused',()=>{
  const p=make(),r=result('🧠'.repeat(2000)),receipt=body(p.project(r)),raw=Buffer.from(JSON.stringify(r));
  const interior=raw.findIndex(x=>(x&0xc0)===0x80);
  for(const offset of [interior,raw.length+1,Number.MAX_SAFE_INTEGER])assert.equal(p.read({receipt_id:receipt.receipt_id,offset}).isError,true);
});
test('repeat page reads are identical and do not increase memory',()=>{
  const p=make(),id=body(p.project(result('x'.repeat(5000)))).receipt_id,before=p.retainedBytes,args={receipt_id:id,offset:0};
  assert.deepEqual(p.read(args),p.read(args));assert.equal(p.retainedBytes,before);
});
test('invalid budgets cannot disable bounds',()=>{
  for(const options of [{responseBytes:0},{responseBytes:Infinity},{responseBytes:1e9},{maxEntries:0},{retainedBytes:-1},{responseBytes:'2048'}]){
    assert.throws(()=>new TextOutputPager(options),/budget/i);}
});
test('paging tool accepts no commands or paths and is read-only',()=>{
  assert.equal(OUTPUT_PAGE_TOOL.annotations.readOnlyHint,true);assert.equal(OUTPUT_PAGE_TOOL.annotations.destructiveHint,false);
  assert.equal(OUTPUT_PAGE_TOOL.inputSchema.additionalProperties,false);
  assert.deepEqual(Object.keys(OUTPUT_PAGE_TOOL.inputSchema.properties).sort(),['offset','receipt_id']);
});
