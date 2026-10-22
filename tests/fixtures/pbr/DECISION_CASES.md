# PBR decision-case fixtures — redacted production cases with provenance

Schema: `pbr.decision_case_fixture.v1` (one JSON file per case, next to this file).
Regenerate all five byte-for-byte with:

```
python tests/fixtures/pbr/decision_cases/_build_decision_cases.py \
    <case_rows.jsonl> <case_fills.jsonl> <MANIFEST.json> <out_dir>
```

The byte-regeneration test runs only when `PBR_DECISION_CASE_INPUT_DIR` points at a
directory holding `case_rows.jsonl`, `case_fills.jsonl` and the capture `MANIFEST.json`
(evidence, not repository content); otherwise it skips and the integrity tests still run.

Source: read-only research capture `research-capture-20261022T073549Z`
(`captured_utc` 2026-10-22T07:35:49Z, manifest sha256
`4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa`). Each
fixture embeds the verbatim redacted rows, per-line sha256 provenance, the
verbatim fills, and the MANIFEST's own linkage statements. These cases are
decision-process evidence only. **Nothing here claims investment value, and no
statement below adjudicates whether any price, size, or position was good or
bad.**

Redaction policy (identical in every fixture, recorded in
`redaction.policy`): retain all row-level fields verbatim except drop
`perception_input`; filter `holdings` and `effective_holdings` to the case
ticker. The dropped holdings rows are enumerated in
`redaction.other_holdings` (ticker, weight, conviction only).

