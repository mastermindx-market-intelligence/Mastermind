# Options Observation-Time Intelligence — Aion-informed Mastermind design

Status: **SPEC_ONLY / architecture candidate**. This document neither implements nor activates a feature. It is original functional design, not recovered competitor source, and not a claim of predictive superiority.

## Mission and end-state
The professional retail user should answer, in one existing Exposure journey: what structure is present, what changed since a comparable observation, whether the change came from open-interest inputs or market repricing, and what the available evidence cannot establish. Prophet remains the primary selection/entry/risk delivery product; this supplies intelligible display context, not another trading signal.

The machine job is to preserve exact published observations, establish comparability, compute transparent descriptive differences, and provide source-bound explanations to the existing product and AI consumers. The moat is useful accumulated history plus rigorously evaluated interpretation, not another heatmap or an inflated count of files. A 10/10 end-state makes historical investigation, normal operation, missingness, corrections and user orientation equally coherent.

Current Chairman direction is the ongoing Aion teardown and end-to-end native upgrade. Protected procedure pin: Mastermind `0fe8074ff953b2ced9025ed40f0f66019c759967`, Skillpack 1.0.1/bootstrap 1. Direct principal rationale: PRINCIPAL_JUDGMENT; the unresolved work is source ownership and comparison semantics, not routine coding. No Executive Job, worker assignment, publication, score, model promotion or deployment is created.

## Evidence that changes the target
Aion's public home now advertises 37,421 archived options surfaces, differentiated refresh schedules, and strike/expiry levels. Its terms describe options analytics as estimates from individual generation-time snapshots, not observations of actual dealer inventory. These statements are compatible: retaining successive snapshots is different from measuring continuously. Counts are vendor claims; neither completeness nor usefulness was independently verified. [A1, A2]

The relevant native facts are more specific than a feature checklist. Terminal already has `ExposureMatrix.tsx`, the shared `StrikeExpiryMatrix.tsx`, filtered expiry views, and dated GEX-ladder reads. Its inspected `flowSource.ts` exposes `matrix:{ROOT}` but no dated matrix read. Macro's inspected `scripts/build_options_matrix.py` writes and publishes a latest per-root JSON. No dated matrix consumer was located in the bounded inspected paths. This is a gap in that verified path, not proof that no archive exists anywhere else. [M1–M4]

Consequently: do not commission a basic matrix, Greek engine, generic history store or duplicate replay framework. The next missing customer job is **observation-time comparison of the existing strike-by-expiry matrix**. Expiration dates across columns are not dates when the data was observed.

## Approaches and choice
1. Rebuild old matrices on demand from today's source store. Cheap for demos, but revisions and today's code can replace what users actually saw. Reject as the original-publication record; retain only as explicitly labeled research reconstruction where existing policy permits.
2. Add a new analytics database and separate replay service. Flexible, but duplicates owners, complicates correction and publication truth, and requires a new operating system for one view. Reject.
3. Extend the existing publisher and read path with source-identified retained observations and a thin comparison projection. **Recommended.** Reuse an accepted existing archive/publication facility when the required semantics fit; do not copy a historical overwrite behavior blindly.

## Scope and owner boundaries
Macro's existing matrix builder remains the numerical producer; the current canonical exposure functions remain the only calculators. Existing ThetaData/EOD source owners retain source access, rights and availability. The existing options publication owner controls retained artifacts. Terminal's current flow resolver, Exposure desk and shared renderer remain the consumer. Existing Agent OS workstreams and DNR decisions govern organizational scope; no approximate new parent is invented.

Mastermind #124 is the liquidity response lab and is not an options dependency. Terminal #592 is the selected-root repair and keeps its own verification hold. Do not add this design's implementation to either PR. Check current ownership and branch collisions before a future wave. Existing bans on unvalidated positioning fusion, charm narratives, off-horizon verdicts and LLM signal origination remain effective; descriptive comparison is not an exception to them.

## User journey and information architecture
The existing Exposure view opens on its current usable observation with source session and age. A date selector chooses an observation date; the existing expiry controls continue to choose expiration dates. The two controls must have different names, values and accessible descriptions. Choosing a historical observation cannot retain today's spot, levels, unusual-volume annotations or state under the historical heading.

