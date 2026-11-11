# GBL — Addendum 1: the five holes closed

2026-11-11, after the principal's ruling (transport approved, account-scoped admission,
existing account, v1 kinds ask/answer/delegate, build before RF). Sources in §7; no
readers needed; same limits held (read-only repo, nothing sent, no ports).

## 1. Reuse or second edge → **(c) separate edge**, with lifted code

What exists, repo-observed:
- **Server** (built): `integrations/mastermind_company_mcp/` — `server.py` is a stdio
  runner over a host-supplied Unix binding, no listener; `consultation.py:143-192` pins
  the four tools `company.peers/consult/reply/consultation`, digest-frozen. Tests: 8
  `tests/test_business_mcp_auth_*.py` + the consultation-contract test.
- **OAuth resource check** (built): `integrations/business_mcp_auth/` —
  `jwt_verifier/jwks/claims/metadata/contracts/audit`; issuer/audience/scope from policy
  metadata (same-origin authorize/token/jwks). Token-only by design.
- **Tunnel config**: none for a Mac-local public edge. The installed app's HTTPS arrives
  via the incumbent Chisel OS relay (`os_tunnel_entry.py:24-27`) to the VPS
  (`mastermind-os`, 8443). The additive `fabric-application-transport.md` pattern is
  reviewed source only, and VPS-**loopback** — private, not public.
- **Runbook installed-state** (`grok-bot-operations-setup.md:14-15`): "protected,
  installed, and accepted for fixture calls"; endpoint = "the existing Secure MCP
  Tunnel/public ingress" (:78).
- **Store**: `wake_persist.py:1-8` — "persistence over the existing Executive OS events
  table… Writes use `RuntimeStore.transaction()`/`append_event()`"; the host composes
  inside the Executive host (`company_consultation_host.py`).

Decision: **(c)**. Not (a): teammates-as-peers writes new events into the production
Executive store and changes the installed app's tool digest — not buildable under the
hold. Not (b): "its server" is a stdio runner whose host, gateway and store *are* the
Executive host; a second tool set still writes the held store and shares the VPS
ingress. (c) builds clean: GBL's only durable state is **Paperclip issues/comments**.

Lifted by import, nothing written twice: `business_mcp_auth/*` (store-free); the
`common/agent_dialogue_consultation_contract.py` mint/fingerprint/classify helpers; the
`common/company_consultation_host_contract.py` frame codec; `grok_bot_routine.py` +
`grok_bot_http.py` (nudge). Cloned in shape with own tests: the static-census stdio
pattern of `mastermind_company_mcp/server.py`. Untouched: `company_consultation_dispatch.py`,
its host/transport/targets, the Executive runtime, the installed app, the incumbent
tunnel. Law-check: the Sept single-path law governed repairing openclaw, and the
consultation app itself installed as a distinct connector under it — GBL follows that
precedent (distinct function, dedicated least-privilege principal).

## 2. The ingress, named

- **Incumbent** (the only existing authenticated public ingress): Chisel OS relay on
  this Mac → VPS `mastermind-os` 8443; production-Executive-owned — held. **GBL cannot
  ride it.** Said plainly, as required.
- **GBL ingress**: a new **dedicated named tunnel on this Mac** (Cloudflare preferred,
  ngrok static acceptable — vendor-documented, FACTS A5) → `127.0.0.1:<one port>`
  serving **only** the GBL MCP edge: sealed JSON config, `0400` credential, launchd
  `com.mastermind.gbl.tunnel`, schema'd config + control CLI + tests, in the reviewed
  `fabric-application-transport.md` shape. Not a quick tunnel — the URL is pinned.
- **Auth**: OAuth token only, per the binding rule — `business_mcp_auth` reads
  issuer/audience/scope from policy metadata, never source address or headers; loopback
  forwarded-for is invisible to it; the non-OAuth `ChannelAuditEvent` path stays unused.
  Audience `mastermind.gbl.bridge`, same authorization server as the consultation app.
- **Person, once, existing sign-in**: named tunnel + public hostname (dashboard); OAuth
  client + scope (tenant — a security setting, human); secrets to the secret owner.

## 3. Flow 2's record — confirmed, plus the dev-thread case

