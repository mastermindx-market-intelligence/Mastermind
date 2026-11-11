# GBL — Architecture: Grok Bot ↔ Mastermind OS two-way link

Lane GBL, 2026-11-11. Design only. Facts cited as `FACTS.md A#` / `B#` rows.
Law base: reuse-first, no new registry/queue/lifecycle/store; Executive OS owns lifecycle;
Paperclip owns work; the carrier owns every conversation edge; the Chairman's T3 app is untouched.

## 1. Recommendation (ten lines)

1. Build one Mastermind-owned **Grok Bridge**: a small authenticated MCP app plus a loopback
   service, both reusing existing owners. It is the only writer toward T3 threads and the only
   reader of Grok wake nudges.
2. Grok Bot reaches it through a **custom MCP connector** (documented, A4/A5) on our existing
   authenticated public ingress, under a dedicated least-privilege OAuth principal.
3. Delegating a job = the bridge **creates and assigns a Paperclip issue** for the named
   teammate. The existing wake carrier then does the work and posts the result on the issue (B5/B6).
4. When the result lands, the bridge sends **one opaque webhook nudge** to the bot's routine
   (A6/A7) through the existing `GrokBotRoutineWakeDispatcher` (B3).
5. The bot's run fetches the result with an authenticated MCP read. The answer appears in the
   same bot conversation. No prose ever crosses the webhook.
6. Questions (not jobs) ride the same loop as bounded asks in RF's shape (B7).
7. Outbound (MMOS asks Grok): a local CLI posts the ask to the loopback bridge; bridge nudges
   the bot; the bot's run answers through an MCP tool; the CLI reads it back into the thread.
8. **Slack is deferred.** Its thread semantics are unverified (A3), our side has no inbound
   push (B14), and Slack cannot prove which bot spoke (A1/A10).
9. The Chairman's T3 app threads use the same carrier command, but stay refused until he names
   an environment (B8/B9). One sentence from him per project.
10. Admission is **account-scoped, never bot-scoped** (A10): the spec names which principals,
    which targets, which job kinds, what rate. Everything else refuses.

## 2. Options compared

| | (A) Direct MCP, synchronous | (B) Slack thread relay | (C) Webhook nudge + MCP substance (async) |
|---|---|---|---|
| Grok-side primitive | custom MCP connector (A4/A5) | Slack app + Slack trigger routine (A1/A2) | webhook routine (A6/A7) **and** the same MCP connector |
| Mastermind-side reuse | new MCP edge; carrier | existing Slack relay outbound only (B14) | existing wake dispatcher (B3) + carrier (B5) + consultation shapes (B13) |
| Identity at the boundary | OAuth principal — strong | "the connected Slack user" — weak, cannot name the bot (A1) | OAuth principal on substance; bearer key on nudge carries no substance |
| Two-way thread semantics | tool call/response — exact | **unverified** whether thread replies fire triggers or bots can reply into threads (A3) | exact: ask id in, answer out |
| Latency/cost | holds a bot run for the whole job; timeout behavior unverified (A14); burns weekly usage while waiting (A9) | each hop is a bot run; busy-channel warning already documented (A2) | one short run per direction; waits happen outside Grok (free) |
| Inbound push to Grok | none needed (bot initiates) | mention triggers a run | webhook POST — documented, 200=started (A7) |
| Inbound to Mastermind | MCP call (pull) | our relay has **no push**, polls only inside a live session (B14) | MCP call (pull); nudge only starts the pull |
| New human ceremony | connector + OAuth (documented flow) | Chairman Agent-OS decision + Slack-admin scope ceremony **before anything starts** (B14), plus Slack connect on the Cursor account | same connector ceremony as A, plus one routine |
| Failure honesty | a hung call is opaque to us | a reply nobody polled is invisible | states are typed end to end (B13 pattern) |
| Verdict | right channel, wrong timing | rejected for v1; revisit as a *human-visible projection* later | **chosen** — C's timing on A's wire; A's synchronous shape kept only for cheap reads |

Why hybrid and not pure C: cheap synchronous reads (`team.status`, `team.result` when already
available) are safe under any A14 outcome; only *waiting* moves out of the tool call.

What would change the recommendation:
- If A3's live check shows threads fire triggers and bots reply in threads **and** the Chairman
  wants the dialogue visible in Slack, add B later as a *projection* of the same ask records —
  never as the carrier of record.