A comparison uses A and B from the same named source family. Both timestamps, scopes and method versions are visible. The default question is "what changed?", not "what should I trade?" A compact summary answers three different questions: where exposure increased at a fixed contract/location; whether a named level migrated; and whether the source/method/coverage changed. The full matrix remains inspectable rather than squeezed into an ornamental strip.

A missing date remains a missing date. An empty chain, an unavailable response, a stale observation, unsupported coverage, incompatible comparison and an intentionally withheld result have different states. Retry and request ordering remain with current owners. An unavailable date cannot fall back to today; changing tickers cannot reuse another ticker's response. Preserve the current selected-root work in #592 before integrating overlapping view changes.

The candidate does not create a Terminal light theme. Current inspected `SectionPreferences.tsx` explicitly stores that shared preference for Macro, while Terminal itself has no light mode; `app/layout.tsx` initializes dark. Test supported appearances and EN/ZH at 1440x900, 820x1180 and 390x844; record absent light capability explicitly. Any later light-mode programme is a separately approved design, not CSS forced into a screenshot. [M5]

## Evidence and publication contract
Retain an exact original published observation and its source identity, not just an economic date. Carry: root/instrument identity; source session; source availability/known-at; generation time; observation identifier/hash; producer/method version; units and sign convention; scope and truncation; coverage/missingness; relevant source receipts; rights/publication eligibility; and correction relation where one exists. Reuse the existing artifact envelope and identity scheme where possible. This is a required semantic inventory, not a declaration of a new universal schema.

The index names only successfully available observations. A failed archive write must not advance its index, and a failed index update must not corrupt the latest current artifact. Replay of the same observation preserves its identity. A changed result for the same historical date is not silently the same observation: retain the original and use the existing correction/amendment mechanism. Clock, contract or method changes never become a backdated original.

Distinguish three evidence classes in every read: originally published; later corrected; and research reconstruction. A reconstruction may answer a historical analytical question but cannot prove what the user could have known. The existing builder's `--date` is not evidence of original publication. Do not populate a forward-only outcome record by retroactively rebuilding attractive cases.

## Comparability before arithmetic
Same ticker text is insufficient. Require compatible instrument identity, currency, contract multiplier, corporate-action adjustment, exposure unit, sign convention, data treatment and expiry/strike scope. Changes in methodology, source or coverage produce an explicit comparison limitation rather than a large-looking "positioning change".

Match contracts by canonical identity, not rounded display strike or row position. Split common eligible contracts from confirmed introductions, confirmed expirations/removals, and unknown/missing members. A contract absent from a partial old snapshot is not proven new. Missing OI is not zero. A shifted wall role is not a fixed strike. Historical OI must use the producer's actual availability law, not later-settled values read from today's table.

The first shipping comparison can report exact published exposure differences on the common comparable subset, with coverage. It must not attribute changes to OI versus repricing unless the input evidence needed below exists. Display a matched-subset result as a subset; never extrapolate it to the whole book by a coverage multiplier.

## Original analytical design: exact two-factor change attribution
For a comparable contract i, let q0 and q1 be the admitted open-interest input at observations A and B, and u0 and u1 be its per-unit exposure evaluated by the existing canonical engine under those observations. The sign convention and multiplier are fixed and already incorporated consistently. This describes changes in modeled exposure, not directly observed dealer inventories.

Define quantity contribution Q_i = (q1 - q0) * (u0 + u1) / 2. Define repricing contribution R_i = (q0 + q1) * (u1 - u0) / 2. Algebra gives Q_i + R_i = q1*u1 - q0*u0 exactly. This symmetric decomposition shares the interaction instead of hiding it in whichever input is changed second. Sum only across the admitted comparable set; preserve numerical tolerance in the receipt.

This is an arithmetic identity, not causal identification. Changing OI inputs does not reveal who opened or closed positions. Repricing reflects changed modeled inputs, not proof of future hedging pressure. If the per-contract inputs are unavailable, abstain from attribution while retaining eligible aggregate differences. Neither an AI explanation nor an approximate inferred gamma may fill that gap.

A later independently scoped refinement may split the repricing component into spot, implied volatility and elapsed-time contributions with symmetric counterfactual evaluations through the same engine. It must expose interaction-allocation conventions and computational cost. Expiry discontinuities, missing IV surfaces and changed contracts are explicit boundary cases, not silently extrapolated counterfactuals. Do not add this complexity until the two-factor view is useful and evidenced.

