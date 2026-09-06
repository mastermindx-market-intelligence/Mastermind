# Executed output-helper characterization — long-run ChatGPT workbench

Date: 2026-09-06 UTC. Research carrier: Mastermind PR #490. Parent operation: `chatgpt-pro-long-run-leaders-research-20260905-sol-001`.

**NEW LOCAL EXPERIMENT / SELECTED SOURCE FUNCTIONS EXECUTED / NOT AN APPLICATION BUILD, HOST CANARY, INDEPENDENT REVIEW OR PRODUCTION ACCEPTANCE.**

## Outcome

The investigation now has executed evidence for a small but important workbench component instead of only a proposed pattern: four immutable upstream output helpers compile under the stated local settings, and **57 unique functional characterization cases pass**, with an identical repeat. Five stronger integration properties are **not satisfied** by these helpers in isolation. Those limitations constrain selective reuse; they are not five claimed upstream contract regressions or a claim that the deployed upstream application is broken.

No Mastermind runtime code is changed. The existing provider/process and CodeIntel/tool-output owners remain responsible for any adoption. The first useful authenticated Steward read remains an independent priority and does not acquire these future-workbench gates.

## Provenance and environment

Upstream: `totec448-spec/chat-on-steroids@dbff15b7296358102ee3e141f183e89a4a8d1e0e`.

| Exact source path under `src/main/codex/` | Git blob SHA | Bytes |
|---|---|---:|
| `head-tail-buffer.ts` | `23e42dcb915a915cf56d38afb4fdda744f75c4e2` | 3617 |
| `unified-exec-constants.ts` | `6d97b7e8c360f20f6801e52038d13f2240eaadcc` | 3238 |
| `truncate.ts` | `b0edc398da145b9f81ea5920c1367db3e023efc5` | 6255 |
| `exec-output.ts` | `76799cd82003abe5426980d399d3137d921124c8` | 2812 |

The four files were fetched through the GitHub connector at the exact commit and reconstructed locally. Each reconstruction was accepted only after computing Git's blob hash and matching the remote SHA. The four source hashes were checked again after both runs and were unchanged. Source permalinks are formed as `https://github.com/totec448-spec/chat-on-steroids/blob/dbff15b7296358102ee3e141f183e89a4a8d1e0e/src/main/codex/<filename>`.

Execution environment: disposable ChatGPT Linux x64 sandbox, kernel 6.18.35, Node v22.16.0, preinstalled TypeScript 5.8.3 and preinstalled Node typings. This is **not the upstream package's complete lockfile/toolchain realization**. Selected-module compile used `--strict --skipLibCheck`, target ES2022, CommonJS and Node module resolution; compiler exit was 0. No npm install or lifecycle script ran. The whole archive retrieval was attempted first but failed at DNS resolution (`curl` exit 6); it did not supply source or build evidence.

First functional execution was recorded at `2026-09-06T09:16:04.841Z`. The identical repeat excludes only the recorded timestamp when comparing the result documents. No application, MCP server, tunnel, browser extension, account, desktop helper, native process manager or provider was started. No vulnerability/exploit reproduction was performed. Existing alleged historical build/test/SBOM and host-canary evidence remains unverified; this is a new, narrower experiment, not recovered history or a replacement host operation.

Protected Mastermind procedure for this continuation: `ffbb2eb138cb3c3cb0d211973e0cf30a314b7520`, Skillpack 1.0.1/bootstrap 1. Research parent before this evidence addition: `a479bb2f891155064fb34884815036490a22471e`.

## Fixed protocol and results

The experiment plan was written before compilation/execution. SHA-256: `c7df946d569b097da68158e975350e90c011ad593d0141682cddb42b58fb1f22`.

| Family | Unique cases | Result |
|---|---:|---|
| One-shot/chunked buffer against exact prefix/suffix and byte-conservation oracle | 24 | 24 pass |
| Same-budget buffer merging and original-byte conservation | 6 | 6 pass |
| ASCII, CJK, emoji, combining-mark and mixed-text string truncation | 15 | 15 pass |
| Empty/trailing-newline/CRLF line counting | 6 | 6 pass |
| Success, failure, timeout and long-output formatting with adequate body budgets | 6 | 6 pass |
| **Functional total** | **57** | **57 pass; 0 fail** |

The six buffer budgets were 0, 1, 2, 7, 64 and 1024 bytes; input sizes were 0, 1, 31 and 4096 bytes. String budgets were 0, 7 and 64 bytes. A repeat ran the same 57 cases, not 57 additional independent cases. All five suitability observations below were reproduced unchanged.

