# T2 — teammate binding and dispatch (Paperclip agent ⇄ T3 thread)

Lane T2 result, 2026-11-10. A **teammate** is a company agent in Paperclip whose
mind runs as a thread on a T3 server. Proven live on two TEST agents in
isolated dev instances (Paperclip :3190, T3 :3800, root
`~/.mastermind/mmos-dev/t3-t2`); evidence `~/.mastermind/mmos_evidence/
t2-20261110/` (01–11); carrier `tools/mmos_teammate/`. The Paperclip `agents`
row IS the teammate record; its `metadata` JSON carries one new key:

```json
"teammate": { "t3": {
  "environmentId": "<T3 env>", "projectId": "<T3 project>",
  "providerInstanceId": "<instance in T3 settings.json>",
  "primaryThreadId": "mcp:<uuid>", "bindingRevision": 2,
  "rotatedAt": "2026-11-10T…Z" } }
```

The provider instance owns the persona: `homePath` (agent home + `CLAUDE.md`
memory file), `launchArgs` with the charter via `--append-system-prompt-file`
(re-read every turn — why rotation keeps the persona), optional `--settings`
for tool enforcement (Mira `deny:["Bash"]` — proven tool-LISTING enforcement,
zero tool_use; Atlas ran Bash fully).

## The wake sequence (numbered)

Paperclip's `process` adapter (heartbeat **off**) spawns `wake_carrier.py` with
`PAPERCLIP_AGENT_ID/COMPANY_ID/API_URL/RUN_ID` and a per-run
`PAPERCLIP_API_KEY` (48h agent JWT). The carrier then:

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
   (marker + identifier + title + description). Exit 0/1/2 = completed /
   failed / needs-human.
7. Deliver, idempotently across runs: comment (skip if the exact reply text is
   already posted) → pending `request_confirmation` (skip if this op's key
   already exists; without a review path this build refuses PATCH to
   `in_review`) → `PATCH` status `in_review`.
8. Any failure releases the issue (comment + back to `todo`); needs-human exits
   0 with the issue left `in_progress`.

Exactly-once is **client-side**: the wake `idempotencyKey` does NOT dedupe
process runs in this build — the marker discipline holds one-send/one-post
(proven across crash-after-send, kill, key replay, T3-down and the adversarial
pass; evidence 08/09/11).

## T3 send surface — chosen and why

**Chosen: the stock `t3` CLI** (`t3 thread send <id> - --wait --json`).
Supported, versioned surface; the CLI mints its own short-lived MCP session
from `T3CODE_HOME`, so **the carrier passes no T3 credential at all** and
`--wait` returns the exact run's reply. Rejected: HTTP/WS bearer (a second
credential to hold and rotate inside the carrier — leak surface, no added
capability) and raw MCP (internal protocol, no stability promise). Token
hygiene (evidence 10): the run token stays in the carrier process env — never
in argv, prompts, thread text, logs or evidence; a bogus configured
`PAPERCLIP_API_KEY` in adapterConfig.env is dropped at spawn (runtime wins).

## What is NOT atomic

- The metadata binding write is **checked, not CAS**: read → verify
  `bindingRevision` → write revision+1 → read back; a concurrent writer between
  read and write is detected afterwards, not prevented.
- Delivery is three calls; a crash between them is repaired by the next wake
  without duplicating (proven incl. the adversarial replay), but a
  delivered-but-not-marked window exists; send and comment are separate
  systems.

## What is NOT proven here

- No concurrent writers on one agent's metadata; not a production install
  (dev instances, glm-5.3-flash, TEST agents).
- The wake `idempotencyKey` does not dedupe process runs (replay spawns a new
  run; it no-ops on the thread — recorded, not fixed here).
- Issue-scoped assignment-automation wakes reliably no-op (own `activeRun`);
  agent-scoped keyed wakes do the work.

## Moving ONE installed agent onto this path (exact steps)

1. Pick one installed Paperclip agent (:3100); write its charter to
   `<host>/CHARTER.md`; `mkdir -p` its home dir (0700).
2. Add a T3 provider instance in the target server's `settings.json` while
   that server is STOPPED: `driver: claudeAgent`, own `homePath`,
   `launchArgs: "--append-system-prompt-file <charter> [--settings …]"`.
3. Start the T3 server; `t3 thread start <projectId> "Reply with just: READY"
   --provider <instance> --model <model> --title "<agent> primary" --json`.
4. Write `carrier.json` next to the agent (expanded paths, no `~`): `t3_bin`,
   `t3_home` (T3CODE_HOME), `t3_cwd` (scratch dir), poll/timeout.
5. PATCH the agent: `adapterType: "process"`, `adapterConfig: {command:
   <python -I>, args: [<abs wake_carrier.py>, <carrier.json>], cwd: <agent
   dir>, timeoutSec: 1500}`, `runtimeConfig.heartbeat.enabled: false`.
6. Write the binding (revision 1), read it back; one keyed on_demand wake;
   verify one succeeded run, one thread turn, comment == thread answer, issue
   → in_review. (`setup_teammate.py` automates 1–6 from a spec file.)

## ATTACK (kimi-k3.1-pro adversarial pass — evidence file 11)

Child t2-attack-001 hunted wake/kill/restart sequences; every claim re-verified
live by the principal. **DOUBLE-SEND: no** (racing keyed wakes serialize at
checkout, loser: HTTP 409; crash-after-send reconciles, no resend; the
sub-second kill-mid-send window was missed 3× and stays **untested**).
**TOKEN-LEAK: no** (0 hits across thread, comments/interactions, run and
provider logs). **DOUBLE-POST: yes — reproduced, then fixed** (`3a28810dd`):
kill the carrier between comment and status, let a later turn answer
differently in the thread, re-wake → (1) `scan_marker` returned the *last*
assistant text, bypassing exact-text dedupe → second answer comment — fixed by
binding the reply to the marker turn's runId; (2) re-POSTing the confirmation
key from a later run is **409, not dedupe** → failed run + release loop —
fixed by reading `interactions` and skipping an existing key. Fix replayed
live on the exact attack end-state (MMO-7, run `0f800c69`): exit 0, no resend,
counts unchanged (5 comments / 1 interaction / 24 messages).