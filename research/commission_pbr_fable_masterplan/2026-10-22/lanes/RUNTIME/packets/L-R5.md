# Lane L-R5 — INSTALL_PROOF_PLAN (class design, C2) — specification only

You are a bounded Fabric design worker for the Mastermind repository (paper-only portfolio bot; production runs on one VPS).
Your working tree is the current directory, a detached checkout of `origin/master`. You write exactly ONE new file:
`research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/INSTALL_PROOF_PLAN.md`.
No source edits, no commits, no network, no ssh. This is a plan; nothing in it is executed by you.

## Inputs
- `~/lanes/tmp/pbr-rt-lr5/INSTALLED_IDENTITY.md` — read-only observation of the VPS taken today (blob identity, restart
  causes, deploy mechanism, journal retention). Treat it as the current-state baseline.
- In the tree: `scripts/deploy_code_to_vps.sh`, `scripts/deploy_from_git.sh`, `app/scheduler.py` (jobstore selection via
  `MASTERMIND_JOBSTORE`, schedules, misfire_grace_time/coalesce), `app/web.py` `/health` (fields `commit`,
  `reasoning_policy_ok`, `scheduled_runtime_ok`), `control_plane/run_ledger.py` (`git_sha` recorded on run events),
  `requirements*.txt` / `pyproject.toml` for the `claude-agent-sdk` pin.
- MASTERPLAN §12.1 (verbatim): "For any later authorized paper-policy cutover: 1. Resolve active receipts, pending targets,
  scheduled work, and current policy identity through their original owners. 2. Capture immutable pre-change state,
  source/config identities, and an executable rollback plan. 3. Install and verify the exact accepted composition, including
  dependencies and loaded service identity where relevant. 4. Observe the first natural cycle and final account/receipt/product
  state; do not treat an API acknowledgment as completed execution. 5. Preserve old and new policy boundaries in evaluation,
  and continue monitoring operational and investment metrics separately. Rollback stops new challenger decisions and restores
  the accepted software/policy route. It does not reverse legitimate already-recorded fills by restoring an old account file."
- MASTERPLAN §10.1 objective: "100% accountable cycles: every due cycle has a timely visible outcome or explicit incident."

## Known facts to design around (orchestrator-verified)
1. `/opt/mastermind` is not a git checkout; identity = git-blob comparison of installed files vs the accepted commit tree.
   `.deployed_git_sha` and `.deploy_prev/` are deploy CLAIMS (corroboration), never proof. `data/deploy_lag.json` is stale.
2. Installed today = ff16c192 (#1682); `origin/master` = d31aade9 (230e9a301 at commissioning); the delta on the manager path is #1614 (price/fx
   evidence + paper_account/settle/polygon/fx), not installed.
3. Restart sources: deploy script; nightly `mastermind-restart.timer` 08:30Z ±120 s; unattended-upgrades + needrestart
   (restarted the service 2026-10-22 06:02:15Z after a liblzma update); unexplained operator restarts (10-21 15:54Z).
   `MASTERMIND_JOBSTORE=memory` ⇒ a restart during a run loses the in-flight job; there is no durable record of it except
   whatever run_events/decision rows were already written (2026-10-16 CN/HK cycles left no run_started at all).
4. Job run_events carry `git_sha: "unknown"`; only `app_started` carries the sha. The loaded Python modules are not proven
   equal to on-disk files after a deploy unless the process started after the rsync (check process start vs `.deployed_git_sha` mtime).
5. The provider SDK is part of identity: VPS has `claude-agent-sdk` 0.2.110, whose error path produces the misleading
   "Claude Code returned an error result: success"; 0.2.151 fixes the message. A dependency change is a distinct version.
6. Manager windows (UTC): china_daily 08:00, hk_daily 09:00, autonomous_daily 23:10 (Mon–Fri); US overnight re-decides
   02:20 / 06:20 / 11:20; Asia overnight watches 00:20 / 14:20 / 20:20; settle_brain_asia 01:35; settle_pending 15:00.
7. Hard rules: live data is read-only for every verifier; no rsync/scp toward the VPS outside the accepted deploy script;
   no account reset, seed rewrite, balancing fill or repair trade; rollback never restores an old account file.

