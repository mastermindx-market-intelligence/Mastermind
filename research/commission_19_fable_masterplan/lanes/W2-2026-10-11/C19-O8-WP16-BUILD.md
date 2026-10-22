C19-O8-WP16-BUILD — composer current-source clock tests (external build lane, TEST-ONLY)
Frozen by Fable seat 7ab343c8 (Commission 19 / Data Intelligence, W2→W3) on 2026-10-11. Repository: Macro
(mastermindx-market-intelligence/macro). Base: FRESH origin/main at launch (`git fetch origin main`; record the sha you build on).
Run id: c19-o8-wp16-build-20261011. Branch: claude/c19-wp16-composer-clock-20261011. Sentinel: the LAST stdout line must be
`C19-O8-WP16-BUILD: <PASS|FAIL|PARTIAL> <commit sha>`.

MISSION
Add ONE new pytest module, tests/test_integrated_answer_clock.py, that pins the composer's current-source clock contract in
app/integrated_answer.py exactly as it behaves today, with ONE strict xfail that names the known defect. No production code changes.

WHY
WP03 and WP08 (both ACCEPTED) found that the composer's financial leg carries a literal request clock as its source clock and that the
page staleness sweep has no end-to-end test. Later C19 build lanes (WP05 request-clock threading, the WP08 ref-binding extension) need a
pinned baseline so their behaviour change is observable in CI, not silent.

SCOPE / OWNED FILES
tests/test_integrated_answer_clock.py (NEW). This is the ONLY file you may create or edit.

