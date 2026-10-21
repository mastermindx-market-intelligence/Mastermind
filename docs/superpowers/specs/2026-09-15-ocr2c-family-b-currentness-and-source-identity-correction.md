# OCR-2C Family B - Currentness realization and source-identity correction

**Date:** 2026-09-15 (America/New_York; evidence run on 2026-09-16 UTC)  
**Owner:** Sol / existing WS:EXECUTIVE-CAPACITY-FABRIC  
**Operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `AUTHOR-SIDE CORRECTION CANDIDATE / RECORDS ONLY / SPEC_ONLY / HOLD FOR INDEPENDENT REVIEW`  
**Protected procedure/source pin:** Mastermind `7642aea155d2817219135b24246b55c1d7611c66`, Sol Skillpack 1.0.1 / bootstrap-major 1.  
**Macro material source pin:** `ad3091c11c336bd20e031301346b17fdfb326450`.  
**Pre-correction candidates:** Mastermind #662 `30f8a4c1188f19f99622da5503a70b643c1ef167`; Macro #7162 `d5ac0d61f1a95b9d21441a6dc3b1905bde6b7c6d`.

## Why this is a bounded repair

The prior source-evidence addendum on #662 raised a concrete B2 currentness concern. A hermetic characterization now reproduces it. This record repairs the affected architectural interpretation; it does not invent another account, realm, quota, lifecycle or retry owner and does not claim independent review. Sol retains the existing records branches. No B1+ implementation or provider effect is released.

Within these two pending PRs, this correction has narrow precedence over their primary designs, implementation plan, multi-host amendments and decision/handoff prose only for:

1. claims that the current V1 receipt seam already supplies authoritative per-realm current state;
2. any implication that domain/host identity alone proves model-family quota eligibility;
3. promises that editing a V1 material-source file can preserve its old material-source digest or complete serialized snapshot bytes.

All other frozen boundaries remain: Macro owns `capacity_capability_id + capability_generation`; the incumbent provider-realm concept/name `realm_generation` is retained; subscription-canary `capacity_generation` remains separate; the production CF2 join/claim/replay path is reused; `/login` with dedicated OS-principal/Keychain isolation remains the first-production auth boundary.

## 1. What the existing realm receipt actually proves

At the protected pin, `control_plane/codex_provider_realm.py` blob `ab1e475e4f0f2b316f228ffbf2e95218d0219a7a` has one closure-global `enrollment_state`. Its issuer accepts caller-supplied `generation`, checks positive integer syntax, reads that global state and HMAC-seals the embedded fields. Its verifier checks the embedded identity and HMAC, not an authoritative current generation/state for the requested realm.

`ops/executive_os/provider_realm_facts.py` blob `a07102df9ce6604ff77d92b752c4b518445aa7f5` delegates validation to that seam. A sealed historical receipt can therefore remain internally valid after fixture enrollment changes. This is evidence integrity, not proof that it may authorize a new execution now.

The current non-test seam has no installed key/enrollment in this characterization and fails closed without them. These results are NOT a production exploit, NOT evidence that a real revoked account executed work, and NOT a reason to weaken the test-only guards. Reusing the existing owner concept does not mean its production realization is already built.

### Executed evidence

Command: `python -m pytest -q test_owner_gap.py` in an isolated ChatGPT sandbox evidence directory.

Result: **5 passed in 0.05s**. Three characterization cases reproduced behavior that B2 must not mistake for V2 authorization, and two controls retained the existing integrity/refusal behavior:

| Case | Observed under the V1 fixture | V2 implication |
|---|---|---|
| Same binding issued generation 9 then 2 | Both receipts pass integrity verification | Positive integer validation is not owner-current generation issuance |
| Enrolled receipt checked while fixture owner is unenrolled | Old receipt still passes integrity verification | New execution needs a separate currentness check |
| A and B issued before/after one enrollment-state change | Both follow the same global state | Per-realm current state is not implemented by this seam |
| Embedded generation altered without matching seal | Rejected | Integrity defense remains useful |
| Owner fixture key absent | Mint refused | Missing owner realization must stay fail-closed |

Scope: unchanged owner-function excerpts with a stub catalog, the unchanged full realm-facts module, public fixture key only, and actual pytest fixtures. The copied realm-facts file's Git blob was recomputed and matched `a07102df...`. This is not a full-repository integration test or installed-host proof.

Evidence file SHA-256:

```text
realm_facts.py         40a836dce30c7686d3e2c64fabcd70f58f57657c4e772c5a3a15450a032a2c84
realm_owner_excerpt.py ded8b5228a21e45b41c157af6be9aa3b4ad17b5c53921cb0315c490388afbed8
test_owner_gap.py     d5c7e8068a2fe45ce710bdfc28291ac0cf1010f76ee7c1c451e7e9cf942228e5
```

The offline evidence bundle accompanies this Sol return. The source identities and behavior above remain recoverable from GitHub even without the disposable chat/sandbox.

## 2. B2 must realize current ownership, not rename a receipt

B2's acceptance now explicitly requires two separate operations at the existing provider-realm boundary:

- **Historical integrity:** establish that a receipt accurately describes the owner-issued fact at issuance. A later revocation must not rewrite that historical fact.
- **Current execution eligibility:** establish that the exact realm remains enrolled at the current owner-issued generation and still belongs to the current registered Macro capability generation. An integrity-valid receipt alone is insufficient.

Current state is scoped to `(host_ref, capacity_capability_id)`, with the accepted `capability_generation`, incumbent `realm_generation`, enrollment state and exact principal/config custody. One realm's enrollment change must not alter another realm's state merely because both use the same module, provider or host.

