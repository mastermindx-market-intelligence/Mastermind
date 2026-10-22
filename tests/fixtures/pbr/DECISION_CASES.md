# PBR decision-case fixtures — redacted production cases with provenance

Schema: `pbr.decision_case_fixture.v1` (one JSON file per case, next to this file).
Regenerate all five byte-for-byte with:

```
python tests/fixtures/pbr/decision_cases/_build_decision_cases.py \
    <case_rows.jsonl> <case_fills.jsonl> <MANIFEST.json> <out_dir>
```

Source: read-only research capture `research-capture-20261022T073549Z`
(`captured_utc` 2026-10-22T07:35:49Z, manifest sha256
`4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa`). These cases
are decision-process evidence only. **Nothing here claims investment value, and
no statement below adjudicates whether any price, size, or position was good or
bad.**

## Data rights and redaction (seat ruling SR-1)

The repository is public and the paper-book narrative is a paid product surface,
so no production narrative is committed here.

- **In the repository (SR-1 option b):** typed, numeric and case fields are kept
  verbatim — tickers, dates, ids, row indices, sizes, prices, weights,
  probabilities, conviction labels, enums. Every string that contains whitespace
  (narrative / PM prose) inside `records`, `fills` and `derived` is replaced by a
  `pbr.prose_digest.v1` object: `sha256` of the UTF-8 original, `length` in
  characters, the `iso_dates` and fiscal `period_labels` it mentions, and which
  `terms` of a declared closed vocabulary it contains (`earnings`,
  `held_without_active_plan`, `no live thesis`, `single-source`, `starter`).
  The rule, patterns and vocabulary are recorded in `redaction.prose_digest` of
  every fixture.
- **Also dropped:** `perception_input`; `holdings` and `effective_holdings` are
  filtered to the case ticker (the dropped rows are enumerated in
  `redaction.other_holdings` as ticker, weight and conviction only).