## Required plan content
1. **Identity definition** — the exact tuple that defines "installed": commit tree blobs (with the deploy script's exclusion
   list made explicit), dependency lock (SDK version + any provider package), unit file + drop-ins (BindPaths, env file
   *names* only, never contents), and loaded-process identity (process start time > deploy write time; `/health.commit`).
2. **Pre-change capture (§12.1 steps 1–2)** — read-only commands to snapshot pending targets, unfinalized receipts, pending
   settlement, scheduled jobs, current blob manifest; where each artifact is stored; the executable rollback route
   (existing `.deploy_prev` snapshot + deploy script rollback) and what rollback must NOT touch.
3. **Install window rule** — choose windows that avoid every manager/settlement window above with margin; state the
   rule and two concrete candidate windows.
4. **Post-install proof (§12.1 step 3)** — blob comparison procedure (hash-object over a pipe, no temp files on the host),
   dependency check, loaded-process check, `/health` fields, and the pass/fail criteria. Include how to prove a renewal PR is
   installed (all its deployable files equal the accepted blobs).
5. **First natural cycle (§12.1 step 4)** — what to observe for the next CN, HK and US cycles (run_started/run_finished with
   target_status, packet_accepted identity, decision row, settlement/receipt), and the disposition taxonomy
   {not_due, disabled, started, accepted_no_change, accepted_change, rejected, failed, incomplete_uncertain}.
6. **Restart hazards** — for each restart source in fact 3: risk, detection evidence, and a proposed mitigation with its
   owner (e.g. needrestart exclusion for `mastermind.service`; durable jobstore; restart timer outside windows). Mark every
   mitigation as a PROPOSAL needing seat approval; none is executed by this plan.
7. **Evidence layout** — where captures live (`/Volumes/Mastermind/evidence/pbr/<capture-id>/...` on the orchestrator
   host), redaction rules (no tokens, emails, env contents), and what is committed to the repo vs kept as evidence.
8. **What this plan does not prove** — separate operational correctness from economic qualification and investment value.
8b. **Release row: provider SDK pin (seat ruling CR-RT-3)** — a table row in the release section with this evidence
   (from `~/lanes/tmp/pbr-rt-lr5/SDK_EVIDENCE.md`): `pyproject.toml` pins `claude-agent-sdk>=0.2` (floor only, no lock);
   VPS runs 0.2.110, whose `_internal/query.py` builds `"; ".join(errors) or str(subtype)` so an API failure arriving as
   `subtype:"success", is_error:true, errors:[]` raises a plain `Exception("Claude Code returned an error result: success")`;
   0.2.151 (`_error_result_text`) prefers `errors[]`, then `result` prose, then a non-success subtype, then
   `API error (HTTP <status>)`, and raises a typed `ResultError` with the result frame in `.data`. State: the pin change is
   a distinct installed version (part of the identity tuple), it is RESERVED to the seat, and specify the regression test that
   must ride with it — a test that feeds a synthetic `{"type":"result","subtype":"success","is_error":true,"errors":[],
   "result":"API Error: 401 ..."}` frame and asserts the produced message is NOT "...error result: success" (skip with a
   reason when the installed SDK is < 0.2.151). Name what the cli_bridge typed-failure record (W4 L-R2) still needs from the
   SDK on either version (AssistantMessage.error, ResultMessage.subtype/is_error/api_error_status).
9. **The one release decision the seat must make** — end the document with a section titled exactly
   `## Seat decision` containing ONE decision, stated as a choice between explicit options with the consequence of each
   (for example: which composition to install next and in which window, or whether to hold at ff16c192 until the W4 PRs
   land). Pick the single decision that blocks the most downstream work and justify that choice in ≤5 lines.

Write concisely (target 180–320 lines). Use tables for the identity tuple, windows and restart hazards.

## Final message
Emit the full RETURN block as your last message:
```
RETURN L-R5
file: research/commission_pbr_fable_masterplan/2026-10-22/lanes/RUNTIME/INSTALL_PROOF_PLAN.md (<lines> lines)
identity tuple: <one line>
windows: <the two candidate windows>
seat decision: <one sentence>
open questions: <n> listed
```