- If A14 shows Grok tolerates multi-minute tool calls, small asks may answer synchronously; the
  ask records stay unchanged either way.
- If the webhook routine proves unable to carry a *specific* conversation pointer (run history
  lands in one bot chat), nothing changes: ask ids already carry the pointer.

## 3. The chosen design

Components (all new code in `integrations/gbl/` and `tools/gbl/`; all durable state in
existing owners):

- **Bridge service** (loopback, AF_UNIX socket, peer-uid check — the Slack relay service
  pattern, B14): owns ask records, admission limits, the deterministic id mint, the nudge
  sender. No T3 credential, no Grok secret in argv.
- **MCP edge** (`integrations/gbl/mcp_server.py`): static four-tool census behind the existing
  authenticated public ingress; OAuth resource-server pattern with exact scope
  `mastermind.gbl.bridge`; per-principal admission table. Tools: `team.delegate`,
  `team.result`, `team.question`, `team.answer`. (Names final at build; the census is frozen
  and digest-pinned like every Mastermind MCP surface, B11.)
- **Ask record**: the Paperclip issue *is* the record (B6). Ask id `gb-<32hex>` = deterministic
  mint over (principal, target, idempotency key) — the consultation mint law (B13). Marker
  `[gb-<askId>]` in the issue body; the TeamLinkMessage.v1 envelope (B15) is embedded for
  correlation fields. No bridge-local database.
- **Bridge service agent**: one Paperclip agent ("Grok Bridge") that owns mirrored issues as
  asker, so the existing "asked-for work returned" wake reaches the bridge (B6). If the
  installed Paperclip build lacks that wake, the lane reports it with evidence and uses the
  assignment wake on a tracking issue instead — decided in lane, not designed around silently.
- **Nudge sender**: reuses `GrokBotRoutineWakeDispatcher` + `grok_bot_http.py` (B3/B13).
  Payload `{schema:"mastermind.gbl.wake.v1", ask_id, state}` — nothing else (the Sept law: no
  prose, no secrets across the webhook; B11).
