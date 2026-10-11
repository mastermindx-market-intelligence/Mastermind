C19-O1-WP05-BUILD — composer financial-leg clock fix (external build lane) — FROZEN 2026-10-11T13:0xZ by Fable seat 7ab343c8 (D-a CONFIRMED, D-b CONFIRMED as bounded); launch gated on the header below
LAUNCH ONLY after the seat confirms tests/test_integrated_answer_clock.py is on origin/main (WP16 MERGED) and the writer-lease read (`gh pr list --repo mastermindx-market-intelligence/macro --state open --search "integrated_answer OR fundamental_forensics OR expectation_state in:title,body" --json number,title,headRefName,isDraft`) shows no open PR touching the owned files.
Drafted by orchestrator O1b for Fable seat 7ab343c8 (Commission 19 / Data Intelligence, W2) on 2026-10-11. Repository: Macro
(mastermindx-market-intelligence/macro). Base: FRESH origin/main at launch (`git fetch origin main`; record the sha you build on).
Run id: c19-o1-wp05-build-20261011. Branch: claude/c19-wp05-composer-clock-20261011. Sentinel: the LAST stdout line must be
`C19-O1-WP05-BUILD: <PASS|FAIL|PARTIAL> <commit sha>`.

MISSION
Fix the composer's financial leg so its request carries the composer's real clock instead of two literals, and so the leg's
`ref.as_of` is derived from the producer's receipt nodes instead of echoing the request. Flip the WP16 strict xfail T8 to a pass.

WHY
WP03/WP08 (ACCEPTED) found that `_leg_financial_facts` in app/integrated_answer.py sends literal cutoffs
(`source_snapshot_at` "2026-08-01T00:00:00Z", `recorded_at` "2026-08-23T12:00:00Z") and then reports that request literal back
as the leg's source clock, so the page stamp is a constant, not evidence. WP16 pinned this as strict xfail T8
(`test_financial_leg_clock_is_threaded_and_producer_derived`, defect C19-WP16-D1). This lane is that fix (seat ruling D13).

