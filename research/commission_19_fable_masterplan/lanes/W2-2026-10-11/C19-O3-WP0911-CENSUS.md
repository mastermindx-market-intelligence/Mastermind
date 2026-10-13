C19-O3-WP0911-CENSUS — expectation comparability + MRI producer/reader census (READ-ONLY)
Lane id: c19-o3-wp0911-census-20261011 · Tier: glm-5.3-flash · Budget: 3600 s wall clock (return PARTIAL at 3000 s)
Host: ubuntu2, repo ~/lanes/repos/macro. The tree is DIRTY and shared: never checkout/reset/stash/add/commit; run ONE
`git fetch origin main`, record `git rev-parse origin/main`, and read every file with `git show origin/main:<path>`.

MISSION
Map, at current Macro origin/main, (A) how a native earnings-expectation comparable pair is built and which columns are
qualified today (issuer, immutable fiscal target, unit, currency, GAAP/adjusted, basic/diluted, provider, observation
clock) in engine/k3e_expectation_surface.py, collectors/equity_revisions.py and engine/expectation_state.py, with the
full strict-xfail inventory; and (B) the macro release-forecast PRODUCER envelope written by scripts/build_release_forecast.py
versus what every READER (engine/event_window.py, engine/release_actuals.py, any other consumer of the output file)
expects — the exact path/envelope/unit/sigma/vintage mismatches. For every masterplan negative case below, say whether
current code REJECTS it (path:line), a test PINS it (path::name), or NEITHER.

WHY
WP09 (MAS-271) must reconcile merged EXP-1 (Macro #8337, 95280c15, DO_NOT_REDO; normalized baseline deliberately null)
with the current strict-xfail gaps without inventing a baseline. WP11 (MAS-273) must confirm no accepted compatibility
adapter already resolves the MRI producer-to-reader mismatch and must bind the intended release target, array element,
unit and native sigma meaning — changing only a filename is insufficient. The seat will not freeze a build packet, and
will not start the D5 writer-lease read, until this census says what the seam looks like on main today.

SCOPE (read-only, origin/main only)
- engine/k3e_expectation_surface.py · collectors/equity_revisions.py · engine/expectation_state.py ·
  scripts/build_release_forecast.py · engine/event_window.py · engine/release_actuals.py · every other file that reads
  the release-forecast output (grep the output filename) · tests/test_k3e_*.py · tests/test_equity_revisions_*.py ·
  tests/test_release_forecast*.py · tests/test_event_window.py · tests/test_release_actuals.py ·
  tests/fixtures/release_forecast_full.json · tests/fixtures/am_edition_fixture/data/release_forecast/latest.json
  (fixtures: read only the top-level key structure, never dump them).
- Grep patterns (`git grep -n <pattern> origin/main -- <paths>`): xfail · strict=True · fiscal · FY1 · +1q · period_end ·
  currency · unit · gaap · adjusted · diluted · basic · contributor · analyst · guidance · consensus · anchor ·
  release_forecast · latest.json · upcoming · UPCOMING · sigma · stdev · surprise · nowcast · consensus_median · vintage ·
  as_of · revision.

OUT OF SCOPE
No edits, branches, commits, pushes, PRs, posts, labels. No pytest. No fixtures over 1 MB dumped. No paid consensus
sources, no FOMC expansion, no regime engine. No Mastermind or Terminal repo.

QUESTIONS — each answer is path:line @ the ONE origin/main sha you fetched
Q1 Comparable-pair construction (WP09): where is a captured expectation value joined to a baseline/anchor? For each of
   the columns issuer id · fiscal target (and its immutability across +1q/FY1 roll) · unit · currency · GAAP/adjusted ·
   basic/diluted · provider/response · observation clock: ENFORCED (path:line of the check) | CARRIED (field present, no
   check) | ABSENT, with quoted lines. State which function returns null for an unsupported provider family.
Q2 Strict-xfail inventory: every xfail in the k3e / equity_revisions tests with path::name, strict flag, and reason text;
   map each to the code gap it names (path:line) or mark UNMAPPED.
Q3 Negative cases, WP09: (a) +1q/FY1 roll compared as the same target; (b) a null anchor treated as equal; (c) a
   contributor entry interpreted as a same-analyst revision; (d) guidance mixed with consensus. For each: REJECTED
   (path:line) | PINNED (tests/…::name) | NEITHER, with the grep used.
Q4 Producer vs readers (WP11): quote where scripts/build_release_forecast.py writes its output (output path, top-level
   keys, case, whether `upcoming` is an array or object, per-element keys, unit and sigma fields, vintage/date field
   granularity). Then for each reader (engine/event_window.py, engine/release_actuals.py, others found by grep) quote the
   path:line where it opens/reads the file and the keys/shape it expects. Produce a mismatch table: key-case · path ·
   array-vs-object · element selection (first matching CPI object? keyed by release id?) · unit · sigma meaning ·
   vintage granularity (date-only vs timestamp).
Q5 Is there an existing adapter/shim/normalizer between producer and readers on main (path:line) or none (grep bounds)?
   Negative cases, WP11: (a) uppercase top-level key assumed on the upcoming array; (b) first matching CPI object
   selected blindly; (c) mixed nowcast/market median called street consensus; (d) date-only vintage admitted intraday;
   (e) revision delta called revision surprise. For each: REJECTED | PINNED | NEITHER, with the grep used.
Q6 Absence claims carry their bounds: print every grep command verbatim with its hit count and the sha.

NOT DONE UNLESS
- Q1–Q6 answered; every claim cites path:line @ one sha; every re-check command printed verbatim.
- Q3 has a verdict for all four cases; Q5 has a verdict for all five cases; Q4's mismatch table has a row per reader.
- Nothing was written in the repo: print `git status --porcelain | wc -l` at start and at end; they must match.

EVIDENCE REQUIRED
- `git rev-parse origin/main` after the single fetch.
- For each Q1 column, each Q4 writer/reader site, 3–8 quoted source lines via `git show origin/main:<path> | sed -n 'A,Bp'`.

RETURN — your final message is exactly this packet and nothing after it
STATUS: PASS | FAIL | PARTIAL
RESULT: Q1 column table · Q2 xfail table · Q3 verdicts · Q4 mismatch table · Q5 adapter answer + verdicts · one paragraph
        each answering "is the MRI seam still broken on main, and where exactly?" and "which WP09 columns are unqualified?"
EVIDENCE: as required above
GAPS: what you could not read and why
DEVIATIONS: anything done outside this packet
NEXT SEAT ACT: one line
Last line, exactly: C19-O3-WP0911-CENSUS: <PASS|FAIL|PARTIAL> <origin/main sha>
Do not end a turn on "now let me…": emit this packet, or return what you have with honest GAPS. A status note is not a return.

HARD LAWS
- Read-only. Never git checkout/reset/stash/add/commit/push/rebase; never modify the dirty tree; never run pytest.
- Never read or print ~/.opencode-go, ~/.glm, ~/.minimax, ~/.bailian, ~/.codex/auth*, any ext/*/.token, any shim.log or
  usage.jsonl. Never print credentials. Never post to Slack or GitHub. Never invent ids or shas.
