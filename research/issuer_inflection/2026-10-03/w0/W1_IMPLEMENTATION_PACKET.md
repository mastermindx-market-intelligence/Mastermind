# I3-W1 first implementation packet — AAPL baseline, transition and refusal

Status: **PREPARED / NOT DISPATCHED / W0 ADMISSION REQUIRED**. Parent #1183; source operation `i3-w0-issuer-inflection-20261003-astra-c4`; integration/recovery owner Astra CEO (C4). This packet is a bounded child of the original audited W1, not a new program or release authorization.

## Outcome

An authorized development user opens the existing Terminal Company Intelligence page for AAPL, selects a prior cutoff, sees the source-backed baseline and descriptive change, opens exact receipts, switches to the known unlinked-assets case and sees the original refusal. An independent machine reader consumes the exact same derived identity, not a separately calculated answer. Before/after selection cannot drop unchanged or missing variables. The preview clearly says development/golden/reconstructed, not live issuer intelligence or a validated inflection signal.

## Entry gates

Consume exact W0 architecture/source-owner acceptance, canonical source-workspace/custody grants, accepted derived schema and reader/publication extension, exact rights-purpose decision and development capture contract. Re-read current affected heads once and compare only the declared dependency closure. Preserve unrelated accepted source. This packet itself grants no new source path, runtime, credential, deployment, paid worker or trading authority.

No paid/Codex-work task or native provider/account selection is authorized here. Preferred ordinary implementation/review avenue is Terra when the current placement owner admits it; current placement is `needs_placement`, with no claimed receiver or START. The current Astra session may retain concentrated fit/integration judgment. Any worker must acknowledge the exact scope and return to this carrier; message delivery is not pickup.

## Exact owner inputs already characterized

Macro source `37122b69fffa98cb160022c4831df0338ef3e7e3`:

- Owner adapter: `engine/fundamental_forensics/ixbrl_raw_ledger.py::GoldenAaplFinancialQueryProvider`.
- Owner request/query: `engine/fundamental_forensics/query_service.py::execute_financial_query`.
- Identity: `ISS:US-XNAS-AAPL`, canonical Data OS security/issuer masters; do not independently derive it from CIK or ticker.
- Frozen accessions: `0000320193-25-000079` and `0000320193-26-000020`. Do not expand the provider's frozen accession tuple or monkey-patch the registry.
- Owner fixture delivery remains exactly `committed_golden_fixture`, `attested=false`, `production_issuer_service=false`; context-only.
- Positive **input pair**: revenue durations `2023-10-01..2024-09-28` and `2024-09-29..2025-09-27`, labels FY2024/FY2025, from the same A1 filing revision. Actual values `391035000000` and `416161000000`, USD. The owner response types both as generic `duration`, not `PeriodKind.ANNUAL`; `fiscal_year`, `fiscal_year_weeks`, and `calendar_kind` remain unknown/null while `inferred_week_count=52` for both. Do not let the FY labels self-authorize annual comparability.
- Positive owner response SHA-256: `a752302d0d11457920be1425cb9ebb6d1f29560b7f1e8f41a5de98075083c6af`.
- Negative input: `total_assets`, instant `2025-09-27`, latest-known query at source cutoff `2026-08-01T00:00:00Z`, recorded cutoff `2026-08-23T12:00:00Z`. Exact owner reason: `unlinked source vintages require an explicit typed revision lineage`.
- Negative owner response SHA-256: `aa6f82dc415e2d3449118c627deb339f98814f0a1be6dff61e88f8819495bb21`.
- Full requests, owner outputs, real reconstruction timestamps and method-before-execution hash are retained in `evidence/`. This is not historical emission or prediction registration.

### Positive-pair technical evidence matrix — descriptive comparison built; annual/production admission still open

