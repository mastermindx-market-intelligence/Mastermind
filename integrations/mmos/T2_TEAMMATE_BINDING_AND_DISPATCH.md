# T2 — teammate binding and dispatch (Paperclip agent ⇄ T3 thread)

Lane T2 result, 2026-11-10. A **teammate** is a company agent in Paperclip whose
mind runs as a thread on a T3 server. Proven live on two TEST agents in
isolated dev instances (Paperclip dev :3190, T3 dev :3800,
root `~/.mastermind/mmos-dev/t3-t2`), real model turns, evidence in
`~/.mastermind/mmos_evidence/t2-20261110/` (files 01–10). Carrier code:
`tools/mmos_teammate/` (`wake_carrier.py`, `setup_teammate.py`, `specs/`).

## The binding

The Paperclip `agents` row IS the teammate record. Its existing `metadata` JSON
carries one new key:

```json
"teammate": { "t3": {
  "environmentId":   "<T3 environment id>",
  "projectId":       "<T3 project id (not Paperclip's)>",
  "providerInstanceId": "<instance in T3 settings.json, e.g. atlas_t2>",
  "primaryThreadId": "mcp:<uuid>",
  "bindingRevision": 2,
  "rotatedAt": "2026-11-10T…Z" } }
```

The provider instance owns the persona: `homePath` (agent home + `CLAUDE.md`
memory file), `launchArgs` carrying the charter via `--append-system-prompt-file`
(re-read every turn — this is why rotation to a new thread keeps the persona),
and an optional `--settings` file for tool enforcement (Mira: `permissions.deny:
["Bash"]` — proven as tool-LISTING enforcement: Bash absent from her init tools
array, zero tool_use; Atlas ran Bash to completion).

## The wake sequence (numbered)

Paperclip's `process` adapter (heartbeat **off**) spawns `wake_carrier.py` with
`PAPERCLIP_AGENT_ID`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_API_URL`,
`PAPERCLIP_RUN_ID` and a per-run `PAPERCLIP_API_KEY` (48h agent JWT).

1. Authenticate as the agent (`GET /api/agents/me`); refuse if the token is for
   another agent.
2. Read inbox (`inbox-lite`); pick the oldest `todo` **or** `in_progress` issue
   with no `activeRun` and dependencies ready (assignment automation moves fresh
   issues to `in_progress` before the run starts — both must be accepted).
3. `POST /api/issues/<id>/checkout` with `expectedStatuses: ["todo",
   "in_progress"]` — binds the issue to this run.
4. Read the `teammate.t3` binding from agent metadata; fatal if absent.
5. Scan the primary thread (`t3 thread show --json --messages 60`) for the
   operation marker `[pc-<issueId>-<sha256(title+"\n"+description)[:10]>]`:
   answered → reconcile that reply (no resend); pending → poll until the
   server-side turn answers (no resend); absent → send.
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
- Supported, versioned surface that any teammate host can call; the CLI mints
  its own short-lived MCP session from `T3CODE_HOME`, so **the carrier passes
  no T3 credential at all**, and `--wait` returns the exact run's reply.
- Rejected: HTTP/WS with a bearer token (would require minting, holding and
  rotating a second credential inside the carrier — a leak surface with no
  added capability), and raw MCP (an internal protocol; no stability promise).

Token hygiene (evidence 10): the run token stays in the carrier process env —
never in argv, prompts, thread text, logs or evidence; a bogus configured
`PAPERCLIP_API_KEY` in adapterConfig.env is dropped at spawn (runtime wins).

## What is NOT atomic

- The metadata binding write is **checked, not CAS**: read → verify
  `bindingRevision` → write revision+1 → read back. A concurrent writer between
  read and write is detected after the fact, not prevented.
- Delivery (comment → confirmation → status) is three calls; a crash between
  them is repaired by the next wake without duplicating anything (proven), but
  there is a window where the issue is delivered-but-not-marked.
- Thread send and comment are separate systems: a crash after send leaves the
  marker pending in-thread; reconciliation relies on the next wake scanning it.

## What is NOT proven here

- No concurrent writers on one agent's metadata were tested.
- Not a production install: dev instances, glm-5.3-flash, TEST agents.
- The wake `idempotencyKey` does not dedupe process runs (replay spawns a new
  run; it no-ops on the thread — recorded, not fixed here).
- Issue-scoped assignment-automation wakes reliably no-op (they see their own
  `activeRun`); agent-scoped keyed wakes do the work. Not tested beyond that
  automation.
- Adversarial attack pass: see the ATTACK section below.

## Moving ONE installed agent onto this path (exact steps)

1. Pick one installed Paperclip agent (installed instance, :3100) and write its
   charter to `<dev-or-host>/CHARTER.md`; `mkdir -p` its home dir (0700).
2. Add a T3 provider instance for it in the target T3 server's
   `settings.json` while that server is STOPPED: `driver: claudeAgent`, its own
   `homePath`, `launchArgs: "--append-system-prompt-file <charter>
   [--settings <settings.json>]"` (one shell-style string), model of choice.
3. Start the T3 server; `t3 thread start <projectId> "Reply with just: READY"
   --provider <instance> --model <model> --title "<agent> primary" --json`
   → record `threadId`.
4. Write `carrier.json` next to the agent (paths expanded — no `~`):
   `t3_bin`, `t3_home` (T3CODE_HOME), `t3_cwd` (scratch dir), poll/timeout.
5. PATCH the installed agent: `adapterType: "process"`,
   `adapterConfig: {command: <python -I>, args: [<abs wake_carrier.py>,
   <carrier.json>], cwd: <agent dir>, timeoutSec: 1500}`,
   `runtimeConfig.heartbeat.enabled: false` (keep heartbeat off until the
   dispatch pattern is accepted).
6. Write the binding into the agent's `metadata.teammate.t3` (revision 1) and
   read it back; issue one keyed on_demand wake and verify: one succeeded run,
   one thread turn, comment == thread answer, issue → in_review.

## ATTACK (kimi-k3.1-pro adversarial pass)

One attack child was briefed to find a sequence of wakes, kills and restarts
that sends the task twice, posts the result twice, or leaks the token.
<!-- ATTACK_RESULTS -->
