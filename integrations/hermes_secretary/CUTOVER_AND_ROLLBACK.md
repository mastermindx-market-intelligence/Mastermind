# Hermes secretary cutover and rollback

This runbook is the procedure. It is not permission to execute it. WP5 is shadow-only. Grok Secretary stays the live bridge. Do not approve, merge, post, deploy, or install cron while following this document.

## Current boundary

- Decisions are JSONL on disk. `would_post` is false. The Slack client is rejected if it exposes a write method.
- `routines/jobs.json` is `installed: false`. Every job is paused, `deliver: local`. `install_into_hermes_home()` raises.
- `mmsecretary` / `mmmeta` are not modified.
- No Slack token belongs in this tree, in a prompt, or in a Hermes profile env checked into git.

## Before any cutover

1. Independent non-author review of the exact head that would be enrolled.
2. Fill the unresolved roster: Chris's Slack user id, each Dot bot user id, and the two rooms where a Chris-voiced message may skip a draft. Until those exist, the default roster ignores unknown users and the voice guard drafts everything.
3. Run shadow mode against a read-only Slack export for a Chairman-chosen window. Compare with `parity.compare`. A refusal must show up as `withheld`, not as a post. Mismatches are investigated. They are not patched by posting.
4. Keep the shadow JSONL. Dedup keys are `channel:ts`. A second pass must not grow the file for the same messages.
5. Do not point Hermes cron at a live home. Profile timezone cannot represent Vancouver, Los Angeles, and Denver at once without converting expressions. See `UNPORTED.md`.
6. Computer-use, Fabric submit, and Codex menu-bar reads stay unported until their own admission. Cutover of the Slack scanner does not turn those on.

## Cutover, only after a separate Chairman grant

1. Leave Grok Secretary running. Shadow and live may overlap. Dedup by Slack ts so the same commission is not handed off twice. If Grok Secretary already ACKed, the detector stays quiet.
2. A later change may flip delivery from local JSONL to a thread reply. That change is not this package. It still may not approve or merge, may not use Always allow, and may not retry a Fabric run id.
3. Enrolling skills into `mmsecretary` is a profile change on the qualification lane, which has its own writer. Do not push that branch from this work. The skills toolset there is disabled on purpose.
4. Wake delivery still belongs to `control_plane.wake_events`. Mint only when the dialogue resolver has already produced `agent_dialogue_attention:<64 hex>`. Do not add a secretary source kind in order to make the timer "more native".
5. Post the receipt and the RESULT on the existing Slack thread and on the PR only after the grant in step 2. Reviewers comment with a `VERDICT:` line. They do not approve.

## Rollback

1. Stop calling `run_shadow` if the JSONL itself is the problem. Deleting the file is optional; it is local evidence, not Slack state.
2. If a Hermes home was given these jobs despite `install_into_hermes_home()` refusing, pause each job id in that home and set delivery back to local. Do not delete the Hermes profile to roll this back.
3. Do not stop Grok Secretary as part of rollback. It was never turned off by this package.
4. Do not revert unrelated incumbent PRs (#1717, #1790, #188, #624, #1657) to undo this slice.
5. A posted message, if a later grant created one, is corrected by a thread reply that names the bad ts. It is not deleted from here, and it is not replaced by a retry of a refusal or a Fabric run.

## Stop

Shadow parity can run any time on fixtures or a read-only export. Live posting, cron install, profile enrollment, Mac actuation, and Fabric submit are out of this runbook's authority.
