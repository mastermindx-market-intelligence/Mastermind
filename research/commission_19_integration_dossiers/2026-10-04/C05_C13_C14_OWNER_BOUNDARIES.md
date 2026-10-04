# C5/C13/C14 — temporal and financial-input boundaries

Partial MAS-264/MAS-265 integration dossier; scope adjudication for MAS-268/H01 and MAS-272/H05. Verdict: **qualify existing FIF and Capital Structure surfaces; do not make unrelated integration holds universal, and do not use an opt-in label to reopen held capabilities**.

## Immutable original evidence

| Report | Original pointer and valuable finding |
|---|---|
| C5 R2, Mastermind #1221, `ebfd9d5b6bcabc7b011f763c2f808e8a84c5d97b` | [Bitemporal audit](https://github.com/mastermindx-market-intelligence/Mastermind/blob/ebfd9d5b6bcabc7b011f763c2f808e8a84c5d97b/research/BITEMPORAL_POINT_IN_TIME_TRUTH_AUDIT_2026-10-04.md): distinguish four replay views, qualify one financial-response-to-consumer slice, preserve original occurrences and complete candidate-set evidence; a timestamp filter is not complete version selection. Retain its forty-case acceptance catalogue. |
| C13, Macro #8419, `d0f655c65cd3dac332f22bb47693be206cbc229e` | [Capital-actions masterplan](https://github.com/mastermindx-market-intelligence/macro/blob/d0f655c65cd3dac332f22bb47693be206cbc229e/research/corporate_capital_actions/2026-10-04-hardening/MASTERPLAN.md): share/capital semantics and phase gates belong to current Capital Structure/CCW owners; G0 must resolve W2/W4/W6 and publication state. |
| C14, Mastermind #1237, `2784878636c4a27dae176f311e2ef126a1932f28` | [Credit/capital-cost masterplan](https://github.com/mastermindx-market-intelligence/Mastermind/blob/2784878636c4a27dae176f311e2ef126a1932f28/research/commission14/ISSUER_CREDIT_CAPITAL_COST_MASTERPLAN_2026-10-04.md): retained financing inputs must qualify before deterministic debt/cash extraction; sponsor-held bond positions are not issuer contractual liabilities. Section L proposes a pure offline opt-in seam. |

Only these integration boundaries were adjudicated. The original reports' broader research, external-source claims and acceptance catalogues are not replaced or certified here.

## Current-source findings

Macro source pin is `9201f1602bfe47e05a63d61802fbed6f7f55a19d` throughout.

