# T2 — teammate binding and dispatch (Paperclip agent ⇄ T3 thread)

Lane T2 result, 2026-11-10. A **teammate** is a company agent in Paperclip whose
mind runs as a thread on a T3 server. Proven live on two TEST agents in
isolated dev instances (Paperclip dev :3190, T3 dev :3800, root
`~/.mastermind/mmos-dev/t3-t2`); evidence `~/.mastermind/mmos_evidence/
t2-20261110/` (01–10). Carrier: `tools/mmos_teammate/`.

## The binding

The Paperclip `agents` row IS the teammate record. Its existing `metadata` JSON
carries one new key:

```json
"teammate": { "t3": {
  "environmentId": "<T3 environment id>", "projectId": "<T3 project id>",
  "providerInstanceId": "<instance in T3 settings.json>",
  "primaryThreadId": "mcp:<uuid>", "bindingRevision": 2,
  "rotatedAt": "2026-11-10T…Z" } }
```

The provider instance owns the persona: `homePath` (agent home + `CLAUDE.md`
memory file), `launchArgs` with the charter via `--append-system-prompt-file`
(re-read every turn — why rotation keeps the persona), optional `--settings`
for tool enforcement (Mira `deny:["Bash"]`, proven as tool-LISTING enforcement:
Bash absent from her init tools array, zero tool_use; Atlas ran Bash fully).

## The wake sequence (numbered)