OUT OF SCOPE (hard)
Editing app/integrated_answer.py, tests/test_integrated_answer_v0.py, engine/**, app/** or any other path; setting or exporting
MACRO_INTEGRATED_ANSWER_ENABLED anywhere (tests included); any PR, label, review, merge, Slack or Linear act; docs; data/ or site/ writes.

FROZEN SPEC — facts at origin/main 866bb4987d2a0b60af5312fef591052323cfdf3b (verify the line numbers at YOUR base and cite yours)
 F-A app/integrated_answer.py `_utc_now` :164-165 is the composer clock. Inject time by monkeypatching `app.integrated_answer._utc_now`
     (or with tests/tools/clock_shift.py). Never use wall-clock dates in any assertion.
 F-B `_make_ref(*, route, as_of, payload, generation_id=None, owner_hash=None)` :192-206 returns exactly
     {route, as_of, generation_id, owner_hash, content_hash}; content_hash = sha256 of the canonical payload.
 F-C `STALE_DAYS = 4` :28. Page as_of = max(ref.as_of over surfaced legs) else composed_at (:638-643);
     stale_before = cutoff − STALE_DAYS (:647); the stale sweep SKIPS the event_workspace leg (:649-650);
     leg clock < stale_before → `stale`; otherwise a leg older than the page stamp → `older_than_page_stamp` (:652-659).
 F-D Financial leg `_leg_financial_facts` :293-345: AAPL-only gate (:299, non-AAPL → absent / not_covered:golden_corpus_is_aapl_only);
     request literals `source_snapshot_at` 2026-08-01T00:00:00Z (:309) and `recorded_at` 2026-08-23T12:00:00Z (:310);
     `result = execute_financial_query(body=body, provider=_financial_provider())` (:327); leg as_of =
     `_normalize_clock(req["policy"]["recorded_at"]) or "2026-08-23T12:00:00Z"` (:334) — i.e. the request cutoff is echoed as the leg's
     source clock. The kernel result (FinancialQueryResult: body, sha256, envelope) carries NO producer clock. Per-fact provenance rows in the body DO carry
     source_snapshot_at / recorded_cutoff_at (+ optional recorded_at, accepted_at) (engine/fundamental_forensics/query.py:955-975).
 F-E Missing-owner-clock fallbacks :418-421, :517-520, :587-590; event_workspace leg clock :479-482.
 F-F The route is default-off: `_require_enabled` :159-161 → 404 unless MACRO_INTEGRATED_ANSWER_ENABLED == "1".
 F-G Idioms: read tests/test_integrated_answer_v0.py FIRST and copy how it stubs legs (monkeypatching the `_leg_*` functions and
     `execute_financial_query` / `_financial_provider` on the `app.integrated_answer` module) and how it drives `_compose_page`.

TESTS (one named function each; deterministic; no network, no data/ reads)
 T1 test_route_stays_off_when_flag_unset — with the env var absent the route answers 404; the test must never set the var.
 T2 test_page_as_of_is_max_of_surfaced_leg_clocks — two surfaced legs with different ref.as_of → page as_of equals the later one.
 T3 test_page_as_of_falls_back_to_composed_at — no surfaced leg → page as_of == composed_at from the injected clock.
 T4 test_stale_boundary_is_stale_days — a leg exactly STALE_DAYS before the cutoff is NOT stale; one second older IS `stale`.
 T5 test_older_than_page_stamp_inside_window — a leg older than the page stamp but inside STALE_DAYS → `older_than_page_stamp`.
 T6 test_event_workspace_leg_is_exempt_from_stale_sweep — an event_workspace leg older than stale_before is NOT marked stale (:649-650).
 T7 test_missing_owner_clock_fallbacks — each fallback site (:418-421, :517-520, :587-590) yields its documented fallback as_of.
 T8 test_financial_leg_clock_is_threaded_and_producer_derived — decorated
     @pytest.mark.xfail(strict=True, reason="DEFECT C19-WP16-D1: financial leg as_of echoes the literal request cutoff "
     "2026-08-23T12:00:00Z (app/integrated_answer.py :310/:334) and the request policy clocks are literals (:309-310); "
     "fix lands in C19 WP05 (ledger D13)")
     Inject `_utc_now` = 2026-10-11T12:00:00Z. Replace `app.integrated_answer.execute_financial_query` with a stub that CAPTURES
     its `body` kwarg and returns a fake FinancialQueryResult(body=<canonical JSON bytes of the envelope>, sha256=<hex>,
     envelope={"receipt": {"query_hash": "...", "nodes": [node, node]}, "delivery": {}}). That is the REAL shape:
     engine/fundamental_forensics/query_service.py ~:577 wraps MetricMatrix.to_dict() (query.py :3443; nodes serialized by
     _unsigned_dict :3425-3440) under "receipt", and each node is a cell dict carrying "provenance": CellProvenance.to_dict()
     (query.py :1339-1359 — source_snapshot_at, recorded_cutoff_at, accepted_at :1358, recorded_at :1359, ...). Give the two nodes
     provenance.recorded_at = 2026-08-23T12:00:00Z and 2026-09-15T00:00:00Z (accepted_at earlier than each; every other key
     minimal — the composer reads none of them today: only result.sha256 and envelope.receipt.query_hash, :327-342).
     Call `_leg_financial_facts("AAPL")` (match the real signature) and assert BOTH:
       (i) captured body["policy"]["recorded_at"] == "2026-10-11T12:00:00Z" (request clock threaded from the composer clock), and
       (ii) the leg ref.as_of == "2026-09-15T00:00:00Z" (max per-node provenance.recorded_at; D13 fallback order: recorded_at →
            accepted_at → threaded request clock when the receipt has no nodes).
     Today (i) fails (literal 2026-08-23T12:00:00Z) and (ii) fails (as_of echoes the literal) → reported XFAIL; strict, so the WP05
     fix flips it loudly. WP05 owns this file afterwards and may adjust the stub's node shape when it implements the parsing.
 T9 test_make_ref_shape_and_stable_content_hash — `_make_ref` returns exactly the five keys; equal payloads hash equal;
     a changed payload changes content_hash.

NOT DONE UNLESS
 - `python -m pytest tests/test_integrated_answer_clock.py -q` → all pass, T8 reported as xfailed, 0 failed, 0 errors.
 - `python -m pytest tests/test_integrated_answer_v0.py -q` still passes (that file untouched).
 - `git status --short` shows ONLY tests/test_integrated_answer_clock.py; `git diff --stat origin/main` names only that file.
 - Committed on claude/c19-wp16-composer-clock-20261011 (created off fresh origin/main) with message
   `test(composer): pin current-source clock contract (C19 WP16)` and a trailing `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` line.
 - `git push -u origin claude/c19-wp16-composer-clock-20261011` attempted; record its rc verbatim. If the push is refused, report
   the branch name, commit sha and the clone path so the seat can fetch it back; do NOT retry with other credentials.
 - The last stdout line is the sentinel.

RETURN PACKET (your final message; sections exactly): STATUS (PASS|FAIL|PARTIAL) / RESULT (test list with pass|xfail per test, commit sha,
push rc, base origin/main sha, the line numbers you verified) / EVIDENCE (pytest tails verbatim, git status + diff --stat output) /
GAPS (anything not done, with the reason) / DEVIATIONS (every departure from this packet).

HARD LAWS
Never set MACRO_INTEGRATED_ANSWER_ENABLED. No edits outside the owned file. Never `git add -A`; never rebase, force-push or stash; never
mutate a primary checkout — if the clone's tree is dirty or on another branch, `git worktree add <dir> -b claude/c19-wp16-composer-clock-20261011 origin/main`
and work there. Never read or print ~/.glm, ~/.opencode-go, ~/.minimax, ~/.bailian, ~/.codex/auth*, ext/*/.token, or any shim log.
Sparse tree: do not touch data/ or site/. No PR, labels, merge, Slack, Linear. No network calls other than git fetch/push to origin.
Turn-ending clause: do not end a turn on "now let me…"; emit the sentinel and the return packet, or return what you have with honest GAPS.
