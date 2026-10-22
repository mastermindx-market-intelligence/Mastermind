# OPERATION pbr-res-r1750r2 — independent DELTA re-review of PR #1750 (findings F1–F5 of R-1750) and of spec errata PR #1754
Class: review · Complexity: C2 · Output: ONE file `~/lanes/tmp/pbr-res-r1750r2/out/REVIEW.md`. You change no repository file (temporary probe edits are allowed only if you restore them; end with `git status --porcelain --untracked-files=all` empty).

## Targets (exact)
- **PR #1750**, branch `pbr/research-w2-r1-facts-thesis-budget`, head `eb22e90224d3053217033cca64095f296d16feb6` (verify `git rev-parse HEAD` in your worktree). The prior review was at `b36ed728003bd726baaf940197683bc7b8665b04`. **Delta to review: `git diff b36ed728..HEAD`** (two commits, six files). Full context: `git diff fc4db8de..HEAD` (base master `fc4db8de1aa78e29572a201701990fc3a793a4a3`).
- **PR #1754** (spec errata), branch `pbr/research-w2-r1-spec-errata`, head `9b9cc7eb049bd459f6147260c3a69a276fbbacfb`, base master `3a6d165fe398507bac179ab76b4ee01aa13116db`. Read it with `git diff 3a6d165f..9b9cc7eb` and `git show 9b9cc7eb:docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md` (both commits are already fetched into your repo).
- Prior review: `~/lanes/tmp/pbr-res-r1750r2/prior/REVIEW.md` (sha256 `c2077b486e7862208ce2ce48b1caf35565a3237de19c8b27ab434056e5f4cb37`; verify). Read F1–F5 and the A2 flag completely first. Its findings: F1 BLOCKER (rule (i) contradicts a forward claim from any dated primary record, with no event-identity check, and admits class-less records), F2 MAJOR (the unreconciled fact factor was hard-coded), F3–F5 MINOR (a docstring citing a spec path absent on master; a falsy `thesis_id` kept; bare numeric config leaves accepted).
- Binding spec as built: `~/lanes/tmp/pbr-res-w2r1-ls5/SPEC.md` (PR #1701 head `a654035`, sha256 `f901e08c3422351cc21487a4c5f4e18a1da5131384e8f4c98a6a201900e3b673`). #1754 amends it with §8; the seat rulings below override both where they differ.
- Original off-repo extracts for the env-gated tests: `~/lanes/tmp/pbr-res-w2r1-ls5/inputs/` (read-only; they contain original PM prose; never quote, copy or paraphrase any of it into REVIEW.md; refer to it only by field name and sha/length).

## Parent rulings the repair implemented (binding; verify the code against them)
- **F1.** Event identity is `period` (compared after `str(...).strip().upper()`); when both the fact and a record carry a non-empty `event` label it must match too (case-insensitive). A record is primary only when `source_class` ∈ `PRIMARY_EVIDENCE_CLASSES`; class-less records are excluded and counted. Records partition into `matched` / `other_identity` (period differs, or event label conflicts) / `unidentified` (no period). Only `matched` takes part in any date comparison. Order: claimed > asof → any matched record ≤ asof → CONTRADICTED `catalyst_already_published_before_asof`, else matched → VERIFIED `forward_catalyst_confirmed_by_primary`. Claimed ≤ asof → matched record dated == claimed → VERIFIED `past_event_confirmed_by_primary`, else matched → CONTRADICTED `primary_dates_past_event_differently`. Fact without period while primary records exist → UNVERIFIED `event_identity_absent`; period but nothing matched → UNVERIFIED `no_identity_matched_primary_record`; no primary records at all → the previous no-primary reasons. `compared` carries matched dates only plus `claimed_period` and the four counts. MU must stay CONTRADICTED in all four components, with the MU identity `period=FY2026-Q4` declared in tests under spec SR-1 rule (3).
- **F2.** The `BASIS_UNRECONCILED`/CONTRADICTED fact factor is read from the frozen config (`unreconciled_fact_factor`), not hard-coded.
- **F3.** Docstrings only: the two module docstrings name "the PBR facts/thesis/risk-budget spec (PR #1701)" instead of a file path; the config is NOT changed (sha256 must stay `355eba682718818246c419735b7ad5de8acaffd945deaa47f7ce6da181351806`).
- **F4.** `out["thesis_id"] = out.get("thesis_id") or make_thesis_id(...)`: a falsy id is regenerated, a supplied id kept.
- **F5.** The params loader rejects a bare int/float/bool parameter leaf (one without `value` + `justification`), except top-level `version`.
- Seat rulings carried from the build (for the §8 accuracy check): **Q1** watched-field mapping thesis_statement←rationale, falsifiers←falsifier, check_by/time_stop←expected_horizon, exit_conditions←exit_plan, size_cap/target_weight←proposed_weight, catalyst←why_now; null later `proposed_weight` = not restated; realised weight/weight_source never watched; conviction is a per-cycle observation (`pbr.thesis_observation.v1`, append-only `observations.jsonl`), never an amendment or finding. **Q2** typed `pbr.reference_mark.v1`; only ECON_UNION_MARK with complete provenance (store_ref, asof, symbol, mark_source non-empty; mark asof ≤ decision asof; symbol equal) qualifies; CALLER_SUPPLIED/incomplete/absent → `BASIS_UNRECONCILED` with reason `reference_mark_not_qualified` / `reference_mark_absent`; no fill-price fallback. **Q3** `freeze_owner: pbr-seat`; shadow-only; negative import test. **Q4** `reason_code` closed enum {FALSIFIED, TIME_STOP, EXIT_PLAN_HIT, SUPERSEDED, MANUAL}, required for INVALIDATED/EXCLUDED, validated whenever present; optional `note`. **CR-R7** schema strings are module constants pinned by tests; `config/contracts.yml` untouched.

## Acceptance (cite path:line; each with PASS/FAIL and evidence)
D1. **F1 closed.** Read `_primary_records` and `_verify_event_date`. Run your own probes (a scratch script under `~/lanes/tmp/pbr-res-r1750r2/`, not in the repo) and report verdict + reason for each:
  (a) forward FY2026-Q4 claim + only an FY2026-Q3 primary record dated before asof;
  (b) (a) plus a matching FY2026-Q4 record dated after asof;
  (c) forward claim + matched record ≤ asof;
  (d) a matched-period record with no `source_class`;
  (e) a record with no `period`;
  (f) a fact with no `period`, primary records present;
  (g) both sides carry conflicting `event` labels; then the same with only one side carrying a label;
  (h) past claim, matched record on the claimed date;
  (i) past claim, matched record on another date;
  (j) past claim + only an other-period record on another date;
  (k) period case/whitespace variants (`fy2026-q4 ` vs `FY2026-Q4`).
  Each must follow the ruling exactly; anything else is a BLOCKER.
D2. **F2 closed.** No hard-coded unreconciled factor remains (grep). Probe with a temp copy of the config whose `unreconciled_fact_factor` value is changed (keep its justification): the evidence factor and eligible weight follow it. State the code path.
D3. **F3 closed.** The docstrings no longer cite the spec path; config sha256 unchanged.
D4. **F4 closed.** Probe `thesis_id` "" and None → generated; a supplied id → kept.
D5. **F5 closed.** Probe temp configs: a bare float leaf, a bare int leaf and a bare bool leaf → each refused; top-level `version` as a bare value → accepted; the shipped config → loads.
D6. **Regressions intact** at head (run the tests and read the assertions): MU entry catalyst CONTRADICTED in all four components with the perturbation VERIFIED; MU silent amendment REJECTED with the thesis unchanged; 688062.SS starter eligible weight strictly below its categorical cap with no specific number asserted; planless MU never NONE_RECORDED when a local record exists; XOM positive control passes in all three files.
D7. **Discrimination.** Swap in the three modules from `b36ed728` (`git show b36ed728:brain/<f>.py > brain/<f>.py`), run the three test files, name every failing test and its failure, then `git checkout -- brain/` and confirm a clean status. Expect exactly the new tests to fail; any new test that passes on `b36ed728` is non-discriminating (say which and judge it).
D8. **Tests at head**, twice (env unset; `PBR_DECISION_CASE_INPUT_DIR=~/lanes/tmp/pbr-res-w2r1-ls5/inputs`): `tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py tests/test_pbr_decision_case_fixtures.py`. Report counts.
D9. **No new defect in the changed lines.** Read the whole delta. Judge in particular:
  - `classless_record_count` also counts non-primary classes (name vs meaning);
  - an event-label conflict is counted as `other_identity`;
  - whether any test hand-types a fact value without tying it to a fixture field or a probe-only comment;
  - whether shadow-only isolation still holds (no new import of a sizing/decision/registry/pending-target/settlement path).
D10. **#1754 accuracy.** One file changed (`git diff --stat 3a6d165f..9b9cc7eb`). Check every statement in §8 (Q1–Q4, CR-R7, E1 items 1–6 and the listed test names, E2) against the rulings above and against the code at #1750 head (cite lines). The inline pointers at §2.2(i), §2.2(ii) and §7 must not contradict any other section. E1 item 6's description of the digests' period labels must be true of the fixtures (check the MU entry fixture digests' `period_labels` by field path; no prose).
D11. **Public repo / SR-1.**
  - Run your own sliding-window scan (30-char windows, step ≤ 5) of the six delta files and the #1754 spec against every whitespace-containing string in the inputs; report the hit count. A hit on a bare enum/identifier is not a leak; say which.
  - Grep for IP addresses and host paths (`/Volumes`, `/home/`, `/Users/`).
D12. **Scope.** `git diff --stat b36ed728..HEAD` touches exactly the six module/test files; config, fixtures, `config/contracts.yml`, `bot/`, `portfolio/`, `app/` are untouched.