- **CLI** (`tools/gbl/gbl_ask.py`): `ask`, `status`, `fetch` — for any local session
  (team-server teammates, the Chairman's app sessions after his word, B9).

### Flow 1 — Grok's Secretary delegates a job to the MMOS Secretary

1. In a Grok Bot run, the Secretary bot calls `team.delegate {target:"secretary", title,
   brief, idempotency_key}` through the connected MCP tool.
2. The MCP edge authenticates the OAuth principal (the Cursor account, A10) and checks the
   admission table: principal allowed? target on the teammate allowlist? job kind allowed?
   under the asks/hour ceiling? Any refusal is typed and closed (the B13 envelope shape).
3. The bridge mints `gb-<32hex>` from (principal, target, idempotency_key). Same key + same
   content returns the same ask (`IDEMPOTENT`); changed content → `CONFLICT` (B13 law).
4. The bridge creates a Paperclip issue in the MMOS company, assigns it to the Secretary
   teammate agent, body = marker + TeamLink correlation + the brief as **data**.
5. Paperclip's assignment automation wakes the teammate's process adapter; the carrier sends
   one message to the bound T3 primary thread (`t3 thread send --wait --json`), marker
   discipline holding one-send (B5). The teammate's turn runs.
6. The carrier posts the answer as an issue comment and sets the issue `in_review` (B5/B6).
7. Paperclip wakes the asker — the bridge service agent — because asked-for work returned.
8. The bridge sends one opaque nudge to the bot's routine URL: 200 = run started (A7). A
   timeout after submission is `WakeEffectUnknown` on that exact nudge: reconcile by run
   history, never resend (B3).
9. The bot's run calls `team.result {ask_id}`. The edge re-authenticates, checks the ask
   belongs to this principal, returns the bounded answer + issue ref.
10. The bot reports in its own conversation. The ask is consumed. If no fetch comes, the
    result waits on the issue; one re-nudge after a cooldown, then it surfaces in "Needs you"
    (the carrier's pending-confirmation pattern, B5) — honest `ANSWER_UNCONSUMED`, no storm.
11. Follow-up: a new ask with a new key, old correlation copied (`followup_requires_new_key`, B15).

### Flow 2 — an MMOS session asks a Grok bot

1. A session runs `gbl_ask.py ask --bot <account-label> --question "..." --wait` (or without
   `--wait`, then `fetch` later). The CLI talks to the loopback socket; peer-uid admits it.
2. The bridge records the ask (same mint, asker = calling session's identity) and POSTs one
   nudge `{ask_id, state:"QUESTION_AVAILABLE"}` to that account's routine.
3. 200 → the bot's run starts → calls `team.question {ask_id}` → gets the question (bounded,
   ≤16k chars, consultation budget shape B1) → does its work.
4. The bot calls `team.answer {ask_id, answer, idempotency_key}`. Answer id is minted
   deterministically; a re-post with the same key is the same answer (B13 law).
5. The bridge stores the answer against the ask (state `ANSWERED`). The waiting CLI returns it
   into the asking thread; a non-waiting session's scheduled task or next `fetch` picks it up
   (existing T3 scheduled tasks, B9).
6. Terminal edge recorded on the ask. Expiry (`expires_at`, TeamLink law B15) returns `EXPIRED`,
   never silence.

## 4. The nine questions

**1. Transport.** Chosen: C over A's wire (§2). One MCP connector carries all substance both
directions; one webhook routine is the only push toward Grok; the loopback socket serves local
sessions. Slack deferred with named re-openers (§2).

**2. Addressing.** A bot names: a **teammate** by Paperclip agent slug (the teammate record,
B4) — the bridge resolves it to the bound thread, the bot never sees thread ids; a **team
thread** only by ask id (answers/follow-ups), never by raw address; a **project** by Paperclip
project id on delegate; a **T3 development thread** by full thread id **and** environment id,
where the environment allowlist starts with the team server only (B8). Mastermind names a Grok
account by its principal label + routine handle from the secret owner (B3). No new registry:
Paperclip rows, T3 settings, the existing secret owner and the admission table carry every
identity (B12).

**3. Job vs message.** "Grok's Secretary delegates to the MMOS Secretary" is a **Paperclip
task**: issue → assignment wake → carrier → T3 turn → result on issue (B6 law). A **message**
(question) is an ask in RF's bounded shape — no chaining, asked party cannot re-ask, at most
three asks per issue (B7) — implemented as the same ask record with kind `question` answered
by a turn of the teammate's thread, not a new mechanism. Results return per Flow 1 steps 7-10.
Follow-ups are new asks with copied correlation (B15).

**4. Return path.** The mapping outbound→owner is the ask record: `ask_id ↔ Paperclip issue ↔
principal`, stored in the issue body marker + the issue's own lineage (the issue is the
record; no bridge database). Owner gone/busy/elsewhere: a **Grok owner** is the account's
routine, not a conversation — any run of that account fetches by ask id; routine paused →
honest `ANSWER_UNCONSUMED` in "Needs you". An **MMOS owner** thread gone → the answer waits on
the ask until expiry, then `EXPIRED`; busy → `--wait` returns "not yet", the session fetches
later. Another server → each environment runs its own bridge; asks never cross servers; a
foreign ask id is refused.

**5. Admission and identity.** Who may put text into which thread: **only the bridge writes to
T3 threads, only via the carrier**; bots address targets, never threads; teammates receive ask
content as quoted data. Proven by: the MCP edge's OAuth principal + scope + admission table
(platform-proven identity, A11: nothing else is provable); the loopback socket's peer-uid
(process identity, B14 pattern); the webhook's bearer key proves the *channel* only — a nudge
carries zero substance, so a stolen key can at worst start a run that fetches nothing (the
Sept law, B11). Loopback TCP and request headers are never admission. Untrusted text: Slack
messages, bot replies, issue text, page text are data; the bridge never executes them; the
admission table lives server-side and model prose cannot widen it (B11). Limits the spec
names: which principals, which teammate targets, which job kinds (v1: ask, answer, delegate;
no source writes, no installs, no spend), asks/hour per principal, payload caps (16k/16k/32k,
B1 budget), one routine per account. Credentials (OAuth client secret, webhook key, signing
secrets) are 0600 in the existing secret owner, never printed, never in a prompt or thread.

**6. Exactly-once and uncertainty.** Idempotency key per message at every write: delegate
(key→ask id mint), answer (key→answer id), nudge (ask id + state, naturally idempotent
because attention-only). A retry of `team.delegate` with the same key returns the same ask
(`IDEMPOTENT`), with changed content `CONFLICT`. `EFFECT_UNKNOWN` per hop: issue-create
timeout → reconcile by deterministic ask id read-back before any retry; nudge POST timeout →
`WakeEffectUnknown`, run-history reconcile, never resend (B3); carrier→T3 → existing marker
discipline (B5); `team.answer` timeout → re-post same key, dedup by answer id. A redelivered
webhook cannot start a second job: nudges carry only `ask_id`; **job creation exists solely
behind the authenticated MCP tool with its own dedupe** — a nudge without a matching ask
returns `ASK_NOT_FOUND` and performs nothing. (In a future Slack projection, a redelivered
Slack event would likewise start at most a fetch-read.)

**7. Human-only, once, in order (batched).** (1) In Grok Bot desktop: confirm/create the
Secretary bot; local execution off; no share link. (2) In Grok Bot: create the "Mastermind
Bridge" webhook routine, keep inactive; move URL+key into the existing secret owner. (3)
Principal: install the bridge MCP app behind the existing authenticated ingress with its
OAuth client (existing runbook path; rollback written). (4) In Grok Bot: add the custom MCP
connector to the bridge URL; complete OAuth consent for the dedicated principal; verify the
tool census is exactly four. (5) Chairman: name the environment(s) the bridge may touch; his
own T3 app stays refused by default. (6) Enable the routine for the canary window; pause
after. — Slack steps (connect Slack on the Cursor account; Slack-admin scope ceremony) exist
only if B is adopted later.

**8. Cost and limits.** Grok side: one weekly usage pool shared with Cursor/Grok apps, metered
on the Cursor account (A9); routines 300/h total, 200/h each, 50/bot (A8); no auto-retry
(A7). Bridge ceilings: 20 asks/hour/principal, 3 re-nudges per ask, one routine per account,
16k payloads. A flood hits a typed `RATE_LIMITED`; extra delegation targets queue as ordinary
Paperclip issues (natural backpressure — issues wait, zero bot runs). A bot cannot flood a
teammate thread: bots never write threads; one issue = one carrier send (B5). Every nudge is
a billable run, so the design minimizes runs: one per direction per ask.

**9. First proofs.** Proof 1 (dev team server + dev Paperclip, FACTS B8): one real
`team.delegate` from a Grok run becomes one issue for the dev Secretary teammate, one carrier
send, one T3 turn, one result comment; the nudge fires; the bot's run fetches via
`team.result` and the answer lands in that bot conversation. Negatives pinned by test:
duplicate key, wrong principal, unknown target, disallowed kind, over-ceiling, paused routine,
oversized payload, redelivered nudge. Proof 2: from a team-server session, `gbl_ask.py ask
--wait` → nudge → bot run → `team.question`/`team.answer` → CLI readback in the asking
thread; plus a follow-up ask (new key, copied correlation) and an expiry case.

## 5. What is not solved

- A3 and A14 are unverified (FACTS §C lists the two live checks). Neither blocks this design;
  both bound it.
- Per-bot authority is impossible today (A10): all bots under the connected account share
  admission. If the Chairman needs "only the Secretary bot may delegate", that is a Grok
  platform fact we cannot mint; the account allowlist is the real boundary.
- "Any bot accesses any team thread" is deliberately narrowed to named teammates and ask ids.
  Arbitrary-thread addressing is a later admission decision, not a missing mechanism.
- The Chairman's own T3 app threads: same command, zero code difference, but nothing may
  touch them until he names that environment (B8). Not designed around; simply refused.
- RF's ask/message contract is not yet installed on the production carrier (B7); until it is,
  the bridge ships delegate + result only, and asks wait for RF's install.
- Whether the installed Paperclip build wakes the asker on return is unverified in lane (B6);
  the fallback (tracking-issue assignment wake) is named, and the lane reports evidence before
  building anything in its place (plan §10 law).
- Latency: worst case one cooldown re-nudge cycle; no push into a *specific* Grok conversation
  exists in the product (A6/A7) — the run lands in the routine owner's chat. Acceptable for
  delegation; noted honestly.
- Cost of the fetch discipline (each nudge is a run) is bounded by ceilings but only measured
  in the canary.

— end of ARCHITECTURE.md —
