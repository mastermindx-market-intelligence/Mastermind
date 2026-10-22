# OPERATION pbr-res-ls1-lineage — V3-S0 lineage reconciliation (#673 vs #1357 vs master)
Class: decompose · Complexity: C2 · Output is a document; you change no source.

## Why
Two draft PRs both implement the V3-S0 immutable decision snapshot and both write `portfolio/decision_snapshot*.py`:
- **#673** — branch `origin/sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001`, head `0b960590c77101b3f3b5545896423f9ad07b7d56`, merge-base with master `8e25bb32601ef5f40a689da6d6f24149e79e31fa`. Also has `portfolio/decision_snapshot_sources.py` and `app/web.py` UI.
- **#1357** — branch `origin/sol/bot-intelligence-renewal-20261011`, head `1e127060b8a034b35853fd23c4be9ed55592728f`, merge-base `cbc7503536b6853ec7c35c2192abdfaccb87b561`. Also has `app/decision_snapshot.py`, `brain/decision_research*.py`, review regressions; source capture held/refused.
- master `230e9a301` (your HEAD). Both refs are already fetched in this repo.
The approved contract is in `docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md` (search for `portfolio_decision_snapshot`, `S0`, `COMPLETE`, `PARTIAL`, `BLOCKED`, `INVALID`, `CORRECTED_GENERATION_AVAILABLE`, `source receipt`). #1357 also carries renewal spec/plan docs under `docs/` (find them with `git diff --stat <merge-base> <head>`).

Captured fact you must use (from `~/lanes/tmp/pbr-res-ls1-lineage/MANIFEST.json`, field `not_found_or_not_retained`): on production the `decision_context` artifacts consumed by the 2026-08-12/13 and 2026-10-02/05 decisions are **not retained** (the host keeps 2026-07-30..08-06 plus two 2026-10-22 sequence files), and decision rows carry **no context digest**. So today no accepted decision can be bound to the context it consumed.

## Do
1. `git diff --stat` and read each PR's snapshot, source, inspector/UI and test files (`git show <ref>:<path>`). Compute conflicts against master with `git merge-tree --write-tree origin/master <head>` (report conflicted paths) for both heads.
2. Optionally (bounded to ≤2 test files per PR) run each PR's own snapshot tests: `git checkout --detach <head>` in THIS worktree, run them with the command in Common rules, then `git checkout --detach 230e9a301` back. Report pass/fail counts verbatim.
3. Read master `brain/decision_context.py` and find who consumes it (`grep -rn "decision_context" --include='*.py' brain bot app portfolio`) and who writes `decisions.jsonl` rows (find the writer and the fields `decision_id`, `submission_sha256`, `target_sha256`).
4. Write `~/lanes/tmp/pbr-res-ls1-lineage/out/S0_LINEAGE.md` with exactly these sections:
   - **A. Frozen S0 contract** — the minimal contract both PRs and the V3 spec agree on, as a table: field → type → meaning → which PR implements it (file:line) → spec citation. Must cover: snapshot identity (content hash + canonicalization), cutoff/known-at, bound account state, bound pending effects (`pending_target.json`, pending orders), qualified market inputs with source receipts, missing sources stay missing, status enum, immutable correction generations, storage location, and how a decision row binds the snapshot digest. Mark every disagreement between PRs/spec explicitly.
   - **B. Per-PR assessment** — what exists, tests, conflicts with master, files outside the RESEARCH family (RESEARCH owns `brain/decision_context.py`, `brain/decision_submission.py`, `portfolio/forward_evaluation.py`, new `brain/thesis*|claims*|facts*|shadow*`; ECON owns `portfolio/paper_account.py`, `portfolio/marks.py`, `bot/settle.py`; PRODUCT owns `app/web.py`, `app/static/**`; note `portfolio/decision_snapshot*.py` and `app/decision_snapshot.py` ownership as unassigned if not listed).
   - **C. Recommendation** — exactly one of `continue-#673`, `continue-#1357`, `merge-path` (fresh branch from master taking named files from each), with the reasons and the risks of the other two.
   - **D. L-S4 task list** — numbered, each with files to add/change, named test files and test names, and acceptance: one real snapshot→inspector journey on CAPTURED data (fixtures under `tests/fixtures/pbr/`, never live data) plus negative cases: missing context, future-dated (known-at after cutoff), forged hash, changed-context input after hashing. Each negative case must end non-COMPLETE. Include the retention gap (decision rows must bind the consumed snapshot digest) as a task, marking which part is RESEARCH-owned and which needs a contract request to another owner.
   - **E. Open questions for the seat** — only genuinely consequential ones.

## RETURN block (your last message)
```
RETURN pbr-res-ls1-lineage
STATUS: COMPLETE | BLOCKED <exact blocker>
RECOMMENDATION: continue-#673 | continue-#1357 | merge-path
CONFLICTS: #673 <paths or none> ; #1357 <paths or none>
TESTS_RUN: <command + verbatim summary line per PR, or NOT_RUN reason>
FILES: <path> <sha256>
L-S4_TASKS: <count>
UNCERTAINTIES: <numbered>
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
