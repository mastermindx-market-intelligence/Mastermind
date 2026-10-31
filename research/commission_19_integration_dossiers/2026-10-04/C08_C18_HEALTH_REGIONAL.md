# C8/C18 — health, actual consumption and regional equivalence

Scope: partial MAS-264 dossier and MAS-270/H03 qualification. Verdict: **reuse the accepted health owner; qualify actual consumption and regional meaning without another catalogue, identity store or health score**.

## Immutable originals and valuable findings

- [C8 hardened observability report, Mastermind #1224](https://github.com/mastermindx-market-intelligence/Mastermind/blob/7cbb03a85cfa96b2a880c297b01fd1c8df3038d4/research/DATA_OBSERVABILITY_LIVE_CENSUS_COMMISSION_8_HARDENED_2026-10-04.md), head `7cbb03a85cfa96b2a880c297b01fd1c8df3038d4`: producer success, artifact freshness, reader observation and actual use are different facts; blindness is not absence; coverage needs an expected-universe generation.
- [C18 original package, Mastermind #1229](https://github.com/mastermindx-market-intelligence/Mastermind/tree/b502668857526d7da9fd69b9801493d387df951c/research/commission18_global_regional_data_parity), head `b502668857526d7da9fd69b9801493d387df951c`: regional parity means equivalent decision evidence, preserving local semantics rather than identical columns. Current snapshots cannot manufacture historical estimates or memberships.

The C18 files specifically reviewed here were `DATA_MODEL_AND_INTEGRATION.md`, `IMPLEMENTATION_HANDOFF.md` and `COVERAGE_AND_SOURCES.md`. This is not independent verification of every vendor/regulatory claim in the original package.

## Existing owners and current-source recensus

Macro pin: `9201f1602bfe47e05a63d61802fbed6f7f55a19d`; Mastermind pin: `5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f`.

| Surface | Current source evidence | Boundary |
|---|---|---|
| [Data OS registry](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/lib/dataos/registry.py#L115) | `DatasetContract` owns dataset ID, owner/producer, grain, temporal profile, code-consumer and licensing metadata; `Registry.consumers_of` derives dataset consumers from inputs | Declared dependencies are not actual-use receipts or legal entitlement |
| [T4 output health](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/output_health.py#L1029) | `resolve_output_health` is a pure injected-time view over Synapse/T1 and observations, with `reader_observations`, blindness and exact/upper dependency bounds | Preserve its existing precedence and nulls; no new monitor, persisted health truth or alpha weight |
| [T4 build adapter](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/scripts/build_output_health.py) | Existing on-demand observation adapter | Do not add a committed health artefact or make T4 grade itself |
| [Mastermind bounded reader](https://github.com/mastermindx-market-intelligence/Mastermind/blob/5b244a2bbe4c2a94ec25a887eb4a0d8fafe1ea2f/brain/portfolio_intelligence.py#L118) | `_read_path` reads allowlisted JSON; `_health` emits available/status/as-of/age/context authority; `_source_ref` bounds packet metadata | Useful current context health; no generation digest, read interval, decision identity or consumed-generation receipt is provided by these functions |

`WS-EVAL-OS-OUTPUT-HEALTH` records accepted deployed proof on 2026-08-28 for the bounded T4/admin capability, including negative and blind states. Its DO_NOT_REDO and the cited `DEC-EVAL-OS-T4-ADMIN-SURFACE` / `DEC-EVAL-OS-RECOVERY-ARCHITECTURE-FREEZE` forbid another health monitor/store/registry. This addendum accepts that historical proof as incumbent evidence; it does not recertify today's runtime or reopen completed T4 work.

The bounded Mastermind helper also catches `OSError`, Unicode and JSON parsing failures together as `malformed`, and selects the first present field in `_asof_value`. Those are inspected source semantics, not a newly reproduced deployed incident. A federation cannot translate all such failures into T4's narrower blindness/absence states without additional observations, nor apply its generic field fallback in place of T4's declared governing watermark.

## Consequential corrections and dispositions

| Disposition | Integration ruling |
|---|---|
| **RETAIN** | C8's distinct producer/artifact/reader/consumer planes, real generation receipts and versioned denominators; C18's local evidence equivalence and prospective history. |
| **CORRECT** | C18's statement that `available_at` alone is the historical admission gate is insufficient across replay views. Source/public availability may support a qualified reconstruction; operational-as-known also needs actual system recording/admission, and recorded-decision replay needs the consumed packet/generation. Preserve channel delay and uncertain date intervals. |
| **CORRECT** | The proposed `SecurityIdentityV1`, `EvidenceObservationV1` and equivalence registry are interface concepts, not authority to build new identity/evidence stores. Preserve native identity owners and effective-dated regional mappings. Data OS owns dataset metadata, not automatically issuer/security equivalence; K1 may reference qualified evidence but is not thereby the identity or equivalence authority. |
| **CORRECT** | A fresh producer or successful read does not prove that a downstream decision used those exact bytes. Existing bounded context-health fields are not a complete `ConsumerReadReceipt`. |
| **SUPERSEDE: none for C18's broader acceptance scope** | H03 qualifies one bounded C19 consumer seam and regional equivalence set. C18's every-active-candidate/family requirement remains intact and requires its own accepted implementation scope. H03 success cannot be called C18 completion. |
| **REJECT** | Automatic confidence caps, health multipliers, identical-column parity, a fresh filesystem checkout as historical health, or a second health/identity authority. Observational labels do not change existing decision effects. |

Regional examples remain separate: CCASS participant holdings are not US beneficial-owner 13F positions; southbound flows are not 13F; mainland margin financing is not US short interest; CN `rev_z` reversal is not analyst revisions; target upside is not a revision sequence. They may answer related questions without being summable or substitutable features. No current regulatory schedule or vendor entitlement was independently checked in this bounded addendum.

## Exact next seam and dependency map

The narrow seam is one existing allowlisted Mastermind research read that already calls `_read_path`, paired with its native Macro output-health observation. Any extension requires current owner approval and source custody. If not already supplied by a current candidate, it would preserve the bytes/generation actually read, consumer build and read interval, contract/watermark field, disposition, and the separately observed health record. It must not hash a later reread and assert it was the consumed generation. A digest proves byte identity, not completeness of the source candidate set.

Coverage joins require a bounded expected-universe definition and generation, entity/listing identities, evidence-family applicability and per-source qualification. A static declared `code_consumer` is not evidence of a read. Absence of a consumer receipt is `consumption_unobserved`, not proof of non-use; `unused` needs explicit bounded run/path evidence. All vocabulary examples here are explanatory, not new canonical enums.

Macro T4 owns health precedence; Data OS owns dataset metadata; native regional/identity owners own local meaning; the chosen Mastermind consumer owns its read/effect. Snapshot PR #673 remains an occupied integration dependency, not a reason to rebuild it. No full current source-writer census or Terminal consumer proof was obtained; implementation must reconcile those exact surfaces before writing. Mastermind's one-path proof does not satisfy C8's eventual Terminal-path requirement.

## Acceptance, falsifiers and nulls

Require discriminating cases through the actual selected consumer:

1. Fresh producer and consumed matching generation; fresh producer but stale consumer generation; healthy output with explicit unused path; no receipt without inferred use/non-use.
2. Complete and partial coverage against the same frozen denominator; changed denominator cannot silently improve coverage.
3. Missing object, unreadable object, malformed payload, stale content, rights-blocked operation and observer unable to inspect remain distinguishable where evidence supports them; unresolved distinctions remain unknown.
4. T4 content-clock field mismatch remains diagnostic. A fresh transport stamp cannot rescue stale content; a definitive reader negative retains producer blindness and partial assessment; preserve the pure-R2 primary-reader exception.
5. Correction after cutoff does not change a sealed historical packet. A date-only availability interval crossing an intraday cutoff abstains; source reconstruction is not labeled system knowledge.
6. A/H listings retain separate identity and basis. Each regional proxy retains subtype/non-equivalence; missing or structurally unavailable never becomes numeric zero.
7. Shadow projection leaves the existing consumer's portfolio actions, sizing and authority unchanged. Test the actual integration effect, not only a constant `execution_authority=false` field.

Falsifier of the specific receipt gap: an accepted current receipt that already binds this exact consumer read to the source bytes, contract, interval and decision/run. Reuse it instead of adding another. Kill a design that needs a new truth store, guessed timestamp, implicit entitlement or numerical health weight. A truthful partial or inspection-blind answer is an acceptable result, not a failed observation to conceal.

## Procurement, unknowns and supersession

No new product is needed to test this seam. Rights remain operation-specific: dataset licensing metadata and successful technical access do not grant retention, redistribution or model-use rights. Costs, delivered history, current per-region coverage, live consumer generations and exact writer availability remain **UNKNOWN/NOT_TESTED** here.

Keep both original reports unchanged. This dossier refines the single-clock and duplicate-owner interpretations stated above. It does not supersede C18's broader implementation or acceptance scope, certify every C18 source, close MAS-270, alter completed T4 acceptance, or enable regional portfolio behavior.
