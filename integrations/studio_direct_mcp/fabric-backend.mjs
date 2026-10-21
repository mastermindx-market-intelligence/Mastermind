#!/usr/bin/env node
/**
 * Fabric-only MCP facade. Desktop Commander owns command processes; the installed
 * fabric_task.py owns composition of routing, admission, runs and retained results.
 * This file adds no scheduler, retry loop, durable run store, provider or auth plane.
 * Deploy behind the existing authenticated/privately enrolled Studio gateway.
 */
import { createHash, randomBytes } from 'node:crypto';
import { homedir } from 'node:os';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const VERSION = '0.2.0';
const ID_PATTERN = '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$';
const ID_RE = new RegExp(ID_PATTERN);
const MAX_RESPONSE_BYTES = 65536;
const MAX_PACKET_BYTES = 32768;
const MAX_CONTROLLERS = 512;
// Capture and hash the actual adapter stdout on M2, before a process transport can
// normalize text or paginate it. This is a fixed program; no caller code is used.
const CAPTURE_PROGRAM = `import base64,hashlib,json,subprocess,sys,tempfile
with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
 p=subprocess.run(sys.argv[1:],stdout=out,stderr=err)
 out.seek(0); data=out.read(131073)
 if len(data)>131072:
  print(json.dumps({'capture_error':'RESULT_RESPONSE_TOO_LARGE'}));sys.exit(0)
 print(json.dumps({'exit_code':p.returncode,'stdout_base64':base64.b64encode(data).decode('ascii'),'stdout_bytes':len(data),'stdout_sha256':hashlib.sha256(data).hexdigest()},separators=(',',':')))
`;
const CLASSES = ['mechanical', 'fix_build', 'review', 'census', 'audit'];
const COMPLEXITIES = ['C0_MECHANICAL', 'C1_ROUTINE_BOUNDED', 'C2_COMPLEX_BOUNDED', 'C3_FRONTIER_JUDGMENT'];
const DEFAULT_ADAPTER = resolve(homedir(), '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py');
const idSchema = { type: 'string', pattern: ID_PATTERN, minLength: 1, maxLength: 128 };
const identity = { run_id: idSchema, root_id: idSchema };
const maxBytes = { type: 'integer', minimum: 1024, maximum: MAX_RESPONSE_BYTES, default: 8192 };
function tool(name, description, properties, required, readOnly) {
  return Object.freeze({ name, description, inputSchema: { type:'object', properties, required, additionalProperties:false },
    annotations: { title:name.replaceAll('_',' '), readOnlyHint:readOnly, destructiveHint:false,
      idempotentHint:readOnly, openWorldHint:name === 'fabric_request' } });
}
export const FABRIC_TOOLS = Object.freeze([
  tool('fabric_capabilities', 'Read adapter availability and the fixed tool boundary. This does not dispatch, prove provider admission, or identify a ChatGPT user.', {}, [], true),
  tool('fabric_request', 'Submit a new bounded commission to the existing M2 Fabric adapter. The installed owner may use up to three immutable attempts after proven pre-task capacity rejection. Checks the exact origin run ID first. A returned controller PID does not prove worker START. Never replay an interrupted request or move an existing Executive operation here.', {
    ...identity, parent_id:idSchema, task_class:{type:'string',enum:CLASSES}, task_complexity:{type:'string',enum:COMPLEXITIES},
    work_packet:{type:'string',minLength:1,maxLength:16000}, escalation_reason:{type:'string',minLength:1,maxLength:1000},
    subject_pool:{type:'string',minLength:1,maxLength:64,pattern:'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$'},
  }, ['run_id','root_id','parent_id','task_class','task_complexity','work_packet'], false),
  tool('fabric_status', 'Read the requested commission and its actual successor through fabric_task.py. Earlier failed attempts remain visible. NOT_FOUND after a lost request is not proof of no effect or permission to retry. Root metadata is not authentication.', identity, ['run_id','root_id'], true),
  tool('fabric_wait', 'Use the incumbent adapter bounded wait for this run, at most ten seconds. Creates no watcher, retry loop, cancellation or background wake.', {...identity,timeout_seconds:{type:'integer',minimum:0,maximum:10,default:5}}, ['run_id','root_id'], true),
  tool('fabric_result', 'Retrieve the actual successor result only when available and the ledger root matches. Returns accept_run_id for exact reviewed-leaf acceptance. Returns a digest of the complete adapter response, not an artifact attestation. Does not accept the result.', {...identity,max_bytes:maxBytes}, ['run_id','root_id'], true),
  tool('fabric_accept', 'Record acceptance only after actual deterministic verification or authorized review. Re-reads the complete response and compares its digest first. Legacy ledger acceptance is not an atomic cryptographic attestation. Never retry an uncertain acceptance.', {
    ...identity, by:{type:'string',enum:['deterministic','reviewer']}, expected_response_sha256:{type:'string',pattern:'^[0-9a-f]{64}$'},
    verification_summary:{type:'string',minLength:1,maxLength:1000}, max_bytes:maxBytes,
  }, ['run_id','root_id','by','expected_response_sha256','verification_summary'], false),
  tool('fabric_controller_output', 'Read retained output from the exact Desktop Commander PID returned by this backend for this root and run. A new backend generation cannot recreate that binding. Never exposes an arbitrary process or starts another worker.', {
    ...identity, controller_pid:{type:'integer',minimum:1,maximum:2147483647}, offset:{type:'integer',minimum:0,maximum:1048576,default:0}, max_lines:{type:'integer',minimum:1,maximum:100,default:60},
  }, ['run_id','root_id','controller_pid'], true),
]);

