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
import {spawn} from 'node:child_process';
import {lstatSync,readFileSync,readdirSync,realpathSync} from 'node:fs';

// Native policy stays inside the incumbent sealed, standalone backend blob.
// Only explicit native mode reads the separately composed Hermes package.
const ENROLLMENT_SCHEMA='mastermind.hermes_native_enrollment.v1';
const NATIVE_ORIGIN_SCHEMA=Object.freeze({
  type:'object', additionalProperties:false,
  required:['schema','kind','profile_id','origin_session_id','session_id','generation',
    'turn_id','tool_call_id','task_key','tool_action','arguments_digest',
    'lease_holder_digest','enrollment_generation'],
  properties:Object.fromEntries(['schema','kind','profile_id','origin_session_id','session_id',
    'generation','turn_id','tool_call_id','task_key','tool_action','arguments_digest',
    'lease_holder_digest','enrollment_generation'].map(k=>[k,{type:'string',minLength:1,maxLength:256}])),
});
const NATIVE_PLUGIN='mastermind-fabric-worker';
const NATIVE_PLUGIN_SOURCE='https://github.com/mastermindx-market-intelligence/Mastermind.git#integrations/hermes_attended_fabric';
const NATIVE_PACKAGE_FILES=Object.freeze([
  '__init__.py','plugin.yaml','native.py','facade_port.py','hermes_mcp_client.py',
  'native_session.py','native_evidence.py','enrollment_check.py'].sort());
const NATIVE_HERMES_TOOLS=Object.freeze([
  'fabric_capabilities','fabric_request','fabric_status','fabric_result']);
const ACTIONS=new Set(NATIVE_HERMES_TOOLS.slice(1));

function ordinaryHermesWorkerEnvironment() {
  return (process.env.POOL_OPERATOR_CHILD_BUDGET??'0')==='0'
    && ['FABRIC_OPERATOR_CHILD_ID','FABRIC_OPERATOR_CAPSULE','FABRIC_OPERATOR_CAPABILITY',
      'FABRIC_OPERATOR_PRELEASE_CONTINUATION','FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION',
      'FABRIC_CANONICAL_PAID_MODE','FABRIC_CANONICAL_PAID_NONCE',
      'FABRIC_CANONICAL_PAID_PAYLOAD_SHA256','FABRIC_CANONICAL_PAID_HOST',
      'POOL_PRELEASE_HANDOFF'].every(k=>!process.env[k]);
}

function createHermesOriginAdmission(config=null) {
  if(config!==null && (typeof config!=='object' || Array.isArray(config)
      || Object.keys(config).sort().join(',')!=='home,packageSha256,python,revision,source'
      || ['home','python','source'].some(k=>typeof config[k]!=='string'
          || !isAbsolute(config[k]) || config[k].includes('\0'))
      || !/^[0-9a-f]{40}$/.test(config.revision??'')
      || !/^[0-9a-f]{64}$/.test(config.packageSha256??'')))
    throw new TypeError('invalid native Hermes enrollment configuration');
  if(config!==null && !ordinaryHermesWorkerEnvironment())
    throw new TypeError('native Hermes requires ordinary worker context');
  if(config!==null)config=Object.freeze({...config});
  const scoped=config!==null;
  function installedHelper() {
    if(!ordinaryHermesWorkerEnvironment())return null;
    try {
      const plugins=resolve(realpathSync(config.home),'plugins');
      const root=resolve(plugins,NATIVE_PLUGIN);
      if(!lstatSync(plugins).isDirectory() || !lstatSync(root).isDirectory())return null;
      if(readdirSync(root).some(n=>/\.(py|so|pyd)$/.test(n) && !NATIVE_PACKAGE_FILES.includes(n)))return null;
      const rows=NATIVE_PACKAGE_FILES.map(name=>{
        const path=resolve(root,name),st=lstatSync(path);
        if(!st.isFile() || st.size>2*1024*1024)throw new Error('package member unavailable');
        return [name,createHash('sha256').update(readFileSync(path)).digest('hex')];
      });
      if(createHash('sha256').update(JSON.stringify(rows)).digest('hex')!==config.packageSha256)return null;
      const record=resolve(plugins,'.install-metadata.json'),st=lstatSync(record);
      if(!st.isFile() || st.size>1024*1024)return null;
      const entry=JSON.parse(readFileSync(record,'utf8'))[NATIVE_PLUGIN];
      if(entry?.source!==NATIVE_PLUGIN_SOURCE || entry?.pinned!==true
          || entry?.revision!==config.revision)return null;
      return resolve(root,'enrollment_check.py');
    }catch{return null;}
  }
  async function check(action,args) {
    const checker=installedHelper();
    if(checker===null)return null;
    const payload=JSON.stringify({action,arguments:args});
    if(Buffer.byteLength(payload)>65536) return null;
    return await new Promise(resolve=>{
      let child,done=false,size=0;
      const chunks=[];
      const finish=value=>{
        if(done)return;
        done=true;clearTimeout(timer);resolve(value);
      };
      const timer=setTimeout(()=>{child?.kill('SIGKILL');finish(null);},10000);
      try {
        child=spawn(config.python,['-I','-B',checker,config.source,config.home,config.revision,config.packageSha256],{
          stdio:['pipe','pipe','ignore'],windowsHide:true,
          env:{PATH:process.env.PATH??'',PYTHONNOUSERSITE:'1'},
        });
        child.on('error',()=>finish(null));
        child.stdout.on('data',chunk=>{
          size+=chunk.length;
          if(size>32768){child.kill('SIGKILL');finish(null);}
          else chunks.push(chunk);
        });
        child.on('close',code=>{
          if(code!==0)return finish(null);
          try {
            const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));
            if(value?.schema!=='mastermind.hermes_origin_check.v1'
                || value.authorized!==true || value.contract?.schema!==ENROLLMENT_SCHEMA
                || value.contract.enabled!==true
                || value.contract.kind!=='hermes_attended_session'
                || value.contract.source_revision!==config.revision
                || value.contract.package_sha256!==config.packageSha256
                || installedHelper()!==checker
                || !/^[0-9a-f]{64}$/.test(value.contract.generation??'')) return finish(null);
            finish(value.contract);
          }catch{finish(null);}
        });
        child.stdin.on('error',()=>{child.kill('SIGKILL');finish(null);});
        child.stdin.end(payload);
      }catch{child?.kill('SIGKILL');finish(null);}
    });
  }
  return Object.freeze({
    scoped,
    async capabilities() {
      return scoped
        ? (await check('fabric_capabilities',{}))??{schema:ENROLLMENT_SCHEMA,enabled:false}
        : {schema:ENROLLMENT_SCHEMA,enabled:false};
    },
    async authorize(action,args) {
      if(!scoped)return args.native_origin===undefined;
      if(!ACTIONS.has(action) || !args.native_origin
          || typeof args.native_origin!=='object' || Array.isArray(args.native_origin))
        return false;
      return (await check(action,args))!==null;
    },
  });
}

