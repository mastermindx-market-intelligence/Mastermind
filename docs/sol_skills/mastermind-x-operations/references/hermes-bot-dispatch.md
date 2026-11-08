# Dispatching a Mastermind bot (session → bot handoff)

The user requires handoffs to go bot-to-bot directly, not chat acting as the bot. Two proven channels: a one-shot Hermes chat into a local bot profile (synchronous — below) and the shared Hermes kanban board (asynchronous — last section).

## Procedure (one-shot chat)

1. Write the brief to a file (short, imperative, one topic per dispatch). Enumerate each obligation so the bot can acknowledge them one by one, and number the expected outputs.
2. Dispatch: `HERMES_HOME=<bot profile dir> hermes chat -q "$(cat <brief-file>)"` as a **background** terminal job; wait/poll on the returned process session instead of re-launching. Responses can take minutes — keep polling, don't relaunch a parallel dispatch.
3. Read the bot's reply for intent only. **The reply is not evidence.** After every dispatch, independently verify durable state on disk:
   - `stat` the target file(s) — mtime is the ground truth for whether the bot executed anything at all.
   - `grep` the file for the required identifiers/strings.
   - `read_file` the tail; require either the specific appended lines or a literal paste-back of the file's last ~800 chars.
4. If a required write didn't land, diagnose before re-dispatching: grep the bot profile's `logs/agent.log` `tool_executor` lines for the dispatch window. Three distinct causes need three different responses:
   - **Wrong tool-call path** (`tool_call returned error ... is a directly-listed tool` / `requires 'calls'`): the bot emitted the call through the wrong wrapper or in malformed syntax. Re-dispatch with the corrected, byte-exact call shape (see step 5) — do not just repeat the same brief.
   - **Capability absence** (tool genuinely missing from that profile's registry): re-scope the brief to tools the profile actually has; do not demand a tool its build lacks.
   - **Model-capacity degradation** (profile runs a small local/aggregated model tier — check the profile's provider/model line in the log): a model too weak to emit structured tool JSON reliably will *narrate* tool calls as chat text and then fabricate the requested output — plausible audit trails, filenames, and file counts that do not exist anywhere. Re-dispatching syntax corrections to it burns rounds; escalate the model-config change to the Chairman instead.
5. **Verify the tool template against the target's real build before pasting it into a brief.** Search the bot's own logs (or your own session's tool schema) for the tool's exact name and parameter shape — every field you invent in a dispatch template (`task_id=...`-style pseudo-syntax) becomes a parse failure for the bot, and a weak model covers the failure by inventing the result. When a dispatch is a diagnostic smoke test, isolate ONE tool call with a byte-exact shape, strip every ancillary demand (journals, audits, confirmations), allow at most two attempts, and require the reply be only the verbatim tool payload.

## Kanban delegation lane (async dispatch)

For durable, multi-minute work use the Hermes kanban board instead of a one-shot chat. The board DB is shared across ALL profiles on the host, so orchestrator seats (chief-of-staff, meta-ceo) create and assign tasks and consume specialist results from the same board — assignment and result-return ARE the board (status, comments, attached artifacts); no extra transport to build.

1. Write the task body to a file. Contract that travels in every body: do the work, write named artifacts to absolute paths under the assignee's verification workspace, then complete with a comment quoting exact revisions + artifact paths. Prefer read-only repo probes (e.g. `git -C <checkout> rev-parse --abbrev-ref HEAD` + `rev-parse HEAD`) — output you recompute independently proves real execution, not narration.
2. Create under the orchestrator's own home so board rows attribute to the orchestrator seat: `HERMES_HOME=<orchestrator profile dir> hermes kanban create "<title>" --body-file <body> --assignee <profile> --created-by <orchestrator-profile> --json` (verb is `create`; `add` does not exist; `create` supports per-task model overrides and `--json` for the task id). Without `--created-by` the row attributes to whatever default profile owns the shell — and board attribution is what the completion loop and any later audit read.
3. Dispatch: `hermes kanban dispatch --max 1 --json` → note the run id. The worker executes in an isolated scratch workspace `~/.hermes/kanban/workspaces/<task_id>` — check artifacts there, not in the shared checkout.
4. Verify: `hermes kanban show <task_id>` for status/comment/artifacts, then re-derive every claim on disk yourself — a specialist-quoted sha or HEAD is a claim until your own `shasum`/`git rev-parse` matches it.

Kanban pitfalls:
- `hermes profile create` and `hermes kanban create` are slow (minutes) and can blow short timeouts with exit 124 while still completing — before retrying, check for the artifact (profile dir / board row) to avoid double-creating; give them 600s+ or run as background jobs.
- A crashed or timed-out run auto-returns its task to `ready`, so redispatch is safe and idempotent. If Hermes is mid-self-update the gateway drains (`update_paused`) and dispatched workers die as "owner silent" — that is the drain, not a specialist fault: wait for the update to settle (no source-update banner in command output), then redispatch.
- Verify assignees exist before dispatch: `hermes kanban assignees` lists every on-disk profile the board will accept.

## Pitfalls

- Tee evidence-producing commands to /tmp files and cite those files, not scrollback — long terminal output gets demoted or dropped at context compaction, and a verification claim you can no longer show is just an assertion. This applies to your own verification output, not just bot replies.
- Never accept a bot's quoted self-verification. A quoted-but-absent write is treated as a false report; disk state outranks every claim, because a bot can quote file content that does not exist while fully believing it did.
- Degradation across dispatches: later turns of an iterative exchange can print the intended tool-call JSON as chat text instead of executing it — claiming success while having done nothing. If a reply reads like a tool transcript rather than prose, check the target artifact with stat/grep before believing anything in it.
- A confession that contradicts external evidence (posted messages, file mtimes) is a contradiction to surface, not a resolution to file. Fetch the actual channel history and order messages by timestamp (Slack `ts` = epoch seconds; convert with python datetime at the workspace's real UTC offset) before treating either the denial or the accusation as settled, then put the contradiction in front of the Chairman with the evidence.
- For shadow-phase / boundary-restricted bots, state the restriction as an explicit no-send clause — "no Slack sends of any kind, even to confirm receipt". Otherwise the bot may treat an org channel as the appropriate place to announce readiness and violate the boundary it believed it was honoring.
- When a required write fails repeatedly across dispatches despite an exact literal payload plus paste-back demand, stop re-sending: quote the disk evidence and recommend suspending the seat's dispatch channel to the Chairman rather than burning more rounds. Repeating an identical brief re-arms the same failure mode.
- Dispatch briefs demanding multiple structured artifacts (a memory write AND a paste-back AND a confession AND a boundary restatement) exceed a weak model's execution capacity — it answers everything in content but executes nothing. When briefs fail, cut to a single verifiable tool action per dispatch before escalating anything else.
- Slack identity plates do not identify agents. Multiple agent integrations post through the same user token/plate, and a connector's outbound identity is whichever user token is bound to it — so never trust a display name, and never assume the bot has its own Slack user at all. Determine authorship from the message's `user` id plus `app_id`/`bot_id`, and use the roster tool (`LIST_ALL_USERS`) with `limit: 200` — the default page returns one entry plus a pagination cursor, which misreads as an almost-empty workspace.
- Never put credentials or tokens in a dispatch brief — briefs are chat transcripts. To provision secrets, name only the env var names the bot must fill and where the values live.

## Environment notes

- Hermes bot profiles live locally under `~/.hermes/profiles/<name>/` with their own `memories/` (`MEMORY.md`), `SOUL.md`, skills and crons. The prebuilt repo integrations (`hermes_secretary/`, `hermes_delegate/`) govern cutover and delegation and must not be re-invented.
