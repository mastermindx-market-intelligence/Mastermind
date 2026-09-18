# Harness Convergence — N1 Useful READ/RESEARCH Provider-Free Prototype Evidence

**Status:** records-only evidence / implementation prototype is disposable / provider execution held  
**Parent:** Mastermind #687, `harness-convergence-dsh-teardown-20260916-sol-001`  
**Design:** `docs/superpowers/specs/2026-09-18-dsh-acp-read-research-worker-design.md`  
**Predecessor implementation:** Draft #825 at `838d70b3625ae61476336615ef4c9b841a208297`  
**Protected procedure basis:** `61a2ff79aba4e8a5685e779707ad5c4426cf5cc5`, Skillpack 1.0.1/bootstrap 1  
**Pinned DSH:** `deepseek-ai/deepseek-harness@0d1f50007f9bca3f52b06e1c3074fa14d5fb0720`

## Purpose

Resolve the next useful-worker uncertainties without modifying #825 while its writer/review/adoption gates remain open.

The prototype asks whether the existing ACP Worker v1 lane can support a useful DSH READ/RESEARCH turn while preserving the accepted lifecycle/result owners:

```text
existing AcpNativeProcessOwner
-> real pinned DSH ACP process
-> exact Agent-created tool attestation
-> exact ACP session/model observation
-> trusted parent pre-prompt refusal gate
-> scoped bounded read_file
-> scoped literal search_text
-> DSH Agent tool-result continuation
-> schema-valid final JSON
-> existing AcpWorkerAdapter/WorkerResult
-> unchanged workspace
-> settled process
```

This is not production source and creates no Job, route, provider enrollment, credential action, adapter registration, deployment, or durable runtime state.

## Predecessor state

Draft #825 is the provider-free predecessor. Exact-head GitHub CI run `35332917739` is green.

A separate Sol prerequisite review of exact #825 head re-executed the four real DSH process cases plus five focused common-seam regressions: 9 passed. Two forbidden mutations independently killed the provider-scoped ACP model selector and cancellation frame-guard regressions. The Sol review therefore treats #825 as a semantically sound predecessor while retaining its Draft/review/adoption holds.

#825 intentionally does not grant tool updates and does not contain the useful-worker pre-prompt gate.

## RED-first useful-worker delta

Against an immutable copy of exact #825, three new tests were RED before prototype implementation:

1. `AcpReadOnlyTurn.run` had no `pre_prompt_check` seam, so a trusted parent could not refuse after exact session/model setup but before prompt.
2. `AcpProfile` had no observed-tool allowlist, so a reviewed DSH tool lifecycle could not be distinguished from an unadmitted update.
3. Unknown tool events could not be expressed as a profile-specific tool refusal because all tool updates were intentionally rejected generically.

The prototype adds only disposable versions of these common semantics:

- immutable `AcpPrePromptObservation(session_id, requested_model, model_option_value)`;
- optional trusted construction-time parent callback, invoked after exact ACP session/model verification and before `conn.prompt`;
- immutable observed-tool names on the ACP profile;
- lifecycle correlation for exact `tool_call` -> same-id terminal `tool_call_update`;
- bounded tool raw-input and text-result observation;
- unresolved open calls make terminal evidence uncertain;
- profiles with no observed-tool allowlist preserve the predecessor's exact `ACP_UNADMITTED_UPDATE` behavior.

ACP remains an observer, not the tool grant. The native exact-Agent tool registry plus process/materialization and OS boundaries remain authoritative.

## Real pinned DSH useful tool journey

The disposable DSH fixture was strengthened from one in-memory fixture tool to two first-profile tools scoped onto the exact Agent during the serial `agent/created` edge:

### `read_file`

Prototype restrictions:

- workspace-relative path only;
- absolute, dot-segment, backslash and hidden path components refused;
- lexical and realpath containment required;
- direct regular files only; symlink final path refused;
- source file <= 1 MiB;
- one read returns at most 65,536 UTF-8 bytes;
- optional offset/length are bounded safe integers;
- result contains relative path, text, file size and SHA-256 of returned bytes.

### `search_text`

Prototype restrictions:

- literal query only, 1–256 characters, no newline;
- hidden entries and symlinks skipped;
- lexical traversal cannot escape the real workspace root;
- <=128 regular files;
- <=65,536 bytes per file;
- <=1 MiB total scanned bytes;
- <=50 matches;
- invalid/binary/oversized files are not surfaced;
- deterministic lexical traversal;
- result contains bounded path/line/text matches plus scanned-file/byte counts.