class Refusal extends Error { constructor(code, details={}) { super(code); this.code=code; this.details=details; } }
const fail = (code, details) => { throw new Refusal(code, details); };
const hash = x => createHash('sha256').update(x).digest('hex');
export const shellQuote = value => "'" + String(value).replaceAll("'", "'\\''") + "'";
function validate(name, args) {
  const spec=FABRIC_TOOLS.find(t=>t.name===name); if (!spec) fail('UNKNOWN_TOOL');
  if (!args || typeof args!=='object' || Array.isArray(args)) fail('INVALID_ARGUMENT');
  for (const k of Object.keys(args)) if (!Object.hasOwn(spec.inputSchema.properties,k)) fail('INVALID_ARGUMENT',{field:k});
  for (const k of spec.inputSchema.required) if (!Object.hasOwn(args,k)) fail('INVALID_ARGUMENT',{field:k});
  for (const [k,v] of Object.entries(args)) {
    const s=spec.inputSchema.properties[k];
    if (s.type==='string' && (typeof v!=='string' || v.includes('\0') || (s.minLength && v.trim().length<s.minLength) || (s.maxLength && v.length>s.maxLength) || (s.pattern && !new RegExp(s.pattern).test(v)))) fail('INVALID_ARGUMENT',{field:k});
    if (s.type==='integer' && (!Number.isSafeInteger(v) || v<s.minimum || v>s.maximum)) fail('INVALID_ARGUMENT',{field:k});
    if (s.enum && !s.enum.includes(v)) fail('INVALID_ARGUMENT',{field:k});
  }
  if (name==='fabric_request') {
    if (Buffer.byteLength(args.work_packet)>MAX_PACKET_BYTES) fail('INVALID_ARGUMENT',{field:'work_packet'});
    if (args.task_complexity==='C3_FRONTIER_JUDGMENT' && !args.escalation_reason?.trim()) fail('INVALID_ARGUMENT',{field:'escalation_reason'});
  }
}
function response(value, isError=false) {
  const envelope={schema:'mastermind.fabric_mcp.v1',...value,retry_allowed:false};
  return {content:[{type:'text',text:JSON.stringify(envelope)}],structuredContent:envelope,...(isError?{isError:true}:{})};
}
function engineText(result) {
  if (!result || result.isError || !Array.isArray(result.content)) fail('PROCESS_TRANSPORT_ERROR');
  const items=result.content.filter(c=>c.type==='text' && typeof c.text==='string');
  if (!items.length) fail('PROCESS_TRANSPORT_ERROR');
  return items.map(c=>c.text).join('\n');
}
function processPid(text) {
  const match=text.match(/^Process started with PID ([1-9]\d*) \(shell: [^\r\n]+\)(?:\r?\n|$)/);
  if(!match) return null;
  const pid=Number(match[1]);
  return Number.isSafeInteger(pid) && pid>0 ? pid : null;
}
function completedOutput(text) {
  const startToken='MMX_FABRIC_BEGIN\n';
  let start=text.indexOf(startToken);
  if (start>=0) start+=startToken.length;
  else { const legacy='Initial output:\n'; start=text.indexOf(legacy); if(start>=0) start+=legacy.length; }
  const finish=text.lastIndexOf('\nMMX_FABRIC_EXIT=');
  if (start<0 || finish<start) return null;
  const match=text.slice(finish).match(/^\nMMX_FABRIC_EXIT=(\d+)(?:\r?\n|$)/);
  if (!match) return null;
  return {stdout:text.slice(start,finish),exit_code:Number(match[1])};
}
function decodeCapturedEnvelope(envelopeText) {
  // Validate ONE complete capture envelope produced by the fixed CAPTURE_PROGRAM
  // wrapper. The envelope carries the original child adapter exit code and the
  // exact verified stdout bytes (base64 + byte count + sha256 + canonical
  // base64 round-trip + strict UTF-8). Returns null on any malformed,
  // truncated, oversized or mismatched framing. capture_error is surfaced via
  // the sole fixed captureError variant; strict UTF-8 retains its existing
  // result diagnostic. No transport-selected error code is reflected.
  let envelope;
  try { envelope = JSON.parse(envelopeText); } catch { return null; }
  if (!envelope || typeof envelope !== 'object' || Array.isArray(envelope)) return null;
  if (Object.hasOwn(envelope, 'capture_error')) {
    if (Object.keys(envelope).length !== 1
        || envelope.capture_error !== 'RESULT_RESPONSE_TOO_LARGE') return null;
    return { captureError: 'RESULT_RESPONSE_TOO_LARGE' };
  }
  if (Object.keys(envelope).length !== 4
      || !Number.isSafeInteger(envelope.exit_code)
      || envelope.exit_code < -255 || envelope.exit_code > 255
      || typeof envelope.stdout_base64 !== 'string'
      || !/^[A-Za-z0-9+/]*={0,2}$/.test(envelope.stdout_base64)
      || !Number.isSafeInteger(envelope.stdout_bytes) || envelope.stdout_bytes < 0
      || envelope.stdout_bytes > MAX_RESPONSE_BYTES * 2) return null;
  const bytes = Buffer.from(envelope.stdout_base64, 'base64');
  if (bytes.length !== envelope.stdout_bytes
      || hash(bytes) !== envelope.stdout_sha256
      || bytes.toString('base64') !== envelope.stdout_base64) return null;
  let stdoutText;
  try { stdoutText = new TextDecoder('utf-8', {fatal: true}).decode(bytes); } catch { return {decodeError: 'RESULT_NOT_UTF8'}; }
  return { exit_code: envelope.exit_code, stdout: stdoutText,
           stdout_sha256: envelope.stdout_sha256, stdout_bytes: envelope.stdout_bytes };
}
function statusJSON(result, runId, follow=false) {
  if (result.exit_code!==0) fail('ADAPTER_OBSERVATION_UNAVAILABLE',{adapter_exit_code:result.exit_code});
  let s; try{s=JSON.parse(result.stdout);}catch{fail('ADAPTER_STATUS_INVALID');}
  if(follow && s?.schema==='mastermind.fabric_continuation.v1') {
    if(s.requested_run_id!==runId || typeof s.effective_run_id!=='string' || !ID_RE.test(s.effective_run_id)
       || !Array.isArray(s.prior_attempts) || s.prior_attempts.length>2
       || !['NOT_APPLICABLE','UNCONFIRMED','RECORDED'].includes(s.controller_return)) fail('ADAPTER_CONTINUATION_INVALID');
    const effective=statusJSON({exit_code:0,stdout:JSON.stringify(s.effective_status)},s.effective_run_id);
    return {...effective,continuation:{requested_run_id:runId,effective_run_id:s.effective_run_id,
      prior_attempts:s.prior_attempts,controller_return:s.controller_return,controller_reason:s.controller_reason??null}};
  }
  if (!s || s.schema!=='mastermind.fabric_task_status.v1' || s.run_id!==runId || typeof s.state!=='string' || typeof s.result_available!=='boolean') fail('ADAPTER_STATUS_INVALID');
  return s;
}
function checkRoot(s, args, strict=false) {
  if (s.root_id && s.root_id!==args.root_id) fail('ROOT_MISMATCH');
  if (strict && s.root_id!==args.root_id) fail('ROOT_UNVERIFIED');
}
function resultReady(s,args) {
  checkRoot(s,args,true);
  if(s.state==='EFFECT_UNKNOWN') fail('EFFECT_UNKNOWN');
  if(!s.result_available) fail('RESULT_UNAVAILABLE');
  if(!Number.isSafeInteger(s.result_bytes) || s.result_bytes<0) fail('RESULT_SIZE_UNVERIFIED');
  if(s.result_bytes>(args.max_bytes??8192)) fail('RESULT_TOO_LARGE',{result_bytes:s.result_bytes,max_bytes:args.max_bytes??8192});
}