### Level migration is not level growth
If the dominant strike moves from 775 to 785, the change in the role's displayed dollar amount is not the growth at a constant location. Show (a) role migration, (b) exposure change at fixed eligible contracts/strikes, and (c) contributing maturities separately. The numbers here are illustrative, not market observations. Preserve signed before/after values; crossing through zero is not a meaningful multiple. Tiny denominators cannot create attention-grabbing "20x" claims without the absolute amounts beside them.

### Original product improvements
A **scope lock** keeps A/B comparisons on a common expiry and strike universe, with omitted coverage visible. A **change explanation** separates the observed calculation from assumptions and unavailable attribution. A **level lineage** distinguishes role migration from magnitude change. A **source correction view** lets a user switch between original and corrected observations without rewriting either. A **comparison quality panel** answers whether the result is complete, partial, or incomparable without inventing a new confidence score. All are proposed features, not claims of industry-first invention.

## Deterministic versus model roles
Identity, time admission, scope matching, numeric validation, arithmetic differences, coverage and publication linkage are deterministic. The existing canonical engines provide exposure values. A language model can explain a structured result, but it may not originate a new level, assign a probability, turn unavailable attribution into a story, rank/size trades, or treat several derivative views of one input as independent confirmation.

Where existing validated Prophet or entry-expert outputs reference this context, presentation must keep the producer's own horizon, conditions and authority. An attention-sorted change board is descriptive research prioritization, not an approved trading ranking. This design neither reopens killed predictive families nor creates an exception to current DNR rules.

## Implementation order: one useful capability per release
**Wave H1 — inspect retained observations.** Confirm the existing publication facility and implement the smallest source-retention plus real dated-reader plus current Exposure selector path. Deliver original/corrected/reconstruction labels, unsupported/missing-date states, root ordering, useful screen space, tests and one production path. Source publisher alone is not customer completion. Split cross-repository implementation only at explicit dependent contracts; do not call either partial PR the delivered whole.

**Wave H2 — compare like with like.** Two admitted observations through the existing reader produce a common-scope delta table and concise summary, with coverage and incompatibility handling. No inferred inventory attribution. Acceptance requires row-to-total reconciliation and a real before/after investigation in the product.

**Wave H3 — explain input change versus repricing.** Only after exact contract inputs are available, add the two-factor calculation and its consumer. Demonstrate identity reconciliation, finite values, source clocks, absent-input abstention and agreement with total change. No new price prediction or trading action.

**Wave H4 — assess usefulness and connect eligible delivery.** Use existing instrumentation to measure whether users answer the intended questions correctly and faster, and whether errors/staleness decrease. Evaluate any predictive hypothesis separately through current experiment/forward-outcome owners before it can influence Prophet. A usability gain is not alpha; alpha is not established by this design.

## Adversarial acceptance matrix
Require distinct failures for wrong-root input, old request completion, mismatched scope, method change, missing observation, empty-but-valid chain, non-finite value, missing OI, corporate-action change, newly listed contract with unknown prior coverage, expiry discontinuity, duplicate original, corrected original and interrupted publication. Verify old artifacts remain recoverable. Test sign/unit consistency in the table, summary, screenshot/export and AI explanation.

An archived selection cannot show today's matrix or annotations under an old date. An exact repeat cannot duplicate an observation. A later repair cannot alter the original record. A failed source cannot become a healthy empty view. For arithmetic attribution, the contributions must reconcile exactly within a declared floating-point tolerance on a known synthetic case; actual observed cases need the same inputs and receipts, not a cosmetic fixture.

Production acceptance: real permitted input through the existing producer/publisher, dated read, visible current and historical selection, comparison, named missing date, and user return to current. Browser evidence must name the deployed source and data identities. CI, screenshots of synthetic input, HTTP 200 and a successful archive upload are individually insufficient. Provider/data rights, source availability and independent review remain prerequisites, not administrative afterthoughts.

## Stop conditions and execution handoff
Before H1 implementation, resolve whether a retained-matrix facility already exists outside the inspected path, which existing publisher supplies original/correction identity, and whether its current rights permit the intended display/history. Freeze those exact interfaces and source pins. Unavailable rights, absent safe retention semantics, unresolved owner collision or a platform-denied action stops that affected lane; do not invent an alternative queue, credential or history service to bypass it.