These restrictions are deliberately narrower than a general filesystem capability. Production still requires the existing owner to bind the exact workspace/isolation policy; this prototype does not create a second protected-path authority.

### Executed positive path

The real confined DSH process performs three inert model steps:

1. model requests `read_file` for the committed fixture evidence;
2. DSH executes the real scoped tool and the second model step consumes its tool result, then requests `search_text`;
3. DSH executes literal search and the third model step consumes that result before producing final schema-valid JSON.

The existing Mastermind ACP consumer observes both exact tool lifecycles and accepts the final result through the existing `WorkerResult` path. The workspace remains clean.

Measured external provider calls: **0**.

## Pre-prompt refusal proof

The serial Agent-created hook writes a fresh transient attestation before DSH ACP `session/new` returns. The parent pre-prompt callback joins:

- exact returned ACP session id;
- requested plain model id;
- observed provider-scoped ACP model option;
- exact native process/run identity;
- exact Agent-scoped tool census.

In the positive control, that joined evidence permits prompt.

In a deliberate parent-refusal case:

- Agent-created attestation still exists;
- pre-prompt callback refuses;
- result is `ACP_PRE_PROMPT_REFUSED`;
- fixture model-call stderr is empty;
- **zero model calls start**.

This is the required before-first-work distinction; refusal is not post-hoc validation.

## OS confinement proof

The provider-free prototype runs the complete DSH process under macOS deny-default Seatbelt before plugins initialize.

Observed canaries:

- exact workspace read: allowed;
- designated scratch write: allowed;
- out-of-scope `/etc/hosts` read: EPERM/EACCES;
- workspace write: EPERM/EACCES;
- child `/bin/echo` process: denied;
- loopback network connect: EPERM/EACCES.

A deliberate sandbox-widening mutation adding unrestricted process/network permission turns the confinement test RED; the network observation becomes `ECONNREFUSED` instead of an OS-policy denial.

This proves the policy is discriminating, not merely decorative.

## Verification receipt

Current disposable useful prototype:

- strict TypeScript typecheck against the exact pinned DSH dependency/project graph: **PASS**;
- selected common + predecessor + useful-provider-free regression set after the payload-provenance prototype: **115 tests, 0 failures, 0 errors, 0 skips**;
- useful native confinement tests: PASS;
- prototype bundle SHA-256: **`56ff5907b2140f7dd3be43dcdfe82e2f96a5d0af6994a9ffea73c84e0ab3e322`**;
- useful tool census: `read_file`, `search_text`;
- model steps in positive useful fixture: 3;
- external provider calls: 0.

The selected regression command intentionally omits one pre-existing local timing-sensitive test, `test_native_process_owner_executes_real_stdio_generation`. Exact #825 hosted CI is green. Under the same Mac environment, untouched #825 was nondeterministic (2 failures / 1 pass across three repeated isolated runs), while the useful prototype passed that exact legacy test 3/3 in the paired probe. Failed receipts showed valid ACP output followed by process SIGTERM at the intentionally short one-second cleanup grace. This is evidence of a pre-existing local timing edge, not evidence that N1 should change cleanup law. Do not widen the useful-worker wave to repair it without separate owner evidence.

## Discriminating useful-worker mutants

Three forbidden changes were tested independently:

1. remove pre-prompt callback invocation -> the zero-model-call refusal test turns RED;
2. remove the observed-tool name check -> the unknown `shell` event is admitted and its test turns RED;
3. widen the Seatbelt policy to unrestricted process/network -> the confinement test turns RED.

Source was restored after each mutation. No canonical branch received these prototype edits.

## New production blocker — confinement wrapper versus executable provenance

The whole-process Seatbelt wrapper exposes a material provenance gap in the current ACP native owner.

`AcpNativeProfile` currently requires `argv[0] == binary.real_path`, and `WorkerProcessRef.binary` therefore attests only argv[0].

For a confined launch:

```text
/usr/bin/sandbox-exec -f <policy> <pinned-node> <pinned-dsh-bundle>
```

the profile attests `sandbox-exec`. But macOS `sandbox-exec` performs `execvp`: the same launched PID becomes the inner Node executable. A live probe and the useful-worker pre-prompt test both observed the process executable as the exact pinned Node path while `WorkerProcessRef.binary.real_path` remained `/usr/bin/sandbox-exec`.

