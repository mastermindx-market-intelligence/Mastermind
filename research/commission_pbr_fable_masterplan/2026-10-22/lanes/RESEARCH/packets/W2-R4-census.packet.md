# OPERATION pbr-res-w2r4-census — census of every reader and writer that assumes one decision row per (book, asof)
Class: extract · Complexity: C0_MECHANICAL · Read-only census. No code changes.

## Base (overrides the Common-rules base line)
Two detached read-only worktrees:
- MASTER = your current working directory, `origin/master` @ `f14fac19`.
- PR673 = `~/lanes/wt/pbr-res-w2r4-census-673`, PR #673 head @ `2a830e60` (branch base is 600 commits behind master). In PR673
  read ONLY these files, which #673 adds or changes: `portfolio/decision_snapshot.py`, `portfolio/decision_snapshot_contracts.py`,
  `portfolio/decision_snapshot_sources.py`, `scripts/portfolio_decision_snapshot.py`, `app/web.py`, `app/static/index.html`,
  `config/contracts.yml`, and `tests/test_decision_snapshot*.py`, `tests/test_contracts.py`.

## Why
Today a book's decision log (`data/portfolios/<book>/decisions.jsonl`, rows built by `bot/decision_rows.py`) holds at most one
row per asof: `bot/decision_rows.py::replace_for_asof` (≈:287–300) overwrites an earlier same-asof row, and
`bot/autonomous.py::_append_decision_log` (≈:863–913) writes through it. The planned change: a later run on the same asof APPENDS a
new row carrying `supersedes=<prior decision_id>` and never overwrites. Every place that assumes "one row per asof" (dict keyed by
asof, `next(... if r["asof"] == asof)`, first/last match, `rows[-1]` as "today's decision", uniqueness asserts, joins of decision
rows to fills/settlements/marks/snapshots by asof) must be found before that change is built.

## Task
Search MASTER (all of `bot/`, `brain/`, `portfolio/`, `app/` incl. `app/static/**`, `loop/`, `data_layer/`, `bridge/`,
`scripts/`, `control_plane/`, `tests/`; exclude `vendor/`, `node_modules/`, `.git/`) and the PR673 files above. Suggested seeds
(not exhaustive; follow call chains one level): `decisions.jsonl`, `decision_log`, `decision_rows`, `replace_for_asof`,
`reconcile_settlement`, `refresh_lesson_links`, `validate_queued_decision_snapshot`, `accepted_identity_fields`, `decision_id`,
`["asof"]`, `.get("asof")`, `asof ==`, `== asof`, `by_asof`, `for_asof`, `latest_decision`, `load_decisions`, `read_decisions`,
`_decisions(`, `rows[-1]`, `decisions[-1]`.

For every hit that READS or WRITES decision-log rows and selects, matches, deduplicates, indexes or joins them by asof (or assumes
the newest row is the asof's decision), record one row. Skip hits that only pass an asof through without selecting decision rows.

## Output (create ONLY this file)
`~/lanes/tmp/pbr-res-w2r4-census/out/CENSUS.md` with:
1. A table, one row per site:
   `| # | tree (MASTER/PR673) | file:line | function | R/W | selection today (exact expression, ≤80 chars, code only) | assumption (UNIQUE_PER_ASOF / FIRST_WINS / LAST_WINS / OVERWRITE / JOIN_BY_ASOF / COUNT_PER_ASOF / OTHER:<…>) | selection needed once supersedes rows exist (LATEST_NON_SUPERSEDED / ALL_ROWS / BY_DECISION_ID / CHAIN / UNCHANGED) | family |`
   Family by path: `bot/decision_rows.py`, `brain/decision_context.py`, `brain/decision_submission.py`,
   `portfolio/forward_evaluation.py`, `portfolio/decision_snapshot*` → RESEARCH; `portfolio/paper_account*`, `portfolio/marks*`,
   `portfolio/price_evidence*`, `bot/settle*`, `*benchmark*` → ECON; scheduler/waterfall/lifecycle code, `bot/autonomous.py`,
   `control_plane/` → RUNTIME; `app/web.py`, `app/static/**`, `app/account.py`, `app/pfolio.py`, `app/decision_availability*` →
   PRODUCT; anything else → OTHER (name the directory). Tests: family of the module they test, suffixed `-test`.
2. A short list "WRITERS": every code path that writes a decision-log row (file:line, function, and whether it can overwrite).
3. A short list "UNSURE": hits you could not classify, with the reason.
4. Counts per family and per tree.
Code expressions only: copy no data-file content. Do not open anything under `data/`.

## Verify, then return
- Re-open each cited file:line and confirm it shows the quoted expression (fix or drop mismatches).
- `sha256sum ~/lanes/tmp/pbr-res-w2r4-census/out/CENSUS.md`; `git status --porcelain` in both worktrees must be empty.

## RETURN block (your last message)
```
RETURN pbr-res-w2r4-census
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>
SITES: <n total> (MASTER <n>, PR673 <n>); by family: RESEARCH <n>, ECON <n>, RUNTIME <n>, PRODUCT <n>, OTHER <n>
WRITERS: <n>   UNSURE: <n>
WORKTREES_CLEAN: yes|no
```
## Common rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research` (Opus), who keeps every git, PR, review and merge step. You are a bounded leaf. No nested workers.
- Repository: your current working directory is a detached worktree of Mastermind at `origin/master` 230e9a301. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY the output paths named in this packet. Never commit, push, open or comment on PRs, edit other files, or touch `~/lanes/repos/Mastermind` directly.
- Forbidden: network access except none (no web fetches, no APIs); reading credentials/.env/keys; running the bot, scheduler, server or anything against live data; any account reset, seed rewrite, balancing fill, or "repair" trade; changing `brain/decision_submission.py` allocation behaviour; resetting or redefining the V2 marker (sha256 75d5182d…) or the August-11 cohort.
- Shadow/new modules terminate in isolated storage: no registry membership, no pending-target route, no settlement call.
- Tests (only when this packet names them): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <named files>`.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value. If blocked, stop and report the exact blocker.
- Your final assistant message is the ONLY thing returned. **Emit the full RETURN block (format below) as your last message**, including the file list with `sha256sum` of every file you wrote.
