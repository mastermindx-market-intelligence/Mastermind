# PBR work packages — owners, dependencies, acceptance

Source of the packet definitions: `MASTERPLAN.md` §11.2 (ordered work packets) and §11.3 (gates).
This file adds the live owner, status and carrier for each packet. Status vocabulary:
`NOT_STARTED` · `COMMISSIONED` (an owner holds it) · `IN_LANES` (fabric lanes running) · `RETURNED`
(worker returns in hand, not yet adjudicated) · `ACCEPTED` (owner adjudicated, PR open/merged with
discriminating tests + independent review) · `INSTALLED` (proven on the real path) · `HELD` (named hold).
"Merged" is never "installed"; "installed" is never "accepted by the commissioning authority".

| Packet | Outcome (condensed) | Owner | Depends on | Status | Carrier(s) | Acceptance evidence (condensed from §11.2) |
|---|---|---|---|---|---|---|
| W0 commission & baseline | Adopt the audit, reconcile owners/heads, publish one integrated issue + risk register, bounded scopes | Fable seat | — | COMMISSIONED 2026-10-22 | this directory; issue + program PR named in `FABLE_START_HERE.md` | manifest, scopes, preserved markers, next executable tasks, exact holds |
| W1 account truth | HK six-symbol quantity bridge; dated explanation of every non-trade cash residual (US +9,214.51 USD, CN +5,782.62 CNY, HK withheld); seed/opening balances; corporate-action/repair history | ECON (pbr-econ) | W0 | COMMISSIONED | new PR(s) by ECON | per-book quantity/cash/wealth bridge; attributable corrections; unresolved intervals explicitly bounded; no balancing trades, no reset |
| W2 prices & replay | Close A02 cost-as-market NAV; A03 direction-aware known-at (#726) + #727/#728 consumers; reconcile #824 with the bot freeze; prove #1614 consumption (install is a separate release gate) | ECON | W0; serial with W1 on `paper_account.py` | COMMISSIONED | #824 #726 #727 #728 (+ new) | future/stale/wrong-session/FX/adjustment counterexamples rejected; source→selected price→receipt trace; no numeric change hidden as a diagnostic |
| W3 economic simulator | Native-currency cash/income/cost events, corporate actions, venue lots (SSE main/STAR, SZSE, HKEX board+odd lot), feasible/partial fills, versioned simulator | ECON | W1 + W2 contracts | NOT_STARTED | — | reconciled venue fixtures; realistic partial/rejected fills; fee/income accounting; versioned simulator + comparison baselines |
| W4 reliable management | Resolve the no-submission failure chain (CN/HK rejected daily since 10-09; terminal label "error result: success"); lifecycle disposition projection; recovery + accepted no-change proofs; installed-identity proof on production | RUNTIME (pbr-runtime) | W0 | COMMISSIONED | #1147 (+ new) | real admitted request→completion→consumer chain; natural-cycle dispositions; negative ambiguous-retry + no-duplicate-effect proofs |
| W5 V3-S0 evidence | Immutable point-in-time snapshot binding actual account, pending effects, qualified inputs, cutoff; one real snapshot→inspector journey | RESEARCH (pbr-research) | W0; W1/W2 interfaces for qualified inputs | COMMISSIONED | #673 #1357 | one real qualified journey; missing/future/forged/changed context cannot become complete evidence |
| W6 PM views & claims | Typed fact/date/unit/currency checks (MU 2026-10-02 regression), durable thesis + amendments (MU amendment regression), evidence-conditioned risk budget (688062.SS regression), bounded claims, source-family independence | RESEARCH | W5 | COMMISSIONED (contract + regression cases first) | #1357 (+ new) | MU fact + thesis cases handled; request/snapshot identity survives; no votes / direct numeric authority; cost + coverage recorded |
| W7 construction | Risk anchor, uncertainty-conditioned budgets, bounded tilts, feasibility, stability — shadow only | RESEARCH | W3 W5 W6 | NOT_STARTED (spec-freeze lane may start) | — | same-set categorical / equal-weight controls; every weight explained; China case + perturbations handled |
| W8 outcomes & experiments | fill→episode→source attribution, factor/cash bridge, trial registry, paired evaluation | RESEARCH | W1 W3 W5 | NOT_STARTED (protocol-freeze lane may start) | — | reproducible net outcomes; declared missingness; no lookahead / trial laundering |
| W9 coherent product | actual / decision / pending / performance / opportunities / position-review / operations views + failure states; authenticated desktop+mobile proof | PRODUCT (pbr-product) | W0; truthful partial versions may ship earlier | COMMISSIONED | #1572 #1580 #1586 merged (consumers) + new | API/browser agreement across books, desktop/mobile, permissions, partial data, closed markets |
| W10 prospective shadow | Challenger + frozen incumbent on upcoming snapshots through the same qualified simulator; separate storage, zero live effects | RESEARCH + ECON | W3–W9 | NOT_STARTED | — | identical assumptions; immutable policy/simulator versions; natural sessions |
| W11 review & cutover | Decide limited paper-policy authority; migrate only the qualified version | Fable seat | W10 evidence + independent review + cutover authority | NOT_STARTED | — | predeclared increment + selection evidence; acceptable risk/cost; proven rollback |

## Defect register → packet map (A01–A16 from MASTERPLAN.md §4)

| ID | P | Packet | One-line disposition |
|---|---|---|---|
| A01 | P0 | W1 | HK six-symbol replay bridge through the existing ledger owner; immutable lineage |
| A02 | P0 | W2 | `paper_account.mark()` NAV must not fall back to `avg_cost`; unavailable stays explicit |
| A03 | P0 | W2 | `marks._days_between()` absolute diff + undated Polygon snapshot → direction-aware known-at (#726) |
| A04 | P0 | W4 | no-submission chain + "error result: success" terminal; original run identities end to end |
| A05 | P0 | W2 | positive-scalar fallback as execution price → explicit executable-price eligibility contract after #1614 |
| A06 | P1 | W3 | whole-share abstraction → versioned venue lots / odd lots / settlement |
| A07 | P1 | W3 | universal 4% cash + missing fees/income → declared native-currency conventions, versioned events |
| A08 | P1 | W8 | V2 power floors unmet → extend observations, never reset the marker |
| A09 | P1 | W8 | candidate-source attribution missing → decision→fill→outcome lineage |
| A10 | P1 | W7 | three-category allocator → test V3 anchor + tilts against simpler controls |
| A11 | P1 | W7/W8 | cash cause → intended / constraint / stranded cash waterfall, each tested |
| A12 | P1 | W2 | benchmark window/sidecar selection → close #1432/#1433/#1434 with consumer proof |
| A13 | P2 | W0/W4 | shipping-vs-working confusion → one owner map, installed-identity proof by blob, real journeys |
| A14 | P0 | W6 | MU contradicted earnings date + unreconciled price basis → typed facts, primary-event verification before new risk |
| A15 | P1 | W6 | MU thesis changed without amendment bridge → persistent position thesis + amendments, local vs provider plan status |
| A16 | P1 | W6/W7 | 688062.SS 12% "starter" → quality-conditioned risk budget, explicit role, matched alternative-sizing evaluation |