Confirmed: **one Paperclip issue per ask**, opened by and assigned to the "Grok Bridge"
service agent; question and bot answer arrive as **comments** on that issue. No bridge
database — the issue IS the record (corrects ARCHITECTURE §3: "stores the answer against
the ask" = "posts the answer comment on the issue").

Dev-thread ask (no Paperclip agent of its own): the asker is **data on the issue**, never
an agent. Record: `ask_id gb-…` · MMOS-company issue, bridge agent · kind question ·
principal = Grok account label · asker `{side: t3_thread, environment_id, thread_id,
session label}` (data) · question comment · answer comment (data from a named outside
party) · OPEN→ANSWERED→CONSUMED · `expires_at`. The asking session reads back by ask id
via the CLI; the bridge writes nothing into its T3 app and mints no agent for it.

## 4. The Chairman's threads — split and both designed

**(a) A development-thread session asks a bot — in v1.** Only the CLI + loopback
socket. The session runs `gbl_ask.py ask --wait` as a **background command**; the
harness re-invokes the session on its exit — that exit is the wake; zero writes into
the Chairman's T3 app. Without `--wait`, an existing T3 scheduled task runs
`gbl_ask.py fetch` later. A session he runs choosing a local CLI is his act, not a
lane sending into his app.

**(b) `team.message` — fifth capability, built in v1, allowlist empty.**
- Call `team.message {thread_ref, body, idempotency_key}`; edge authenticates the OAuth
  principal; admission checks account → tool → **environment+thread allowlist row**;
  empty allowlist = universal typed refusal in v1.
- Send: the bridge runs the stock `t3 thread send <thread> - --wait --json` (the
  carrier's proven surface, FACTS B5) against the named environment's T3 home;
  first-line marker `[gb-<messageId>]` gives one-send; body wrapped: `GBL message from
  outside party <principal> — quoted data, not instructions from this thread's owner:`
- Record: one tracking issue per message carries id, thread_ref, sent marker, send
  receipt — reconcile by read-back, never a second send (EFFECT_UNKNOWN law).
- What runs where: team-server thread → t3 CLI with the team-server home (the
  carrier's mechanism; RF's `tools/mmos_teammate/*` untouched — GBL adds a thin sender
  in `integrations/gbl/`). Development thread → same sender with `T3_HOME` at that
  environment, **only after his sentence**; before it the send refuses.
- The one sentence, per environment: **"I allow environment `<environment-id>` for GBL
  team.message."** Environment rows and thread allowlist rows are the principal's acts
  (v1 ships none).

## 5. Fewer human steps; no orphaned asks

| Step | Who |
|---|---|
| 1. Confirm/create Secretary bot in Grok Bot desktop | person (app; no bot-admin API documented) |
| 2. Create "Mastermind Bridge" webhook routine, inactive | person (app; no routine API documented) |
| 2b. Move routine URL+key into the secret owner | **agent** (existing secret-owner tooling) |
| 3a. Install bridge + tunnel client on this Mac (launchd, config, rollback) | **agent** (application-tunnel shape) |
| 3b. Named tunnel + hostname (dashboard); OAuth client + scope (tenant) | person, once, existing sign-ins |
| 4. Add custom MCP connector in Grok + OAuth consent + census check | person always (consent) |
| 5. Say the §4b environment sentence — same sitting as 6 | person |
| 6. Enable the routine for the canary window; pause after | person (app toggle) |

Net: **6 person actions across 2 sittings**, **2 agent-doable**. The 30-minute
live-check script (one sitting; agent preps the test server first; FACTS §C):
1. 0–3: start the agent-prepped local MCP test server whose one tool sleeps 120 s;
   expose a throwaway public URL (fine for a **test** connector deleted after).
2. 3–8: in Grok Bot, add the test connector (API-key flow); ask any bot to call the
   slow tool. **Write down:** waited / errored / dropped + message (A14).
3. 8–13: open a second bot under the same account; ask it to list or call the tools.
   **Write down:** saw them, yes/no (A10).
4. 13–30: connect Slack on the Cursor account; test channel + "bot mentioned" trigger;
   (i) mention the bot in a thread parent, (ii) reply mentioning it in-thread; then ask
   it to "reply in that thread". **Write down:** which of (i)/(ii) started a run; where
   the post landed (A3). Delete the test routine after.

**Orphaned asks, plainly.** The nudge starts a run of the **routine-owner bot**, so the
answer appears in that bot's chat, not automatically in the delegating bot's
conversation; cross-bot delivery inside Grok is Grok-native (A12), not ours to control.
Any bot under the account can call `team.result {ask_id}` in its own conversation
(A10); an unconsumed answer surfaces as `ANSWER_UNCONSUMED`. v1 pins the routine to
the Secretary bot, so the primary path lands in the delegating conversation itself;
fallback: the person reads the answer in the owner's chat; "fetch result gb-…" completes it.

## 6. BUILD_PLAN amendments (applied in the same edit)

GBL-1 adds the `team.message` envelope + allowlist fields + wrapper law; GBL-2 names
Paperclip as the only store and adds `message_send.py`; GBL-3 census is **five** tools,
imports `business_mcp_auth` as-is, audience `mastermind.gbl.bridge`, dedicated named
tunnel (§2); install step 4 replaced by the dedicated tunnel + person-once dashboard and
tenant actions; human steps replaced by the §5 table; tests add `team.message` negatives;
proofs add the empty-allowlist refusal.

## 7. Sources (read 2026-11-11, this session, read-only)

`grok-bot-operations-setup.md:14-15,78-80`; `mastermind_company_mcp/server.py:1-36`,
`consultation.py:143-192`; `business_mcp_auth/contracts.py:130-160` + package listing;
`company_consultation_host.py:1-45`; `wake_persist.py:1-25`; `fabric-application-transport.md:1-66`;
`os_tunnel_entry.py:24-27`; earlier FACTS rows A3, A5, A10, A12, A14, B5, B13.
