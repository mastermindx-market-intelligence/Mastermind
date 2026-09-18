# DSH ACP Read/Research Worker — N1 Design

**Status:** records-only design / SPEC_ONLY / provider execution held  
**Parent:** `harness-convergence-dsh-teardown-20260916-sol-001` (#687)  
**Predecessor:** N0 native-observation candidate #756 at `c69cf4fab41d7cad02897321a6d1c49ef2560b78`  
**Decision operation:** `harness-convergence-dsh-acp-read-worker-n1-20260918-sol-001`  
**Protected procedure pin:** Mastermind `61a2ff79aba4e8a5685e779707ad5c4426cf5cc5`, Skillpack 1.0.1/bootstrap 1  
**Pinned upstream:** `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`

## 1. Outcome

N1 is the first useful real-worker vertical after N0. A READ/RESEARCH Job admitted by the existing Executive/Worker owners must be able to run through the pinned DSH native agent loop, use a tiny reviewed read-only tool set, return schema-valid structured evidence through the existing ACP Worker consumer, settle its native process, and preserve truthful provider/effect identity.

N1 is not a rich sustained operator, not a replacement Worker adapter, and not a new scheduler. It is one bounded Worker turn. It does not weaken #660's native-resume requirement and does not claim that N0's synthetic host identity proves production process/provider provenance.

The user-visible/company capability unlocked by N1 is concrete: an admitted Mastermind worker can inspect an exact clean workspace with bounded read/search tools and return a validated research result, while provider credentials, retries, account selection, workspace writes, and lifecycle remain outside model control.

## 2. Existing owners reused

N1 reuses these existing authorities instead of creating parallel planes:

- **Executive/Worker lifecycle:** current Job/Attempt/Worker, broker and supervisor owners.
- **Worker process ownership:** `integrations/acp_worker/native.py::AcpNativeProcessOwner`.
- **Worker result normalization:** `integrations/acp_worker/adapter.py::AcpWorkerAdapter`.
- **ACP client and frame policy:** `integrations/acp_worker/turn.py::AcpReadOnlyTurn` plus the existing strict frame reader.
- **Native agent/session/tool loop:** pinned DSH Cordis + AgentRegistry + AgentLoop + ToolRuntime + ACP bridge.
- **Pre-work capability/config comparison:** existing OHF comparison, with N0's exact-Agent observation work supplying the DSH-native facts after it is accepted into an owning production profile.
- **OpenCode Go provider effect boundary:** existing attempt-owned `GoHarnessEndpoint` + Go transport/guard/credential owners.
- **Review/evaluation:** existing review and Agent Evaluation owners.

No DSH-specific queue, lifecycle database, account registry, retry engine, transcript store, model router or permission system is introduced.

## 3. Alternatives considered

### A — Extend the existing ACP Worker lane for a fixed DSH native profile **(chosen)**

Use the existing ACP Worker lifecycle and native process owner. Add only the missing pre-prompt observation gate and a fixed read-tool lifecycle observation policy. DSH remains the subordinate agent loop.

This has the smallest new authority surface and preserves the provider-neutral Worker contract.

### B — Create a DSH-specific `WorkerExecutionAdapter`

Rejected. It duplicates lifecycle/process/result machinery already implemented by the ACP Worker lane and would turn a harness integration into another control plane.

### C — Launch the stock DSH ACP profile and validate after the prompt

Rejected. Stock ACP is broader than the first admitted profile, and post-hoc validation is too late: session creation/composition happens before prompt and tool/model capability drift must fail before first work.

### D — Give DSH the real OpenCode Go credential directly

Rejected. It would move account/credential/retry/effect authority into the child harness and duplicate the existing provider-control boundary.

## 4. Frozen N1 journey

```text
existing Job/Attempt admission
-> exact clean workspace + WorkerLaunchSpec
-> AcpNativeProcessOwner launches one fixed DSH ACP profile
-> OS confinement applies before DSH plugins initialize
-> DSH session/new creates the exact owned Agent
-> child publishes one bounded native pre-work observation
-> parent binds observation to the exact process/run/profile and existing OHF expectation
-> parent pre_prompt_check returns ALLOW or typed refusal
-> only on ALLOW: ACP prompt begins
-> model may call only reviewed read_file/search_text tools
-> ACP client observes and validates those exact tool lifecycles
-> model returns schema-valid JSON
-> existing AcpWorkerAdapter verifies unchanged workspace/result identity
-> native owner settles process/captures
-> existing WorkerResult reaches parent consumer
```

No model/provider request is permitted before the pre-prompt gate completes.

## 5. Provider seam: loopback capability, not provider key

The pinned DSH DeepSeek Chat Completions adapter accepts a custom `baseURL`. N1 points it only at the current Attempt's existing `GoHarnessEndpoint.base_url`.

The child receives:
- the loopback endpoint URL;
- an opaque per-endpoint client capability used as the adapter's bearer value;
- the exact admitted model id;
- no OpenCode Go provider key;
- no account home or account-selection credential.

The parent endpoint retains:
- exact provider account choice;
- real credential loading;
- request admission/economic checks;
- fixed model/session/protocol checks;
- cancellation;
- provider-effect uncertainty;
- failure poisoning.

The DSH provider retry policy is `mode=normal, maxRetries=0`; the retry plugin is omitted from the N1 composition. The endpoint's fail-stop behavior remains an independent backstop. A child error cannot trigger provider/account fallback.

Provider activation is currently **held**. Protected Mastermind still projects the OpenCode Go realm as SPEC_ONLY and has no active subscription harness binding for it. N1 may prove provider-free composition and loopback compatibility now; a real provider turn requires the existing provider realm/enrollment/capacity/canary/usage-policy owners to clear their gates.

## 6. Pre-prompt attestation

Current `AcpReadOnlyTurn` progresses from `session/new` and model selection directly to `session/prompt`. N1 needs one generic trusted seam:

```python
pre_prompt_check: Callable[[AcpPrePromptContext], Awaitable[None]]
```

The callback executes after:
- initialize succeeds;
- `session/new` returns one exact session id;
- required mode/model selection is verified;

and before:
- `frame_guard.begin_prompt()`;
- `self._phase = "prompt"`;
- `conn.prompt(...)`.

It receives immutable owner facts only: WorkerLaunchSpec identity, WorkerProcessRef/launch attestation, exact ACP session id, and the trusted native-observation receipt location/value supplied by the native owner. It cannot change model, tools, workspace, route, provider account or prompt.

Any missing, stale, malformed, changed or refusing observation blocks prompt. Lost callback completion is effect-unknown only for any setup effects already owned by the native process; it never implies that a model request happened.

### Observation transport

For N1, prefer one private run-directory attestation file created at a path fixed by the native owner before launch and writeable only by the child profile. It is transient evidence, not a new store. The DSH composition writes once atomically before `session/new` returns; parent reads once at the pre-prompt gate and binds bytes to the exact run/process/session/profile.

The path and file permissions are owner inputs, never Job/model inputs. No model-facing write tool exists. Corrections require a new process generation/receipt; finalized evidence is not rewritten.

If the existing process owner can expose a safer already-owned side channel without widening lifecycle semantics, that owner may choose it. N1 does not add a general RPC inspector.

## 7. Process-generation binding

Do not mint another process identity.

The production DSH observation binds:
- `run_id` to existing Attempt/Worker run identity;
- `worker_id` to WorkerLaunchSpec;
- native ACP session id to `session/new`;
- process generation to the existing process-owner identity tuple and launch nonce.

The parent constructs the expected binding from `WorkerProcessRef` / launch attestation; the child reports only the opaque generation token intentionally injected by the trusted process owner. PID, host name, or a digest alone is not authority.

N0's synthetic `process_generation_id` is laboratory evidence only.

## 8. Read-only tool ceiling

N1 ships exactly two original Mastermind tools:

### `read_file`
- workspace-relative path only;
- regular files only;
- symlink/escape refusal after canonical resolution;
- bounded offset/length and total bytes;
- UTF-8 text only for v1;
- no directory listing side effect beyond the requested path;
- result carries path, bounded text, size and content digest.

### `search_text`
- literal search only for v1;
- workspace-relative bounded roots;
- bounded files scanned, bytes read, matches and context bytes;
- deterministic lexical order;
- no subprocess/ripgrep;
- skips binary/oversized/unreadable files with bounded typed counters;
- never returns content outside the admitted workspace.

No shell, terminal, browser, MCP, arbitrary network, package install, git write, file write, patch or subagent tool is mounted.

The OS sandbox remains the ultimate boundary: workspace read, exact runtime reads, run/scratch writes required by the harness, and loopback only when a provider canary is separately admitted. External network and child subprocesses stay denied.

## 9. ACP tool-lifecycle observation

The current ACP client deliberately rejects `tool_call` and `tool_call_update` as `ACP_UNADMITTED_UPDATE`. N1 does **not** convert ACP into a tool permission authority.

Extend `AcpProfile` with an immutable observed-tool allowlist. For each allowed tool:
- accept `tool_call` only during prompt phase;
- require one fresh bounded `toolCallId`;
- require title/name to equal an allowed tool;
- require status `in_progress`;
- require bounded JSON rawInput;
- remember the id/name but do not execute anything client-side;
- accept one terminal `tool_call_update` for the same id;
- require status completed/failed;
- bound content and reject images/unknown content in N1;
- refuse duplicate, terminal-before-start, name/id drift, updates after prompt, unknown tools, or open calls at terminal response.

The authoritative capability grant still comes from DSH's exact scoped tool registry + N1 native observation + OS sandbox. ACP merely verifies that the semantic event stream does not claim ungranted tool behavior.

Any ACP permission request remains denied. N1 read tools are composed so they require no interactive approval.

## 10. Structured result

The worker prompt requires one JSON object matching the existing Job-owned result schema. N1 does not add an output protocol.

The first canary schema should be narrow and machine-checkable, for example:

```json
{
  "type": "object",
  "required": ["question", "findings", "evidence"],
  "properties": {
    "question": {"type": "string"},
    "findings": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    "evidence": {
      "type": "array",
      "maxItems": 16,
      "items": {
        "type": "object",
        "required": ["path", "sha256", "claim"],
        "properties": {
          "path": {"type": "string"},
          "sha256": {"type": "string"},
          "claim": {"type": "string"}
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

Existing `AcpWorkerAdapter` remains the acceptance consumer: output identity, schema, git cleanliness, process settlement and result hashes must all pass.

## 11. Retry, cancellation and effect law

- DSH provider retry: zero.
- No provider fallback.
- No account fallback.
- No worker-carrier fallback after START.
- ACP SDK deadlines/cancellation remain existing owner behavior.
- OpenCode endpoint admits at most the exact bound request and poisons after terminal admitted failure.
- Process uncertainty remains on the existing run/process carrier.
- N1 never interprets timeout/silence as no provider effect.
- Any open tool call at cancellation/terminal becomes refusal/effect uncertainty according to existing ACP/process law.

## 12. Provider-free proofs required before a real canary

N1 source may not request a provider credential until all of these pass:

1. Real pinned DSH ACP process interoperates with Python `agent-client-protocol==0.12.1` at protocol v1.
2. Pre-prompt gate demonstrably runs after exact session/model selection and before any prompt/model request.
3. Missing/refusing native observation produces zero prompt calls.
4. Real DSH read_file/search_text calls produce allowed `tool_call` / `tool_call_update` sequences and unchanged workspace.
5. Unknown/write/shell/MCP tool events fail closed.
6. Cancellation with an open read tool settles or returns effect-unknown; no late success.
7. OS sandbox denies external network/subprocess/out-of-scope read/write.
8. Synthetic DSH-shaped Chat Completions traffic reaches the existing Go loopback endpoint while child-visible bearer data is only the endpoint capability.
9. DSH retry is zero and a failed endpoint cannot yield a second provider attempt.
10. Existing result consumer accepts the positive fixture and rejects malformed/stale/mismatched evidence.

## 13. Real-provider canary gate

A real canary is a later effectful operation and requires the existing owners to prove:
- reviewed/enrolled OpenCode Go realm for this path;
- capacity/account generation known;
- exact DeepSeek V4.1 Flash model/protocol offer current;
- usage/economic policy current;
- credential principal bound outside child;
- N1 process/profile/capability materialization accepted;
- current provider canary budget/authority;
- clean isolated workspace and exact Job/Attempt.

The canary uses a tiny public/read-only repository question and one bounded result. It is not a benchmark or routing promotion.

## 14. Implementation ownership and source boundaries

N1 should be a fresh bounded implementation carrier after source custody is reconciled. Do not widen #756 or #687 with production code.

Likely existing-owner modifications:
- `integrations/acp_worker/turn.py`: generic pre-prompt callback and tool-lifecycle observation policy.
- `integrations/acp_worker/adapter.py`: supply immutable pre-prompt owner context if needed; no new lifecycle.
- existing ACP tests for those generic semantics.

DSH-specific production composition belongs in a narrow integration package selected by the #600/HF1/ACP owner. It may reuse/adapt the accepted N0 algorithms but must not import an experimental profile as production law or duplicate OHF policy.

Provider-control files change only if their incumbent owner separately promotes/enrolls the Go realm/binding. N1 source must not self-arm that route.

## 15. Acceptance

N1 is accepted only when the real path is proven:

```text
admitted READ/RESEARCH Job
-> real DSH native process
-> exact pre-prompt attestation ALLOW
-> one or more bounded read tool calls
-> schema-valid answer
-> unchanged workspace
-> settled process
-> existing WorkerResult
-> parent consumer receives/uses result
```

For the first provider-free implementation milestone, use an inert scripted model adapter and prove every lifecycle/tool/attestation edge. That milestone is `BUILT_NOT_PROVEN` for provider execution.

For the first real-provider canary, separately prove the existing provider admission/account/effect gates and one actual model turn. Only that can establish a real read/research DSH worker. Neither milestone qualifies rich resume, write/test operation, autonomous routing or a globally superior harness.

## 16. Executed evidence informing this design

This design is based on current executable and source evidence, not only prose:

- N0 current head `c69cf4f...` mounts real pinned DSH/Cordis core and feeds actual native observation into existing OHF.
- Mastermind Python ACP SDK `0.12.1` reports protocol version 1 and passes its 13 provider-free subprocess conformance cases.
- Current `AcpReadOnlyTurn` was directly probed: DSH-standard `tool_call` and `tool_call_update` both refuse as `ACP_UNADMITTED_UPDATE`.
- A DSH-shaped Chat Completions request for `deepseek-v4.1-flash`, including `stream_options`, tools and extra DSH headers, was sent through the real existing `GoHarnessEndpoint` with synthetic upstream transport. The endpoint returned the streamed terminal response, preserved exact model/session/body, did not forward the client Authorization header, and made zero provider calls.
- Pinned DSH source supports custom Chat Completions `baseURL`; its retry policy accepts `maxRetries=0`.
- Current Mastermind Go provider realm remains SPEC_ONLY and has no active subscription harness binding, so no real provider call is authorized by this record.

## 17. Continuation

1. Keep #756 on its current semantic head while its one justified CI rerun and independent review/adoption gates resolve.
2. Deliver this N1 design to the incumbent #600/ACP integration owner for source-custody/adoption review.
3. After custody is explicit, implement provider-free N1 in one fresh branch/PR with RED-first tests.
4. Do not request or load a real OpenCode Go credential until provider realm/binding/capacity/canary/usage gates are explicitly cleared.
5. After provider-free N1 proof, perform one bounded real read/research canary; only then consider write/test capability or rich sustained operation.