1. [`engine/fundamental_forensics/query.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/fundamental_forensics/query.py#L594) already provides `QueryPolicy` with required `source_snapshot_at` and `recorded_at`, separate `as_reported`, `latest_known_as_of` and `latest_restated` selections, and `BitemporalMetricQueryEngine.query_cell` / `query_matrix`. Formula output is an on-demand cutoff-qualified projection; it is not automatically a stored historical computation or decision.
2. [K1 vocabulary](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/contracts/evidence_foundation/vocabulary.v1.json#L50) accepts `fif.raw_occurrence` with its actual `fif_occurrence_id` and `RawFactLedger.by_id` reader. A pointer proves selected-object identity, not cutoff, rights, candidate-set completeness or downstream use.
3. [K1's current recipe contract](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/contracts/evidence_foundation/README.md#L130) has no validated bridge-object input. Its four-family AAPL security recipe is `REFUSED / identity_unresolved`. This remains a real boundary for that cross-type composition. It is not proof that a narrower native FIF reader cannot be qualified. Do not bypass the refusal by relabeling native subject IDs as Data OS security IDs.
4. [`engine/debt_maturity.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/debt_maturity.py#L135), blob `cb5688451aa025156aed89566f9076729526d27e`, sorts candidate annual periods by latest filing and selects `periods[0]`. The `as_of` argument supplies output/staleness context; it does not itself filter source versions before this winner selection. Historical qualification must select eligible retained inputs upstream.
5. [Capital Structure contract](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md) preserves default-off `CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED`. Direct `CommonStockSharesOutstanding`, `EntityCommonStockSharesOutstanding` and `EntityPublicFloat` observations remain separate; the source does not thereby choose current outstanding or fully diluted supply. The incumbent workstream retains W2 proof and W4/W6 gates.

Native Sol COO reviewed C13/C14; the Program CEO independently inspected the current query, K1 contract, debt selection and share-observation law. These are source findings, not runtime or real-data proofs.

## Dispositions and dependency collisions

| Disposition | Ruling |
|---|---|
| **RETAIN** | C5's view-specific clocks, corrections/withdrawals, provenance, retention and real consumer proof; C13's phase/publication gates; C14's deterministic extractor reuse. |
| **CORRECT** | Any blanket claim that K1's refused four-family security recipe blocks native-only financial qualification. Keep identity admission whenever the scope crosses into issuer/security composition. |
| **CORRECT** | A debt function accepting `as_of` does not prove cutoff-eligible source selection. A later ineligible filing can hide an earlier eligible one when filtering occurs after winner selection. |
| **CORRECT** | Direct share-observation qualification and selecting a current/fully diluted denominator are distinct capabilities. The former need not reopen the latter's held phases. |
| **SUPERSEDE, scope only** | A single undifferentiated debt/share implementation packet is split into input qualification, direct-observation qualification and separately held selected-denominator/publication use. This is decomposition within the existing owners, not new workstreams or authority. |
| **REJECT** | New temporal/financial engines, fabricated identity joins, historical computations mislabeled stored observations, sponsor holdings as issuer debt, or an opt-in wrapper that changes default/live callers. |

Mastermind Snapshot #673 remains an occupied draft implementation, observed at `0b960590c77101b3f3b5545896423f9ad07b7d56`. Reconcile its actual carrier before snapshot integration. This dossier does not prove any current Macro writer lease, clear collisions, or amend W2/W4/W6. Current permitted source custody is a separate implementation prerequisite.

## Bounded slices and discriminating acceptance

**H01 native financial slice:** select one permitted original occurrence and its correction ancestry through the existing query policy into an actual native research reader. Freeze source/recorded cutoffs, concept/fiscal period/unit/basis, governed mappings and inventory witness. Require a same-generation consumer receipt. Add late correction, unknown/date-only clock, withdrawal, ambiguous identity, missing rights and incomplete inventory cases. Keep C5's original acceptance catalogue; one happy path cannot replace it. A subsequent security-level K1 composition needs the accepted identity bridge and cannot inherit success from this native-only slice.

**H05 retained debt inputs:** first check for an equivalent existing qualification adapter. If absent and source custody permits, the pure offline seam belongs inside existing Capital Structure. Inputs include explicit replay mode/cutoff, retained source/term/parser/correction generations, source and system availability, issuer identity distinct from source CIK, fiscal period/form/unit and economic perimeter. Select the eligible version **before** calling the existing pure debt/cash extractor. Output a source-bound eligible payload or typed missing/ambiguous/unsupported result. Missing clocks are not invented. No default caller, pipeline or published artifact changes are included.

Required negatives: a later filing must not conceal an older eligible fact; amendments and parser re-extractions obey their own availability; same-day ambiguity abstains; wrong unit/period/form/issuer and sponsor-held bond par cannot qualify; duplicate capital actions cannot double count. Test positive normal extraction, not only refusals. A repaired input filter does not demonstrate a deployed or natural-time result.

**Direct share observations:** qualify disclosed observations with their original metric, unit, class/security, observation date and split basis. Preserve public-float dollars separately from counts; weighted-average EPS denominators are not outstanding shares. Return unsupported for a requested selected/current/fully diluted denominator while its owner gates remain held. Do not forbid lawful source observation simply because selection/publication is held.

## Rights, falsifiers, unknowns and supersession

No data purchase, retention entitlement, vendor pricing or real source delivery was verified. Identity bridges, allowed source generations, their lawful use, full source inventory and actual reader consumption remain **UNKNOWN/NOT_TESTED** for these slices.

Falsifiers are specific: an accepted native query/reader receipt can discharge H01's bounded proof; an existing cutoff-qualified debt adapter can eliminate a proposed new helper; current accepted owner evidence closing W2/W4/W6 and supplying a qualified share selector can change the selected-denominator hold. Historical labels, a passing fixture or merely finding code cannot do so. Missing inputs may correctly produce refusal; no negative result becomes zero, neutral or a guessed denominator.

Preserve C5/C13/C14 unchanged. This addendum only adjudicates the integration splits above. Full dossiers, real P0 acceptance, financial arithmetic integration, golden-answer dependencies and production authority remain separate obligations.
