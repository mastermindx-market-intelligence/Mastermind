# Web-Sol Chat Context Continuity — Bounded Implementation Plan

> **Execution rule:** every child follows `RED -> GREEN -> exact-head CI/security -> independent review -> production proof` at the precision appropriate to that release. One logical modifying operation binds to one carrier until reconciled.

**Chairman operation:** `web-sol-chat-context-continuity-20260901-chairman-001`  
**CR-F0 operation:** `web-sol-chat-context-continuity-cr-f0-20260901-sol-001`  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Linear projection:** `MAS-198`  
**Protected source at plan freeze:** `187490f3d5676adf7a249d69afacedd00b3efcec`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Current state:** `RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT`.

**No browser/runtime implementation is authorized by CR-F0.** CR-F0 freezes law, design, tests, dependency gates, carrier boundaries, and proof sequence only.

## 1. Program objective

Deliver governed exact-session succession for future ChatGPT Project Sol conversations:

```text
exact bound predecessor becomes rotation-required
-> one same-profile/same-Project successor
-> one deterministic continuation bootstrap
-> exact successor surface verification
-> accepted semantic readiness
-> CAS/ABA-safe RuntimeBinding generation succession
-> predecessor fencing
-> navigation projection
-> successor completes the next observable governed action
```

The program is not complete until one **real approved Project Sol rotation** succeeds without Chairman opening a chat, copying text, or selecting a session.

## 2. Authority and carrier precedence

Before each child starts:

1. re-pin protected Mastermind;
2. atomically load the current Skillpack from that exact SHA;
3. reconcile current Executive/Agent OS responsibility;
4. inspect open GitHub carriers and immutable heads;
5. inspect current Slack dialogue/carrier state;
6. preserve effect uncertainty and watcher law;
7. freeze exact scope and non-goals.

Current implementation carriers that must be preserved:

- **PR #306** / `sol/wsx-r1-self-reconstitution-20260901` owns R1 service-worker/browser reconstitution and its bounded review repairs.
- **PR #308** / `sol/wsx-t1-transport-hardening-20260901` owns T1 native transport hardening and its bounded review repairs.

**Do not absorb or replace either existing carrier.** Do not reset, rebase away accepted evidence, copy stale master over them, or create sibling repair PRs. Context-rotation implementation waits for their accepted protected descendants or explicitly declares a reviewed stack.

Every later child is **one independently useful capability per PR**. The parent operation is not one giant implementation carrier.

## 3. Release graph

```text
R1 #306 repair ----\
                     -> accepted/protected Web-Sol base -> CR-P1
T1 #308 repair ----/                               |       |
                                                     |       +-> CR-D1
CR-F0 source law -----------------------------------+       |
                                                             +-> CR-B1 -> CR-D1 -> CR-PROD1
provider continuation falsifier -------------------+
RuntimeBinding writer discovery gate --------------+
semantic ACK owner discovery gate -----------------+
```

CR-P1 may be implemented before CR-B1 only if it has no RuntimeBinding authority effect. CR-B1 cannot start until both owner-discovery gates are resolved.

## 4. Existing-carrier repair lane

### Task R1-R — preserve and repair PR #306

**Mission:** make one installed MV3 worker restore its exact-profile target mapping and native connection after worker/browser interruption without resetting an exhausted reconnect sequence or hanging forever in handshake.

**Carrier:** PR #306 / `sol/wsx-r1-self-reconstitution-20260901` only.

**Required behavior:**

- one volatile reconnect generation per recovery sequence;
- probes may report/forward only; they never start or reset a reconnect generation;
- retries remain `1m -> 5m -> 15m -> stop` within one generation;
- connected-but-silent native port has a bounded handshake timeout;
- successful handshake cancels the exact timeout;
- stale alarm/disconnect callbacks from old port/generation are inert;
- no action persistence, replay, queue, polling loop, or retry ledger;
- service-worker restart may start one fresh boot generation but never replay prior browser actions.

**RED tests:**

- exhausted generation followed by valid probe creates no new native connection;
- silent connected port times out and schedules only the next bounded reconnect;
- successful ACK cancels timeout;
- stale timeout after success has no effect;
- old-generation alarm after restart is inert.

**GREEN files:** existing R1 production/test paths only. Do not add generic browser actions or persistent reconnect state.

