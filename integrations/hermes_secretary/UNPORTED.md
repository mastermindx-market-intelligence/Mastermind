# What this port does not run

The 2026-10-25 teaching snapshot was ported as procedures, guards, and shadow decisions. These pieces still need a separate admission before they can do the live job.

1. **m2studio browser actuation.** AppleScript (`~/gwcap/sweeptabs.scpt`, `listtabs.scpt`, and the `cjs` / `gw` / `pastev` helpers), Peekaboo clicks, Multilogin/Orbita window control, and the "ChatGPT started debugging this browser" recovery are not executable here. They need an admitted macOS computer-use grant on m2studio (`61f4e9d7-b202-4cda-85ed-36904689931e`) and the existing `~/gwcap` tree. The Hermes qualification profile still disables `computer_use`, `browser`, and `terminal`.

2. **Menu-bar Codex usage and Codex Switcher.** Routine 5's 7-day usage read, the 10–25 relogin windows, and the Tab-to-accept / `~/nudge.txt` relaunch path need that same Mac session. This package only chooses the next account and records who would be nudged.

3. **`codex-drift-check.py` and `codex-session.sh`.** Routine 7's FRESH / STALE / DRIFTING / LOST actions are decided here. The charter files under `~/gwcap/project-charters/<slug>/` and the restore script are not in this repo.

4. **Live `fabric_task.py` submission.** The once-only guard is implemented. The owner script, the m2studio shell, and `http://127.0.0.1:45119/readyz` are not called. Sibling `integrations/hermes_delegate/` is absent on this head, so there is no second submitter to wire.

5. **Chris's Slack user id and the Dot bot user ids.** The snapshot names them and gives ids only for Grok Secretary, ChatGPT1, ChatGPT2, ChatGPT3/Sol, and Ryan. The default roster does not guess. A live shadow pass must be given those ids explicitly.

6. **The two rooms where a message under Chris's name may skip a draft.** The snapshot says "the two rooms" and does not name them. Zero or one configured room fails closed to draft-only. Shadow mode still refuses the send.

7. **One Hermes profile clock versus three timezones.** Ping scan is `America/Vancouver`, Codex usage is `America/Los_Angeles`, continuity audit is `America/Denver`. Hermes cron at this pin uses the profile timezone. Jobs whose routine named no zone are pinned to `America/Vancouver` and marked `assumed_secretary_home`. Do not install them into one profile clock without converting the expressions.

8. **BLOCKED keyword trigger.** Hermes cron at pin `1c0cd66` has duration, interval, and five-field cron, not a Slack keyword. The listener is stored as a trigger and exercised by `run_shadow(mode="blocked_trigger")`. It is not a cron job.

9. **Wake obligations for a raw Slack ts.** Masterplan P4 (PR #1841) maps timer observations into the existing Wake fabric. That fabric has no scheduler and only admits canonical source refs (`agent_dialogue_attention:<64 hex>` and the other closed kinds). This package mints an in-memory envelope when that ref is already present. It does not invent a source kind, write `wake_ledger`, or treat a Slack ts as an obligation id. Until the dialogue resolver emits the ref, the timer stays Hermes cron.

10. **Profile enrollment.** `mmsecretary` and `mmmeta` remain disarmed (`clarify` only, skills and cronjob disabled). These skills are not copied into those profiles.