The handoff is for the existing options engineering owner after lawful placement, with the mission, scope, clocks, null/correction policy and acceptance above. Routine placement is not Chairman labor. No worker is presently assigned by this document. Stop a bounded H1 worker at its granted review/proof boundary; return a concise exact-head result, actual tests, unresolveds and next action to the existing commissioning owner. An independent next wave needs its own approved scope and placement.

This design is ready for architecture review, not implementation acceptance. The primary next action is to approve the original-publication versus reconstruction and common-scope contracts, then commission H1 as an end-to-end read/replay capability. The liquidity forecast programme and #124's failed hosted gate remain separate. #592 keeps its platform-limited mounted-race proof and independent review requirement; this document does not waive them.

## Verification and limits of this document
The attribution equation is an algebraic design, not a market backtest. The source-path observations were read at the pins below. Public competitor claims were read on September 16, 2026; no authenticated Aion terminal, proprietary algorithm, paid content extraction or performance audit was performed. No screenshot from another service is treated as Aion-origin merely because it appeared in a subscriber's combined workflow. Independent software review is still needed before adopting interfaces.

## Sources
[A1] Aion public product page, observed 2026-09-16: https://aionanalytics.com/ . Counts are advertised scope, not audited coverage or performance.
[A2] Aion terms, updated 2026-09-13, sections 14–15: https://ai.aionanalytics.com/terms.html . Generation-time options estimates and model limitations; no proprietary reconstruction claimed.
[M1] Terminal `702d81bb35f2c900a5aa1215437bf968aa9e6d93`: `terminal/components/gexdesk/ExposureMatrix.tsx`, `terminal/components/shared/StrikeExpiryMatrix.tsx`.
[M2] Same Terminal pin: `terminal/lib/flowSource.ts` (blob `978c49827780ac734feff5169c2351e5fe451206`), dated GEX/surface routes versus latest matrix route.
[M3] Macro `459eafb838d9944e58e6a65413e282f2a13826ef`: `scripts/build_options_matrix.py` (blob `9b97efefa65a7f10009575bd6ccb768b84021454`), latest per-root publication path.
[M4] Macro `9579caf3f950f1a2e7b959a9b3b68d26e42e5d06`: `engine/options_matrix.py` (blob `3fdfa848f3569a76ba6bffef1f422abf00f28fc0`), exact-side history and raw-chain profile method. Preserve its existing source/units semantics.
[M5] Terminal #592 candidate `27a759373b3feced2f313358cc0ef507155eca6b`: `terminal/components/settings/SectionPreferences.tsx` (blob `001aa26496ca640625632227b0d47499eb916e87`), lines 126–142; `terminal/app/layout.tsx`, dark root initialization.
[M6] Macro `9579caf3f950f1a2e7b959a9b3b68d26e42e5d06`: `agentos/workstreams/WS-OPTIONS-ALPHA-INTELLIGENCE-RECOVERY.md`, existing campaign/calibration/Issue Desk ownership and DNR boundaries. This design does not merge its distinct gates into matrix display work.

## Follow-through: existing history publisher inspected
The existing GEX history path is now traced, not merely presumed. At Macro `459eafb838d9944e58e6a65413e282f2a13826ef`, `scripts/build_options_hub_nightly.py` (blob `a6ad24e8db9b4fd34660582c1c275deb962f561b`) uses `_gex_history_relpath` (lines 734–756), `_list_gex_history_dates` (834–860), `_heal_gex_history` (902–947), and `publish_gex_history_index` (950–980).

Reusable mechanisms: the session index is derived from paginated object listing rather than a second mutable ledger; a listing error does not publish an empty index; the NYSE calendar distinguishes missing sessions from non-sessions; and the self-heal work has an explicit budget. These are useful existing publication behaviors, not a reason to create another scheduler or storage service.

Important difference from original-publication history: self-heal deliberately reconstructs missed dates using available source stores, sets `self_healed:true`, and trims the attached scalar history to avoid later dates. That is a useful reconstruction feature, but it does not establish that the reconstructed output was originally available on the economic date. A dated key alone therefore cannot carry the original-publication claim required by the new comparison workflow.