**Acceptance:** exact-head repository CI/security green, fresh independent review resolves prior CHANGES_REQUESTED, PR remains `BUILT_NOT_PROVEN / PRODUCTION_NOT_INSTALLED` until installed D1/D2 evidence.

### Task T1-R — preserve and repair PR #308

**Mission:** make deadline-aware native framing correct on real Chrome stdio pipes when Python buffering could otherwise prefetch payload bytes beyond the selected four-byte header.

**Carrier:** PR #308 / `sol/wsx-t1-transport-hardening-20260901` only.

**Required behavior:**

- use stable unbuffered raw stdin/stdout pipe endpoints at the native-host entry boundary;
- preserve one monotonic deadline through handshake/action/receipt;
- retain `select` readiness for real unbuffered descriptors;
- retain non-fd test-stream support;
- do not add a reader thread, queue, retry plane, second transport, or busy loop;
- preserve public action/effect semantics.

**RED test:** a real `os.pipe()` containing a full framed document while the writer remains open must reproduce current buffered-prefetch timeout and pass after the entry boundary uses raw streams.

**GREEN files:** native host plus exact regression test only unless an existing deployment assertion requires bounded reconciliation.

**Acceptance:** exact-head repository CI/security green, fresh independent review resolves prior CHANGES_REQUESTED, state remains `BUILT_NOT_PROVEN / PRODUCTION_NOT_INSTALLED` until real host/browser proof.

## 5. CR-F0 — context rotation source law

**Mission:** freeze exact owner boundaries, identity law, closed actions, classifier, effect states, deterministic bootstrap, 12-step sequence, RuntimeBinding succession, provider falsifiers, failure matrix, release DAG, and no-rebuild boundaries.

**Carrier:** `sol/web-sol-chat-continuity-cr-f0-20260901` / one records-only PR.

**Files:**

- `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`
- `docs/superpowers/specs/2026-09-01-web-sol-chat-context-continuity-design.md`
- `docs/superpowers/plans/2026-09-01-web-sol-chat-context-continuity.md`
- `tests/test_web_sol_context_rotation_source_law.py`

**RED:** source-contract test fails because the law/spec/plan do not exist.

**GREEN:** all required records exist and assert:

- Sol identity is not a chat;
- title/history are advisory;
- no duplicate lifecycle/session/memory/retry/authority plane;
- closed Project-only successor/bootstrap/verify actions;
- generic provider error is not exact context exhaustion;
- effect uncertainty blocks modifying continuation;
- visible output is not semantic ACK;
- RuntimeBinding is generation-fenced and CAS/ABA-safe;
- navigation cannot roll authority back;
- product remains `SPEC_ONLY`.

**Stop:** no extension, native host, RuntimeBinding, Agent Relay, Wake, surface-binding, account, install, or production mutation.

## 6. PF-1 — provider continuation falsifier

**Mission:** establish what current ChatGPT Project context actually contributes and when exact successor identity becomes observable, without using sensitive company state.

**Environment:** one **disposable/non-sensitive ChatGPT Project**, one approved disposable managed profile, harmless unique synthetic markers, no Mastermind secrets or production operation.

**Experiments:**

1. new Project chat: continue exact predecessor title;
2. **duplicate predecessor titles**;
3. **renamed predecessor title**;
4. provide **exact predecessor reference/URL** if supported;
5. ask for a **synthetic fact that existed ONLY in the predecessor**;
6. repeat outside the Project to establish whether **Project membership is essential**;
7. observe creation before first message, if possible;
8. observe first-message identity minting;
9. interrupt service worker/native transport between creation and submission;
10. make Project history unavailable where supported.

**Evidence packet:** exact source date, profile/Project/predecessor/successor fingerprints, observed provider stages, screenshots/receipts with no transcript content beyond harmless markers, and typed conclusions:

```text
TITLE_CONTINUATION_RELIABILITY
DUPLICATE_TITLE_BEHAVIOR
RENAMED_TITLE_BEHAVIOR
PROJECT_HISTORY_SCOPE
PREDECESSOR_ONLY_FACT_RECALL
SUCCESSOR_ID_MINTING_STAGE
CREATE_AND_SUBMIT_EFFECT_SHAPE
```

**Non-authority rule:** Project history may improve rehydration UX but never elects predecessor/successor or replaces canonical continuation.