| Comparator prerequisite | Exact observed evidence | Status |
|---|---|---|
| Canonical issuer / metric | Same AAPL owner identity; `metric.revenue/v1` | satisfied |
| Mapping / concept | Same `mapping.revenue/v1`, mapping digest `ef978677...`, concept `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | satisfied |
| Unit / scope | Same USD semantic unit; no denominator; empty explicit/typed dimensions | satisfied |
| Revision basis | FIF query arithmetic defines the basis as `(source, accession, document_id, source_body_sha256)`; both cells match `sec-edgar`, accession `0000320193-25-000079`, document `sec_document_d23a...`, body `548ae597...` | satisfied |
| Duration geometry | Two immediately adjacent, non-overlapping 364-day generic durations; both infer 52 weeks | **satisfied for equal-duration descriptive comparison** |
| Reported precision | Both selected facts carry `decimals=-6`, `precision=null` | **satisfied for deterministic arithmetic over the reported values; not exact underlying economics** |
| Typed fiscal meaning | Owner cells are generic `duration`; fiscal year/calendar metadata are unknown/null. Current financial-query wire admits only `duration`/`instant` | **annual/YoY claim unavailable** |
| Public/model-use rights | FIF response exposes no `rights`/`rights_profile`; shared `sec_edgar` rights row remains held on #7870 and absent on protected Macro main | **missing on admitted mainline path** |
| Production source | `committed_golden_fixture`, `attested=false`, `production_issuer_service=false` | **development only** |

The positive mathematical demonstration is now executable through `equal_duration_comparison.py`. It produces comparison `i3devcmp_75b3515ed838ab4f97ac8ed9`: 391035000000 → 416161000000 USD, exact difference 25126000000, exact percentage `502520/78207`, display 6.43%. Twenty-two comparator adversarial tests pass, after the shared owner-response validator grew to 52 baseline/owner-envelope tests, and the suite is included in the normal repository I3 consumer entry. The comparator deliberately sets `owner_typed_annual=false`, `annual_or_yoy_claim_permitted=false`, `comparison_admitted=false`, `product_publication_admitted=false`, `trial_registered=false`, and `emitted_at=null`. See `EQUAL_DURATION_COMPARISON_RESULT.md` and `evidence/equal-duration-comparison/result.json`.

This closes the W1 **development positive-comparison proof** at the narrow source-interval level without creating fiscal semantics. It does not close W0 owner acceptance or authorize annual/YoY copy. If a future FIF owner wants an annual result, it must expose typed annual semantics through an accepted owner interface rather than relying on display labels.

### FIF lineage consumption boundary

Current merged/tested FIF-3A3 responses used by this packet do not carry an accepted cross-filing lineage bridge, so the assets case above remains the canonical W1 refusal. The incumbent #7518 candidate shows the intended future owner seam without granting its unmerged implementation: when FIF has actually applied cutoff-visible lineage evidence, `execute_financial_query` adds a top-level `lineage` disclosure to the existing `fundamental_forensics.financial_query_response/v1` envelope. The disclosure is schema `fundamental_forensics.financial_query_lineage/v1`, relation `xbrl_confirmation`, explicitly `is_reported_revision=false`, and leaves the existing receipt/query hash unchanged when absent.

I3 must therefore consume lineage only through an owner-issued financial-query response. It must not import `engine.fundamental_forensics.lineage_evidence`, derive confirmation receipts itself, or reinterpret `xbrl_confirmation` as an amendment/restatement/correction. Absence of the owner disclosure cannot be repaired by I3; the existing not-evaluable reason propagates unchanged. A future accepted positive owner response can be referenced as supporting cross-filing evidence only after the FIF owner returns the admitted revision/source/cutoff and the response bytes are captured under the current program method.

The same-filing period pair is not a prior-cutoff state reconstruction by itself. W1 must additionally exercise the distinct source/system cutoffs before SEC acceptance and before fixture admission, then at eligibility, and preserve unaffected baseline variables throughout.

## Source scope to obtain, not silently assume

Macro: one owner-approved, presentation-neutral I3 composition module and its closed schema/tests. FIF lineage/comparability must return through incumbent Macro #7518 at a58ef81168687ff6aedcb37ed0070dab05cdbe9b. Company Intelligence read/publication remains owned by Macro #7426 at 7bc04876747d773861b47519061279ae033a148d, but owner return 5977167854 places its unmerged wire on **REQUEST_RECOMPOSE / HOLD**: protected/current-main `event_workspace_manifest.v3` requires `source_clock`, while K4-G's unmerged v3 requires `revision_index`, and both are closed exact-key contracts under the same identifier. I3 must not bind W1 to either historical K4-G v3 shape, union the fields, or choose a replacement schema/version. Preserve only the conceptual owner invariants—generation-addressed/hash-verified reads, context-only authority, fail-closed history, same-origin routing, immutable generations before mutable marker, and compare-and-swap promotion—until #7426 or an accepted successor returns a compatibility-preserving semantic head. Terminal must preserve the existing Company Intelligence workspace, same-origin BFF terminal/app/api/company-intelligence/[symbol]/route.ts at blob 9a9f9c3f9bb45be065408567da078d776570b7ce, closed normalizer terminal/lib/companyIntelligence.ts at blob 6b15b8f1a68348c2fcaebd3dc973d7748b4a1b33, and existing E2E suite. No modifying Macro or Terminal path is granted while this owner HOLD remains; this packet never grants writes to the entire engine/app/template tree.

Forbidden edits: FIF query/raw-ledger/metric kernels, frozen AAPL fixture accessions and original tests; CDV-1 economic interpretation/observation implementation or frozen probes; E3 holdout/parser ownership; Capital collectors/schedulers; #7870 shared kernel/private publisher; security/rights/identity registries; new generic lifecycle/store/queue/feedback ledger. A discovered owner defect is returned with a minimal reproducer to that owner, not patched under I3.

## Ordered implementation and discriminating tests

1. **Freeze the actual entry set.** Record accepted definition/schema hashes, source heads, publication/rights decisions, exact workspaces, reviewer independence and consumer interfaces. Store method/context/exposure/correction evidence at the existing admitted owner before any grade or emission.
2. **RED first for state composition.** A transition-only implementation must fail tests for unchanged variables, missing baseline, unsupported new variable, ambiguous duplicate owner refs, correction ancestry and separate source/system cutoffs. Never edit owner tests to obtain GREEN.
3. **Build a pure derived composer.** Take admitted immutable owner receipts and explicit cutoffs/definition. Reference before/after/baseline cells and source revisions. Calculate only the owner-accepted descriptive comparison using the bounded exact-rational policy, explicit units and one integer half-even display rounding. Retain exact numerator/denominator separately from display; never use ambient Decimal context. Preserve owner refusals. No network, implicit now, provider read, financial metric inference, identity minting or publication side effect in this function.
4. **Prove positive and refusal.** Positive pair keeps exact owner source/metric/unit/dimension/period/mapping refs. The unlinked instant remains not-evaluable even when values agree, the later source is preferred by caller, or a narrative asks for a number. Negative/zero denominators, quarter-vs-YTD, 52/53-week mismatch, nil, wrong issuer, missing rights, changed mapping and late input must fail closed.
5. **Prove deterministic identity and correction.** Same inputs/method/cutoffs → same semantic identity independent of build-time noise. Changing a load-bearing source revision, method or comparison cutoff changes identity. A corrected input appends a successor; the original as-known query stays reproducible. Rights revocation suppresses present access through the owner without falsifying the old record.
6. **Connect the existing preview.** Preserve the current Terminal contract in `docs/COMPANY_INTELLIGENCE_WORKSPACE.md`: the browser reads **only** the same-origin `/api/company-intelligence/<ticker>` BFF, consumes one bounded validated generation, never fetches/infer/rewrites source data, and displays `authority=context_only` / `is_context_only=true`. Use `/analysis?symbol=AAPL&page=intelligence` and the accepted versioned sibling BFF/normalizer extension; `ANALYSIS_LOCAL_PREVIEW=1` is development-only and must never be enabled in production. Do not append fields silently to closed `company_intelligence_context.v1` or have the browser call R2/Macro directly. One canonical derived generation feeds both display and machine fixture. The browser renders; it does not recompute percentages or infer meaning.

   **Public-rights fence:** the existing anonymous event-workspace glance publishes exact evidence only when its source span is `byte_replayed` and has rights profile `rp_public_primary_v1`/`public_primary`; it removes raw receipts/URLs/hashes. Current FIF query responses carry no rights profile. Therefore the W1 FIF-derived transition remains development/internal-only until the existing source-rights owner binds every load-bearing financial input to an admitted consumer purpose. Never infer public redistribution/model-use rights from an SEC URL or from a successful BFF fetch. Missing rights must fail closed.
7. **Make the preview useful.** First read: reporting periods versus comparison cutoffs, prior/current amounts and units, a concise descriptive change or exact refusal, source/system/reconstruction badges, baseline variables, missing context, correction state and View evidence. No bright Buy/inflection badge or unsupported economic explanation. Both the same-filing pair and cross-filing refusal must be reachable, not hidden in a test-only route.
8. **Browser and consumer proof.** Use the existing `terminal/e2e/company-intelligence.spec.ts` contract at 1440×900, 820×1180 and 390×844. Exercise selected-cutoff change, reset stale evidence, rapid issuer/event switch, source drawer, refused response, missing-data state, keyboard close/focus return, overflow, sign-out/account switch and late-response fencing. Capture actual rendered evidence for the development environment, explicitly distinct from production.
9. **Privacy/failure proof.** Unauthenticated or wrong-purpose access must deny before opening the provider; late/corrupt generation/unknown owner/cross-issuer reference fails closed without leaking data. No-store and generation identity survive the BFF. Browser and machine trace to the same owner input and derived content hashes.
10. **Review and normal release separation.** Publish one coherent candidate with RED/GREEN/mutation/source-identity evidence and development browser proof. Independent exact-head review is required. W1 development acceptance does not admit an attested issuer service or release; normal protected checks/current-base composition and approved non-Vercel deployment remain later gates.

## Return contract

Return exact operation/carrier and accepted receiver, source base/head and changed paths, input/definition/schema/capture hashes, actual test commands/results including failures, browser viewports/screens/evidence-to-source IDs, machine parity hash, independent review disposition, rights/authority checks and remaining owner blockers. Preserve unchanged baseline/missing fields, refusal wording and earlier method/exposure/correction records.

Allowed completion label: **W1 DEVELOPMENT VERTICAL ACCEPTED**, only after all development gates actually pass. Disallowed labels from this packet alone: production-proven, broad issuer coverage, economic-classification validation, analyst-usefulness win, predictive edge or trading authority. Parent W2–W11 scope remains open and Astra advances the next permitted owner-bound task rather than treating W1 as mission completion.