const VERSION = '0.3.0';
const ID_PATTERN = '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$';
const ID_RE = new RegExp(ID_PATTERN);
const MAX_RESPONSE_BYTES = 65536;
const MAX_RETAINED_BYTES = 8_388_608; // incumbent adapter's fixed result ceiling
const MAX_PAGE_BYTES = 4096; // base64 plus duplicate MCP envelope fits the 16-KiB gateway budget
const MAX_PACKET_BYTES = 32768;
const MAX_CONTROLLERS = 512;
// Internal exact-ID history, not provider/task admission: at most 2 MiB of
// UTF-16 identity payload (8192 * 128 * 2), plus bounded Set overhead.
// Never evict an identity. A new process generation does not inherit this
// memory; the incumbent adapter remains the durable run/result owner.
const MAX_ATTEMPT_IDENTITIES = 8192;
const MAX_RETENTION_CANDIDATES = 4;
// Capture and hash the actual adapter stdout on M2, before a process transport can
// normalize text or paginate it. This is a fixed program; no caller code is used.
const CAPTURE_PROGRAM = `import base64,hashlib,json,re,subprocess,sys,tempfile
with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
 p=subprocess.run(sys.argv[1:],stdout=out,stderr=err)
 out.seek(0); data=out.read(131073)
 if len(data)>131072:
  print(json.dumps({'capture_error':'RESULT_RESPONSE_TOO_LARGE'}));sys.exit(0)
 reply={'exit_code':p.returncode,'stdout_base64':base64.b64encode(data).decode('ascii'),'stdout_bytes':len(data),'stdout_sha256':hashlib.sha256(data).hexdigest()}
 # Native read-only preview emits rc=75 and a policy refusal on stderr.
 # Never include raw stderr or any worker/request/result stderr in MCP.
 if p.returncode and len(sys.argv)>3 and sys.argv[3]=='preview' and not data:
  err.seek(0); line=err.read(128)
  match=re.fullmatch(rb'NONE reason=([a-z][a-z0-9_]{0,79})\\r?\\n?',line)
  if match: reply['native_reason']=match.group(1).decode('ascii')
  elif re.fullmatch(rb'NONE reason=pool (?:grok|glm|minimax|bailian|cursor|ocfree|go) has no eligible mode on requested host\\r?\\n?',line):
    reply['native_reason']='no_eligible_host'
 print(json.dumps(reply,separators=(',',':')))
`;
// Capture the *incumbent adapter's* bounded response into an ephemeral local file,
// hash and UTF-8 validate every byte, and return only one small page. No direct
// artifact-file access, alternate result store, or caller-supplied program/path.
const PAGE_CAPTURE_PROGRAM = `import base64,codecs,hashlib,json,subprocess,sys,tempfile
offset=int(sys.argv[1]); length=int(sys.argv[2])
with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
 p=subprocess.run(sys.argv[3:],stdout=out,stderr=err)
 if p.returncode:
  print(json.dumps({'exit_code':p.returncode},separators=(',',':')));sys.exit(0)
 out.seek(0); full=hashlib.sha256(); decode=codecs.getincrementaldecoder('utf-8')('strict'); count=0
 try:
  while True:
   part=out.read(65536)
   if not part: break
   count+=len(part)
   if count>8388608:
    print(json.dumps({'capture_error':'RESULT_RESPONSE_TOO_LARGE'}));sys.exit(0)
   full.update(part);decode.decode(part)
  decode.decode(b'',final=True)
 except UnicodeDecodeError:
  print(json.dumps({'capture_error':'RESULT_NOT_UTF8'}));sys.exit(0)
 out.seek(offset); page=out.read(length)
 print(json.dumps({'exit_code':0,'response_bytes':count,'response_sha256':full.hexdigest(),'offset':offset,'page_bytes':len(page),'page_sha256':hashlib.sha256(page).hexdigest(),'page_base64':base64.b64encode(page).decode('ascii')},separators=(',',':')))
`;
const CLASSES = ['mechanical', 'fix_build', 'review', 'census', 'audit'];
// Fixed evidence-basis codes prevent acceptance metadata from becoming a
// prompt or workflow-control channel. These labels do not prove the checks.
const ACCEPT_VERIFICATION_CODES = Object.freeze([
  'deterministic_test_evidence', 'artifact_digest_comparison',
  'manual_result_review', 'independent_review_evidence'
]);
const COMPLEXITIES = ['C0_MECHANICAL', 'C1_ROUTINE_BOUNDED', 'C2_COMPLEX_BOUNDED', 'C3_FRONTIER_JUDGMENT'];
const MANUAL_POOLS = ['grok', 'glm', 'minimax', 'bailian', 'cursor', 'ocfree', 'go', 'experiential'];
// Experiential uncensored pool: the exact slug is mandatory (never
// glm-5.3-flash-uncensored, auto or omitted) and the provider retains prompts
// and responses, so every request needs an explicit caller opt-in first.
const EXPERIENTIAL_POOL = 'experiential';
const EXPERIENTIAL_MODEL = 'glm-5.3-uncensored';
const DEFAULT_ADAPTER = resolve(homedir(), '.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/fabric_task.py');
const idSchema = { type: 'string', pattern: ID_PATTERN, minLength: 1, maxLength: 128 };
const identity = { run_id: idSchema, root_id: idSchema, native_origin:NATIVE_ORIGIN_SCHEMA };
const maxBytes = { type: 'integer', minimum: 1024, maximum: MAX_RESPONSE_BYTES, default: 8192 };
const pageBytes = { type:'integer', minimum:1, maximum:MAX_PAGE_BYTES, default:MAX_PAGE_BYTES };
const pageOffset = { type:'integer', minimum:0, maximum:MAX_RETAINED_BYTES, default:0 };
function tool(name, description, properties, required, readOnly) {
  return Object.freeze({ name, description, inputSchema: { type:'object', properties, required, additionalProperties:false },
    annotations: { title:name.replaceAll('_',' '), readOnlyHint:readOnly, destructiveHint:false,
      idempotentHint:readOnly, openWorldHint:name === 'fabric_request' } });
}
export const FABRIC_TOOLS = Object.freeze([
  tool('fabric_capabilities', 'Read adapter availability and the fixed tool boundary. This does not dispatch, prove provider admission, or identify a ChatGPT user.', {}, [], true),
  tool('fabric_request', 'Submit a new bounded commission to the existing M2 Fabric adapter. The installed owner may use up to three immutable attempts after proven pre-task capacity rejection. Checks the exact origin run ID first. A returned controller PID does not prove worker START. Native placement for complex C2 reviews may require a factual escalation_reason; preview refusals never authorize retry. Never replay an interrupted request or move an existing Executive operation here.', {
    ...identity, parent_id:idSchema, task_class:{type:'string',enum:CLASSES}, task_complexity:{type:'string',enum:COMPLEXITIES},
    max_turns:{type:'integer',minimum:1,maximum:400,description:'Optional per-request Claude turn ceiling. Only tightens the admitted wrapper limit; not a token, tool-call, dollar or acceptance budget.'},
    work_packet:{type:'string',minLength:1,maxLength:16000,description:'In human-readable brief prose, abbreviate SHA-256 file hashes and git commit IDs to their first ~12 hex characters. Preserve complete values in explicit machine-verification fields, code, or commands requiring exact identity. Packets are forwarded unchanged; no content scanner or secret/key rejection is added.'}, escalation_reason:{type:'string',minLength:1,maxLength:1000},
    subject_pool:{type:'string',minLength:1,maxLength:64,pattern:'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$'},
    pool:{type:'string',enum:MANUAL_POOLS,description:'Optional strict provider-pool pin; omitted means native AUTO. No cross-provider quota continuation. experiential additionally requires the exact model glm-5.3-uncensored and retention_opt_in:true on every request.'},
    model:{type:'string',minLength:1,maxLength:64,pattern:'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$',description:'Optional exact qualified model inside pool. Use auto to let the pinned pool choose its admitted model. pool experiential accepts only the exact glm-5.3-uncensored; auto and every other slug are refused before dispatch.'},
    retention_opt_in:{type:'boolean',description:'Experiential uncensored retains prompts and responses, including after storage settings are disabled. Required true for every explicit experiential manual request.'},
    sensitive_data_opt_in:{type:'boolean',description:'Explicit approval for submitting this request to an external prompt-retaining provider. Required true for experiential only; not passed to the provider.'},
    code_exposure_opt_in:{type:'boolean',description:'Explicit permission for potential proprietary code exposure by the worker to the retaining provider. Required true for experiential, even when the immediate packet is public, and independently rechecked by the native owner.'},
  }, ['run_id','root_id','parent_id','task_class','task_complexity','work_packet'], false),
  tool('fabric_status', 'Read the requested commission and its actual successor through fabric_task.py. Earlier failed attempts remain visible. NOT_FOUND after a lost request is not proof of no effect or permission to retry. Root metadata is not authentication.', identity, ['run_id','root_id'], true),
  tool('fabric_wait', 'Use the incumbent adapter bounded wait for this run, at most ten seconds. Creates no watcher, retry loop, cancellation or background wake.', {...identity,timeout_seconds:{type:'integer',minimum:0,maximum:10,default:5}}, ['run_id','root_id'], true),
  tool('fabric_result', 'Retrieve the actual successor result only when available and the ledger root matches. Returns accept_run_id for exact reviewed-leaf acceptance. Returns a digest of the complete adapter response, not an artifact attestation. Does not accept the result.', {...identity,max_bytes:maxBytes}, ['run_id','root_id'], true),
  tool('fabric_result_page', 'Read one bounded page of the observed successor result; returns accept_run_id for exact-leaf acceptance after strict root and size checks. Each page carries the SHA256 of the complete UTF-8 result. Pages must cover all bytes in order before oversized acceptance; no new worker, result store or acceptance.', {
    ...identity, offset:pageOffset, max_bytes:pageBytes, expected_response_sha256:{type:'string',pattern:'^[0-9a-f]{64}$'},
  }, ['run_id','root_id'], true),
  tool('fabric_accept', 'Effectful acceptance of one fully reviewed worker result. Requires independently checked evidence and the exact response digest. Oversized results require complete contiguous page delivery for this exact leaf in the current backend generation and a fresh full digest check. This changes the existing ledger; never retry an uncertain acceptance.', {
    ...identity, by:{type:'string',enum:['deterministic','reviewer']}, expected_response_sha256:{type:'string',pattern:'^[0-9a-f]{64}$'},
    verification_summary:{type:'string',enum:ACCEPT_VERIFICATION_CODES,
      description:'One fixed evidence-basis code after actual verification. No prose or workflow instructions. Backend does not attest external checks.'}, max_bytes:maxBytes,
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
  if (name==='fabric_accept') {
    const {by, verification_summary: basis}=args;
    const deterministic=['deterministic_test_evidence','artifact_digest_comparison'];
    const reviewer=['manual_result_review','independent_review_evidence'];
    if (!(by==='deterministic' ? deterministic : reviewer).includes(basis))
      fail('INVALID_ARGUMENT',{field:'verification_summary'});
  }
  if (name==='fabric_request') {
    if (Buffer.byteLength(args.work_packet)>MAX_PACKET_BYTES) fail('INVALID_ARGUMENT',{field:'work_packet'});
    if (args.task_complexity==='C3_FRONTIER_JUDGMENT' && !args.escalation_reason?.trim()) fail('INVALID_ARGUMENT',{field:'escalation_reason'});
    if (args.model && !args.pool) fail('INVALID_ARGUMENT',{field:'pool'});
    // Native per-request turn limits are qualified for GLM/MiniMax modes only.
    // Refuse incompatible manual pools before reserving a run or controller.
    if (args.pool && args.max_turns!==undefined && !['glm','minimax'].includes(args.pool))
      fail('INVALID_ARGUMENT',{field:'max_turns'});
    // Experiential uncensored retention gate, enforced before reserving a run
    // or touching the native adapter: exact-model pin plus explicit per-request
    // opt-in for the prompt+response-retaining provider, scoped to this pool.
    if (args.pool===EXPERIENTIAL_POOL) {
      if (args.model!==EXPERIENTIAL_MODEL) fail('INVALID_ARGUMENT',{field:'model'});
      if (args.retention_opt_in!==true) fail('INVALID_ARGUMENT',{field:'retention_opt_in'});
      if (args.sensitive_data_opt_in!==true) fail('INVALID_ARGUMENT',{field:'sensitive_data_opt_in'});
      // Treat the worker's potential code access as proprietary by default:
      // never let the caller assert public-data-only to bypass code consent.
      if (args.code_exposure_opt_in!==true) fail('INVALID_ARGUMENT',{field:'code_exposure_opt_in'});
      // The native experiential53 source contract currently admits bounded labor only.
      // Avoid misleading positive previews for reviewer/audit classes it cannot run.
      if (!['mechanical','fix_build'].includes(args.task_class))
        fail('INVALID_ARGUMENT',{field:'task_class'});
    } else {
      for(const field of ['retention_opt_in','sensitive_data_opt_in','code_exposure_opt_in'])
        if(args[field]!==undefined) fail('INVALID_ARGUMENT',{field});
    }
  }
}
/**
 * Evidence-only failure interpretation for attended callers. This projection is
 * NOT an admission, retry, fallback, lifecycle or permission owner. In particular,
 * EXECUTION_NOT_ELIGIBLE is an acceptance projection, not a refusal cause.
 * Never inspect work_packet, free-form output or provider prose for authority.
 */
export function projectFabricFailureDiagnosis(value) {
  const observation=value && typeof value==='object' && !Array.isArray(value) ? value : {};
  const candidate=observation.status;
  const s=candidate && typeof candidate==='object' && !Array.isArray(candidate)
    && candidate.schema==='mastermind.fabric_task_status.v1' ? candidate : {};
  const code=typeof observation.error==='string' ? observation.error : '';
  const state=typeof s.state==='string' ? s.state : '';
  const signal=typeof s.signal==='string' ? s.signal : '';
  // Only typed owner fields participate. acceptance_reason is deliberately absent.
  const typed=[code,s.error,s.reason,signal,observation.native_reason];
  const explicitDenials=new Set([
    'SAFETY_DENIED','SAFETY_REFUSAL','PERMISSION_DENIED','AUTHORIZATION_DENIED',
    'safety_denied','safety_refusal','permission_denied','authorization_denied',
  ]);
  const policyDenied=typed.some(x=>typeof x==='string' && explicitDenials.has(x));
  const uncertain=code==='EFFECT_UNKNOWN' || state==='EFFECT_UNKNOWN'
    || signal==='effect_unknown' || s.continuation?.controller_return==='UNCONFIRMED'
    || ['STATUS_UNREADABLE','RESULT_UNAVAILABLE','REQUEST_RETAINED_NO_START_EVIDENCE'].includes(state)
    || code==='CONTROLLER_RETURN_UNCONFIRMED';
  let classification='UNCLASSIFIED';
  let nextStep='INSPECT_ORIGINAL_TYPED_RECEIPT';
  if(uncertain) {
    classification='EFFECT_UNCERTAIN';nextStep='RECONCILE_ORIGINAL_EFFECT_NO_REPLAY';
  } else if(policyDenied) {
    classification='EXPLICIT_SAFETY_OR_ACCESS_DENIAL';nextStep='STOP_DENIED_ACTION_CONTINUE_INDEPENDENT_WORK';
  } else if(['ROOT_MISMATCH','ROOT_UNVERIFIED','CONTROLLER_NOT_BOUND'].includes(code)) {
    classification='IDENTITY_OR_BINDING_GATE';nextStep='VERIFY_ORIGINAL_IDENTITY_NO_SUBSTITUTION';
  } else if(code==='INVALID_ARGUMENT') {
    const consentFields=['retention_opt_in','sensitive_data_opt_in','code_exposure_opt_in'];
    classification=consentFields.includes(observation.field) ? 'REQUIRED_CONSENT_MISSING' : 'REQUEST_SCHEMA_ERROR';
    nextStep=consentFields.includes(observation.field)
      ? 'OBTAIN_ACTUAL_REQUIRED_CONSENT_NOT_AUTOFILL_TRUE'
      : 'CORRECT_INPUT_WITHIN_SCOPE_THEN_EXISTING_OWNER_RECHECK';
  } else if(code==='MANUAL_ROUTE_PREFLIGHT_REFUSED') {
    classification='NATIVE_ELIGIBILITY_REFUSAL';
    nextStep=observation.native_reason==='bounded_complexity_requires_escalation'
      ? 'VERIFY_FACTUAL_ESCALATION_REQUIREMENT_WITH_EXISTING_OWNER'
      : 'INSPECT_NATIVE_ELIGIBILITY_PRESERVE_MANUAL_PIN';
  } else if(['REQUEST_ALREADY_ATTEMPTED','RUN_EXISTS'].includes(code)) {
    classification='ORIGINAL_OPERATION_ALREADY_EXISTS';nextStep='OBSERVE_ORIGINAL_RUN_NO_DUPLICATE';
  } else if(['MANUAL_ROUTE_UNAVAILABLE','ADAPTER_CONTINUITY_UNAVAILABLE','ADAPTER_TURN_LIMIT_UNAVAILABLE',
    'ADAPTER_OBSERVATION_UNAVAILABLE','OBSERVATION_INCOMPLETE','PROCESS_TRANSPORT_ERROR','CAPTURE_INVALID','UNKNOWN_TOOL'].includes(code)) {
    classification='TECHNICAL_INTERFACE_OR_TRANSPORT';nextStep='DIAGNOSE_ORIGINAL_INTERFACE_AND_EFFECTS_WITHIN_GRANT';
  } else if(['RESULT_TOO_LARGE','RESULT_NOT_FULLY_DELIVERED','RESULT_OFFSET_OUT_OF_RANGE'].includes(code)) {
    classification='RESULT_RETRIEVAL_REQUIREMENT';nextStep='READ_ORIGINAL_RESULT_WITH_EXISTING_PAGING';
  } else if(signal==='quota' || s.reason==='prelease_broker_busy') {
    classification='CAPACITY_OR_QUOTA';nextStep='INSPECT_INCUMBENT_CONTROLLER_CAPACITY_DISPOSITION';
  } else if(state==='REQUEST_REFUSED_BEFORE_LAUNCH') {
    classification='PRELAUNCH_REFUSAL_CAUSE_UNRESOLVED';nextStep='INSPECT_ORIGINAL_PRELAUNCH_REASON_AND_EFFECT_EVIDENCE';
  } else if(['ACTIVE_OR_WAITING','SETTLING'].includes(state)) {
    classification='EXECUTION_PENDING';nextStep='OBSERVE_ORIGINAL_CONTROLLER_NO_DUPLICATE';
  } else if(state==='NOT_FOUND') {
    classification='ORIGINAL_RUN_NOT_FOUND';nextStep='VERIFY_ORIGINAL_REQUEST_LINEAGE_NOT_ABSENCE_BY_INFERENCE';
  } else if(state==='TERMINAL' && s.rc===0 && signal==='ok' && s.result_available===true) {
    classification=s.accepted===true && s.acceptance_state==='ACCEPTED'
      && ['reviewer','deterministic'].includes(s.accepted_by) ? 'ACCEPTED_RESULT_OBSERVED' : 'RESULT_VERIFICATION_REQUIRED';
    nextStep=classification==='ACCEPTED_RESULT_OBSERVED'
      ? 'CONSUME_VERIFIED_ORIGINAL_RESULT' : 'VERIFY_ORIGINAL_RESULT_BEFORE_ACCEPTANCE';
  } else if(['TERMINAL','TERMINAL_FAILURE','RECONCILED_PRESTART_FAILURE','RECONCILED_PREEXEC_FAILURE'].includes(state)) {
    classification='EXECUTION_FAILURE';nextStep='DIAGNOSE_ORIGINAL_FAILURE_WITHIN_EXISTING_GRANT';
  }
  return {
    schema:'mastermind.fabric_failure_diagnosis.v1',classification,
    policy_denial_evidence:policyDenied ? 'EXPLICIT_TYPED_DENIAL' : 'NOT_ESTABLISHED',
    effect_evidence:uncertain ? 'UNCERTAIN' : s.execution_absence_proven===true
      ? 'OWNER_REPORTS_EXECUTION_ABSENCE' : 'NO_ABSENCE_PROOF',
    acceptance_reason_scope:'RESULT_ACCEPTANCE_ONLY_NOT_FAILURE_CAUSE',
    retry_allowed_scope:'CALLER_REPLAY_OR_REROUTE_OF_ORIGINAL_EFFECT',
    next_step:nextStep,
    // Interpretation does not turn owner evidence into new authority.
    caller_replay_authorized:false,diagnosis_grants_permission:false,
  };
}

function response(value, isError=false) {
  const envelope={schema:'mastermind.fabric_mcp.v1',...value,retry_allowed:false,
    ...(value.action==='capabilities'?{recovery_semantics:{
      retry_allowed_scope:'CALLER_REPLAY_OR_REROUTE_OF_ORIGINAL_EFFECT',
      acceptance_reason_is_admission_denial:false,caller_replay_authorized:false,
      technical_repair_owner:'existing_authorized_owner',
      controlled_continuation_owner:'incumbent_native_controller',
    }}:{}),
    ...(value.error || value.status?{failure_diagnosis:projectFabricFailureDiagnosis(value)}:{}),
  };
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
function decodeCapturedEnvelope(envelopeText, allowPreviewReason=false) {
  // Validate ONE complete capture envelope produced by the fixed CAPTURE_PROGRAM
  // wrapper. The envelope carries the original child adapter exit code and the
  // exact verified stdout bytes (base64 + byte count + sha256 + canonical
  // base64 round-trip + strict UTF-8). A bounded native stderr reason is
  // admitted only for explicit read-only preview with nonzero exit and empty stdout.
  // Returns null on malformed, truncated, oversized or mismatched framing.
  // capture_error is surfaced via
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
  const hasReason=Object.hasOwn(envelope,'native_reason');
  if (Object.keys(envelope).length !== (hasReason?5:4)
      || (hasReason && (!allowPreviewReason || envelope.exit_code===0
          || envelope.stdout_bytes!==0 || typeof envelope.native_reason!=='string'
          || !/^[a-z][a-z0-9_]{0,79}$/.test(envelope.native_reason)))
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
           stdout_sha256: envelope.stdout_sha256, stdout_bytes: envelope.stdout_bytes,
           ...(hasReason?{native_reason:envelope.native_reason}:{}) };
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
function resultIdentityReady(s,args) {
  if(s.continuation?.controller_return==='UNCONFIRMED') fail('CONTROLLER_RETURN_UNCONFIRMED',{effective_run_id:s.run_id});
  checkRoot(s,args,true);
  if(s.state==='EFFECT_UNKNOWN') fail('EFFECT_UNKNOWN');
  if(!s.result_available) fail('RESULT_UNAVAILABLE');
  if(!Number.isSafeInteger(s.result_bytes) || s.result_bytes<0) fail('RESULT_SIZE_UNVERIFIED');
}
function resultReady(s,args) {
  resultIdentityReady(s,args);
  if(s.result_bytes>(args.max_bytes??8192)) fail('RESULT_TOO_LARGE',{result_bytes:s.result_bytes,max_bytes:args.max_bytes??8192});
}
function pageReady(s,args,offset) {
  resultIdentityReady(s,args);
  if(s.result_bytes>MAX_RETAINED_BYTES) fail('RESULT_EXCEEDS_ADAPTER_LIMIT',{result_bytes:s.result_bytes,max_bytes:MAX_RETAINED_BYTES});
  if(offset>=s.result_bytes) fail('RESULT_OFFSET_OUT_OF_RANGE',{offset,result_bytes:s.result_bytes});
}

/**
 * Read-only parent attention derived from the incumbent exact-run observation.
 * It creates NO wake, retry, reviewer acceptance, lease, or new lifecycle.
 * Parent consumers must independently check source/effects before acting.
 */
export function projectFabricParentRecovery(s, expectedRoot) {
  if (!s || s.schema!=='mastermind.fabric_task_status.v1'
      || typeof s.run_id!=='string' || !ID_RE.test(s.run_id)
      || typeof expectedRoot!=='string' || !ID_RE.test(expectedRoot)
      || typeof s.state!=='string' || typeof s.result_available!=='boolean')
    throw new TypeError('FABRIC_PARENT_RECOVERY_STATUS_INVALID');
  const rootVerified=s.root_id===expectedRoot;
  // The native prelaunch refusal carries request correlation, not attested
  // worker/ledger root. Expose it for diagnosis without authorizing parent wake.
  const prelaunchCorrelated=s.state==='REQUEST_REFUSED_BEFORE_LAUNCH'
    && s.execution_absence_proven===true && s.root_id===null
    && s.request_root_id===expectedRoot;
  const controller=s.continuation?.controller_return;
  let disposition='WAIT_ORIGINAL_CONTROLLER';
  // A foreign attested root is not our original run. Preserve its mismatch
  // label; otherwise retain the native state-specific diagnosis even when
  // the native root is legitimately unverified/null. No new parent authority.
  const foreignRoot=typeof s.root_id==='string' && s.root_id!==expectedRoot;
  // For this original run, controller uncertainty outranks apparent success.
  if (foreignRoot) disposition='VERIFY_ORIGINAL_LINEAGE';
  else if (s.state==='EFFECT_UNKNOWN' || controller==='UNCONFIRMED'
      || ['STATUS_UNREADABLE','RESULT_UNAVAILABLE','REQUEST_RETAINED_NO_START_EVIDENCE'].includes(s.state))
    disposition='RECONCILE_ORIGINAL_EFFECT';
  else if (s.state==='TERMINAL' && s.rc===0 && s.signal==='ok'
      && s.result_available===true) {
    disposition=(s.accepted===true && s.acceptance_state==='ACCEPTED'
        && ['reviewer','deterministic'].includes(s.accepted_by))
      ? 'ACCEPTED_RESULT_OBSERVED' : 'RESULT_VERIFICATION_REQUIRED';
  } else if (['TERMINAL','TERMINAL_FAILURE'].includes(s.state) && s.signal==='quota')
    disposition='CAPACITY_BLOCKED_OR_REVIEW_FAILED';
  else if (s.state==='REQUEST_REFUSED_BEFORE_LAUNCH'
      && s.execution_absence_proven===true && (rootVerified || prelaunchCorrelated))
    disposition='RECONCILE_PRELAUNCH_REFUSAL';
  else if (['TERMINAL','TERMINAL_FAILURE','RECONCILED_PRESTART_FAILURE','RECONCILED_PREEXEC_FAILURE']
      .includes(s.state))
    disposition='RECONCILE_TERMINAL_FAILURE';
  else if (['ACTIVE_OR_WAITING','SETTLING'].includes(s.state))
    disposition='WAIT_ORIGINAL_CONTROLLER';
  else if (!rootVerified)
    disposition='VERIFY_ORIGINAL_LINEAGE';
  const attentionRequired=!['WAIT_ORIGINAL_CONTROLLER','VERIFY_ORIGINAL_LINEAGE']
    .includes(disposition);
  return {
    schema:'mastermind.fabric_parent_recovery_projection.v1',
    requested_run_id:s.continuation?.requested_run_id??s.run_id,
    effective_run_id:s.run_id, root_verified:rootVerified,
    request_correlation_only:prelaunchCorrelated,
    disposition, parent_attention_required:rootVerified && attentionRequired,
    // The true lifecycle and provider state remain owned by the native run.
    wake_proven:false, retry_authorized:false, dispatch_authorized:false,
    result_consumption_authorized:false,
  };
}

export function createFabricFacade(engine, options={}) {
  const cfg={adapterPath:DEFAULT_ADAPTER,python:'python3',workerCwd:'~',quotaFallback:false,...options};
  const nativeOrigin=createHermesOriginAdmission(cfg.hermesNative??null);
  if(!isAbsolute(cfg.adapterPath) || cfg.adapterPath.includes('\0') || typeof cfg.python!=='string' || !cfg.python || cfg.python.includes('\0') || typeof cfg.workerCwd!=='string' || !cfg.workerCwd || cfg.workerCwd.includes('\0')) throw new TypeError('invalid operator configuration');
  // This index only fences returned incumbent process handles. It has no run state,
  // admission, scheduling or retry authority and is never persisted or reconstructed.
  const controllers=new Map();
  const attempted=new Set(); // exact generation-local replay fence, never delete
  const reservations=new Map(); // preflight + dispatched/UNKNOWN slots, <=512
  // Bounded generation-local read coverage, keyed by the observed effective leaf.
  // Stores no result bytes and grants no worker, retry, or acceptance authority.
  const deliveredPrefixes=new Map();
  let retentionCursor=0;
  function loseControllerBinding(pid) {
    const prior=controllers.get(pid);
    if(prior) {
      controllers.delete(pid);
      prior.pid=null; prior.terminalObserved=false;
    }
  }
  function terminal(s, binding) {
    return s.root_id===binding.root_id && ['TERMINAL','TERMINAL_FAILURE'].includes(s.state)
      && Number.isSafeInteger(s.rc) && s.rc>=0 && s.rc<=255
      && typeof s.signal==='string' && s.signal!=='effect_unknown'
      && s.continuation?.controller_return!=='UNCONFIRMED';
  }
  function observeTerminal(s, args) {
    const binding=reservations.get(args.run_id);
    if(binding?.dispatched && binding.root_id===args.root_id)
      binding.terminalObserved=terminal(s,binding);
  }
  function activePids(raw) {
    if(raw?.isError || raw?.content?.length!==1 || raw.content[0].type!=='text') return null;
    const text=raw.content[0].text;
    if(typeof text!=='string' || Buffer.byteLength(text)>MAX_RESPONSE_BYTES) return null;
    if(text==='No active sessions') return new Set();
    const pids=new Set();
    for(const line of text.split('\n')) {
      const match=/^PID: ([1-9][0-9]*), Blocked: (?:true|false), Runtime: [0-9]+s(?:, RemoteCall: [A-Za-z0-9_.:-]{1,128})?$/.exec(line);
      if(!match) return null;
      const pid=Number(match[1]);
      if(!Number.isSafeInteger(pid) || pid>2147483647 || pids.has(pid)) return null;
      pids.add(pid);
    }
    return pids;
  }
  function retentionExpired(raw, pid) {
    return raw?.isError===true && raw.content?.length===1
      && raw.content[0].type==='text'
      && raw.content[0].text===`No session found for PID ${pid}`;
  }
  async function reclaimOne() {
    // A terminal observation only nominates a candidate. It is never enough
    // to discard a live handle or retained output. No timers or background GC.
    const candidates=[...reservations.values()].filter(x=>x.dispatched && x.pid && x.terminalObserved);
    if(!candidates.length) return;
    const begin=retentionCursor%candidates.length;
    retentionCursor=(begin+MAX_RETENTION_CANDIDATES)%candidates.length;
    try {
      const active=activePids(await engine.callTool({name:'list_sessions',arguments:{}}));
      if(active===null) return;
      for(let n=0;n<Math.min(MAX_RETENTION_CANDIDATES,candidates.length);n++) {
        const binding=candidates[(begin+n)%candidates.length];
        if(!binding.pid || reservations.get(binding.run_id)!==binding
            || controllers.get(binding.pid)!==binding || active.has(binding.pid)) continue;
        const expired=await engine.callTool({name:'read_process_output',arguments:{
          pid:binding.pid,timeout_ms:0,offset:1,length:1}});
        if(!retentionExpired(expired,binding.pid)) continue;
        // At most ONE fresh adapter observation in this capacity guard.
        const current=await status({run_id:binding.run_id,root_id:binding.root_id});
        if(terminal(current,binding) && reservations.get(binding.run_id)===binding
            && controllers.get(binding.pid)===binding) {
          controllers.delete(binding.pid);
          reservations.delete(binding.run_id);
        }
        return;
      }
    } catch { /* Unavailable/malformed owner evidence preserves capacity. */ }
  }
  async function reserve(args) {
    const key=Buffer.from(args.run_id,'utf8').toString('utf8');
    const check=()=>{
      if(attempted.has(key) || reservations.has(key)) fail('REQUEST_ALREADY_ATTEMPTED');
      if(attempted.size>=MAX_ATTEMPT_IDENTITIES) fail('GENERATION_TRACKING_CAPACITY');
    };
    check();
    if(reservations.size>=MAX_CONTROLLERS) { await reclaimOne(); check(); }
    if(reservations.size>=MAX_CONTROLLERS) fail('CONTROLLER_TRACKING_CAPACITY');
    // No await between this size check and reservation. The ID is fenced
    // permanently only at actual dispatch; proved preflight failure refunds
    // this temporary slot, never a dispatched/no-PID/UNKNOWN reservation.
    const binding={run_id:key,root_id:args.root_id,pid:null,dispatched:false,terminalObserved:false};
    reservations.set(key,binding);
    return binding;
  }
  function command(argv, packet, capture=false, page=null) {
    const prefix=page?[cfg.python,'-c',PAGE_CAPTURE_PROGRAM,String(page.offset),String(page.max_bytes),cfg.python,cfg.adapterPath]:
      capture?[cfg.python,'-c',CAPTURE_PROGRAM,cfg.python,cfg.adapterPath]:[cfg.python,cfg.adapterPath];
    let c=[...prefix,...argv].map(shellQuote).join(' ');
    if(packet!==undefined) {
      let marker; do{marker='MMX_FABRIC_PACKET_'+randomBytes(12).toString('hex');}while(packet.split('\n').includes(marker));
      c+=` <<'${marker}'\n${packet}\n${marker}\n`;
    } else c+='\n';
    return `printf '%s\\n' 'MMX_FABRIC_BEGIN'\n${c}mmx_fabric_rc=$?\nprintf '\\nMMX_FABRIC_EXIT=%s\\n' "$mmx_fabric_rc"`;
  }
  async function runShort(argv, timeoutMs=10000, capture=false, page=null) {
    const raw=await engine.callTool({name:'start_process',arguments:{command:command(argv,undefined,capture,page),timeout_ms:timeoutMs}});
    let text=engineText(raw), parsed=completedOutput(text); const pid=processPid(text);
    // Every start_process is a new process, including short observations.
    // A reused native PID cannot retain an older root's output authority.
    if(pid) loseControllerBinding(pid);
    if(!parsed && pid) {
      // Native --help/status can outlive start_process's initial output window
      // on a busy M2. Reobserve ONLY this exact process handle. These are
      // bounded read-only observations, never an adapter command retry or a
      // second controller/worker dispatch. Keep an incomplete PID as evidence.
      for(let readNo=0;readNo<4 && !parsed;readNo++) {
        const read=await engine.callTool({name:'read_process_output',arguments:{
          pid,timeout_ms:3000,offset:0,length:200
        }});
        text=engineText(read); parsed=completedOutput(text);
      }
    }
    if(!parsed) fail('OBSERVATION_INCOMPLETE',{controller_pid:pid});
    return parsed;
  }
  // Reusable captured-short helper for adapter commands whose output the
  // facade must interpret (status, wait, accept completion/readback,
  // capabilities/help). Reuses the fixed CAPTURE_PROGRAM and validates ONE
  // complete capture envelope. Outer wrapper success is required; the
  // returned exit_code is the ORIGINAL child adapter exit code and the
  // stdout is the exact verified bytes. Native preview-only, nonzero-exit
  // stderr may supply one validated, low-entropy reason token; never raw stderr.
  async function runCapturedShort(argv, timeoutMs=10000) {
    const parsed=await runShort(argv,timeoutMs,true);
    if(parsed.exit_code!==0) fail('CAPTURE_INVALID');
    const decoded=decodeCapturedEnvelope(parsed.stdout,argv[0]==='preview');
    if(!decoded || decoded.captureError || decoded.decodeError) fail('CAPTURE_INVALID');
    return {exit_code:decoded.exit_code,stdout:decoded.stdout,
      ...(decoded.native_reason?{native_reason:decoded.native_reason}:{})};
  }
  async function continuityAvailable(requestHelp=null) {
    if(!cfg.quotaFallback) return false;
    requestHelp ??= await runCapturedShort(['request','--help']);
    const statusHelp=await runCapturedShort(['status','--help']);
    return requestHelp.exit_code===0 && statusHelp.exit_code===0 &&
      requestHelp.stdout.includes('--quota-fallback') && statusHelp.stdout.includes('--follow');
  }
  async function status(args,follow=cfg.quotaFallback) {
    const s=statusJSON(await runCapturedShort(['status',args.run_id,...(follow?['--follow']:[])]),args.run_id,follow);
    checkRoot(s,args);observeTerminal(s,args);return s;
  }
  async function retained(args,s) {
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
  async function retainedPage(args,s,offset,length) {
    pageReady(s,args,offset);
    const r=await runShort(['result',s.run_id,'--max-bytes',String(MAX_RETAINED_BYTES)],10000,false,{offset,max_bytes:length});
    if(r.exit_code!==0) fail('RESULT_UNAVAILABLE',{adapter_exit_code:r.exit_code});
    let captured;try{captured=JSON.parse(r.stdout);}catch{fail('RESULT_TRANSFER_INVALID');}
    if(!captured || typeof captured!=='object' || Array.isArray(captured)) fail('RESULT_TRANSFER_INVALID');
    if(Object.hasOwn(captured,'capture_error')) {
      if(Object.keys(captured).length===1 && ['RESULT_RESPONSE_TOO_LARGE','RESULT_NOT_UTF8'].includes(captured.capture_error)) fail(captured.capture_error);
      fail('RESULT_TRANSFER_INVALID');
    }
    if(!Number.isSafeInteger(captured.exit_code) || captured.exit_code < -255 || captured.exit_code > 255) fail('RESULT_TRANSFER_INVALID');
    if(captured.exit_code!==0) {
      if(Object.keys(captured).length!==1) fail('RESULT_TRANSFER_INVALID');
      fail('RESULT_UNAVAILABLE',{adapter_exit_code:captured.exit_code});
    }
    if(Object.keys(captured).length!==7 || !Number.isSafeInteger(captured.response_bytes) || captured.response_bytes!==s.result_bytes ||
       captured.offset!==offset || !Number.isSafeInteger(captured.page_bytes) ||
       captured.page_bytes!==Math.min(length,s.result_bytes-offset) ||
       typeof captured.response_sha256!=='string' || !/^[0-9a-f]{64}$/.test(captured.response_sha256) ||
       typeof captured.page_sha256!=='string' || !/^[0-9a-f]{64}$/.test(captured.page_sha256) ||
       typeof captured.page_base64!=='string' || captured.page_base64.length > Math.ceil(length/3)*4 ||
       !/^[A-Za-z0-9+/]*={0,2}$/.test(captured.page_base64))
      fail('RESULT_TRANSFER_INVALID');
    const bytes=Buffer.from(captured.page_base64,'base64');
    if(bytes.length!==captured.page_bytes || hash(bytes)!==captured.page_sha256 ||
       bytes.toString('base64')!==captured.page_base64) fail('RESULT_TRANSFER_INVALID');
    if(args.expected_response_sha256 && captured.response_sha256!==args.expected_response_sha256)
      fail('RESULT_CHANGED',{current_response_sha256:captured.response_sha256});
    return {response_bytes:captured.response_bytes,response_sha256:captured.response_sha256,
      offset,page_bytes:captured.page_bytes,page_sha256:captured.page_sha256,
      page_base64:captured.page_base64,next_offset:offset+captured.page_bytes};
  }
  function recordPage(args,s,page) {
    let witness=deliveredPrefixes.get(s.run_id);
    if(!witness || witness.root_id!==args.root_id ||
       witness.response_bytes!==page.response_bytes || witness.response_sha256!==page.response_sha256) {
      if(!witness && deliveredPrefixes.size>=MAX_CONTROLLERS) fail('DELIVERY_TRACKING_CAPACITY');
      witness={root_id:args.root_id,response_bytes:page.response_bytes,
        response_sha256:page.response_sha256,contiguous_bytes:0};
      deliveredPrefixes.set(s.run_id,witness);
    }
    if(page.offset===witness.contiguous_bytes) witness.contiguous_bytes+=page.page_bytes;
    return witness.contiguous_bytes;
  }
  return { async call(name,args={}) {
    let effectStarted=false;
    let reservation=null;
    try {
      validate(name,args);
      if(name==='fabric_capabilities') {
        const h=await runCapturedShort(['--help']);
        const continuity=await continuityAvailable();
        let manualReady=false;
        if(h.exit_code===0 && h.stdout.includes('preview')) {
          try { const requestHelp=await runCapturedShort(['request','--help']);
            manualReady=requestHelp.exit_code===0 && requestHelp.stdout.includes('--strict-manual-pin'); } catch {}
        }
        return response({action:'capabilities',adapter_available:h.exit_code===0 && ['request','status','result','accept'].every(x=>h.stdout.includes(x)),
          quota_continuity:{enabled:cfg.quotaFallback,adapter_available:continuity,max_attempts:3,
            replay_basis:'pre_task_capacity_rejection',mid_task_replay:false,native_parent_wake:false,background_execution:false},
          manual_routing:{available:manualReady,default:'AUTO',exact_model_requires_pool:true,
            selection_preflight:'native_preview_no_reservation',strict_pin_required:true,cross_provider_fallback:false},
          controller_tracking:{max_unresolved:MAX_CONTROLLERS,max_generation_identities:MAX_ATTEMPT_IDENTITIES,scope:'backend_process_generation_only',restart_persistent:false},
          hermes_native_origin:await nativeOrigin.capabilities(),
          worker_admission:'UNPROBED',worker_start:'UNPROBED',backend:'existing Desktop Commander process owner',
          tools:FABRIC_TOOLS.filter(t=>!nativeOrigin.scoped || NATIVE_HERMES_TOOLS.includes(t.name)).map(t=>t.name),caller_identity:'trusted enrolled channel; not individual ChatGPT identity',root_metadata_is_authentication:false});
      }
      // A native-scoped channel cannot omit origin metadata to become a
      // general operator. Check existing profile/SessionDB before any effect.
      if(!await nativeOrigin.authorize(name,args)) fail('HERMES_NATIVE_ORIGIN_REFUSED');
      if(name==='fabric_controller_output') {
        const binding=controllers.get(args.controller_pid);
        if(!binding || binding.run_id!==args.run_id || binding.root_id!==args.root_id) fail('CONTROLLER_NOT_BOUND');
        const raw=await engine.callTool({name:'read_process_output',arguments:{pid:args.controller_pid,timeout_ms:1000,offset:args.offset??0,length:args.max_lines??60}});
        if(controllers.get(args.controller_pid)!==binding) fail('CONTROLLER_NOT_BOUND');
        return response({action:name,...args,process_output:raw,execution_absence_proven:false});
      }
      if(name==='fabric_request') {
        reservation=await reserve(args);
        const requestKey=reservation.run_id;
        let requestHelp=null;
        if(args.max_turns!==undefined) {
          requestHelp=await runCapturedShort(['request','--help']);
          if(requestHelp.exit_code!==0 || !requestHelp.stdout.includes('--max-turns')) fail('ADAPTER_TURN_LIMIT_UNAVAILABLE');
        }
        if(args.pool) {
          requestHelp ??= await runCapturedShort(['request','--help']);
          if(requestHelp.exit_code!==0 || !requestHelp.stdout.includes('--strict-manual-pin')) fail('MANUAL_ROUTE_UNAVAILABLE');
          // The native request entrypoint must independently own and attest the
          // retention, sensitive-disclosure, and conservative code-exposure gates.
          // Old adapters never receive this request, even if preview claims a route.
          if(args.pool===EXPERIENTIAL_POOL && ![
            '--experiential-retention-acknowledged',
            '--experiential-sensitive-data-opt-in',
            '--experiential-proprietary-code',
            '--experiential-code-exposure-opt-in',
          ].every(flag=>requestHelp.stdout.includes(flag))) fail('MANUAL_ROUTE_UNAVAILABLE');
        }
        if(cfg.quotaFallback && !args.pool && !await continuityAvailable(requestHelp)) fail('ADAPTER_CONTINUITY_UNAVAILABLE');
        const s=await status(args,false);
        if(s.state!=='NOT_FOUND') fail(s.state==='EFFECT_UNKNOWN'?'EFFECT_UNKNOWN':'RUN_EXISTS');
        if(args.pool) {
          // Native preview cannot reserve capacity. The native strict pin MUST
          // recheck the same pool/model before any launch and refuse drift.
          const previewArgs=['preview','--id',args.run_id,'--class',args.task_class,
            '--pool',args.pool,'--model',args.model?.toLowerCase()==='auto'?'auto':args.model??'auto',
            '--task-complexity',args.task_complexity];
          if(args.escalation_reason) previewArgs.push('--escalation-reason',args.escalation_reason);
          if(args.subject_pool) previewArgs.push('--subject-pool',args.subject_pool);
          let route;
          try {
            const preview=await runCapturedShort(previewArgs);
            if(preview.exit_code!==0) {
              // Keep native policy refusal distinct from unavailable/invalid
              // transport. Only a closed, low-entropy reason token is exposed.
              // This is diagnosis, never permission to replay the same run.
              const reason=preview.native_reason ?? /^NONE reason=([a-z][a-z0-9_]{0,79})\r?\n?$/.exec(preview.stdout)?.[1];
              if(reason) fail('MANUAL_ROUTE_PREFLIGHT_REFUSED',{
                native_reason:reason,
                ...(reason==='bounded_complexity_requires_escalation'
                  ?{required_field:'escalation_reason'}:{})
              });
              fail('MANUAL_ROUTE_UNAVAILABLE');
            }
            route=JSON.parse(preview.stdout);
          } catch(error) {
            if(error instanceof Refusal && error.code==='MANUAL_ROUTE_PREFLIGHT_REFUSED') throw error;
            fail('MANUAL_ROUTE_UNAVAILABLE');
          }
          if(route?.state!=='PREVIEW_ONLY' || route.reserved!==false
            || route.strict_pin_enforced_at_request!==true
            || route.selection_rechecked_at_request!==true
            || route.run_id!==args.run_id || route.pool!==args.pool
            || typeof route.model!=='string' || !route.model
            || (args.max_turns!==undefined && !['glm','minimax'].includes(route.mode))
            || (args.model && args.model.toLowerCase()!=='auto' && route.model.toLowerCase()!==args.model.toLowerCase()))
            fail('MANUAL_ROUTE_UNAVAILABLE');
          // The experiential slug is checked exactly, not case-insensitively:
          // the native recheck must witness the identical uncensored model.
          if(args.pool===EXPERIENTIAL_POOL && (
            route.model!==EXPERIENTIAL_MODEL || route.mode!==EXPERIENTIAL_POOL
            || typeof route.host!=='string' || !/^[A-Za-z0-9_.:-]+$/.test(route.host)
          )) fail('MANUAL_ROUTE_UNAVAILABLE');
        }
        const argv=['request','--id',args.run_id,'--class',args.task_class,'--task-complexity',args.task_complexity,'--cwd',cfg.workerCwd,'--root',args.root_id,'--parent',args.parent_id,'--stdin'];
        if(cfg.quotaFallback && !args.pool) argv.push('--quota-fallback');
        if(args.pool) argv.push('--pool',args.pool,'--strict-manual-pin');
        if(args.pool===EXPERIENTIAL_POOL) argv.push(
          '--experiential-retention-acknowledged',
          '--experiential-sensitive-data-opt-in',
          '--experiential-proprietary-code',
          '--experiential-code-exposure-opt-in',
        );
        if(args.model && args.model.toLowerCase()!=='auto') argv.push('--model',args.model);
        if(args.max_turns!==undefined) argv.push('--max-turns',String(args.max_turns));
        if(args.escalation_reason) argv.push('--escalation-reason',args.escalation_reason);
        if(args.subject_pool) argv.push('--subject-pool',args.subject_pool);
        // Async capacity/manual preflight may outlive native permission.
        if(!await nativeOrigin.authorize(name,args)) fail('HERMES_NATIVE_ORIGIN_REFUSED');
        if(attempted.has(requestKey)) fail('REQUEST_ALREADY_ATTEMPTED');
        if(attempted.size>=MAX_ATTEMPT_IDENTITIES) fail('GENERATION_TRACKING_CAPACITY');
        attempted.add(requestKey);
        reservation.dispatched=true;
        effectStarted=true;
        const raw=await engine.callTool({name:'start_process',arguments:{command:command(argv,args.work_packet),timeout_ms:1000}});
        const text=engineText(raw),pid=processPid(text);
        if(!pid) fail('EFFECT_UNKNOWN');
        if(controllers.has(pid)) {
          loseControllerBinding(pid);
          fail('CONTROLLER_PID_COLLISION');
        }
        reservation.pid=pid;
        controllers.set(pid,reservation);
        const settled=completedOutput(text);
        return response({action:name,run_id:args.run_id,root_id:args.root_id,parent_id:args.parent_id,controller_pid:pid,
          delivery:'CONTROLLER_CREATED',worker_started:null,worker_start_proven:false,
          ...(args.max_turns!==undefined?{requested_max_turns:args.max_turns}:{}),
          ...(args.pool?{requested_pool:args.pool,requested_model:args.model??'auto',strict_manual_pin:true,
            ...(args.pool===EXPERIENTIAL_POOL?{
              retention_opt_in:true,sensitive_data_opt_in:true,code_exposure_opt_in:true,
            }:{})}:{}),
          adapter_exit_code:settled?.exit_code??null,execution_absence_proven:false,
          next_observation:'fabric_status with the same run and root; fabric_controller_output with this PID when needed'});
      }
      const s=await status(args);
      if(name==='fabric_status') {
        if(!await nativeOrigin.authorize(name,args)) fail('HERMES_NATIVE_ORIGIN_REFUSED');
        return response({action:name,run_id:args.run_id,effective_run_id:s.run_id,expected_root_id:args.root_id,status:s,parent_recovery:projectFabricParentRecovery(s,args.root_id),root_verified:s.root_id===args.root_id,execution_absence_proven:false});
      }
      if(name==='fabric_wait') {
        const seconds=args.timeout_seconds??5;
        const waited=statusJSON(await runCapturedShort(['wait',args.run_id,'--timeout',String(seconds),'--interval','2',...(cfg.quotaFallback?['--follow']:[])],Math.min(12000,(seconds+2)*1000)),args.run_id,cfg.quotaFallback);
        checkRoot(waited,args);observeTerminal(waited,args);
        return response({action:name,run_id:args.run_id,effective_run_id:waited.run_id,status:waited,parent_recovery:projectFabricParentRecovery(waited,args.root_id),root_verified:waited.root_id===args.root_id,execution_absence_proven:false});
      }
      if(name==='fabric_accept' && s.accepted===true) fail('ALREADY_ACCEPTED');
      if(name==='fabric_accept' && s.run_id!==args.run_id) fail('ACCEPT_EXPLICIT_SUCCESSOR_REQUIRED',{effective_run_id:s.run_id});
      if(name==='fabric_result_page') {
        const page=await retainedPage(args,s,args.offset??0,args.max_bytes??MAX_PAGE_BYTES);
        const contiguous_bytes=recordPage(args,s,page);
        return response({action:name,run_id:args.run_id,effective_run_id:s.run_id,accept_run_id:s.run_id,root_id:args.root_id,...page,
          delivered_prefix_bytes:contiguous_bytes,full_result_delivered:contiguous_bytes===page.response_bytes,
          accepted:s.accepted===true,digest_scope:'exact complete adapter CLI response; not artifact attestation'});
      }
      let data;
      if(name==='fabric_accept' && s.result_bytes>MAX_RESPONSE_BYTES) {
        pageReady(s,args,0);
        const witness=deliveredPrefixes.get(s.run_id);
        if(!witness || witness.root_id!==args.root_id || witness.response_bytes!==s.result_bytes ||
           witness.contiguous_bytes!==s.result_bytes) fail('RESULT_NOT_FULLY_DELIVERED');
        const check=await retainedPage(args,s,0,1);
        if(witness.response_sha256!==check.response_sha256 ||
           args.expected_response_sha256!==check.response_sha256)
          fail('RESULT_CHANGED',{current_response_sha256:check.response_sha256});
        data={response_sha256:check.response_sha256};
      } else data=await retained(args,s);
      if(name==='fabric_result') {
        if(!await nativeOrigin.authorize(name,args)) fail('HERMES_NATIVE_ORIGIN_REFUSED');
        return response({action:name,run_id:args.run_id,effective_run_id:s.run_id,accept_run_id:s.run_id,root_id:args.root_id,...data,accepted:s.accepted===true,
          digest_scope:'exact complete adapter CLI response; not a cryptographic artifact attestation'});
      }
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
      if(reservation && !effectStarted && !reservation.dispatched
          && reservations.get(reservation.run_id)===reservation)
        reservations.delete(reservation.run_id);
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
  const hermesFields=[process.env.MMX_FABRIC_HERMES_HOME,process.env.MMX_FABRIC_HERMES_SOURCE,
    process.env.MMX_FABRIC_HERMES_PYTHON,process.env.MMX_FABRIC_HERMES_REVISION,
    process.env.MMX_FABRIC_HERMES_PACKAGE_SHA256];
  const hermesNative=hermesFields.some(x=>x!==undefined)
    ? {home:hermesFields[0],source:hermesFields[1],python:hermesFields[2],
       revision:hermesFields[3],packageSha256:hermesFields[4]} : null;
  const facade=createFabricFacade(engine,{adapterPath:process.env.MMX_FABRIC_ADAPTER_PATH??DEFAULT_ADAPTER,python:process.env.MMX_FABRIC_PYTHON??'python3',workerCwd:process.env.MMX_FABRIC_WORKER_CWD??'~',quotaFallback:true,hermesNative});
  await engine.connect(new StdioClientTransport({command:process.execPath,args:[engineEntry],cwd:homedir(),env:{...process.env},stderr:'inherit'}));
  const server=new Server({name:'mastermind-subagent-fabric',version:VERSION},{capabilities:{tools:{}}});
  const advertised=hermesNative ? FABRIC_TOOLS.filter(t=>NATIVE_HERMES_TOOLS.includes(t.name)) : FABRIC_TOOLS;
  server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:advertised}));
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