**Stop condition:** if exact same-Project successor identity cannot be verified without generic browser control, return the typed blocker before CR-P1 implementation.

## 7. OWN-1 — RuntimeBinding writer discovery gate

**Mission:** locate and prove the current canonical writer/source for ChatGPT RuntimeBinding succession before writing integration code.

This is the **RuntimeBinding writer discovery gate**.

**Archaeology targets:**

- `control_plane/session_targets.py` contracts;
- `control_plane/runtime_binding_projection.py` read projection;
- Executive Runtime/Operator Harness persistence source;
- accepted SessionTargetRegistry owner;
- current binding-generation and provider-handle source;
- CAS/ABA enforcement and lost-response reconciliation path;
- exact consumer that fences stale generations.

**Required decision:**

```text
WRITER_PROVEN_EXISTING
WRITER_EXISTS_BUT_CHATGPT_UNSUPPORTED
WRITER_MISSING_ARCHITECTURE_RULING_REQUIRED
```

The read-only dataclass, storeless resolver, and `surface_bindings` are not a writer. Do not create a second persistence store.

**Proof:** a test fixture demonstrates generation N current, exactly one N+1 commit, stale/duplicate/ABA refusal, and readback reconciliation.

## 8. OWN-2 — semantic readiness owner discovery gate

**Mission:** identify the accepted production path that converts a successor’s deterministic bootstrap into organizational `PICKUP_ACK` / `START` without scraping model output.

This is the **semantic ACK owner discovery gate**.

**Archaeology targets:**

- Agent Relay;
- Company Dialogue;
- Wake and accepted continuation transport;
- plugin/MCP paths available to ChatGPT Project Sol;
- source-resolution and receiver-binding law;
- current production proof status.

**Required decision:**

```text
SEMANTIC_ACK_OWNER_PROVEN
SEMANTIC_ACK_OWNER_EXISTS_BUT_NOT_CHATGPT_PROVEN
SEMANTIC_ACK_OWNER_MISSING_ARCHITECTURE_RULING_REQUIRED
```

A visible generated response, browser DOM text, conversation title, or inferred intent is not ACK. If the owner is not production-proven, CR-B1 remains blocked while CR-P1 may still prove browser-side successor/bootstrap behavior without authority transfer.

## 9. CR-P1 — exact successor + deterministic bootstrap

**Prerequisites:**

- CR-F0 accepted/protected;
- R1/T1 accepted base or explicitly reviewed stack;
- **provider continuation falsifier** complete;
- exact Project/profile identity fields and provider identity-minting stage frozen;
- one authorized disposable profile available for tests.

**Mission:** from one exact bound Project predecessor, create one exact same-profile/same-Project successor, deliver one deterministic bootstrap, and verify the exact successor surface.

**One independently useful capability:** browser-side exact successor/bootstrap, no RuntimeBinding authority transfer.

**Likely files after archaeology:**

- new versioned Web-Sol rotation protocol module;
- extension background closed semantic handlers;
- content-script provider adapter limited to creation/bootstrap/verification;
- native client/host framing extensions only where required by the new protocol;
- deterministic bootstrap renderer/validator;
- exact provider fixture tests;
- deployment capability digest/version reconciliation.

Do not silently widen `mastermind.web_sol_surface_action.v1`. Use a separately versioned request/receipt contract and explicit capability digest.

### 9.1 RED contract tests

Fail before implementation for:

- free-form Project/profile/account URL;
- non-Project predecessor;
- title-only predecessor;
- wrong Project/profile/account;
- same conversation returned as successor;
- two candidate successors;
- invalid/stale binding generation;
- arbitrary bootstrap text;
- missing/stale continuation reference;
- unresolved predecessor effect;
- second create attempt after `EFFECT_UNKNOWN`;
- second bootstrap after ambiguous submission;
- transcript/output/DOM export fields;
- service-worker/native restart at each effect boundary.

### 9.2 Provider behavior tests

Use recorded synthetic fixtures from PF-1 plus disposable browser tests. Prove:

- exact target derived from predecessor binding;
- one creation attempt;
- exact identity obtained at the provider’s real minting stage;
- same profile and Project;
- different new conversation identity;
- one deterministic bootstrap;
- exact successor responsive;
- no transcript reads;
- no title/newest-tab election;
- no blind retry after ambiguous effect.

### 9.3 CR-P1 statuses

