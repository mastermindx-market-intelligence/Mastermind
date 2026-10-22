# OPERATION pbr-res-ls2-fixtures — redacted decision-case fixtures with provenance
Class: extract · Complexity: C1 · Mechanical extraction; no judgement about investment merit.

## Inputs (read-only, already on this host)
- `~/lanes/tmp/pbr-res-ls2-fixtures/case_rows.jsonl` — 11 original production decision rows. Each line is `{source_book, source_host_path, source_in_service_path, source_file_sha256, line_index_0based, line_sha256, row}`; `row` is the verbatim parsed decision row. Rows: autonomous lines 38, 39, 40, 75, 76, 77, 78, 89; china lines 35, 36, 37.
- `~/lanes/tmp/pbr-res-ls2-fixtures/case_fills.jsonl` — 9 verbatim fill rows (MU, XOM, 688062.SS) with the same provenance keys.
- `~/lanes/tmp/pbr-res-ls2-fixtures/MANIFEST.json` — capture manifest; its own sha256 is `4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa`; capture dir `/Volumes/Mastermind/evidence/pbr/research-capture-20261022T073549Z`. Read its `records`, `related_links` and `not_found_or_not_retained` sections and copy the relevant statements into the fixtures.

## Outputs (create only these, inside this worktree)
1. `tests/fixtures/pbr/decision_cases/_build_decision_cases.py` — a deterministic stdlib-only script: `python _build_decision_cases.py <case_rows.jsonl> <case_fills.jsonl> <MANIFEST.json> <out_dir>` regenerates every fixture byte-for-byte (`json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`). It must not import repo modules or read anything else.
2. Five fixtures in `tests/fixtures/pbr/decision_cases/`, each schema `pbr.decision_case_fixture.v1`:
   | file | case_role | records (book:line) | fills | extra |
   |---|---|---|---|---|
   | `mu_2026-10-02_entry.json` | regression A14 | autonomous:75 | MU fills whose `fill_id` is in row 75 `settlement_fill_ids` | `external_facts` (below) |
   | `mu_2026-10-05_amendment.json` | regression A15 | autonomous:75, autonomous:76 | none | `derived.case_holding_changes` = every key of the MU holding whose value differs between line 75 and 76 as `{key: {"old":…, "new":…}}`, plus the same for row-level `falsifiers` filtered to MU |
   | `mu_2026-10-22_planless_summary.json` | regression A15 | autonomous:89, autonomous:78 | none | `derived`: `ticker_in_holdings` per record; the MU entries of `requested_exit_decisions`/`exit_decisions` verbatim; `prior_thesis_refs` = decision_id + MU `falsifier` + `exit_plan` of lines 75 and 76; every sentence (split on `. `) of `summary` and `decision_memo` values containing `MU` or `held_without_active_plan` |
   | `cn_688062_2026-08-12_sizing.json` | regression A16 | china:35, china:36, china:37 | all 688062.SS fills | `derived.cap_reference`: cite the file:line in THIS worktree of `brain/decision_submission.py` where the regional `conviction_caps` {"high": 0.18, "medium": 0.12, "low": 0.06} are defined (verify by reading; quote the line verbatim) |
   | `xom_2026-08-12_positive_control.json` | positive_control | autonomous:38, 39, 40 | all XOM fills | none |
   Fixture body:
   ```
   {"schema":"pbr.decision_case_fixture.v1","case_id":<file stem>,"case_role":…,"defect_ref":"A14|A15|A16|none",
    "ticker":"MU|688062.SS|XOM",
    "capture":{"capture_dir":…,"manifest_sha256":"4c55f3f8…(full)","captured_utc":<from MANIFEST>},
    "provenance":[{source_book,source_host_path,source_in_service_path,source_file_sha256,line_index_0based,line_sha256,decision_id}],
    "redaction":{"policy":"retain all row-level fields verbatim except: drop perception_input; filter holdings and effective_holdings to the case ticker","dropped_row_fields":[…per record…],"other_holdings":[{"line_index_0based":…,"ticker":…,"weight":…,"conviction":…}]},
    "records":[{"line_index_0based":…,"decision_id":…,"row":{…retained verbatim…},"case_holding":{…verbatim holding dict of the case ticker or null…},"case_effective_holding":{…or null…},"case_row_falsifiers":[…row falsifiers strings containing the ticker or its name…]}],
    "fills":[{"line_index_0based":…,"line_sha256":…,"linked_decision_ids":[decision_ids among provided rows whose settlement_fill_ids contain this fill_id],"row":{…verbatim…}}],
    "linkage_note": <copy the MANIFEST statement about linked/UNLINKED fills for this ticker>,
    "external_facts":[…],"derived":{…},
    "records_sha256": sha256 of json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",",":")).encode() }
   ```
   `external_facts` (MU entry only; cited by the program audit, NOT re-fetched by you — set `"verification_status":"cited_by_audit_not_refetched"`):
   - `{"fact":"Micron announced on 2026-08-26 that fiscal Q4 2026 results would be reported on 2026-09-30","event_date":"2026-09-30","published":"2026-08-26","url":"https://investors.micron.com/news/press-release/2026/Micron-Technology-to-Report-Fiscal-Fourth-Quarter-Results-on-September-30-2026/default.aspx"}`
   - `{"fact":"Micron reported fiscal Q4 and full-year 2026 results on 2026-09-30","event_date":"2026-09-30","published":"2026-09-30","url":"https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Fiscal-Fourth-Quarter-and-Full-Year-2026-Results/"}`
   - `{"fact":"SEC-hosted fiscal Q4 2026 results release (exhibit 99.1)","published":"2026-09-30","url":"https://www.sec.gov/Archives/edgar/data/723125/000072312526000018/a2026q4ex991-pressrelease.htm"}`
