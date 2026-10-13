# Acceptance matrix

This supplements the original C5 forty-case and C9 Q01-Q20 catalogues and every retained specialist acceptance casebook. None is silently narrowed. These 50 cases are **required future observations**, not 50 tests executed in this authoring session. Exact test implementation, expected units, source identity and evidence thresholds are frozen before their relevant effects/outcomes.

## Evidence classes

Source inspection proves code/contract presence. Isolated synthetic tests prove the exercised logic only. Real retained artifacts prove the specified input behavior. Actual consumer/browser receipts prove that path. Natural prospective outcomes address a separately declared empirical question. Every receipt states which class it is and what it does not prove.

| ID | Family | Case | Package | Required observation |
|---|---|---|---|---|
| A01 | Temporal | Real native original and later correction | WP03 | Exact dual cutoffs select expected version; source inventory and reader receipt retained. |
| A02 | Temporal | Date-only interval crosses an intraday cutoff | WP03 | Unknown/refused for that view, never invented midnight precision. |
| A03 | Temporal | Naive or invalid timestamp | WP16 | Source-specific timezone/precision evidence or typed failure; invalid calendar date not normalized. |
| A04 | Temporal | Uniformly old source legs | WP16 | Source-specific freshness against request/reference time, not newest old leg. |
| A05 | Temporal | Future source clock | WP16 | No future eligibility or promotion of page cutoff; preserve diagnostic. |
| A06 | Temporal | Missing event source clock but fresh serving stamp | WP16 | Serving time separate, source clock unknown; no silent ok. |
| A07 | Temporal | Corrected history after sealed answer | WP20 | Original recorded view immutable; later revised view explicitly different. |
| A08 | Identity | Same ticker with different historical issuer/listing | WP04 | Use effective-dated native bridge or refuse join. |
| A09 | Identity | Same-native financial subject without K1 security bridge | WP03 | Allow qualified native-only use without implying cross-type acceptance. |
| A10 | Evidence | Two syndications of one origin | WP05 | Preserve source refs and shared origin without doubling independence. |
| A11 | Evidence | Missing dependence edge or correction new ID | WP05 | No empirical independence claim; correction ancestry retained. |
| A12 | Financial | Later ineligible filing hides earlier eligible filing | WP13 | Select eligible retained source before winner extraction. |
| A13 | Financial | Wrong unit, fiscal period or economic perimeter | WP13 | Typed mismatch; no scalar computed from incompatible input. |
| A14 | Financial | Public float value vs count and weighted-average vs outstanding shares | WP14 | Metric and denominator meaning preserved; no convenient substitution. |
| A15 | Financial | Authorization vs execution, split and warrant double count | WP14 | Actual state and basis retained; no invented dilution or cash effect. |
| A16 | Financial | Direct issuer scenario with disclosed driver and explicit assumption | WP15 | Reproducible nontrivial numerical consequence, units, horizon and sensitivity. |
| A17 | Financial | No measured supply-chain exposure | WP15 | Qualitative mechanism or refuse numeric consequence; no arbitrary economic_share. |
| A18 | Expectations | Real comparable estimate pair | WP09 | Identical target/unit/basis/issuer, known clocks and permitted use; real reader proof. |
| A19 | Expectations | Relative horizon roll or missing target anchor | WP09 | No unsupported same-target subtraction. |
| A20 | Expectations | Changed contributors but no contributor identity | WP09 | No same-analyst revision attribution. |
| A21 | Expectations | Guidance vs prior guidance, no consensus | WP10 | Named guidance delta only; no consensus surprise. |
| A22 | Macro | Producer path fixed but envelope still wrong | WP11 | Full intended producer-to-reader fixture test catches both failures. |
| A23 | Macro | Model/market median or current consensus supplied after event | WP11 | Not an eligible pre-event economist baseline. |
| A24 | Macro | Original print and later revision | WP11 | Both replayable; revision delta separate from expected revision surprise. |
| A25 | Health | Fresh producer, stale actual consumer bytes | WP08 | Actual consumed generation and content watermark govern displayed freshness. |
| A26 | Health | Missing receipt, unreadable, absent, malformed or denied source | WP08 | Distinguish where evidenced; inspection blindness remains unknown. |
| A27 | Health | Changing universe denominator | WP08 | Versioned applicable universe; coverage cannot improve through silent exclusions. |
| A28 | Security | Private evidence for public/other account view | WP18 | Denied content and metadata withheld according to incumbent policy; no cross-user cache leak. |
| A29 | Security | Global attestation receipt for another subject | WP17 | No subject-specific permission inferred without correct binding. |
| A30 | UX | Switch ticker while old request is in flight | WP19 | Old response cannot replace the new company answer. |
| A31 | UX | Evidence link and correction drill-down | WP18 | Open exact revision/span used by displayed claim; generation visible. |
| A32 | UX | Partial essential evidence vs optional enrichment | WP17 | Core conclusion bounded; optional absence not zero/neutral confidence. |
| A33 | Evaluation | Append error followed by same-instance retry | WP06 | No false durable state; permitted retry persists exactly once. |
| A34 | Evaluation | Corrupt/torn/unreadable ledger and concurrent writers | WP06 | Declared durable accounting contract tested; no silent evaluation admission. |
| A35 | Evaluation | Future-dependent cost warmup, initial loss, rank deficiency | WP07 | Original C9 questions preserved; valid positive and negative controls. |
| A36 | Evaluation | Same exposed holdout under renamed family or another agent | WP31 | Exposure persists; no fresh-study fiction. |
| A37 | Evaluation | Source-family ablation leaves descendants | WP31 | Remove information descendants or bound interpretation; use common keyed support. |
| A38 | Ownership | Missing filing row or mixed ownership planes | WP23 | No inferred sale/current flow; legal perimeter and partialness retained. |
| A39 | Borrow | Observed zero, no message and censored availability | WP24 | Distinct outputs; no market-wide supply claim. |
| A40 | Microstructure | Sparse trade BBO used for continuous book or participant labels | WP25 | Unsupported grain/identity refused; late quotes and unavailable OI excluded. |
| A41 | Telemetry | Old source edition, aggregate metric and issuer bridge | WP26 | Edition versus collection clocks separate; no unsupported issuer effect. |
| A42 | Telemetry | Queue capacity called load or revenue | WP27 | Correct quantity meaning and actual issuer KPI evidence or refusal. |
| A43 | Regional | A/H, CCASS/13F, reversal/revision non-equivalence | WP29 | Region-native identities and semantics preserved; missing is not zero. |
| A44 | Generality | Second issuer or contradicting event | WP22 | Same reusable contracts; selection not based on realized winner. |
| A45 | Production | Merged dark route or flag without real source consumer | WP32 | No production completion claim; exact served code/config/use verified separately. |
| A46 | Production | Rollback and source correction during partial outage | WP32 | Known previous release recoverable, old snapshots intact, no duplicate effect. |
| A47 | Orchestration | Native child lacks Fabric action; operator lacks worker spawn | WP00 | Transparent permitted relay or operator direct execution; no invented capability. |
| A48 | Orchestration | Interrupted modify, denied action or original C19 not_found | WP00 | Freeze affected effect and reconcile; no alternate-key/carrier retry. |
| A49 | Orchestration | Eight coordinators inherit separate budgets | WP00 | Reject multiplying root/grant/capacity; observe existing shared accounting. |
| A50 | Closure | One demo finished but P1/evaluation/source obligations remain | WP33 | Mission incomplete or explicit evidenced disposition; no orphaned work. |

## Global completion gates

A full P0 answer requires an actual permitted event, matched company/financial subject, usable original/correction financial evidence, reproducible meaningful mechanism/calculation, qualified expectation comparison or explicit claim limitation, source overlap, real reader and user-path proof. An all-null or static AAPL demonstration is not the completed product.

The macro and evaluation P0 obligations are separately accepted even when they are not ingredients in a particular company narrative. P1 domains receive evidence-based acceptance/rejection/deferral, never a convenient blanket defer. Required review remains independent where current release/science law demands it.

No fixed minimum trading return or significance level is invented here. The evaluator freezes the estimand, useful-effect threshold, sample/power or precision plan, dependence, trial exposure and costs before outcomes. Failure to establish alpha is a valid scientific result, not permission to relax source correctness or fabricate a successful product claim.

Natural time maturity remains an external fact. A declared future observation without a verified executor and return path is not scheduled. Code, deployed configuration, active data path, actual use and empirical value are reported separately.
