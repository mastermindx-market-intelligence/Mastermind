# Web-Sol Exact Continuation + Durable Return R3 Implementation Plan

> **Operation:** `web-sol-exact-continuation-return-r3-20260918-sol-001`  
> **Protected base:** `20dc89a201b9dfa65c2b6a2366072f45d885cb5c`  
> **Recovered R1/R2 stack:** exact replay through `c1f0341d`  
> **Authority:** Chairman HANDOFF B, 2026-09-18  
> **Scope:** smallest existing-owner continuation slice; no new session registry, wake system, transcript reader, arbitrary prompt sender, or browser controller.

## Outcome

Prove one production journey:

```text
exact managed Web CEO binding
→ exact current RuntimeBinding precondition
→ one fixed continuation submission
→ fresh exact-target generation START
→ canonical material terminal return
→ responsible parent consumes the return
→ explicit STOP
```

The implementation must preserve truthful no-effect / possible-effect / started classification and must survive stale target, wrong conversation, duplicate nonce/turn, and runtime-generation movement without blind replay.

## Existing owners and non-owners

- `control_plane.surface_bindings` remains navigation only. It is used only to resolve an exact managed profile coordinate and adapter instance. It is never promoted into lifecycle or authority.
- `control_plane.session_targets.RuntimeBinding` remains the public exact runtime-binding value.
- Web-Sol owns exact browser observation and the fixed continuation actuator.
- Executive Runtime owns canonical Job/Attempt/Worker/terminal result truth.
- Company Dialogue / terminal-return projection / Wake own durable return delivery and source correlation.
- Agent Dialogue close law owns explicit CONTINUE/STOP.

## Design

### 1. Runtime-only Web-Sol binding projection

Add a pure projection module that consumes:

1. one already-validated ChatGPT managed-profile navigation row;
2. one complete, stable, exact profile census with exactly one authenticated conversation;
3. one logical `SessionTarget` resolved from checked-in policy;
4. the current Web-Sol transport handshake boot identity.

It emits one immutable `RuntimeBinding` plus an exact target fingerprint. The binding:

- keeps the logical `session_alias` and `reasoning_surface` from `SessionTargetRegistry`;
- derives `binding_id` from the adapter instance, current native-host boot nonce, profile identity, and exact conversation fingerprint;
- uses generation `1` for that boot-bound identity;
- changes binding id when the native host/browser life changes, preventing generation-1 ABA;
- carries no URL, title, transcript, selector, token, cookie, or account credential.

This is a projection, not a persistence writer. No second RuntimeBinding store is introduced.

### 2. Pre-effect RuntimeBinding fence

Package `0.4.0` adds closed continuation request/receipt fields:

- `session_alias`
- `runtime_binding_id`
- `runtime_binding_generation`
- `runtime_binding_fingerprint`

The client completes the transport handshake first, projects the current binding, compares it with the caller's expected binding, and only then writes the continuation action frame. A mismatch returns a stable definite-no-effect refusal before the action frame exists on the native-host action channel.

The native host independently re-derives the same boot-bound binding and refuses drift before forwarding to the extension. The extension treats these fields as immutable correlation data and echoes them in the receipt.

### 3. Exact target from census, not URL/newest-tab selection

Add a closed helper that accepts only a full census receipt for the exact adapter instance and requires:

- `COMPLETE` inventory and stable consistency;
- no omitted/private/unobserved additions;
- exactly one unique conversation and one probed row;
- canonical URL-hash identity evidence;
- authenticated normal conversation;
- no provider error;
- exact conversation fingerprint present.

It returns a runtime target containing only profile identity and the fingerprint. It never elects by title, recency, tab order, selection state, or caller URL.

### 4. One-shot / ambiguity law

R2's fixed directive and closed outcomes remain:

- `CONTINUATION_NOT_SUBMITTED`
- `CONTINUATION_SUBMIT_EFFECT_UNKNOWN`
- `CONTINUATION_STARTED`

The client exposes no retry. Duplicate nonce/turn is rejected in the native host and extension for the current binding. A runtime restart changes the binding id; stale expected bindings are refused before effect. Ambiguous possible-send receipts remain `EFFECT_UNKNOWN` and are not replayed.

### 5. Canonical return / parent consumption / STOP

Do not add Web-Sol model-output reading. Production proof uses the existing Executive terminal-return and Wake owners:

1. create one disposable, bounded Executive child with a deterministic material artifact/result;
2. seal completion through Executive Runtime;
3. project the canonical terminal `RESULT` through the existing terminal-return event family;
4. correlate the resulting Wake to the responsible parent;
5. prove parent consumption using existing canonical source/ACK state, not UI text;
6. write one explicit `STOP` edge under Agent Dialogue close law.

If the authenticated Web CEO cannot reach the existing Executive/Dialogue tools after generation starts, classify the exact missing capability as `EXACT_HUMAN_GATE`; do not scrape output or fake semantic ACK.

## TDD sequence

### Task A — Exact target projection

Create failing tests for:

- stable sole authenticated census → exact target;
- wrong adapter instance, incomplete inventory, duplicate rows, auth wall, provider error, active unrelated generation, and ambiguous/missing fingerprint → refusal;
- no URL/title/transcript escapes the projected value.

Implement the smallest pure module and make tests green.

### Task B — RuntimeBinding projection

Create failing tests for:

- deterministic binding within one boot;
- different native boot nonce → different binding id;
- exact SessionTarget alias/surface preservation;
- malformed target/boot/profile/fingerprint refusal;
- generation remains positive and ABA-safe through binding-id rotation.

Implement the pure projector and make tests green.

### Task C — Protocol and transport fence

Create failing tests for:

- package `0.4.0` and closed request/receipt fields;
- stale expected binding returns definite no effect before frame write;
- native host re-derivation mismatch refuses before extension forwarding;
- receipt correlation includes exact RuntimeBinding fields;
- R2 no-effect/effect-unknown/started truth table remains unchanged;
- duplicate turn/nonce remains fenced;
- host restart rotates binding and stale request cannot submit.

Implement client/native/extension changes and make Python + Node suites green.

### Task D — Production bundle/install

- Render one immutable release bundle from the reviewed candidate tree.
- Verify hashes, package version, extension id, instance id, native wrapper and manifest.
- Install only into the selected managed test seat through the existing profile-local deployment path.
- Restart/reload only that exact browser/native-host instance.
- Re-census and prove package/instance/transport coherence.

### Task E — Live negative matrix

Prove and retain redacted receipts for:

- stale navigation binding refusal;
- wrong conversation refusal;
- duplicate nonce refusal;
- duplicate turn refusal;
- native-host/browser restart binding rotation and stale-binding refusal;
- injected lost/ambiguous submit response with zero replay.

### Task F — Live positive loop

- Establish one disposable exact target from a stable sole-conversation census.
- Pin its RuntimeBinding before effect.
- Submit exactly one fixed R2 continuation.
- Require fresh exact-target active generation for START.
- Observe canonical Executive terminal return through existing owner.
- Prove responsible parent consumption.
- Issue explicit STOP.

## Verification and review gates

- focused Python/Node suites;
- full Web-Sol suite;
- `git diff --check`;
- immutable candidate SHA and tree;
- exact-head CI/security;
- independent review packet against this outcome and negative matrix;
- production receipt bundle with secret-safe fingerprints only.

No merge or production claim until review is independent and current-head evidence is green.