## Five integration limitations, kept separate from functional conformance

1. **Retained text budget is not final response size.** For a 100-byte input and an 8-byte text budget, the formatted truncation result is 32 UTF-8 bytes: `0123…92 chars truncated…6789`. Marker/framing bytes are additional. A hard tool-response ceiling must budget the full serialized result, not just retained content.
2. **The buffer marker also costs bytes.** The buffer retains exactly 8 bytes, but the omission-marker rendering is 34 bytes. This is correct retained-byte accounting, not final wire-budget enforcement.
3. **A byte buffer is not a UTF-8 boundary adapter.** A 7-byte head/tail buffer fed ten emoji preserves exact retained bytes; direct UTF-8 decoding of its marker rendering produces one replacement character at the head boundary. The string truncator's tested cases do preserve complete code points. This experiment did not inspect or execute the upstream application's complete streaming-decode chain; it must not be reported as a demonstrated application corruption bug.
4. **Timeout text can disappear although exit metadata survives.** With a timed-out synthetic result and an 8-byte body budget, the output still says `Exit code: 124`, but the explicit timeout phrase is lost to truncation. Exit code alone is not a general replacement for the typed `timedOut` fact. Required effect/timeout/cancellation/cleanup facts should be exposed through the existing structured result contract outside the truncatable display body.
5. **Head/tail is not complete diagnostic retrieval.** A unique diagnostic placed in the middle of a 2024-byte synthetic log is absent from the 90-byte rendered result using a 64-byte retained-content budget. The renderer discloses truncation, but a consumer cannot infer that the original log contained no error. Keep the existing authoritative full artifact or replayable cursor path; do not create another log store or use the display as acceptance evidence.

These are deliberately stronger **Mastermind suitability questions**, not undocumented guarantees retroactively imposed on upstream helper functions. In particular, tiny-budget observations are boundary characterization, not evidence that normal default-budget operation regularly fails.

## Measured display reduction and its limits

A fixed 1,048,576-byte synthetic ASCII input rendered to **8,221 bytes** at an 8,192-byte retained-content budget, a **99.215984% reduction in display bytes**. That is a direct measurement of this fixture only. It is not a measured reduction in model tokens, GPU work, latency, cost, real log traffic or reasoning quality. The middle-diagnostic observation demonstrates why display reduction alone cannot be a success metric.

Useful adoption boundary: bounded output may improve ergonomics only when exact source identity, truncation/coverage, immutable evidence retrieval and mandatory structured result facts remain available. Existing process/Attempt state must remain authoritative; a short displayed log cannot elect success, completion or retry.

## Reproduction and evidence identity

The self-contained characterization harness is included below. Obtain the four exact upstream files into `upstream/src/`, verify the table's Git blob hashes, compile to `upstream/build/`, create `evidence/experiment_plan.json` from the archived plan, then run the harness. There is no application or native dependency installation step.

Commands used in the recorded environment:

```sh
tsc upstream/src/*.ts --target ES2022 --module commonjs --moduleResolution node \
  --strict --types node \
  --typeRoots /opt/nvm/versions/node/v22.16.0/lib/node_modules/ts-node/node_modules/@types \
  --skipLibCheck --outDir upstream/build
node characterize-output.cjs
```

That typings path is an environment-specific input, not a required Mastermind host path. A reproducer must record its own compiler, typings and runtime versions rather than claiming the same toolchain silently.

| Archived evidence | SHA-256 |
|---|---|
| Harness, 9351 UTF-8 bytes | `bd54f9e6b5ef5ef74885e04b2c5333461ef1bdd76a00e378e834e04549f40db0` |
| First full result JSON, 7074 UTF-8 bytes | `1a57af5b749c61616c6692f788821c67cfa2b830e84e34918f1f4d189304a0c3` |
| Source manifest, 1606 UTF-8 bytes | `11f07dcf1693b47a352adbfb67ea85b43af36e04950b9c33245f0facb8972838` |
| Pre-execution experiment plan, 2412 UTF-8 bytes | `c7df946d569b097da68158e975350e90c011ad593d0141682cddb42b58fb1f22` |

The archived result includes all 57 case IDs, all five unsatisfied suitability observations, environment details and claim exclusions. Reproduction yields a new timestamp and therefore a new raw result digest; compare behavioral fields separately. No third-party source is republished in Mastermind by this report.

## Existing-owner continuation

