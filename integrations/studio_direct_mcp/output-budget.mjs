/** Bounded text-result projection attached to the existing backend owner.
 * No disk, transcript, scheduler, backend call, retry, or execution authority.
 */
import { createHash, randomUUID } from 'node:crypto';
export const DEFAULT_OUTPUT_BUDGET = Object.freeze({responseBytes:16384,retainedBytes:8388608,maxEntries:8});
export const OUTPUT_COMPAT_READ_PREFIX='studio-output://receipt/';
export const OUTPUT_PAGE_TOOL = Object.freeze({
  name:'studio_output_page', title:'Read retained Studio output',
  description:'Read a bounded UTF-8 page of an already-returned result using receipt_id and next_offset. This is a local receipt read and does not invoke the original tool. Receipts expire with their existing backend owner or bounded eviction. An unavailable receipt provides no evidence about the effect of the original call.',
  inputSchema:{type:'object',properties:{receipt_id:{type:'string',minLength:36,maxLength:36,pattern:'^[0-9a-f-]{36}$'},offset:{type:'integer',minimum:0,maximum:Number.MAX_SAFE_INTEGER}},required:['receipt_id','offset'],additionalProperties:false},
  annotations:{title:'Read retained Studio output',readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:false},
  _meta:{'private-studio-mcp/gateway':true},
});
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const PREVIEW_CHARS=256;
const wireBytes=value=>Buffer.byteLength(JSON.stringify(value),'utf8');
const toolResult=(data,isError)=>({content:[{type:'text',text:JSON.stringify(data)}],...(typeof isError==='boolean'?{isError}:{})});
const errorResult=status=>toolResult({status,notice:'No backend call was made. Receipt unavailability does not establish the original effect; the original source or effect remains unresolved.'},true);
export class TextOutputPager {
  #entries=new Map(); #bytes=0; #closed=false;
  constructor(options={}) {
    this.limits=Object.freeze({...DEFAULT_OUTPUT_BUDGET,...options});
    const {responseBytes,retainedBytes,maxEntries}=this.limits;
    if(!Number.isSafeInteger(responseBytes)||responseBytes<1024||responseBytes>65536||
       !Number.isSafeInteger(retainedBytes)||retainedBytes<responseBytes||retainedBytes>67108864||
       !Number.isSafeInteger(maxEntries)||maxEntries<1||maxEntries>64) throw new RangeError('Invalid output budget');
  }
  get retainedBytes(){return this.#bytes;}
  get size(){return this.#entries.size;}
  project(result,{toolName='unknown',hasOutputSchema=false}={}) {
    if(!result||typeof result!=='object'||hasOutputSchema||!Array.isArray(result.content)||!result.content.length||
       !result.content.every(item=>item?.type==='text'&&typeof item.text==='string')) return result;
    // JSON-RPC result bytes only. Never retain request arguments or log bodies.
    const raw=Buffer.from(JSON.stringify(result),'utf8');
    if(raw.length<=this.limits.responseBytes)return result;
    const sha256=createHash('sha256').update(raw).digest('hex');
    const retained=!this.#closed&&raw.length<=this.limits.retainedBytes;
    const receiptId=retained?randomUUID():undefined;
    if(retained){
      while(this.#entries.size>=this.limits.maxEntries||this.#bytes+raw.length>this.limits.retainedBytes){
        const oldest=this.#entries.keys().next().value;
        this.#bytes-=this.#entries.get(oldest).raw.length;this.#entries.delete(oldest);
      }
      this.#entries.set(receiptId,{raw,sha256});this.#bytes+=raw.length;
    }
    const data={status:retained?'OUTPUT_PAGED':'OUTPUT_NOT_RETAINED',
      ...(retained?{receipt_id:receiptId,read_tool:OUTPUT_PAGE_TOOL.name,next_offset:0,
        compat_read_tool:'read_file',compat_read_path:OUTPUT_COMPAT_READ_PREFIX+receiptId,
        compat_offset_argument:'offset'}:{}),
      source_tool:typeof toolName==='string'&&/^[A-Za-z0-9_.-]{1,64}$/.test(toolName)?toolName:'unknown',source_bytes:raw.length,sha256,
      backend_is_error:typeof result.isError==='boolean'?result.isError:null,
      retention:'existing_backend_owner_bounded_memory',
      preview:{head:result.content[0].text.slice(0,PREVIEW_CHARS),tail:result.content.at(-1).text.slice(-PREVIEW_CHARS)},
      notice:retained?
        'Output projection only, not an execution verdict. Retained pages expose result content without re-executing the original action; previews omit content. Receipt may expire with owner closure or eviction. If a frozen app snapshot does not expose studio_output_page, call read_file with compat_read_path and offset=next_offset; this reads the same retained bytes and never invokes the original source tool.':
        'Backend response received, but full output exceeds retention or its owner is closed. No full-result receipt exists. Output retention provides no re-execution authority; the original source or effect remains authoritative.'};
    let response=toolResult(data,result.isError);
    while(wireBytes(response)>this.limits.responseBytes&&(data.preview.head.length||data.preview.tail.length)){
      data.preview.head=data.preview.head.slice(0,Math.floor(data.preview.head.length/2));
      data.preview.tail=data.preview.tail.slice(Math.ceil(data.preview.tail.length/2));
      response=toolResult(data,result.isError);
    }
    return response;
  }
  readCompat(args){
    if(!args||typeof args!=='object'||Array.isArray(args)||
       typeof args.path!=='string'||!args.path.startsWith(OUTPUT_COMPAT_READ_PREFIX)||
       args.isUrl===true||
       Object.keys(args).some(k=>!['path','isUrl','offset','length','origin'].includes(k))||
       (args.offset!==undefined&&(!Number.isSafeInteger(args.offset)||args.offset<0))||
       (args.length!==undefined&&(!Number.isSafeInteger(args.length)||args.length<1))||
       (args.origin!==undefined&&args.origin!=='llm'&&args.origin!=='ui'))
      return errorResult('OUTPUT_PAGE_ARGUMENT_INVALID');
    const receiptId=args.path.slice(OUTPUT_COMPAT_READ_PREFIX.length);
    return this.read({receipt_id:receiptId,offset:args.offset??0});
  }
  read(args){
    if(!args||typeof args!=='object'||Array.isArray(args)||Object.keys(args).some(k=>k!=='receipt_id'&&k!=='offset')||
       typeof args.receipt_id!=='string'||!UUID.test(args.receipt_id)||!Number.isSafeInteger(args.offset)||args.offset<0)
      return errorResult('OUTPUT_PAGE_ARGUMENT_INVALID');
    const entry=this.#entries.get(args.receipt_id);
    if(!entry||this.#closed)return errorResult('OUTPUT_NOT_AVAILABLE');
    const {raw,sha256}=entry;const offset=args.offset;
    if(offset>raw.length||(offset<raw.length&&(raw[offset]&0xc0)===0x80))return errorResult('OUTPUT_PAGE_OFFSET_INVALID');
    const boundary=end=>{while(end>offset&&end<raw.length&&(raw[end]&0xc0)===0x80)end--;return end;};
    const makePage=end=>toolResult({status:'OUTPUT_PAGE',receipt_id:args.receipt_id,encoding:'utf-8',sha256,
      source_bytes:raw.length,offset,next_offset:end,done:end===raw.length,text:raw.toString('utf8',offset,end)},false);
    // Bound actual serialized tool-result bytes, including JSON-in-JSON escaping.
    let low=offset,high=Math.min(raw.length,offset+this.limits.responseBytes),best=offset;
    while(low<=high){const mid=Math.floor((low+high)/2),end=boundary(mid);
      if(wireBytes(makePage(end))<=this.limits.responseBytes){best=Math.max(best,end);low=mid+1;}else high=mid-1;}
    if(best===offset&&offset<raw.length)return errorResult('OUTPUT_PAGE_BUDGET_INVALID');
    return makePage(best);
  }
  clear(){this.#entries.clear();this.#bytes=0;this.#closed=true;}
}

/** Projection errors are not backend execution errors. Never route them into
 * timeout/taint handling or repeat a call whose backend response was received.
 */
export function projectOutputSafely(pager, result, options) {
  try {
    return pager.project(result, options);
  } catch {
    return toolResult({
      status: 'OUTPUT_PROJECTION_FAILED',
      backend_result_received: true,
      backend_is_error: typeof result?.isError === 'boolean' ? result.isError : null,
      notice: 'The backend already replied, but its output projection failed. No output receipt is available. Projection failure provides no re-execution authority; the original source or effect remains authoritative. This is not an execution verdict.',
    }, typeof result?.isError === 'boolean' ? result.isError : undefined);
  }
}
