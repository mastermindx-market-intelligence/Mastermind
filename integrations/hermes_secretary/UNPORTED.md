# What this port does not run

The 2026-10-25 teaching snapshot was ported as procedures, guards, and shadow decisions. These pieces still need a separate admission before they can do the live job.

1. **m2studio browser actuation.** AppleScript (`~/gwcap/sweeptabs.scpt`, `listtabs.scpt`, and the `cjs` / `gw` / `pastev` helpers), Peekaboo clicks, Multilogin/Orbita window control, and the "ChatGPT started debugging this browser" recovery are not executable here. They need an admitted macOS computer-use grant on m2studio (`61f4e9d7-b202-4cda-85ed-36904689931e`) and the existing `~/gwcap` tree. The Hermes qualification profile still disables `computer_use`, `browser`, and `terminal`.

2. **Menu-bar Codex usage and Codex Switcher.** Routine 5's 7-day usage read, the 10–25 relogin windows, and the Tab-to-accept / `~/nudge.txt` relaunch path need that same Mac session. This package only chooses the next account and records who would be nudged.

3. **`codex-drift-check.py` and `codex-session.sh`.** Routine 7's FRESH / STALE / DRIFTING / LOST actions are decided here. The charter files under `~/gwcap/project-charters/<slug>/` and the restore script are not in this repo.

4. **Live `fabric_task.py` submission.** The once-only guard is implemented. The owner script, the m2studio shell, and `http://127.0.0.1:45119/readyz` are not called. Sibling `integrations/hermes_delegate/` is absent on this head, so there is no second submitter to wire.

5. **Chris's Slack user id and the Dot bot user ids.** `roster.json` has a required `CHRIS_SLACK_USER_ID` slot. It is null, and an unset or blank value adds nobody. Dot bot user ids are still unknown. Do not guess either.

6. **Resolved in `roster.json`.** The standing-authorized post rooms are `#dotsandgroksecretary` `C0CBC6AEAQZ` and `#metaceo` `C0C5FCK1F45`. A thread reply there of kind receipt, PICKUP, or RESULT is pre-authorized. Everything else is draft-only. Shadow mode still posts nothing.

7. **Resolved on the catalog clock.** Every job is `America/Cancun` (UTC-5, no DST). Original wall clocks are on each job as `wall_clock_intent`. Every-hour minute crons and the 30-minute interval did not change expression. `*/3` and `*/2` match Pacific and Mountain standard time; during US daylight time those two jobs fire one hour later than the source wall clock. The BLOCKED listener is still not a cron.

8. **BLOCKED keyword trigger.** Hermes cron at pin `1c0cd66` has duration, interval, and five-field cron, not a Slack keyword. The listener is stored as a trigger and exercised by `run_shadow(mode="blocked_trigger")`. It is not a cron job.

9. **Wake obligations for a raw Slack ts.** Masterplan P4 (PR #1841) maps timer observations into the existing Wake fabric. That fabric has no scheduler and only admits canonical source refs (`agent_dialogue_attention:<64 hex>` and the other closed kinds). This package mints an in-memory envelope when that ref is already present. It does not invent a source kind, write `wake_ledger`, or treat a Slack ts as an obligation id. Until the dialogue resolver emits the ref, the timer stays Hermes cron.

10. **Profile enrollment.** `mmsecretary` and `mmmeta` remain disarmed (`clarify` only, skills and cronjob disabled). These skills are not copied into those profiles.