3. `tests/fixtures/pbr/DECISION_CASES.md` — one section per fixture: provenance table (host path, in-service path, line, line_sha256, decision_id), the verbatim decisive quotes (≤3 per case, each ≤40 words, copied exactly), what is observed vs what is NOT established (e.g. MU: the fill price itself is not shown wrong; 688062: a 12% weight is not universally wrong; XOM: one winner does not validate its reasoning), and what a future contract must do with the case (MU entry: a dated catalyst already reported before `asof` cannot support new risk; MU amendment: falsifier/exit change needs an explicit amendment record; planless summary: missing provider plan ≠ missing local thesis; 688062: stated "starter"/single-source uncertainty must connect to an explicit risk budget, caps must not be fitted to this known loss; XOM: must remain eligible under any new check).
4. `tests/test_pbr_decision_case_fixtures.py` — pytest, stdlib only, ≥8 tests: all five files load; schema/case_id/role present; every provenance `line_sha256`/`source_file_sha256` is 64-hex and `decision_id` matches `^decision\.v1\.[0-9a-f]{24}$`; `records_sha256` recomputes; MU entry holding falsifier text contains `2026-10-22` and an external fact has `event_date` `2026-09-30` < record `asof`; amendment `case_holding_changes` contains `falsifier` and `exit_plan`; planless fixture: MU absent from line-89 holdings and some summary/memo sentence contains `held_without_active_plan` or `no live thesis`; 688062 line-35 holding weight == 0.12 and rationale contains `starter`; XOM fixture has ≥1 fill; regenerating with `_build_decision_cases.py` into a tmp dir reproduces identical bytes IF the inputs exist at `~/lanes/tmp/pbr-res-ls2-fixtures/` (skip with reason otherwise).

## Verify, then return
Run: the Common-rules pytest command on `tests/test_pbr_decision_case_fixtures.py`. Then `git status --porcelain` and `sha256sum` every file you created.

## RETURN block (your last message)
```
RETURN pbr-res-ls2-fixtures
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every created file)
TESTS: <verbatim pytest summary line>
CASE_FACTS: mu_entry falsifier_date=<…> asof=<…> fills=<ids> ; amendment changed_keys=<…> ; planless mu_in_holdings=<bool> ; 688062 weight=<…> cap_line=<file:line> ; xom fills=<n>
DEVIATIONS: <numbered, or none>
```
