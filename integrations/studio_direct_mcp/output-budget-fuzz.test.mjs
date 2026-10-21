import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {TextOutputPager, projectOutputSafely} from './output-budget.mjs';
const bytes=x=>Buffer.byteLength(JSON.stringify(x));
const body=x=>JSON.parse(x.content[0].text);
const sample=(text,extra={})=>({content:[{type:'text',text}],...extra});
const alphabet=['a','漢','🧠','\u0000','\n','\t','\\','"','\ud800','\u2028'];
let seed=178968;
function next(){seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;}

test('deterministic adversarial corpus preserves bytes and every response ceiling',()=>{
  for(let i=0;i<64;i++){
    const limit=[1024,2048,4096,16384][i%4];
    let text='';for(let n=0;n<1200+(i*31);n++)text+=alphabet[next()%alphabet.length];
    const original=sample(text,{isError:i%3===0,_meta:{case:i}});
    const pager=new TextOutputPager({responseBytes:limit});
    const receipt=pager.project(original,{toolName:i%2?'read_file':'\u0000'.repeat(64)});
    assert.ok(bytes(receipt)<=limit,`receipt case ${i}: ${bytes(receipt)} > ${limit}`);
    if(bytes(original)<=limit){assert.equal(receipt,original);continue;}
    const info=body(receipt);assert.equal(info.status,'OUTPUT_PAGED');
    let offset=0,joined='';
    for(let page=0;page<1000;page++){
      const response=pager.read({receipt_id:info.receipt_id,offset});
      assert.ok(bytes(response)<=limit,`page case ${i}`);const item=body(response);
      assert.equal(item.status,'OUTPUT_PAGE');joined+=item.text;
      if(item.done)break;assert.ok(item.next_offset>offset);offset=item.next_offset;
    }
    assert.equal(Buffer.byteLength(joined),info.source_bytes);
    assert.equal(createHash('sha256').update(joined).digest('hex'),info.sha256);
    assert.deepEqual(JSON.parse(joined),original);
  }
});

test('projection failure preserves each backend error truth and exposes no exception',()=>{
  const broken={project(){throw new Error('sensitive stack or filesystem path');}};
  for(const isError of [true,false,undefined]){
    const original=sample('sensitive result',isError===undefined?{}:{isError});
    const out=projectOutputSafely(broken,original,{});
    assert.equal(out.isError,isError);assert.equal(body(out).backend_result_received,true);
    assert.equal(body(out).status,'OUTPUT_PROJECTION_FAILED');
    assert.ok(bytes(out)<=1024);assert.doesNotMatch(JSON.stringify(out),/sensitive|NOT_APPLIED|EFFECT_UNKNOWN/);
  }
});

test('end-of-result page is bounded, empty and terminal',()=>{
  const pager=new TextOutputPager({responseBytes:1024});
  const info=body(pager.project(sample('x'.repeat(10000))));
  const out=pager.read({receipt_id:info.receipt_id,offset:info.source_bytes});
  assert.ok(bytes(out)<=1024);assert.equal(body(out).done,true);assert.equal(body(out).text,'');
});