Closed result examples:

```text
SUCCESSOR_CREATED_VERIFIED
SUCCESSOR_CREATE_NO_EFFECT
SUCCESSOR_CREATE_EFFECT_UNKNOWN
BOOTSTRAP_DELIVERED_VERIFIED
BOOTSTRAP_NO_EFFECT
BOOTSTRAP_EFFECT_UNKNOWN
SUCCESSOR_UNRESPONSIVE
WRONG_PROJECT
WRONG_PROFILE
AMBIGUOUS_SUCCESSOR
NON_PROJECT_CONVERSATION_UNSUPPORTED
```

### 9.4 Acceptance

Exactly one correct successor and one bootstrap can be created/verified on the disposable Project. State is `BUILT_NOT_PROVEN` until installed browser proof. No RuntimeBinding, semantic ACK, or production continuity claim.

## 10. CR-B1 — RuntimeBinding succession

**Prerequisites:**

- CR-P1 exact successor receipt;
- OWN-1 `WRITER_PROVEN_EXISTING`;
- OWN-2 `SEMANTIC_ACK_OWNER_PROVEN`;
- accepted semantic readiness for the exact successor;
- predecessor effect fence clear.

**Mission:** preserve one logical responsibility while advancing the existing canonical binding exactly generation N -> N+1 and fencing generation N.

**RED tests:**

- expected generation mismatch;
- duplicate N+1;
- ABA N -> N+1 -> stale N request;
- successor profile/Project mismatch;
- successor handle mismatch;
- missing semantic ACK;
- visible text without ACK;
- predecessor `EFFECT_UNKNOWN`;
- writer response lost after possible commit;
- navigation update failure after commit;
- stale predecessor action after cutover.

**GREEN invariants:**

- preserve `responsibility_ref` and `session_alias`;
- compare exact predecessor binding/generation/provider handle;
- commit only N+1 through canonical writer;
- readback reconciles lost response;
- generation N remains stale forever;
- successor is authoritative even if navigation is stale;
- no second RuntimeBinding store;
- no title/browser/tab authority.

**Acceptance:** deterministic fixture + integrated disposable binding proof; independent review; no production claim before CR-D1/CR-PROD1.

## 11. CR-D1 — disposable end-to-end canary

**Environment:** synthetic responsibility, **disposable/non-sensitive ChatGPT Project**, disposable approved managed profile, synthetic Agent OS continuation, no production Mastermind responsibility.

**Mission:** prove the whole path with **Zero Chairman click/type/message shuttling**.

Sequence:

1. establish exact predecessor and generation N;
2. create harmless canonical state and one completed item that must not restart;
3. create one open reciprocal dialogue edge;
4. mark predecessor `ROTATION_REQUIRED`;
5. inject no unresolved effect;
6. create exactly one successor;
7. deliver exactly one bootstrap;
8. verify successor surface;
9. establish semantic ACK through the accepted owner;
10. commit RuntimeBinding N+1;
11. fail a navigation update once and prove authority remains N+1;
12. restore navigation projection;
13. revive predecessor and prove stale refusal;
14. successor completes one bounded observable task;
15. verify completed work was not restarted and open dialogue was recovered.

### 11.1 Required fault injection

- **wrong ChatGPT Project**;
- **wrong managed profile/account**;
- **two candidate new conversations**;
- provider creates new chat but receipt is lost;
- bootstrap may have submitted but receipt is lost;
- successor never becomes responsive;
- **successor responds visibly but semantic ACK is absent**;
- predecessor still has an active generation;
- predecessor has `EFFECT_UNKNOWN`;
- **RuntimeBinding generation race / ABA**;
- navigation binding update fails after authority cutover;
- **extension service worker restarts during rotation**;
- **native transport disconnects during each effect boundary**;
- auth wall;
- provider transient;
- generic “Thinking failed” without proof of context exhaustion;
- **predecessor already totally dead before checkpoint**;
- **ChatGPT Project history unavailable**;
- **Agent OS continuation record unavailable/stale**;
- **stale predecessor later becomes responsive again**.

Every ambiguous mutation must produce no duplicate successor/bootstrap/binding swap.

### 11.2 CR-D1 acceptance packet