- **Kept verbatim because they are builder-authored, not production prose:**
  `capture`, `redaction`, `linkage_note` (the capture MANIFEST's own linkage
  statement), `external_facts` (public facts cited by the program audit, marked
  `cited_by_audit_not_refetched`) and `derived.cap_reference` (a quote of this
  repository's own source).
- **Outside the repository (SR-1 option c):** the verbatim rows live under
  `/Volumes/Mastermind/evidence/pbr/research-decision-case-inputs-20261022T073549Z/`
  (`case_rows.jsonl`, `case_fills.jsonl`, `MANIFEST.json`, `SHA256SUMS`). Point
  `PBR_DECISION_CASE_INPUT_DIR` at that directory to run the env-gated tests:
  byte-for-byte regeneration, every digest matching an original string, and no
  original prose of 24 or more characters appearing in any committed file under
  `tests/fixtures/pbr/`. Without it those tests skip with a reason and the
  integrity tests still run.

Defect references `A14`/`A15`/`A16` are the program's case labels
(Mastermind#1693 / PR #1695); the fixtures record them, they do not interpret
them. Each case below cites the decisive fields by fixture path and digest; the
digest tables are checked by the test suite against the fixtures.

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

Decisive fields (digests):

| field (fixture path) | sha256 (first 12) | length | iso_dates | period_labels | terms |
|---|---|---|---|---|---|
| `records@75.case_holding.falsifier` | `bb74d2e837e7` | 209 | `2026-10-22` | `Q4 FY2026` | — |
| `records@75.case_holding.why_now` | `abd5e36612e0` | 177 | — | — | `earnings` |

External fact (public, builder-authored, `verification_status:
cited_by_audit_not_refetched`): "Micron reported fiscal Q4 and full-year 2026
results on 2026-09-30".

**Observed:** the entry was decided `asof` 2026-10-02; its MU falsifier names
the period label `Q4 FY2026` and the date 2026-10-22, and its `why_now` names an
earnings catalyst; the audit-cited external facts (not re-fetched here) state
Micron's fiscal Q4 2026 results were published 2026-09-30 — before the entry's
`asof`.

**NOT established:** the fill price itself is not shown wrong; nothing here
says MU was a bad position; the mismatch between the row's `Q4 FY2026` /
2026-10-22 pairing and the audit-cited 2026-09-30 fiscal-Q4 publication is
recorded, not adjudicated.

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
`falsifiers` strings that mention MU. Prose values appear as digests, so a
change is visible as a differing `sha256`.

Decisive fields (digests):

| field (fixture path) | sha256 (first 12) | length | iso_dates | period_labels | terms |
|---|---|---|---|---|---|
| `derived.case_holding_changes.falsifier.old` | `bb74d2e837e7` | 209 | `2026-10-22` | `Q4 FY2026` | — |
| `derived.case_holding_changes.falsifier.new` | `72c5a841697d` | 167 | — | — | — |
| `derived.case_holding_changes.exit_plan.old` | `bda8a5c4fd80` | 210 | — | — | `earnings` |
| `derived.case_holding_changes.exit_plan.new` | `f4e984a3a404` | 189 | — | — | — |
| `derived.case_row_falsifier_changes.old[0]` | `613f7238e46d` | 119 | `2026-10-22` | — | — |

**Observed:** between 2026-10-02 and 2026-10-05 the held MU position's
falsifier and exit plan were replaced: the line-75 falsifier names `Q4 FY2026`
and 2026-10-22, the line-76 falsifier names no date and no fiscal period, and
the exit plan's digest changed as well; both rows are ordinary decision rows —
no retained field marks a thesis amendment or references the prior decision.

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

## mu_2026-10-22_planless_summary.json — regression A15 (exit justified by the `no live thesis` term)

| book | host path | in-service path | line | line_sha256 | decision_id |
|---|---|---|---|---|---|
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 89 | `3561d19ffb9a3f193ab7153c04d2152bfcac823a0730f8cce9f094fd3e18b5df` | `decision.v1.cbf98cc5bfd573cec5ba33e0` |
| autonomous | `/opt/mastermind-live-data/portfolios/autonomous/decisions.jsonl` | `/opt/mastermind/data/portfolios/autonomous/decisions.jsonl` | 78 | `410bcf6d2fab29d7262a1d4d97db4679272c9bc46b3c81c67ebdd0d55b1fe575` | `decision.v1.9b919e509e3e2d663fa6ae1a` |

Fills: none. Line 89 is the latest queued US summary (2026-10-22) in which MU
is absent from `holdings`/`effective_holdings` and exited via
`requested_exit_decisions`/`exit_decisions` (the MU entries, digested, are in
`derived`); line 78 (2026-10-07) is the earlier leash-hold record.
`derived.summary_and_memo_sentences` keeps a digest of every
`summary`/`decision_memo` sentence (split on `". "`) that mentions `MU` or
`held_without_active_plan`. Line 89's `perception_input` is the one dropped
field in these fixtures.

Decisive fields (digests):

| field (fixture path) | sha256 (first 12) | length | iso_dates | period_labels | terms |
|---|---|---|---|---|---|
| `derived.mu_exit_decisions[0].entry.reason` | `b5346150d5f6` | 597 | — | — | `held_without_active_plan`, `no live thesis` |
| `derived.mu_exit_decisions[0].entry.evidence[2]` | `ce3f021a9a31` | 64 | — | — | `held_without_active_plan` |
| `derived.mu_exit_decisions[0].entry.evidence[3]` | `daf38df2b4c4` | 57 | — | — | — |
| `records@78.case_holding.falsifier` | `5cbe339eafab` | 213 | — | — | — |

**Observed:** at line 89 the MU exit reason carries the terms `no live thesis`
and `held_without_active_plan`, and MU has no case holding on that line;
MANIFEST `not_found_or_not_retained` states `brain/theses.jsonl` has no MU
thesis; the retained local records (lines 75/76, referenced in
`derived.prior_thesis_refs`) did carry falsifiers and exit plans, replaced
without an amendment record (see the amendment case above).

**NOT established:** a missing provider plan is **not** evidence there was
never a local thesis — the 75/76 rows prove one existed; nothing here says the
exit itself was wrong or right.

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

Decisive fields (digests):

| field (fixture path) | sha256 (first 12) | length | iso_dates | period_labels | terms |
|---|---|---|---|---|---|
| `records@35.case_holding.rationale` | `04a8eff527d7` | 531 | `2026-08-19` | — | `single-source`, `starter` |
| `records@35.case_holding.evidence[4]` | `3ebd89009c38` | 63 | — | — | `single-source` |
| `records@35.case_holding.exit_plan` | `84011340c9dd` | 199 | — | — | `starter` |

**Observed:** the line-35 688062.SS `weight` is exactly 0.12 with conviction
`medium` — the medium conviction cap of the regional allocator — while the same
holding's rationale and exit plan carry the terms `starter` and
`single-source`; the entry fill printed 32.65 and every later fill (a partial
exit) printed below it.

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

Decisive fields (digests):

| field (fixture path) | sha256 (first 12) | length | iso_dates | period_labels | terms |
|---|---|---|---|---|---|
| `records@38.case_holding.falsifier` | `b3278894a5b4` | 105 | — | — | — |
| `records@40.case_holding.rationale` | `47414b02e5bc` | 767 | — | — | — |

Capture linkage statement (builder-authored MANIFEST text, verbatim in
`linkage_note`): "the August entry fill is UNLINKED to its decision (settlement
link fields only populated from later rows)".

**Observed:** XOM was targeted 2026-08-12 (queued, `run_id` null), re-affirmed
and executed 2026-08-13/14 with stated falsifiers and exit plans, filled
2026-08-13/17, and was still held at line 89 on 2026-10-22; the entry fill has
no recorded settlement link.

**NOT established:** one winner does not validate its reasoning — the held
outcome does not confirm the energy thesis, the gate, or that the process
caused the gain; the UNLINKED entry fill is an observed linkage gap, not
evidence of misbehavior.

**A future contract must do:** XOM must remain eligible under any new check —
a replacement gate, falsifier, or sizing rule that would have excluded XOM at
any of 2026-08-12/13/14 must explicitly explain how the positive control
survives; and any new settlement-linkage contract must state how historical
unlinked fills are treated (recorded gap, not silent match).