Paperclip's `process` adapter (heartbeat **off**) spawns `wake_carrier.py` with
`PAPERCLIP_AGENT_ID`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_API_URL`,
`PAPERCLIP_RUN_ID`, per-run `PAPERCLIP_API_KEY` (48h agent JWT).

1. Authenticate (`GET /api/agents/me`); refuse if the token is for another agent.
2. Read inbox (`inbox-lite`); pick the oldest `todo` **or** `in_progress` issue
   with no `activeRun` and dependencies ready (assignment automation moves
   fresh issues to `in_progress` before the run starts — both are accepted).
3. `POST /api/issues/<id>/checkout`, `expectedStatuses: ["todo","in_progress"]`
   — binds the issue to this run.
4. Read the `teammate.t3` binding from agent metadata; fatal if absent.
5. Scan the primary thread (`t3 thread show --json --messages 60`) for the
   operation marker `[pc-<issueId>-<sha256(title+"\n"+description)[:10]>]`:
   answered → reconcile that reply; pending → poll until the server-side turn
   answers; absent → send. Never resend an existing marker.
6. Send: `t3 thread send <thread> - --wait --json`, message on **stdin**
   (marker + issue identifier + title + description). Exit 0 completed / 1
   failed / 2 needs-human.
7. Deliver, idempotently: comment (skipped if the exact reply text is already
   posted) → pending `request_confirmation` interaction (idempotencyKey
   `<op>-confirm`; this build refuses agent PATCH to `in_review` without a
   review path) → `PATCH` status `in_review`.
8. Any failure releases the issue (comment + back to `todo`); needs-human exits
   0 with the issue left `in_progress`.

Exactly-once is **client-side**: the wake `idempotencyKey` does NOT dedupe
process runs in this Paperclip build — the marker discipline above is what
holds one-send/one-post (proven across crash-after-send, kill, key replay and
T3-down; evidence 08/09).

## T3 send surface — chosen and why

**Chosen: the stock `t3` CLI** (`t3 thread send <id> - --wait --json`).
Supported, versioned surface; the CLI mints its own short-lived MCP session
from `T3CODE_HOME`, so **the carrier passes no T3 credential at all** and
`--wait` returns the exact run's reply. Rejected: HTTP/WS with a bearer token
(a second credential to mint, hold and rotate inside the carrier — leak surface,
no added capability) and raw MCP (internal protocol, no stability promise).

Token hygiene (evidence 10): the run token stays in the carrier process env —
never in argv, prompts, thread text, logs or evidence; a bogus configured
`PAPERCLIP_API_KEY` in adapterConfig.env is dropped at spawn (runtime wins).

## What is NOT atomic

- The metadata binding write is **checked, not CAS**: read → verify
  `bindingRevision` → write revision+1 → read back; a concurrent writer between
  read and write is detected afterwards, not prevented.
- Delivery is three calls (comment → confirmation → status); a crash between
  them is repaired by the next wake without duplicating (proven), but a
  delivered-but-not-marked window exists.
- Send and comment are separate systems: a crash after send leaves the marker
  pending in-thread; the next wake's scan reconciles it.

## What is NOT proven here

- No concurrent writers on one agent's metadata were tested; not a production
  install (dev instances, glm-5.3-flash, TEST agents).
- The wake `idempotencyKey` does not dedupe process runs (replay spawns a new
  run; it no-ops on the thread — recorded, not fixed here).
- Issue-scoped assignment-automation wakes reliably no-op (they see their own
  `activeRun`); agent-scoped keyed wakes do the work. Not tested beyond that.
- Attack pass ran (below); the sub-second kill-mid-send window stayed untested.

## Moving ONE installed agent onto this path (exact steps)

1. Pick one installed Paperclip agent (:3100); write its charter to
   `<host>/CHARTER.md`; `mkdir -p` its home dir (0700).
2. Add a T3 provider instance in the target T3 server's `settings.json` while
   that server is STOPPED: `driver: claudeAgent`, own `homePath`, `launchArgs:
   "--append-system-prompt-file <charter> [--settings <settings.json>]"` (one
   shell-style string).
3. Start the T3 server; `t3 thread start <projectId> "Reply with just: READY"
   --provider <instance> --model <model> --title "<agent> primary" --json`.
4. Write `carrier.json` next to the agent (paths expanded — no `~`):
   `t3_bin`, `t3_home` (T3CODE_HOME), `t3_cwd` (scratch dir), poll/timeout.
5. PATCH the installed agent: `adapterType: "process"`,
   `adapterConfig: {command: <python -I>, args: [<abs wake_carrier.py>,
   <carrier.json>], cwd: <agent dir>, timeoutSec: 1500}`,
   `runtimeConfig.heartbeat.enabled: false` (heartbeat stays off until the
   dispatch pattern is accepted).
6. Write the binding into `metadata.teammate.t3` (revision 1), read it back;
   issue one keyed on_demand wake and verify: one succeeded run, one thread
   turn, comment == thread answer, issue → in_review.

## ATTACK (kimi-k3.1-pro adversarial pass — evidence file 11)

Child t2-attack-001 hunted wake/kill/restart sequences; every claim re-verified
live by the principal before acceptance. **DOUBLE-SEND: no** — racing keyed
wakes serialize at checkout (loser gets HTTP 409), crash-after-send reconciles
with no resend; kill-mid-send (sub-second window) was missed 3× and stays
**untested**. **TOKEN-LEAK: no** — 0 pattern hits across thread, comments,
interactions, 18 run logs, 5 provider event logs. **DOUBLE-POST: yes,
reproduced then fixed** (`3a28810dd`): kill the carrier between comment and
status, let any later turn answer differently in the thread, re-wake →
(1) `scan_marker` returned the *last* assistant text, so a changed reply
bypassed the exact-text comment dedupe → second answer comment — fixed by
binding the reply to the marker turn's T3 runId (verified live: marker and its
answer share `ordinal:9`, the side message is `ordinal:10`); (2) re-POSTing the
confirmation key from a later run is **409, not dedupe** in this build → failed
run, release comment, todo reset, automation re-wake loop (3 release comments
observed) — fixed by reading `interactions` and skipping an existing key. Fix
replayed live against the exact attack end-state (MMO-7, run `0f800c69`):
exit 0, no resend, comment/interaction/message counts unchanged (5/1/24).