export function createFabricFacade(engine, options={}) {
  const cfg={adapterPath:DEFAULT_ADAPTER,python:'python3',workerCwd:'~',quotaFallback:false,...options};
  if(!isAbsolute(cfg.adapterPath) || cfg.adapterPath.includes('\0') || typeof cfg.python!=='string' || !cfg.python || cfg.python.includes('\0') || typeof cfg.workerCwd!=='string' || !cfg.workerCwd || cfg.workerCwd.includes('\0')) throw new TypeError('invalid operator configuration');
  // This index only fences returned incumbent process handles. It has no run state,
  // admission, scheduling or retry authority and is never persisted or reconstructed.
  const controllers=new Map();
  const attempted=new Set(); // bounded frontend anti-replay, not a run ledger
  function command(argv, packet, capture=false) {
    const prefix=capture?[cfg.python,'-c',CAPTURE_PROGRAM,cfg.python,cfg.adapterPath]:[cfg.python,cfg.adapterPath];
    let c=[...prefix,...argv].map(shellQuote).join(' ');
    if(packet!==undefined) {
      let marker; do{marker='MMX_FABRIC_PACKET_'+randomBytes(12).toString('hex');}while(packet.split('\n').includes(marker));
      c+=` <<'${marker}'\n${packet}\n${marker}\n`;
    } else c+='\n';
    return `printf '%s\\n' 'MMX_FABRIC_BEGIN'\n${c}mmx_fabric_rc=$?\nprintf '\\nMMX_FABRIC_EXIT=%s\\n' "$mmx_fabric_rc"`;
  }
  async function runShort(argv, timeoutMs=10000, capture=false) {
    const raw=await engine.callTool({name:'start_process',arguments:{command:command(argv,undefined,capture),timeout_ms:timeoutMs}});
    let text=engineText(raw), parsed=completedOutput(text); const pid=processPid(text);
    if(!parsed && pid) {
      // One bounded read of the same incumbent handle, never another command.
      const read=await engine.callTool({name:'read_process_output',arguments:{pid,timeout_ms:1000,offset:0,length:200}});
      text=engineText(read); parsed=completedOutput(text);
    }
    if(!parsed) fail('OBSERVATION_INCOMPLETE',{controller_pid:pid});
    return parsed;
  }
  // Reusable captured-short helper for adapter commands whose output the
  // facade must interpret (status, wait, accept completion/readback,
  // capabilities/help). Reuses the fixed CAPTURE_PROGRAM and validates ONE
  // complete capture envelope. Outer wrapper success is required; the
  // returned exit_code is the ORIGINAL child adapter exit code and the
  // stdout is the exact verified bytes (no reserialization, no stderr use).
  async function runCapturedShort(argv, timeoutMs=10000) {
    const parsed=await runShort(argv,timeoutMs,true);
    if(parsed.exit_code!==0) fail('CAPTURE_INVALID');
    const decoded=decodeCapturedEnvelope(parsed.stdout);
    if(!decoded || decoded.captureError || decoded.decodeError) fail('CAPTURE_INVALID');
    return {exit_code:decoded.exit_code,stdout:decoded.stdout};
  }
  async function continuityAvailable() {
    if(!cfg.quotaFallback) return false;
    const requestHelp=await runCapturedShort(['request','--help']);
    const statusHelp=await runCapturedShort(['status','--help']);
    return requestHelp.exit_code===0 && statusHelp.exit_code===0 &&
      requestHelp.stdout.includes('--quota-fallback') && statusHelp.stdout.includes('--follow');
  }
  async function status(args,follow=cfg.quotaFallback) {
    const s=statusJSON(await runCapturedShort(['status',args.run_id,...(follow?['--follow']:[])]),args.run_id,follow);
    checkRoot(s,args);return s;
  }
  async function retained(args,s) {
    if(s.continuation?.controller_return==='UNCONFIRMED') fail('CONTROLLER_RETURN_UNCONFIRMED',{effective_run_id:s.run_id});
    resultReady(s,args);
    const r=await runShort(['result',s.run_id,'--max-bytes',String(args.max_bytes??8192)],10000,true);
    if(r.exit_code!==0) fail('RESULT_UNAVAILABLE',{adapter_exit_code:r.exit_code});
    const decoded=decodeCapturedEnvelope(r.stdout);
    if(!decoded) fail('RESULT_TRANSFER_INVALID');
    if(decoded.captureError) fail('RESULT_RESPONSE_TOO_LARGE');
    if(decoded.decodeError) fail('RESULT_NOT_UTF8');
    if(decoded.exit_code!==0) fail('RESULT_UNAVAILABLE',{adapter_exit_code:decoded.exit_code});
    return {adapter_response:decoded.stdout,response_sha256:decoded.stdout_sha256,response_bytes:decoded.stdout_bytes};
  }
  return { async call(name,args={}) {
    let effectStarted=false;
    try {
      validate(name,args);
      if(name==='fabric_capabilities') {
        const h=await runCapturedShort(['--help']);
        const continuity=await continuityAvailable();
        return response({action:'capabilities',adapter_available:h.exit_code===0 && ['request','status','result','accept'].every(x=>h.stdout.includes(x)),
          quota_continuity:{enabled:cfg.quotaFallback,adapter_available:continuity,max_attempts:3,
            replay_basis:'pre_task_capacity_rejection',mid_task_replay:false,native_parent_wake:false,background_execution:false},
          worker_admission:'UNPROBED',worker_start:'UNPROBED',backend:'existing Desktop Commander process owner',
          tools:FABRIC_TOOLS.map(t=>t.name),caller_identity:'trusted enrolled channel; not individual ChatGPT identity',root_metadata_is_authentication:false});
      }
      if(name==='fabric_controller_output') {
        const binding=controllers.get(args.controller_pid);
        if(!binding || binding.run_id!==args.run_id || binding.root_id!==args.root_id) fail('CONTROLLER_NOT_BOUND');
        const raw=await engine.callTool({name:'read_process_output',arguments:{pid:args.controller_pid,timeout_ms:1000,offset:args.offset??0,length:args.max_lines??60}});
        return response({action:name,...args,process_output:raw,execution_absence_proven:false});
      }
      if(name==='fabric_request') {
        const requestKey=args.run_id;
        if(attempted.has(requestKey)) fail('REQUEST_ALREADY_ATTEMPTED');
        if(attempted.size>=MAX_CONTROLLERS) fail('CONTROLLER_TRACKING_CAPACITY');
        if(cfg.quotaFallback && !await continuityAvailable()) fail('ADAPTER_CONTINUITY_UNAVAILABLE');
        const s=await status(args,false);
        if(s.state!=='NOT_FOUND') fail(s.state==='EFFECT_UNKNOWN'?'EFFECT_UNKNOWN':'RUN_EXISTS');
        const argv=['request','--id',args.run_id,'--class',args.task_class,'--task-complexity',args.task_complexity,'--cwd',cfg.workerCwd,'--root',args.root_id,'--parent',args.parent_id,'--stdin'];
        if(cfg.quotaFallback) argv.push('--quota-fallback');
        if(args.escalation_reason) argv.push('--escalation-reason',args.escalation_reason);
        if(args.subject_pool) argv.push('--subject-pool',args.subject_pool);
        if(attempted.has(requestKey)) fail('REQUEST_ALREADY_ATTEMPTED');
        attempted.add(requestKey);
        effectStarted=true;
        const raw=await engine.callTool({name:'start_process',arguments:{command:command(argv,args.work_packet),timeout_ms:1000}});
        const text=engineText(raw),pid=processPid(text);
        if(!pid) fail('EFFECT_UNKNOWN');
        controllers.set(pid,{run_id:args.run_id,root_id:args.root_id});
        const settled=completedOutput(text);
        return response({action:name,run_id:args.run_id,root_id:args.root_id,parent_id:args.parent_id,controller_pid:pid,
          delivery:'CONTROLLER_CREATED',worker_started:null,worker_start_proven:false,
          adapter_exit_code:settled?.exit_code??null,execution_absence_proven:false,
          next_observation:'fabric_status with the same run and root; fabric_controller_output with this PID when needed'});
      }
      const s=await status(args);
      if(name==='fabric_status') return response({action:name,run_id:args.run_id,effective_run_id:s.run_id,expected_root_id:args.root_id,status:s,root_verified:s.root_id===args.root_id,execution_absence_proven:false});
      if(name==='fabric_wait') {
        const seconds=args.timeout_seconds??5;
        const waited=statusJSON(await runCapturedShort(['wait',args.run_id,'--timeout',String(seconds),'--interval','2',...(cfg.quotaFallback?['--follow']:[])],Math.min(12000,(seconds+2)*1000)),args.run_id,cfg.quotaFallback);
        checkRoot(waited,args);
        return response({action:name,run_id:args.run_id,effective_run_id:waited.run_id,status:waited,root_verified:waited.root_id===args.root_id,execution_absence_proven:false});
      }
      if(name==='fabric_accept' && s.accepted===true) fail('ALREADY_ACCEPTED');
      if(name==='fabric_accept' && s.run_id!==args.run_id) fail('ACCEPT_EXPLICIT_SUCCESSOR_REQUIRED',{effective_run_id:s.run_id});
      const data=await retained(args,s);
      if(name==='fabric_result') return response({action:name,run_id:args.run_id,effective_run_id:s.run_id,accept_run_id:s.run_id,root_id:args.root_id,...data,accepted:s.accepted===true,
        digest_scope:'exact complete adapter CLI response; not a cryptographic artifact attestation'});
      if(data.response_sha256!==args.expected_response_sha256) fail('RESULT_CHANGED',{current_response_sha256:data.response_sha256});
      effectStarted=true;
      const accepted=await runCapturedShort(['accept',args.run_id,'--by',args.by]);
      if(accepted.exit_code!==0) fail('ACCEPTANCE_UNCONFIRMED',{adapter_exit_code:accepted.exit_code});
      const after=await status(args);
      if(after.accepted!==true) fail('ACCEPTANCE_UNCONFIRMED');
      return response({action:name,run_id:args.run_id,root_id:args.root_id,accepted:true,accepted_by:after.accepted_by,
        reviewed_response_sha256:data.response_sha256,verification_summary:args.verification_summary,
        legacy_acceptance_not_atomic_attestation:true});
    } catch(error) {
      const code=effectStarted ? 'EFFECT_UNKNOWN' : (error instanceof Refusal?error.code:'ADAPTER_OBSERVATION_UNAVAILABLE');
      return response({action:name,...(args && typeof args==='object'?{run_id:args.run_id,root_id:args.root_id}:{}),error:code,
        ...(error instanceof Refusal?error.details:{}),execution_absence_proven:false},true);
    }
  }};
}

