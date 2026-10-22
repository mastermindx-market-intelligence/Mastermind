## Common rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research` (Opus), who keeps every git, PR, review and merge step. You are a bounded leaf. No nested workers.
- Repository: your current working directory is a detached worktree of Mastermind at `origin/master` 230e9a301. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY the output paths named in this packet. Never commit, push, open or comment on PRs, edit other files, or touch `~/lanes/repos/Mastermind` directly.
- Forbidden: network access except none (no web fetches, no APIs); reading credentials/.env/keys; running the bot, scheduler, server or anything against live data; any account reset, seed rewrite, balancing fill, or "repair" trade; changing `brain/decision_submission.py` allocation behaviour; resetting or redefining the V2 marker (sha256 75d5182d…) or the August-11 cohort.
- Shadow/new modules terminate in isolated storage: no registry membership, no pending-target route, no settlement call.
- Tests (only when this packet names them): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <named files>`.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value. If blocked, stop and report the exact blocker.
- Your final assistant message is the ONLY thing returned. **Emit the full RETURN block (format below) as your last message**, including the file list with `sha256sum` of every file you wrote.