- exact protected SHA/Skillpack;
- child operation and carrier;
- reviewed installed source digest;
- profile/Project/predecessor/successor fingerprints;
- create/bootstrap effect receipts;
- semantic ACK receipt;
- generation N/N+1 receipt;
- stale predecessor refusal;
- next bounded action evidence;
- fault-injection matrix;
- rollback/uninstall/readback receipts;
- zero Chairman interaction declaration backed by event evidence.

State after a passing disposable canary is still not `PROVEN_LIVE` for production.

## 12. CR-PROD1 — one real approved Sol rotation

**Prerequisites:** all earlier waves accepted; reviewed exact source installed; admin/credential gates satisfied; rollback rehearsed; no unresolved effects; exact real responsibility selected through current authority.

**Mission:** perform one **real approved Project Sol rotation** and prove continuity.

Product journey:

1. current bound real Project Sol is deliberately made rotation-required;
2. exactly one successor is created in its exact profile/Project;
3. one bounded bootstrap is delivered;
4. successor reconstructs protected source and Agent OS state;
5. completed work does not restart;
6. open dialogue is recovered;
7. semantic readiness is accepted;
8. RuntimeBinding advances N -> N+1;
9. predecessor N is fenced;
10. navigation follows successor or reports truthful degradation;
11. successor completes the next governed action;
12. stale predecessor cannot complete it.

**Do not call the program PROVEN_LIVE before CR-PROD1.** Merge, green CI, installed extension, visible response, ACK, RuntimeBinding swap, and next-action completion remain separate evidence facts.

## 13. Proof and review rules

For every child:

1. freeze exact operation, carrier, base, paths, non-goals, and authority;
2. commit a discriminating RED before production implementation;
3. capture hosted RED receipt;
4. implement the smallest coherent vertical capability;
5. run focused tests, compile/static checks, full discovered repository suite, and security analysis;
6. compare exact head to protected base;
7. obtain independent adversarial review from a non-author account;
8. repair only on the same carrier;
9. re-run exact-head proof after every repair;
10. obtain disposable/production browser proof where applicable;
11. Sol reviews against Chairman outcome;
12. update Agent OS and selective Linear projection;
13. terminally close watchers/dialogues with explicit STOP.

A stale PR body, prior green head, Slack prose, QUEUED state, or merge is not proof of the current exact head or production behavior.

## 14. No-rebuild and security checklist

Every child must prove absence of:

- Chat-session registry;
- transcript/model-output store;
- second RuntimeBinding source;
- second lifecycle;
- rollover queue or retry ledger;
- browser-tab authority;
- generic click/type/send/navigation/JS/selectors;
- arbitrary input text;
- cookie/storage/clipboard/proxy/fingerprint/credential access;
- account switching;
- caller-selected profile/Project/account;
- title/newest-tab selection;
- silent OpenClaw fallback;
- action replay after reconnect;
- authority rollback for navigation cosmetics;
- usage-limit evasion.

## 15. Durable-record sequence

After CR-F0 material acceptance:

1. add an Agent OS decision recording exact chat succession identity/authority law;
2. update `WS:CHAIRMAN-CONTROL-ROOM` capability state and next action;
3. add a continuation handoff with exact PR/head/proof/gates;
4. project current status to `MAS-198` without overriding GitHub truth;
5. close obsolete watcher/dialogue edges explicitly.

After each later release, update the same workstream/decision chain. Do not create a context-rotation workstream or memory database.

## 16. Stop/escalation conditions

Stop and return a typed dependency only when:

- protected laws materially conflict and cannot be reconciled;
- exact same-Project successor creation/verification requires forbidden generic browser authority;
- canonical RuntimeBinding writer is absent;
- semantic ACK owner is absent/unproven and an authority transfer is requested;
- production admin/credential action requires Chairman intervention;
- a modifying effect is `EFFECT_UNKNOWN` and current owners cannot reconcile it.

Routine profile, account, Project, predecessor, or successor selection is derived from exact bindings and is not a Chairman question.

## 17. Exact next action after CR-F0

1. finish same-carrier R1 #306 and T1 #308 repairs;
2. obtain fresh exact-head CI/security/review;
3. protect accepted descendants;
4. execute PF-1 provider continuation falsifier;
5. complete OWN-1 and OWN-2 discovery gates;
6. commission CR-P1 against the accepted base;
7. proceed to CR-B1, CR-D1, then CR-PROD1 without combining their authority/effect boundaries.