async function main() {
  // Dependencies come from this release's pinned package lock. Never install on call.
  const sdkPackage=process.env.MMX_FABRIC_SDK_PACKAGE;
  if(sdkPackage && (!isAbsolute(sdkPackage) || sdkPackage.includes('\0'))) throw new Error('SDK_PACKAGE_MUST_BE_ABSOLUTE');
  const require=createRequire(sdkPackage??import.meta.url);
  const {Server}=require('@modelcontextprotocol/sdk/server/index.js');
  const {Client}=require('@modelcontextprotocol/sdk/client/index.js');
  const {StdioServerTransport}=require('@modelcontextprotocol/sdk/server/stdio.js');
  const {StdioClientTransport}=require('@modelcontextprotocol/sdk/client/stdio.js');
  const {ListToolsRequestSchema,CallToolRequestSchema}=require('@modelcontextprotocol/sdk/types.js');
  const engineEntry=process.env.MMX_FABRIC_ENGINE_ENTRY??resolve(homedir(),'.local/share/desktop-commander-service/vendor/node_modules/@wonderwhy-er/desktop-commander/dist/index.js');
  if(!isAbsolute(engineEntry)) throw new Error('ENGINE_ENTRY_MUST_BE_ABSOLUTE');
  const engine=new Client({name:'mastermind-fabric-process-transport',version:VERSION},{capabilities:{}});
  await engine.connect(new StdioClientTransport({command:process.execPath,args:[engineEntry],cwd:homedir(),env:{...process.env},stderr:'inherit'}));
  const facade=createFabricFacade(engine,{adapterPath:process.env.MMX_FABRIC_ADAPTER_PATH??DEFAULT_ADAPTER,python:process.env.MMX_FABRIC_PYTHON??'python3',workerCwd:process.env.MMX_FABRIC_WORKER_CWD??'~',quotaFallback:true});
  const server=new Server({name:'mastermind-subagent-fabric',version:VERSION},{capabilities:{tools:{}}});
  server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:FABRIC_TOOLS}));
  server.setRequestHandler(CallToolRequestSchema,async req=>facade.call(req.params.name,req.params.arguments??{}));
  await server.connect(new StdioServerTransport());
  let closing=false;
  const close=async()=>{if(closing)return;closing=true;await server.close();await engine.close();};
  process.once('SIGTERM',()=>close().finally(()=>process.exit(0)));
  process.once('SIGINT',()=>close().finally(()=>process.exit(0)));
  process.stdin.once('end',()=>close().catch(()=>{}));
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  main().catch(()=>{process.stderr.write('FABRIC_MCP_STARTUP_FAILED\n');process.exitCode=1;});
}
