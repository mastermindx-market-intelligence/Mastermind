# C2 — native expectations before paid history

Scope: partial MAS-264 dossier and MAS-271/H04 source qualification. Verdict: **native producer identified; qualified historical comparison and real SRC-A1 consumer proof remain unproven**.

## Immutable original and retained thesis

[C2 hardened audit, Macro #8402](https://github.com/mastermindx-market-intelligence/macro/blob/63208615f081804e388c8c30a8d2c0fe6ec86dd4/research/alpha_intelligence/expectation_market_dynamics/COMMISSION_2_PIT_ANALYST_EXPECTATIONS_HARDENED_AUDIT_2026-10-04.md) at `63208615f081804e388c8c30a8d2c0fe6ec86dd4` remains the original research. Its valuable thesis is to qualify incumbent prospective estimates, establish the incremental value of consensus history, and only then consider contributor detail. Consensus movement mixes continuing-contributor changes, entry/exit, stale expiry, withdrawals, fiscal rolls, methodology and corrections. A present snapshot cannot reconstruct historical expectations.

This addendum does not assert that the original overlooked all the limitations below. It makes those limitations binding on the proposed C19 integration slice.

## Current source and exact seams

All Macro links below use `9201f1602bfe47e05a63d61802fbed6f7f55a19d`.

| Owner surface | Verified source behavior | Integration consequence |
|---|---|---|
| [`collectors/equity_revisions.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/equity_revisions.py#L281), `_expectation_rows`; blob `8f1d3d822543fd11e18b5a78b957259d43e4c164` | EPS/revenue consensus snapshots preserve raw horizon and optional provider `period_end`; issuer/security, fiscal period/year, unit/currency/basis and contributor ID are null; source-effective/publication clocks are null; provider/system observation clocks are retained; rights are `UNKNOWN` | Useful prospective lineage, not a fully comparable historical pair |
| Same collector, supersession logic | Differing **non-null** `period_end` prevents false supersession; null anchors do not prove equal target identity | Never compare relative labels such as `FY1` or `+1q` as immutable targets |
| Same collector, observation-clock guard | Caller-supplied historical system clock more than 60 seconds from now is refused | Preserve prospective capture; do not relabel later retrieval as past knowledge |
| [`engine/theme_revisions.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/theme_revisions.py#L69), `_latest`, `_history` | Reads legacy `data/revisions/latest.parquet` and `history.parquet` | A concrete reader exists, but this is not proof it consumed SRC-A1 long-form observations or qualified comparability |
| [`DATA_CLOCK_RIGHTS_MATRIX.md`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/research/alpha_intelligence/expectation_market_dynamics/DATA_CLOCK_RIGHTS_MATRIX.md) | Nullable fiscal mapping, distinct clocks and typed missing/rights states | Use this existing contract; do not create a third analyst-history store |

The Program CEO independently inspected the exact producer fields and legacy reader paths after the native Sol COO review. This is source evidence only: historical row counts, source coverage and deployed consumption were not inspected.

## Dispositions and collisions

| Disposition | Claim or recommendation |
|---|---|
| **RETAIN** | SRC-A1/K3E prospective ownership, source-grounded missingness, attempts and lineage. MAS-119 owns common expectation semantics; MAS-118 owns incorporation science. |
| **CORRECT** | Any interpretation that current source proves mature institutional PIT consensus. Actual retained historical coverage is **UNKNOWN** here; null source clocks and comparability fields are directly observed code behavior. |
| **CORRECT** | Fiscal-roll protection is conditional on known differing target anchors. Same relative horizon does not establish same fiscal target; missing anchors are not evidence of equality. |
| **REJECT** | Continuing-analyst revision attribution when contributor identity is absent; guidance-versus-consensus without an issuer-guidance receipt and matched target/basis; inferred currency, unit, share basis or identity. |
| **SUPERSEDE, narrowly** | Any C19 instruction to acquire broad paid history before qualifying this native baseline. Purchase remains conditional after measured gap and rights/value review. No original historical finding is otherwise erased. |

Candidate source custody remains separate. At review, Macro #8312 was draft/open at `69d8c407e7033b9aa1e2fb4699398b454d7864c2`; #8337 was draft/open at `13910854fbd652dcdf975301bdc8c6728c2e4767`. The latter's proposed `engine/k3e_expectation_surface.py` returned 404 at the inspected main revision. Candidate repair evidence may supersede a defect only for its exact reviewed carrier; neither candidate grants current-main or deployment acceptance. These observations do not establish writer liveness or an exclusive lease.

## Bounded implementation and acceptance

First qualify the existing owner's input contract, before wiring a new consumer. A synthetic positive pair must have the same issuer, metric, immutable fiscal target, unit, currency, accounting/share basis and observation type, plus declared rights and cutoff-qualified clocks. Deterministic subtraction may then produce the explicitly named comparison. This positive fixture would prove arithmetic/admission only, not existence of a lawful real pair.

Mutate one property at a time and require a typed unavailable/ambiguous result:

- Fiscal target roll or missing target anchor; no comparison on raw horizon alone.
- Contributor-only composition change; no claim of same-analyst revision.
- Issuer guidance versus consensus without a qualified guidance source.
- Currency, unit, GAAP/adjusted or basic/diluted mismatch.
- Post-cutoff correction, unresolved issuer/security join, or missing rights for the requested operation.
- Missing source publication clock for a **source-as-known** claim. Operational-as-known uses its own actual observation/recording/admission requirements; do not universally require a source clock where the declared view does not depend on it.

Next, use a real permitted owner pair or return the precise missing-input result. A reader receipt must identify the exact observation generations, cutoff/view, target semantics, source contract, consumer build and actual disposition. Do not upgrade legacy theme breadth into this receipt by renaming it. A missing prerequisite is a valid qualification result; it does not satisfy MAS-271's real positive consumer exit.

## Procurement, unknowns and falsifier

No vendor is selected, contacted or purchased. A later sample decision must name the consumer and missing historical interval/target coverage; compare the cheapest adequate consensus baseline against any contributor-level increment; verify delivered original vintages, corrections, retention/transform/display/model-use rights, cost and integration burden. Price, entitlement, historical coverage and incremental information value remain **UNKNOWN/NOT_TESTED**.

Falsifier: a current accepted owner receipt for a real historical pair with matching identity/target/basis, qualified clocks and rights, and exact reader consumption. Such a receipt would advance the specific comparison without certifying unrelated metrics, regions or histories. Kill/defer any sample that cannot supply the history or rights needed by its named consumer; a null incremental result is acceptable. No market outcomes were accessed here.

## Supersession statement

Preserve C2 verbatim. This addendum narrows H04 to native source qualification and preserves occupied candidates. It supersedes only the interpretations and sequencing explicitly identified above; it does not close C2, MAS-118, MAS-119, K3E, MAS-264 or MAS-271.