H1 should reuse the owner and applicable index/calendar mechanisms, while extending its artifact provenance/correction behavior explicitly where needed. Do not silently rename the existing reconstructed history as original snapshots or overwrite its historical semantics. Before implementation, determine the accepted original-observation identity and first-publication receipt in the current data/publication owner; unknown first-publication remains unknown, not copied from session date. No archival or rights capability is declared live by this source inspection.


## H1 publication-owner qualification — 2026-09-16
A more relevant retained-artifact facility already exists inside the options domain, not only in unrelated company/research publishers. At Macro `e729d0fd9d48868b49a1911d4098c689b3d373bd`, `scripts/build_options_structure_intraday.py` (blob `6cf89d9cc12129674a5c0173b0dcca7e4ca606f1`) owns `Artifact`, `_remote_object`, `_put_immutable`, `PublicationBundle` and `publish_bundle`. Its companion `engine/options_structure_intraday.py` (blob `d452fee692d9915d2be6fe7af562706417a2d874`) owns strict JSON serialization and receipt construction. This resolves the earlier uncertainty about whether an existing options publication implementation can protect retained bytes.

The immutable primitive reads body/metadata/length/ETag from one coherent GET; verifies exact body and digest; conditionally creates an absent object; refuses a differing existing object; and verifies after creation. The full publisher writes immutable packets before its authoritative global discovery index, then repairs derivative current pointers. It distinguishes collision, regression, uncertain commit and incomplete derivative repair. Do not create a second upload/retry/receipt/cursor controller to obtain those behaviors.

**Important reuse boundary:** this is presently a Light U-CHAIN contract-eligibility publisher, not the EOD strike-by-expiry matrix. Its profile filters, quarter-hour bucket identity, completion/admission receipts and current-epoch index cannot be relabelled as matrix history. An immutable packet is not by itself proof of historical index visibility or what a user saw. The EOD observation/correction contract still needs explicit integration with that owner. Never activate an intraday collector, change its frozen profile authority, invent a capture time, or infer runtime readiness from these source tests.

### Executed qualification
An exact Git archive containing the source, required imports and test inputs ran the two unchanged suites `tests/test_build_options_structure_intraday.py` and `tests/test_options_structure_intraday.py`: **106 passed**. Initial incomplete archive attempts failed for omitted `collectors/` and then `config.yml`; adding those exact same-commit source dependencies resolved collection/CLI tests without modifying production or tests. A private test temporary directory avoided touching unrelated shared test cleanup. No full-Macro-suite, live-R2, fresh-source or deployment proof is claimed.

A separate bounded compatibility probe passed the existing Terminal SPY/QQQ matrix fixtures through the exact options-domain `Artifact` and immutable-write primitive against the existing test-only `FakeR2`. It proved strict roundtrip equality, repeat idempotence, refusal to replace the same address with changed bytes, and preservation of the original. The resulting documents passed the exact Terminal `isMatrixDocForRoot` reader for their own roots and were refused for the other root. The fixtures retain their July dates; they are not newly observed market data. Network attempts and real remote writes were zero. No historical selector, production publication or amendment system was implemented.

Native proof home: `/Volumes/Mastermind/agent-evidence/aion-options-publication-reuse-20260916-sol-001/`. The committed verification JSON carries exact input/output digests and the probe results. The probes are compatibility evidence, not production modules. This positively identifies reusable retention and reader primitives while leaving the genuinely missing interface work visible.

### Narrowed next implementation boundary
H1 must connect the existing EOD matrix producer to the existing options publication owner and the current Terminal reader/renderer. Share or expose only the necessary low-level immutable primitive through its existing owner; do not import unrelated Prophet selection and contract-eligibility logic into an EOD persistence operation. Preserve exact bytes before advertising a saved observation. Bind an observation index to retained artifact identity and successful publication evidence; keep economic session, generation, first-known evidence and correction relationship separate. A missing publication-time receipt stays unknown, never reconstructed from the date in the filename.

The next acceptance decision is the EOD-specific historical discovery/correction interface and safe shared-primitive boundary, followed by the complete producer→dated-read→existing-UI vertical. The broad design is not promoted to BUILT_NOT_PROVEN by these tests: it remains SPEC_ONLY. Current source authority already admits the existing ThetaData/EOD display use; do not restore the obsolete Polygon entitlement blocker. Independently new redistribution remains outside this reuse ruling.