SCOPE
app/integrated_answer.py: `_leg_financial_facts` and the one call site in `_compose_page`. The two test files listed under OWNED
FILES, only for the edits enumerated in FROZEN SPEC (v). Anchors below are at origin/main 6ba70f04; re-verify each at your base
with `grep -n` and report any drift.
 - `_utc_now` :164-165 returns `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
 - `_normalize_clock` :168-184 returns the same format (or None; never raises).
 - `def _leg_financial_facts(ticker: str)` :297; literals :309 (`source_snapshot_at`) and :310 (`recorded_at`);
   `execute_financial_query(...)` :327; echo `as_of = _normalize_clock(req["policy"]["recorded_at"]) or "2026-08-23T12:00:00Z"` :334.
 - Sibling idiom to copy: `_leg_earnings_expectation(ticker, composed_at)` :363 (also :470, :540 take `composed_at`).
 - `_compose_page` :620; `composed_at = _utc_now()` :621; `_leg_financial_facts(ticker),` :623.
 - Real receipt shape (read, do not edit): engine/fundamental_forensics/query_service.py:577 `"receipt": matrix.to_dict()`;
   query.py :3425-3440 `_unsigned_dict` carries `"nodes"` (:3436); each node dict carries `"provenance"` (:1867/:1901);
   CellProvenance.to_dict :1339-1359 carries `accepted_at` (:1358) and `recorded_at` (:1359).

OUT OF SCOPE
engine/fundamental_forensics/** and lib/dataos/** (read-only; a second identity binder is forbidden). Any change to STALE_DAYS (:28)
or the stale sweep in `_compose_page`. Any other leg. Never set MACRO_INTEGRATED_ANSWER_ENABLED in your environment (tests that
monkeypatch it themselves are fine). No PR, label, merge, review, Slack, Linear. No data/ or site/ reads. No full-suite run.

FROZEN SPEC
(i) Request clock. `_leg_financial_facts` threads ONE clock value per compose into `req["policy"]["source_snapshot_at"]` AND
    `req["policy"]["recorded_at"]`, formatted exactly as `_normalize_clock` output. Seat ruling D-a (CONFIRMED): signature becomes
    `def _leg_financial_facts(ticker: str, composed_at: str | None = None)`, with
    `request_clock = _normalize_clock(composed_at) or _utc_now()`, and `_compose_page` calls `_leg_financial_facts(ticker, composed_at)`
    (same `composed_at` it already passes to the sibling legs). Both policy keys get `request_clock`; `_utc_now()` is called at most once.
(ii) Leg `ref.as_of` = max over `result.envelope["receipt"]["nodes"][*]["provenance"]["recorded_at"]`, each value passed through
    `_normalize_clock` before comparison (raw values may carry milliseconds, e.g. "2025-10-31T10:01:26.000Z"). If no node yields a
    recorded_at, fall back to the max normalized per-node `provenance["accepted_at"]`; if still none (or no nodes), fall back to
    `request_clock`. Parsing is defensive: missing/None/non-dict at any level is skipped; it never raises. TRIPWIRE: provenance also
    carries `recorded_cutoff_at` and `source_snapshot_at`, which echo the REQUEST — never read those for as_of. This replaces :334;
    no literal fallback remains.
(iii) Remove the `@pytest.mark.xfail(...)` decorator from T8 in tests/test_integrated_answer_clock.py. T8 must PASS (not xpass).
    T8 calls `_leg_financial_facts("AAPL")` with ONE argument and injects `_utc_now`; under D-a that path is the default-None branch.
    WP16's packet permits WP05 to adjust T8's stub node shape; do so only if the stub does not match the real shape above, and say so.
(iv) tests/test_integrated_answer_v0.py stays green. You MAY rename the misnamed `test_later_correction_under_earlier_cutoff` (:189;
    it actually asserts k3e as_of == composed_at) only if its body is otherwise untouched; say so in the commit body.
(v) The complete set of authorized test edits — anything beyond this list is a DEVIATION and requires PARTIAL:
    a. T8's xfail decorator removed (iii); T8 stub node shape only if needed (iii).
    b. Stub-signature-only edits (D-a): every `monkeypatch.setattr(integrated_answer, "_leg_financial_facts", lambda _t: ...)` in either
       owned test file becomes `lambda _t, *_a, **_k: ...` with the body byte-identical. At 6ba70f04 the v0 sites are :122, :206, :237,
       :282, :310; find the clock-file sites with `grep -n "_leg_financial_facts" tests/test_integrated_answer_clock.py`. List every
       edited line number in RESULT.
    c. Seat ruling D-b (CONFIRMED, bounded): golden literal: `test_real_golden_h01_aapl` (v0 :384) asserts at :402 `leg["ref"]["as_of"] == "2026-08-23T12:00:00Z"` — the
       echoed request literal this fix removes. Run the test after the fix and OBSERVE the derived value. You may replace the :402
       expected literal ONLY with the observed value, and ONLY if it equals one of the golden manifests' `fixture_recorded_at`:
       tests/fixtures/fundamental_forensics/aapl_10q_2026q3/package_manifest.json:14 ("2026-08-23T07:02:13Z") or
       aapl_10k_2025/package_manifest.json:14 ("2026-08-23T00:32:31Z"). If the observed value is today's date/clock, or anything
       else, the derivation is wrong (or fell back) — do not edit :402; return PARTIAL with the observed value and the node dump
       (count of nodes, distinct provenance.recorded_at values). Disclose the :402 change in the commit body.
    d. Optional rename (iv).
(vi) Expected-unaffected checks (observe, do not edit): `test_stale_vs_page_stamp` (v0 :405, asserts :425-426 status "stale" /
    "older_than_page_stamp") — page stamp comes from the theme leg at today's date, so an Aug-2026 derived as_of stays stale;
    `test_unavailable_financial_component` (v0 :318) — NVDA is refused before any query. If either fails, PARTIAL with the tail.
(vii) Golden admission tripwire: the request clock moves from 2026-08-23T12:00:00Z to now, which is after the golden provider's
    `FIF3A4_LINEAGE_AVAILABLE_AT` (2026-09-20; engine/fundamental_forensics/ixbrl_raw_ledger.py:54). If the golden leg now returns
    refused/absent (v0 :399 `status == "ok"` fails), do NOT clamp or hard-code a clock to restore it — return PARTIAL with the
    admission/unavailable code verbatim.

OWNED FILES (exactly these three; `git add` only these paths, by name)
app/integrated_answer.py · tests/test_integrated_answer_v0.py · tests/test_integrated_answer_clock.py

TESTS (flag unset; run from the repo root of your worktree; never the full suite)
env -u MACRO_INTEGRATED_ANSWER_ENABLED python3 -m pytest tests/test_integrated_answer_clock.py tests/test_integrated_answer_v0.py -q -p no:cacheprovider
Run it once BEFORE editing (record the baseline tail: T8 should report xfailed) and once AFTER.
Literal gate: git grep -n -e '2026-08-01T00:00:00Z' -e '2026-08-23T12:00:00Z' -- app/integrated_answer.py   (must print nothing; rc 1)

NOT DONE UNLESS
 - `git diff --stat origin/main` names only the three owned paths (app file plus at most the two test files).
 - T8 PASSES: the after-run shows 0 xfailed, 0 xpassed, 0 failed, 0 errors across both files; T8 has no xfail decorator.
 - Both test files green (after-run tail pasted verbatim), with every test edit inside FROZEN SPEC (v) and listed by line number.
 - The literal gate above prints nothing (paste the command and its rc).
 - Committed on claude/c19-wp05-composer-clock-20261011 created off fresh origin/main, subject
   `fix(composer): thread request clocks and derive leg as_of from receipt nodes (C19 WP05)`, body naming every test edit (v)
   and the observed golden as_of, last line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
 - `git push -u origin claude/c19-wp05-composer-clock-20261011` attempted; rc recorded verbatim. If refused, report branch, commit
   sha and clone/worktree path so the seat can fetch it back; do NOT retry with other credentials.
 - The last stdout line is the sentinel.

RETURN (your final message; sections exactly)
STATUS (PASS|FAIL|PARTIAL) / RESULT (commit sha, base origin/main sha, push rc, anchors re-verified with any drift, the final
`_leg_financial_facts` signature, observed golden as_of, every edited test line) / EVIDENCE (before and after pytest tails verbatim,
literal-gate command + rc, `git status --short` + `git diff --stat origin/main`) / GAPS / DEVIATIONS (every departure from this
packet) / NEXT SEAT ACT (one line).

HARD LAWS
Same as C19-O1-R3-CENSUS, adapted to a build lane: never read or print ~/.opencode-go, ~/.glm, ~/.minimax, ~/.bailian,
~/.codex/auth*, any ext/*/.token, any shim.log or usage.jsonl; never print credentials; never post to Slack or GitHub; never invent
ids, shas or line numbers. Never `git add -A`; never force-push, rebase, or bare `git stash`; never `pkill -f`; never cancel any
GitHub Actions run. Never mutate a primary checkout — if the clone's tree is dirty or on another branch,
`git worktree add <dir> -b claude/c19-wp05-composer-clock-20261011 origin/main` and work there. Never read data/ or site/. Never run
the full suite. No network calls other than git fetch/push to origin.
Turn-ending clause: do not end a turn on "now let me…"; emit the sentinel and the return packet, or return what you have with honest
GAPS. A partial packet with honest GAPS is useful; a status note is not.