The exact reviewer of PR #490 should consider this executed evidence when adjudicating selective output-helper reuse. The existing provider/process and CodeIntel/tool-output owners should reuse the relevant cases only within their current bounded missions: complete serialized byte budget, Unicode-safe display composition, typed nontruncatable failure facts, and source-backed expansion of omitted content. No source worker, new facade, schema, queue, process store, generic evaluator, install or release is commissioned here.

This settles only the selected output-helper experiment. The whole upstream build, native dependency realization, full suite, SBOM, read-only host containment, live ChatGPT tool journey, exact worker binding, material-return wake, context succession and production program acceptance remain open. The original 40-case research casebook and 24-task leader evaluation remain NOT_RUN by this experiment.

## Executed harness

Save the following block byte-for-byte as `characterize-output.cjs` (including the final newline).

```javascript
'use strict';
// Characterization only: loads four immutable, independently hash-checked source modules.
// Run after compiling them to upstream/build. This creates no application/server/process owner.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const crypto = require('node:crypto');
const path = require('node:path');
const { HeadTailBuffer } = require('./upstream/build/head-tail-buffer.js');
const trunc = require('./upstream/build/truncate.js');
const fmt = require('./upstream/build/exec-output.js');
const root = __dirname;
const results = [];
function check(id, fn) {
  try { fn(); results.push({id, result:'PASS'}); }
  catch (error) { results.push({id, result:'FAIL', error:String(error.stack || error)}); }
}
function expectedBytes(input, budget) {
  if (input.length <= budget) return input;
  const h = Math.floor(budget / 2), t = budget - h;
  return Buffer.concat([input.subarray(0, h), t ? input.subarray(input.length - t) : Buffer.alloc(0)]);
}
const budgets = [0,1,2,7,64,1024];
for (const budget of budgets) {
  for (const size of [0,1,31,4096]) {
    check(`buffer-${budget}-${size}`, () => {
      const input = Buffer.from(Array.from({length:size}, (_,i) => i % 251));
      const single = new HeadTailBuffer(budget); single.pushChunk(input);
      const stream = new HeadTailBuffer(budget);
      let i=0, step=1;
      while (i<input.length) { stream.pushChunk(input.subarray(i,i+step));i+=step;step=step%29+1; }
      for (const b of [single,stream]) {
        assert.deepEqual(b.toBytes(), expectedBytes(input,budget));
        assert.equal(b.totalBytes(), size);
        assert.equal(b.retainedBytes(), Math.min(budget,size));
        assert.equal(b.omittedBytes(), Math.max(0,size-budget));
        const rendered=b.toBytesWithOmissionMarker();
        if (size<=budget) assert.deepEqual(rendered,input);
        else assert(rendered.includes(Buffer.from(`... ${size-budget} bytes omitted ...`)));
      }
    });
  }
  check(`buffer-merge-${budget}`, () => {
    const left=Buffer.from('L'.repeat(277)),right=Buffer.from('R'.repeat(555));
    const a=new HeadTailBuffer(budget), b=new HeadTailBuffer(budget);
    a.pushChunk(left);b.pushChunk(right);a.pushBuffer(b);
    const input=Buffer.concat([left,right]);
    assert.equal(a.totalBytes(),input.length);
    assert.deepEqual(a.toBytes(),expectedBytes(input,budget));
  });
}
function wellFormed(text) {
  for (let i=0;i<text.length;i++) {
    const n=text.charCodeAt(i);
    if (n>=0xD800 && n<=0xDBFF) {
      const next=text.charCodeAt(++i); if(!(next>=0xDC00&&next<=0xDFFF))return false;
    } else if(n>=0xDC00&&n<=0xDFFF)return false;
  }
  return true;
}
const strings=[['ascii','alpha beta gamma'],['cjk','项目状态与证据更新'],['emoji','🧪🚀✅🙂'],['combining','e\u0301a\u0308o\u0302'],['mixed','Status 状态 🧪 e\u0301']];
for(const [name,text] of strings)for(const budget of [0,7,64])check(`string-${name}-${budget}`,()=>{
  const out=trunc.truncateMiddleChars(text,budget);
  assert(wellFormed(out));assert(!out.includes('\uFFFD'));
  if(Buffer.byteLength(text)<=budget)assert.equal(out,text);
  else{
    const match=out.match(/…(\d+) chars truncated…/);assert(match);
    const [before,after]=out.split(match[0]);
    assert(text.startsWith(before));assert(text.endsWith(after));
    assert.equal(Number(match[1]),[...text].length-[...before].length-[...after].length);
    assert(Buffer.byteLength(before+after)<=budget);
  }
});
for(const [i,input,expected] of [[0,'',0],[1,'a',1],[2,'a\n',1],[3,'a\nb',2],[4,'\n',1],[5,'a\r\nb\r\n',2]])check(`lines-${i}`,()=>assert.equal(trunc.countLines(input),expected));
const formatterCases=[
  {id:'empty',text:'',exit:0,ms:0,timeout:false,budget:64},
  {id:'success',text:'all done\n',exit:0,ms:245,timeout:false,budget:64},
  {id:'failure',text:'validation failed\n',exit:1,ms:1500,timeout:false,budget:128},
  {id:'timeout',text:'waiting\n',exit:124,ms:2500,timeout:true,budget:128},
  {id:'long',text:'phase output\n'.repeat(1000),exit:1,ms:3421,timeout:false,budget:64},
  {id:'long-timeout',text:'phase output\n'.repeat(1000),exit:124,ms:5000,timeout:true,budget:256}
];
for(const c of formatterCases)check(`format-${c.id}`,()=>{
  const output=fmt.defaultExecToolCallOutput();Object.assign(output,{exitCode:c.exit,durationMs:c.ms,timedOut:c.timeout});output.aggregatedOutput.text=c.text;
  const s=fmt.formatExecOutputForModel(output,{kind:'bytes',bytes:c.budget});
  assert(s.startsWith(`Exit code: ${c.exit}\nWall time: ${Math.round(c.ms/1000*10)/10} seconds\n`));
  if(c.timeout)assert(s.includes(`command timed out after ${c.ms} milliseconds`));
  if(Buffer.byteLength(fmt.buildContentWithTimeout(output))<=c.budget)assert(s.endsWith(c.text));
});
const suitability=[];
function observe(id, requirement, actual, satisfied, implications){suitability.push({id,requirement,observed:actual,result:satisfied?'SATISFIED':'NOT_SATISFIED',implications});}
const demo='0123456789'.repeat(10), str=trunc.truncateMiddleChars(demo,8);
observe('final-response-byte-ceiling','An 8-byte payload budget is also an 8-byte serialized response ceiling',{budget:8,rendered_bytes:Buffer.byteLength(str),rendered:str},Buffer.byteLength(str)<=8,'Reserve envelope/marker bytes separately; helper promises retained content budget, not final wire ceiling.');
const bb=new HeadTailBuffer(8);bb.pushChunk(Buffer.from(demo));
observe('buffer-rendered-ceiling','An 8-byte retained buffer produces at most 8 rendered bytes',{budget:8,retained:bb.retainedBytes(),rendered:bb.toBytesWithOmissionMarker().length},bb.toBytesWithOmissionMarker().length<=8,'Marker/framing overhead is outside retained bytes.');
const unicode=new HeadTailBuffer(7);unicode.pushChunk(Buffer.from('🙂'.repeat(10)));const unicodeDecoded=unicode.toBytesWithOmissionMarker().toString('utf8');
observe('byte-buffer-text-decoding','Naively decoding retained UTF-8 bytes preserves complete characters',{input_bytes:40,retained_bytes:7,rendered:unicodeDecoded,replacement_characters:[...unicodeDecoded].filter(c=>c==='\uFFFD').length},!unicodeDecoded.includes('\uFFFD'),'The byte buffer is binary-safe, not independently UTF-8-boundary-safe. Test the real upstream decode chain separately; use a proven streaming decoder or string boundary adapter.');
const output=fmt.defaultExecToolCallOutput();Object.assign(output,{exitCode:124,durationMs:5000,timedOut:true});output.aggregatedOutput.text='progress\n'.repeat(100);
const tiny=fmt.formatExecOutputForModel(output,{kind:'bytes',bytes:8});
observe('timeout-fact-survival','Timeout status remains explicit even with 8-byte body budget',{rendered:tiny,explicit_timeout:tiny.includes('timed out'),exit_code_preserved:tiny.includes('Exit code: 124')},tiny.includes('timed out'),'Exit code survives, but timeout text may not. Preserve timedOut/effect/cleanup fields in non-truncatable structured metadata.');
const diagnostic='UNIQUE_MIDDLE_DIAGNOSTIC';const log='H'.repeat(1000)+diagnostic+'T'.repeat(1000);const diagnosticDisplay=trunc.truncateMiddleChars(log,64);
observe('diagnostic-recall','A head-tail display always preserves a middle-only diagnostic',{input_bytes:Buffer.byteLength(log),display_bytes:Buffer.byteLength(diagnosticDisplay),diagnostic_present:diagnosticDisplay.includes(diagnostic)},diagnosticDisplay.includes(diagnostic),'A display summary is not a complete evidence source; retain an exact immutable artifact/cursor path and structural failure metadata.');
const large='A'.repeat(1024*1024),largeDisplay=trunc.truncateMiddleChars(large,8192);
const measured={synthetic_input_bytes:Buffer.byteLength(large),retained_content_budget:8192,rendered_display_bytes:Buffer.byteLength(largeDisplay),display_byte_reduction:1-Buffer.byteLength(largeDisplay)/Buffer.byteLength(large),not_token_or_quality_uplift:true};
const summary={experiment_id:'LRL-OUTPUT-HELPERS-20260906',recorded_at:new Date().toISOString(),environment:{node:process.version,platform:process.platform,architecture:process.arch,kernel:os.release()},plan_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'evidence/experiment_plan.json'))).digest('hex'),functional_total:results.length,functional_passed:results.filter(x=>x.result==='PASS').length,functional_failed:results.filter(x=>x.result==='FAIL').length,suitability_total:suitability.length,suitability_not_satisfied:suitability.filter(x=>x.result==='NOT_SATISFIED').length,results,suitability,measured,claims:{selected_source_functions_executed:true,whole_application_build:false,whole_upstream_suite:false,sbom:false,mastermind_integrated:false,installed_host_or_browser:false,security_exploit_test:false,leader_24_task_benchmark:false,production_proven:false}};
fs.writeFileSync(path.join(root,'evidence/results.json'),JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify({functional_total:summary.functional_total,functional_passed:summary.functional_passed,functional_failed:summary.functional_failed,suitability_total:summary.suitability_total,suitability_not_satisfied:summary.suitability_not_satisfied,measured},null,2));
for(const result of results.filter(x=>x.result==='FAIL'))console.log(result);
for(const row of suitability)console.log(row.id+': '+row.result+' '+JSON.stringify(row.observed));
process.exitCode=summary.functional_failed?1:0;
```