Only the accepted provisioning/realm owner may allocate or advance `realm_generation` and change enrollment state. A Worker, model request, preflight, receipt consumer or arbitrary caller cannot supply a desired generation/state. Re-enrollment must not make an old generation current again. Ordinary token refresh is not a provider-domain replacement.

A request cannot establish Macro registration provenance by computing the public `registration_receipt_digest`. The realm owner must consume the exact current registration through an approved owner/source-acquisition boundary and compare identity, generation, state and source evidence. Public hashes detect content changes; they do not authenticate a caller.

### Concrete owner-realization gate

Before B2 implementation START, the bounded B2 pickup must name and freeze the actual incumbent provisioning/host-config authority that persists each realm's current generation/state, its privileged update seam, and the read seam used by claim and pre-spawn validation. That realization is **not proven by the current V1 closure**.

If current source/host composition does not supply those seams, return `REALM_OWNER_REALIZATION_REQUIRED` as a design/provisioning blocker to Sol. Do not return a receipt-only B2 implementation as complete; do not introduce an ad hoc registry database, credential copier, signing daemon, or second realm/account owner. A missing implementation behind the existing owner must be designed there before it is coded or activated.

The accepted CF2 claim path and existing broker admission must fence owner-current state at their actual effect boundary. A revocation between observation and provider spawn cannot be ignored because the earlier receipt was valid. Exact transaction/lease/fence mechanics must be frozen against those existing owners; this record does not assert a cross-repository transaction already exists.

Historical replay returns the original accepted claim evidence without re-reading or re-ranking current provider state. It must not spawn a new provider process. Any genuinely new execution uses current owner eligibility. This preserves both truthful history and revocation safety.

Required discriminators: A enrolled/B unenrolled concurrently; old generation after re-enrollment refused for a new execution; embedded tampering refused; public digest forgery refused; domain-generation and realm-generation staleness rejected independently; wrong host/principal/custody refused; owner unavailable fails closed; revocation during claim-to-spawn refuses or enters the existing effect-reconciliation path; replay remains historical and effect-free.

## 3. Provider-domain placement is not model-sublimit algebra

B0-B5 establish provider-domain/realm identity, observations and the versioned CF2 consumer boundary. They do not, by adding `realm_binding`, establish a resource relationship between a shared provider allowance and an additional model-family sublimit.

Until the existing Shared AI Provider Control / quota-economics / model-capability owners expose an accepted relationship contract, Family B must not claim model-family remaining quota, independent model wallets, or Fable-versus-Opus quota-aware placement from generic weekly/five-hour rows. The related #676 capability work is a dependency to reconcile, not evidence that this relationship has been implemented here.

Model Router continues to determine task/model suitability. Current known model restrictions remain binding; unknown model-resource evidence stays unknown under the applicable policy. Unknown does not automatically mean available, unavailable or unlimited. Host-replica deduplication cannot multiply either a shared domain allowance or a nested sublimit.

This is a capability ceiling, not a reduction of the end-state. Model-qualified placement remains a later composition proof through existing owners, never a second quota graph or per-model wallet service.

## 4. V1 compatibility must not freeze false source identity

At Macro `ad3091c...`, `engine/provider_capacity.py` blob `68eda49254003956dd43193ad1284959a0a14593` lists itself in `MATERIAL_SOURCE_PATHS`. `_material_rows()` hashes the actual bytes of every listed path. The B4 plan also proposes editing that same file. Therefore the earlier unconditional promise of unchanged V1 material-source digest/complete output bytes across that edit is unsatisfiable.

The corrected compatibility contract is:

1. The currently installed/pinned CF1/H0 producer release and its consumers remain untouched by B1-B4. No automatic source migration occurs.
2. V1 schema, slot inventory, evidence meaning, null/freshness rules and decision behavior remain compatible. Merely adding a V2 registry must not expand the V1 material-path census or insert native slots into V1.
3. If an existing V1 material-source file is changed, a newly built release must truthfully emit its new material-source identity. Any downstream digest change caused by that declared source identity must be visible and reviewed; never hard-code the old digest, hide the edited file from its source census or forge byte equivalence.
4. Golden tests compare exact bytes for the unchanged pinned release and same-source fixtures. For a necessary material-source change, tests explicitly account for the expected provenance delta while continuing to check all V1 behavioral fields. Do not broadly delete producer/audit/hash fields from tests and call that compatibility.
5. Adoption of a changed producer release remains a separate current-source acquisition/release gate. Share normalization through the existing owner; do not clone a second normalizer just to preserve a stale hash.

## 5. Review and continuation

These are author-side corrections motivated by executed characterization and direct source inspection. They do not satisfy independent review. The same pending review operation/carrier remains `ocr2c-family-b-paired-architecture-review-20260914-sol-001`, Slack `C0BSBM78V1N/1789456126.495979`.

Independent review must consume this correction with both exact candidate heads, attack the owner-currentness versus historical-integrity split, model-resource capability ceiling and honest V1 source-identity contract, then return PASS or REQUEST_CHANGES. Candidate head movement requires new exact-head checks; predecessor green is not reused as acceptance.

The Executive connection returned `Unauthorized - Manual reauthentication required` during this continuation; no CEO intent was submitted. No reviewer is bound merely because this evidence exists. B0 remains unaccepted until independent review, current-base integration/check evidence and explicit Sol source release. B1+ remains unstarted. No provider credential, login, capacity registration, runtime state, worker, host permission or browser/GUI effect was changed by this record.