Therefore **production N1 must not call that receipt complete**.

### Required repair boundary

Extend the existing ACP native process/materialization owner rather than creating another identity plane.

The accepted owner should bind, before spawn:

- confinement launcher identity;
- exact inner Node binary attestation;
- exact DSH bundle/build-input digest;
- exact rendered argv and sandbox-policy digest.

After spawn, it must verify the live PID executable is the admitted Node executable using the existing OS process-path evidence primitive (or an owner-approved shared equivalent), while preserving the existing boot/start/pgid/session/UID/GID checks.

The resulting facts belong in the existing native launch attestation/receipt. Missing, changed or mismatched inner executable/bundle evidence refuses before prompt. Do not represent a wrapper attestation as the payload executable.

This is an owner-coordinated extension to `integrations/acp_worker/native.py` / its existing materialization contract, not a new process registry.

### Disposable repair-shape proof

The required native-owner shape was then implemented only in the disposable exact-#825 prototype, reusing the existing `BinaryAttestation` / `_assert_binary_unchanged` file-identity primitive rather than creating another hash or identity service.

The prototype adds to `AcpNativeProfile`:

- a bounded immutable tuple of launch payload attestations;
- one optional expected post-`execvp` executable, required to be a member of that tuple.

Before spawn, every admitted payload identity is rechecked with the existing file-identity primitive. After spawn, the existing macOS PID-to-executable primitive verifies the live process executable equals the admitted inner Node binary. The existing boot/start/pgid/session/UID/GID checks remain unchanged. The existing ACP native launch-attestation mapping carries the payload identities and expected post-exec executable.

The confined useful profile binds exactly:

1. `/usr/bin/sandbox-exec` as the launch wrapper;
2. the pinned Node executable as an admitted payload and required live post-exec executable;
3. the exact built DSH ACP bundle as another admitted payload.

Executed results:

- positive read/search/final WorkerResult path: PASS;
- deliberate parent pre-prompt refusal: PASS with zero model calls;
- Seatbelt effect canaries: PASS;
- deliberately setting the DSH bundle as the expected live executable: **refused before `AcpWorkerAdapter.start` can return**, with `ACP post-exec process executable does not match admission`;
- strict pinned-DSH TypeScript integration typecheck: PASS;
- refreshed selected regression receipt: **115 tests / 0 failures / 0 errors / 0 skips**;
- external provider calls: 0.

This removes uncertainty about whether the provenance gap is technically repairable inside the existing owner. It does **not** authorize those disposable changes for #825 or production. The incumbent ACP integration owner must still adopt the exact source boundary, and a canonical implementation must receive current-base CI/security plus independent review.

## Provider boundary remains held

No real DeepSeek/OpenCode provider call occurred.

Protected source still holds the OpenCode Go realm as SPEC_ONLY and has no active subscription harness binding for this DSH path. The useful provider-free prototype therefore grants no provider activation.

The prior provider-free HTTP composition remains informative only: a DSH-shaped `deepseek-v4.1-flash` Chat Completions request can traverse the existing Attempt-owned `GoHarnessEndpoint` with the child seeing only an endpoint capability; real credential/account/admission/effect authority stays outside DSH. DSH's pinned retry policy can be configured with `maxRetries=0`.

A real canary still requires the existing realm/enrollment/capacity/current-offer/usage-policy/canary authorities.

## Exact continuation

1. Do not modify #825 from this prototype; its source writer/review/adoption state remains separate.
2. Obtain incumbent #600/ACP owner adoption for the useful-worker common seams and the new confinement/provenance repair boundary.
3. Open one fresh bounded useful-N1 implementation carrier only after source custody is explicit.
4. Implement RED-first common pre-prompt/tool-observation semantics, then the native launch-provenance extension, then the DSH-specific read profile.
5. Reproduce this provider-free three-step read/search/result path on canonical source with current-base hosted/security proof and attributable independent review.
6. Only then request one bounded real provider canary through existing provider owners.
7. Rich resume, WRITE/TEST, general shell/MCP/browser capabilities and routing promotion remain later waves.

## Proof ceiling

This evidence establishes a technically viable, provider-free useful DSH READ/RESEARCH path and identifies its remaining production provenance gate.

It does **not** establish:

- real provider execution;
- provider/account enrollment;
- Executive production admission;
- independent source review;
- integration-owner adoption;
- production release;
- rich/resumable operation;
- WRITE/TEST capability;
- superiority of DSH over another harness.
