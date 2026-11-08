# Shipping Agent OS records to macro (DEC/DSC/handoff PRs)

The macro repo is multi-GB; cloning it to add one record wastes an hour and usually times out. Ship through the GitHub API with `gh` and let repo CI validate — the fence that runs `scripts/agentos.py validate` (AGENT_OS_RECORD_CONTRACT) is the gate, so a local checkout is optional.

## Procedure
1. Author the record locally (e.g. `~/hermes-migration/`). Mirror the frontmatter key set of an existing record under `agentos/decisions/`; the nightly index derives `created`/`updated` and git fields itself — do not hand-write them.
2. Pre-flight the values you CAN check: `reversibility` must be exactly `costly`, `easy`, or `one_way`; enum violations fail the fence with `[bad-enum]`. If unsure of another field's contract, read `scripts/agentos.py` via the contents API before pushing.
3. Ship API-only, all through `gh`:
   - branch from main HEAD: `gh api -X POST repos/mastermindx-market-intelligence/macro/git/refs -f ref=refs/heads/<branch> -f sha=<main-sha>`
   - put the file: `base64 -i <file> | tr -d '\n'` → `gh api -X PUT repos/.../contents/agentos/decisions/<KEY>.md -f message=... -f branch=<branch> -f content=<b64>`
   - `gh pr create`, then `gh pr edit <n> --add-label merge-on-green`
4. Watch `gh pr checks`; confirm MERGE by readback (`gh pr view <n> --json state,mergedAt`). An armed PR sitting OPEN with a *new* wave of pending checks is the sweeper refreshing the branch — not a failure.

## merge-on-green sweeper behavior (read before diagnosing)
- The `merge-on-green` label ARMS the PR; the scheduled sweep (`.github/workflows/merge-on-green.yml`, woken by ci/fences/integration-baseline completions) performs the actual merge once every check concludes clean. Never merge by hand — with no branch-protection required checks, `gh pr merge --auto` merges IMMEDIATELY and bypasses the queue law.
- `ci-authority/codex/merge-queue-pilot: fail` is tolerated by design (`CI_AUTHORITY_INACTIVE_CONTEXT` in `scripts/merge_on_green.py`); it fails identically on already-merged PRs. Never treat it as your PR's regression.
- When main moves — especially when it changes check definitions — the sweep merges main into armed heads and lets the fresh checks decide on a later sweep (log line: "checks were clean but the base had moved"). Expect multiple refresh cycles on an active main; a large armed backlog further serializes merges. Hours are normal; intervene never.
- The sweep's log states its verdict per PR: `gh run list --workflow merge-on-green.yml --limit 3`, pull the newest completed run's log, grep for your PR number before concluding anything is stuck.

## Diagnosing any failed macro check
1. `gh api repos/mastermindx-market-intelligence/macro/check-runs/<id> --jq '{conclusion, summary: .output.summary, text: .output.text}'` — fence verdicts put the exact rule violation here (e.g. `[bad-enum] ... allowed: costly, easy, one_way`).
2. `.../check-runs/<id>/annotations` — often empty for fences; don't stop there.
3. `gh api repos/.../actions/jobs/<job-id>/logs` — `continue-on-error` steps still print their diagnostics into the job log; grep for the fence/check name. A fence step whose summary says `failure` while sibling units pass means one unit failed — find that unit's line in the log, not the workflow's exit code.