## Archived pre-execution plan

```json
{
  "experiment_id": "LRL-OUTPUT-HELPERS-20260906",
  "scope": "Local source-function characterization of four pinned upstream modules; synthetic inputs only",
  "new_execution_not_recovered_history": true,
  "upstream_commit": "dbff15b7296358102ee3e141f183e89a4a8d1e0e",
  "environment": "ChatGPT disposable Linux sandbox, not Chairman host or browser",
  "isolation": "No application launch, MCP server, provider call, account, tunnel, extension, OS desktop or external service invocation in the experiment",
  "dependency_policy": "Use preinstalled Node/TypeScript/node typings; install no dependencies and run no package lifecycle scripts",
  "functional_cases": {
    "head_tail_matrix": "24 fixed cases: budgets 0,1,2,7,64,1024 crossed with input sizes 0,1,31,4096. Compare one-shot and chunked writes with byte-exact prefix/suffix oracle and omitted-byte conservation",
    "merge_matrix": "6 same-budget buffer merges at budgets 0,1,2,7,64,1024; compare to concatenated input oracle and total-byte conservation",
    "unicode_string_matrix": "15 cases: ASCII, CJK, emoji, combining marks, mixed multilingual strings crossed with budgets 0,7,64. Require complete scalar substrings and exact original preservation when it fits",
    "line_counts": "6 fixed Rust-style line count cases",
    "formatter": "6 fixed exit/timeout/truncation formatting controls with adequate body budget"
  },
  "suitability_questions_not_upstream_guarantees": [
    "Does configured retained-content byte budget equal final serialized response byte ceiling?",
    "Does naive UTF-8 decoding of byte-capped buffer always preserve Unicode scalar boundaries?",
    "Does timedOut remain observable outside truncatable text at very small budgets?",
    "Does a middle-only diagnostic survive a head-tail presentation summary?"
  ],
  "measurement": "Measure bytes of fixed synthetic 1MiB output and bounded display; not tokens, GPU time, leader-quality uplift or real workload benchmark",
  "preregistered_thresholds": "Functional expected behaviors must hold; unsuitable compositional properties are recorded as limitations, never patched or silently excluded",
  "non_goals": ["full upstream typecheck/build/test suite", "software bill of materials", "vulnerability or exploit reproduction", "native installation", "Mastermind integration", "40-case casebook completion", "24-task leader evaluation", "production acceptance"]
}
```
