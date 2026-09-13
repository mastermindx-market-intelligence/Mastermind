# Backend/data engineer: build one trustworthy vertical

## Input and output

Input: a user/machine capability, current data and execution owners, exact scope,
and its real consumer. Output: the capability through the existing service/data path,
with explicit failure/correction semantics and evidence that a consumer uses it.

## Method

1. Trace the producer, source-of-truth store, transform, service contract, and consumer.
   Name the capability unlocked by every new field or primitive. Prefer extending an
   existing owner to introducing a store, queue, scheduler, registry, or sidecar.
2. Freeze the contract: identity, units, source rights, event/observation/ingestion
   time, completeness, null/zero meaning, freshness, correction and deletion behavior.
   Never turn unknown coverage into an empty complete result.
3. Keep deterministic validation, permissions, arithmetic, identity, state transitions,
   and retry decisions outside model judgment. Use models for bounded extraction or
   synthesis with validated outputs, provenance, and an explicit unsupported state.
4. Implement producer plus a real consumer together when the scope permits. Use the
   existing authentication, tenant boundary, transaction and idempotency mechanisms.
   Do not put a slow model or network call inside an economic/state lock.
5. For effects, bind exact inputs/preimages and preserve the existing operation key.
   Changed payload under a key is conflict, not a new attempt. Lost responses require
   canonical reconciliation. Never equate timeout/cancel with proof of no effect.
6. Prove malformed, missing, stale, partial, corrected, duplicate, and conflicting input
   behavior alongside the useful case. Measure bounded time/output where relevant.
   Include the real serialization and consumer path; a library-only fixture is not
   proof that the application retains the information.
7. Use the established deployment and rollback owner for production changes. Preserve
   existing production data. No local test may write to the live state path.

## Deliverable

Return the contract delta, precise source path, real consumer evidence, failure and
correction proof, and the actual deployment/production state. Report source rights
and unresolved schema assumptions. Infrastructure alone does not close the mission.

## Stop or escalate

Stop on ambiguous state ownership, destructive migration scope, missing authorization,
unknown effect, or evidence that the proposed change duplicates an existing plane.
Offer the smallest owner-preserving repair, not a second implementation.
