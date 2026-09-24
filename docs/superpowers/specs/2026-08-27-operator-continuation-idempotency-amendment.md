# Operator Continuity — Continuation Capsule Idempotency Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This closes an idempotency defect found during Sol adversarial review of OCR-3 before the architecture carrier is accepted.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1.  
**Parent architecture:** `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`  
**Affected plan:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr3-continuation-binding.md`.

## 1. Defect found

The first OCR-3 plan allowed a caller to pass `generated_at` into `build_current_continuation(...)` while `capsule_id` hashed the entire closed capsule. Two otherwise identical retries could therefore supply different current timestamps and mint different capsule IDs for the same source->target Attempt transition.

That violates the stable-operation/one-carrier law and would make provider/transport uncertainty capable of producing multiple continuation identities.

## 2. Frozen ruling

A target Attempt may have **at most one prepared continuation capsule identity**.

The lifecycle is:

```text
source/target canonical facts
-> build semantic continuation draft (NO generated_at, NO capsule_id)
-> fenced Executive PREPARE transaction
     - re-read exact current target Attempt/provider session/source terminal facts
     - refuse any existing semantically different preparation
     - assign generated_at from Executive Runtime clock
     - compute capsule_id over the finalized closed capsule
     - append OPERATOR_CONTINUATION_PREPARED with capsule identity/digest
-> return immutable finalized capsule bytes
-> every provider dispatch/reconciliation for that target Attempt reuses those exact bytes/id
-> exact provider-session ACK may append OPERATOR_CONTINUATION_ACKNOWLEDGED
```

Neither model, adapter, Slack, OpenClaw nor external caller authors `generated_at` or `capsule_id`.

## 3. Contract split

Use two typed concepts:

### `OperatorContinuationDraft`

Contains every semantic field needed to prepare continuation except:

```text
schema (may be fixed by constructor)
generated_at
capsule_id
```

The draft is rebuilt from current canonical sources immediately before PREPARE and is not durable lifecycle state by itself.

### `OperatorContinuation`

The finalized closed wire contains:

```text
schema = mastermind.operator_continuation.v1
all semantic draft fields
generated_at
capsule_id
```

`capsule_id` is SHA-256 over canonical JSON of the finalized capsule excluding only `capsule_id` itself. `generated_at` participates because it is now Executive-minted immutable preparation evidence, not caller entropy.

## 4. Preparation event is the idempotency authority

The existing Executive Event table remains the only durable seam.

`OPERATOR_CONTINUATION_PREPARED` must bind at least:

```text
schema_version
target_attempt_id
source_attempt_id
capsule_id
capsule_semantic_digest
provider_session_id
```

The event uses a deterministic `command_id` derived from the target Attempt, for example:

```text
operator-continuation:prepare:<target_attempt_id>
```

subject to current `_COMMAND_ID_RE`/length law.

Replay semantics:

- same target Attempt + same semantic draft + same current provider session -> return the exact previously prepared capsule; no second PREPARED Event;
- same target Attempt + changed semantic draft -> conflict/refuse;
- same target Attempt + changed provider session after preparation -> conflict/reconciliation; do not mint another capsule;
- new target Attempt -> new preparation identity is allowed.

If reconstruction of the exact previously prepared finalized capsule from Event data is required, the PREPARED Event must contain either the complete bounded capsule or enough canonical fields/digest pairs to reproduce it exactly. Prefer the complete bounded secret-free capsule in the existing Event payload if it stays within current Event payload limits; do not create a capsule table/file store.

## 5. Source movement before vs after PREPARE

Before PREPARE, current GitHub/Agent OS/runtime source facts may legitimately move. Rebuild the draft and use current accepted source law.

After PREPARE, material source movement does **not** mutate the capsule. The target provider operation is bound to the prepared source snapshot. If the movement invalidates work authority/safety before dispatch, refuse/cancel/reconcile the target Attempt under existing law; do not overwrite the prepared capsule under the same Attempt.

A later lawful Attempt may prepare a new capsule against newer sources.

## 6. ACK law

`OPERATOR_CONTINUATION_ACKNOWLEDGED` is also deterministic/idempotent for the exact target Attempt + capsule + provider session. A changed capsule/provider session conflicts.

ACK remains evidence that the exact bound provider session accepted/consumed the exact prepared continuation-bearing turn. It is not model-authored authority, Job completion or Wake `TARGET_ACKNOWLEDGED`.

## 7. OCR-3 implementation corrections

When implementing OCR-3, supersede these draft-plan details:

- do **not** expose `generated_at` as a caller argument to `build_current_continuation()`;
- `build_current_continuation()` should return a semantic draft/current-source material, not a finalized replayable capsule;
- finalization and PREPARED Event persistence happen together under the active target Attempt lease/fence;
- tests must call PREPARE twice and prove byte-identical finalized capsule/id with exactly one Event;
- tests must prove changed semantic draft or provider session under the same target Attempt refuses rather than minting capsule #2;
- timeout/effect uncertainty after PREPARE reuses the existing prepared capsule identity.

## 8. No-rebuild proof

This repair adds no database/table, file-backed capsule cache, retry registry or transport cursor. Existing Executive Events plus exact target Attempt identity are sufficient.