Defect references `A14`/`A15`/`A16` are the program's case labels
(Mastermind#1693 / PR #1695); the fixtures record them, they do not interpret
them.

---

## mu_2026-10-02_entry.json — regression A14 (MU entry, catalyst dating)

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 75 | `de8f662f6c8fac99b418850ae58ec1498102c16c057db052dd77c113ed2ac8f1` | `decision.v1.8d700b90434853b846f2ef2e` |

Fills (autonomous `fills.jsonl`, file sha256 `778f2846e0e9e527b314a91e0cf105604186c8f081085c0b543a63da54df0a91`):
line 91, `c9ec0d95…` — 2026-10-05 MU buy 92 @ 1069.68, linked via row 75
`settlement_fill_ids[0]` (transaction `b222043d…`). Row 75's second settlement
fill id `2501e62b…` is **not present in the capture** (recorded in
`derived.settlement_fill_ids_absent_from_capture`). The 2026-10-09 MU sell
(`a547c584…`) belongs to no retained settlement link and is deliberately
excluded from this fixture.

Decisive quotes (verbatim):

> "Q4 FY2026 gross margin (reported 2026-10-22) prints below 35.5%, confirming the Q3 revenue-beat/margin-miss pattern is structural not transitional; or crowding crosses ~0.82 into the DELL/EME crowded-top band." (row 75, MU holding `falsifier`)

> "DRAM ASP inflection and preserved HBM share are showing up in flows and news now, with a 10/22 earnings catalyst that can gate full size if gross-margin actuals finally confirm." (row 75, MU holding `why_now`)

> "Micron reported fiscal Q4 and full-year 2026 results on 2026-09-30" (external fact, `verification_status: cited_by_audit_not_refetched`)

**Observed:** the entry was decided `asof` 2026-10-02 with its sizing gate and
falsifier pinned to a report dated 2026-10-22; the audit-cited external facts
(not re-fetched here) state Micron's fiscal Q4 2026 results were published
2026-09-30 — before the entry's `asof`.

**NOT established:** the fill price itself is not shown wrong; nothing here
says MU was a bad position; the mismatch between the row's "Q4 FY2026
(reported 2026-10-22)" label and the audit-cited 2026-09-30 fiscal-Q4
publication is recorded as text, not adjudicated.

**A future contract must do:** treat a dated catalyst whose publication date
already lies before `asof` as unable to support new risk; an entry may not lean
on an already-reported catalyst as a forward gate, and quarter/date labels on
catalysts must be checked against a calendar at decision time.

---

## mu_2026-10-05_amendment.json — regression A15 (MU thesis changed without amendment record)

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 75 | `de8f662f6c8fac99b418850ae58ec1498102c16c057db052dd77c113ed2ac8f1` | `decision.v1.8d700b90434853b846f2ef2e` |
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 76 | `db3d83041e4896c6a268676fd2098e78bd3cb4400bdf70af7535b96dd10a3f58` | `decision.v1.978d5a72e61fdefbaad6c902` |

Fills: none.

`derived.case_holding_changes` enumerates every MU holding key whose value
differs between lines 75 and 76 (14 keys, including `falsifier`, `exit_plan`,
`conviction`, `weight_source`, `expected_horizon`, `why_now`);
`derived.case_row_falsifier_changes` does the same for the row-level
`falsifiers` strings that mention MU.

Decisive quotes (verbatim):

> "MU gross-margin actuals miss below 35.5% on 2026-10-22, breaking the central re-rating thesis for the one offensive add" (line 75, row-level falsifier mentioning MU)

> "MU underperforms SPY by >5% over 60d, OR government support stops accelerating and subsequent operating evidence shows no memory-market improvement (intake falsifier)." (line 76, MU holding `falsifier`)

> "Exit on the 60d rel-return falsifier breach, a radar flip to CONFIRMED_DOWN/distribution on MU itself, or a break of the 200d uptrend; trim into parabolic extension if a blow-off top forms." (line 76, MU holding `exit_plan`)

**Observed:** between 2026-10-02 and 2026-10-05 the held MU position's dated,
quarter-specific falsifier (GM% print on 2026-10-22) and its exit plan were
silently replaced by a relative-performance falsifier and a different exit
plan; both rows are ordinary decision rows — no retained field marks a thesis
amendment or references the prior decision.

**NOT established:** whether an amendment mechanism exists outside the
retained fields (the `decision_context` snapshots these rows consumed were not
retained — see MANIFEST `not_found_or_not_retained`); whether either falsifier
is objectively stronger; the 2026-10-05 MU buy linked to line 75 is not
re-litigated here.

**A future contract must do:** require an explicit amendment record (naming
the superseded `decision_id`) whenever a held position's falsifier or exit
plan changes; unchanged-thesis asserts must fail closed when the falsifier text
mutates without one.

---

## mu_2026-10-22_planless_summary.json — regression A15 (exit justified by "no live thesis")

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 89 | `3561d19ffb9a3f193ab7153c04d2152bfcac823a0730f8cce9f094fd3e18b5df` | `decision.v1.cbf98cc5bfd573cec5ba33e0` |
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 78 | `410bcf6d2fab29d7262a1d4d97db4679272c9bc46b3c81c67ebdd0d55b1fe575` | `decision.v1.9b919e509e3e2d663fa6ae1a` |

Fills: none. Line 89 is the latest queued US summary (2026-10-22) in which MU
is absent from `holdings`/`effective_holdings` and exited via
`requested_exit_decisions`/`exit_decisions` (verbatim MU entries in
`derived`); line 78 (2026-10-07) is the earlier leash-hold record. `derived.summary_and_memo_sentences`
keeps every `summary`/`decision_memo` sentence (split on `". "`) containing
`MU` or `held_without_active_plan`. Line 89's `perception_input` is the one
dropped field in these fixtures.

Decisive quotes (verbatim):

> "It carries no live thesis (rationale was null; Prophet lists it held_without_active_plan), is -14.6% unrealized after only 16 days, and SMH 20d momentum is -8.07%." (line 89, `exit_decisions[0].reason` sentence)

> "book: MU -14.58% unrealized, 16 days held, rationale null" (line 89, exit evidence item)

> "Cycle_blocked veto persists AND MU breaks the Prophet invalidation / loses another ~3-4% from here, OR SMH loses FRESH-BUY leadership — then exit promptly; conversely the veto lifting restores it to a normal hold." (line 78, MU holding `falsifier`)

**Observed:** at line 89 the exit's "no live thesis" evidence is a null local
rationale plus the absence of a Prophet plan; MANIFEST
`not_found_or_not_retained` states `brain/theses.jsonl` has no MU thesis; the
retained local records (lines 75/76, echoed in `derived.prior_thesis_refs`)
did carry falsifiers and exit plans, replaced without an amendment record (see
the amendment case above).

**NOT established:** missing provider plan is **not** evidence there was never
a local thesis — the 75/76 rows prove one existed; the -14.6%/-14.58% figure
is the row's own unrealized mark at that time, not an audited return; nothing
here says the exit itself was wrong or right.

**A future contract must do:** treat "missing provider plan ≠ missing local
thesis" — the local decision record (thesis, falsifier, exit plan) is the
thesis source of truth; a planless/exit claim must distinguish "provider has
no plan" from "no local thesis was ever recorded", and thesis lifecycle events
(create/amend/suspend/expire) must be explicit rather than inferred from a
provider field going null.

---

## cn_688062_2026-08-12_sizing.json — regression A16 (starter wording, cap-sized weight)

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| china | `/opt/mastermind-live-data/portfolios/china/decisions.jsonl` | `/opt/mastermind/data/portfolios/china/decisions.jsonl` | 35 | `9e3fe9e2b1ef4d405739af85b54a940f9e1bac375dd4d27fe1b123845445db82` | `decision.v1.d1f14bdd0e04d6d379f17efe` |
| china | `/opt/mastermind-live-data/portfolios/china/decisions.jsonl` | `/opt/mastermind/data/portfolios/china/decisions.jsonl` | 36 | `2dd37adc0c392ebb30343c01b69e8317c1172524f3632cc48c675651a921babd` | `decision.v1.85921831a0252fec3afb46a2` |
| china | `/opt/mastermind-live-data/portfolios/china/decisions.jsonl` | `/opt/mastermind/data/portfolios/china/decisions.jsonl` | 37 | `83e632664ff62e245634c3ce33ecf411c3fc34842ffbc8f634eb70a391ee7408` | `decision.v1.91cc93129955be21e1590c18` |

Fills (china `fills.jsonl`, file sha256 `ed5f35b9d22c1630a25f696611d2152578afa464037cdb75bd4ed483919ee5a7`):
all five 688062.SS fills — 2026-08-13 buy 3716 @ 32.65 (`c88ac1d2…`), then
sells 2026-08-25 @ 29.23, 2026-09-18 @ 25.73, 2026-09-21 @ 26.62, 2026-10-08
@ 27.04. Per the MANIFEST, the 2026-08-13 entry fill is **UNLINKED** to any
decision row (copied verbatim into `linkage_note`); none of the five carries a
`linked_decision_ids` entry among the retained rows.

Cap reference (`derived.cap_reference`, read verbatim from this worktree at
fixture authoring time on origin/master 230e9a301 — the builder neither
imports nor executes it): `brain/decision_submission.py` line 450,
`"conviction_caps": {"high": 0.18, "medium": 0.12, "low": 0.06},` — the
regional `deterministic_incremental_regional_allocator.v1` policy.

Decisive quotes (verbatim):

> "Its healthcare exposure fits the locally confirmed defensive rotation, but single-source evidence, degraded technical coverage, and an advisory Neural Web kernel that is not FDR-cleared require a measured starter rather than a high-concentration assertion." (line 35, 688062.SS holding `rationale`)

> "Technical coverage is degraded and the signal is single-source." (line 35, holding evidence item)

> "Treat 迈威生物 (688062.SS) as a measured starter; review trim-and-trail first, but exit if the buy-zone gate disappears with weakening healthcare momentum or if trusted eligibility or priceability fails." (line 35, holding `exit_plan`)

**Observed:** the line-35 688062.SS `weight` is exactly 0.12 — the medium
conviction cap of the regional allocator — while the same text calls the
position a "measured starter" justified by single-source evidence; the entry
fill printed 32.65 and every later fill (a partial exit) printed below it.

**NOT established:** a 12% weight is not universally wrong — no statement here
says any cap value is correct or incorrect; the below-entry exit prices are
observed fill prices, not an adjudication that the sizing caused the loss or
that a smaller weight would have avoided it.

**A future contract must do:** stated "starter"/single-source uncertainty must
connect to an explicit risk budget — either an explicit fraction-of-cap or a
named sizing exception — instead of coexisting with a full-cap weight; and any
cap change must be justified independently of this known loss (caps must not
be fitted to a case the caps are later used to judge).

---

## xom_2026-08-12_positive_control.json — positive control (process ran end-to-end on a held winner)

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 38 | `bb5e0334b6c1b35daa315035a1be747a98743fc3b285affd4f6b8e3e2fb7ea92` | `decision.v1.3050203fdc5b109680b6c74e` |
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 39 | `406165bb704ee0ca05ed6b2b47a8ca38aec805a80448943c689551a97655e122` | `decision.v1.c48571d8801d522e51120c37` |
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 40 | `7f2ae1f7664758710790d6d2f4fc48261a1a509c3b43a7bebe25b5a9ab63631b` | `decision.v1.7d572dc4a0fe98f9fa16a92d` |

Fills (autonomous `fills.jsonl`): 2026-08-13 buy 618 @ 158.03 (`a805e529…`,
**UNLINKED** — neither the fill id nor its transaction id appears in any
decisions row, positions ledger, or captured brain run, per the MANIFEST
statement copied verbatim into `linkage_note`) and 2026-08-17 buy 299 @ 160.10
(`8d9c94d7…`, linked to line 40's `settlement_fill_ids[0]`).

Decisive quotes (verbatim):

> "Close below $153; structural failure below approximately $137.50; or Energy loses its 200-day leadership." (line 38, XOM holding `falsifier`)

> "XOM is a genuinely confirmed stock-specific energy leader, not an ETF proxy." (line 40, XOM holding `rationale`, first sentence)

> "the August entry fill is UNLINKED to its decision (settlement link fields only populated from later rows)" (MANIFEST `related_links["XOM entry"]`, also in `linkage_note`)

**Observed:** XOM was targeted 2026-08-12 (queued, `run_id` null), re-affirmed
and executed 2026-08-13/14 with stated falsifiers and exit plans, filled
2026-08-13/17, and was still held (and the row's stated overnight winner) at
line 89 on 2026-10-22; the entry fill has no recorded settlement link.

**NOT established:** one winner does not validate its reasoning — the held
outcome does not confirm the energy thesis, the gate, or that the process
caused the gain; the UNLINKED entry fill is an observed linkage gap, not
evidence of misbehavior.

**A future contract must do:** XOM must remain eligible under any new check —
a replacement gate, falsifier, or sizing rule that would have excluded XOM at
any of 2026-08-12/13/14 must explicitly explain how the positive control
survives; and any new settlement-linkage contract must state how historical
unlinked fills are treated (recorded gap, not silent match).
