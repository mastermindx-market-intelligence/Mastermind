# GBL — Build plan

Lane GBL, 2026-11-11. Follows `ARCHITECTURE.md` (same evidence dir). Programme rules apply:
tests first, one writer per file, blind DeepSeek panel on critical surfaces (PROGRAM_PLAN_V4
§26 ruling: one narrow question each, blind, with probes), installs reserved to the principal,
 Chairman-only steps batched and asked once.

## Lanes, files, ownership

| Lane | Owns (files, one writer each) | Depends on | Model |
|---|---|---|---|
| GBL-1 Contract | `common/gbl_contract.py` (wake/nudge schemas `mastermind.gbl.wake.v1`, ask envelope embedding `TeamLinkMessage.v1` correlation, `team.message` envelope + environment/thread allowlist fields + quoted-data wrapper law, states, budget maxima) + `tests/common/gbl_contract_test.py` | none | GLM |
| GBL-2 Bridge core | `integrations/gbl/bridge_service.py` (socket service, ask records over Paperclip — Paperclip issues/comments are the ONLY store, ADDENDUM §1/§3, id mint, admission table, ceilings) + `integrations/gbl/nudge.py` (wraps `GrokBotRoutineWakeDispatcher` + `grok_bot_http.py`) + `integrations/gbl/message_send.py` (thin per-environment `team.message` sender via stock `t3 thread send`, marker `[gb-<id>]`; RF's `tools/mmos_teammate/*` untouched) + tests | GBL-1 | GLM |
| GBL-3 MCP edge | `integrations/gbl/mcp_server.py` (static **five**-tool census incl. `team.message`, digest-pinned schemas; imports `business_mcp_auth` as-is — jwt/jwks/claims/metadata/audit; audience `mastermind.gbl.bridge`; token-only, never source address) + `integrations/gbl/admission.py` (principal→targets→kinds→rates→per-thread allowlist, ships empty) + tests | GBL-1, GBL-2 | GLM |
| GBL-4 CLI + service agent | `tools/gbl/gbl_ask.py` (ask/status/fetch; `--wait`) + bridge service-agent roster entry + `integrations/gbl/paperclip_client.py` (issue create/assign/read as the service agent) + tests | GBL-2 | GLM |
| GBL-5 Ask/return wiring | the asker-side wake edge on the carrier path (`tools/mmos_teammate/` adjacency — **RF owns those files**; GBL-5 adds only `integrations/gbl/ask_return.py` and, if the Paperclip "asked-for work returned" wake is missing, reports evidence per plan §10 instead of editing RF's files) | GBL-2, GBL-4, RF install state | GLM |

One writer per file is absolute: `tools/mmos_teammate/*` stay RF's; `control_plane/*` and
`common/agent_dialogue_*` are untouched (GBL-1 only adds a new module). No file this programme
already assigns to another lane is edited by a GBL lane.

## Tests first (each lane's first commit is a failing test)

- GBL-1: mint determinism (same principal+target+key → same ask id; changed content →
  `CONFLICT`); wake payload closed-key check (only `schema`, `ask_id`, `state`); budget
  maxima; expiry math; `followup_requires_new_key`.
- GBL-2: socket admits peer-uid only; admission refusals (unknown principal/target/kind,
  over-ceiling → `RATE_LIMITED`); issue-create timeout → reconcile-by-read-back, never a
  second create (EFFECT_UNKNOWN law); nudge redelivery → no second job (`ASK_NOT_FOUND`
  no-op); `ANSWER_UNCONSUMED` surfacing; one re-nudge per cooldown.
- GBL-3: wrong scope/revoked principal refused before dispatch; tool census exactly five,
  digest-pinned; caller cannot override admission fields; oversized payload (`FRAME_TOO_LARGE`);
  no dynamic tool registration. `team.message` negatives: empty allowlist → typed refusal;
  thread not listed → refusal; redelivery → exactly one send (marker), reconcile by
  read-back only (ADDENDUM §4b).
- GBL-4: CLI `--wait` returns the answer or "not yet"; asker identity recorded; token hygiene
  (no secret in argv/prompts/logs); `EXPIRED` on stale fetch.
- GBL-5: asker wake reaches the bridge exactly once per issue return; duplicate wake no-ops;
  missing-wake evidence file produced if the installed build lacks the edge.

## Critical surfaces → blind panel before install

Per §26: a panel of DeepSeek reviewers, one narrow question each, blind to each other and to
the lane's own attack round, each with probes; Kimi only if a GLM child failed twice.

1. **The MCP edge + admission table** (GBL-3) — question 1 (whose words does this code trust,
   and can the wrong ones win) and question 3 (every state the record can be in).
2. **The nudge sender + message sender** (GBL-2 `nudge.py`, `message_send.py`) — question 2
   (what happens when each call fails, times out, or succeeds without its answer arriving);
   for `message_send.py` also question 1 (can any text reach a thread the allowlist did not
   name; is it always quoted data).
3. **The loopback socket door + CLI** (GBL-4) — question 1 (local privilege: can a process
   that should not ask, ask) and question 3.
4. **The Paperclip write path** (GBL-4 `paperclip_client.py`) — question 4 (installation,
   cut-over, rollback) and question 2.
5. **The ask/return edge** (GBL-5) — question 3, including the missing-wake fallback.

## Install steps reserved to the principal (each with rollback, no teammate run live)

1. Merge GBL-1..GBL-5 branches after their panels; the deputy merges, per its standing brief.
2. Install the bridge service on the team-server host (launchd job, loopback socket).
3. Create the "Grok Bridge" service agent in the production Paperclip; fence its old
   heartbeat path if one exists (the T2 six-step pattern).
4. Install the MCP edge behind a **new dedicated named tunnel on this Mac** (Cloudflare
   preferred / ngrok static acceptable; launchd `com.mastermind.gbl.tunnel`, sealed config,
   `0400` credential, control CLI + tests in the `fabric-application-transport.md` shape;
   terminates at one loopback port serving only this edge). The incumbent Chisel/OS relay
   → VPS 8443 is held by this programme and is NOT used (ADDENDUM §2). Person-once, before
   this step: create the tunnel + public hostname (provider dashboard) and the OAuth
   client + scope `mastermind.gbl.bridge` (authorization-server tenant) with existing
   sign-ins; hand secrets to the existing secret owner. Census check: exactly five tools.
5. Enable one SessionTarget row (`grok-bot` surface, `gbl-webhook` transport instance of the
   existing `grok-computer` family) — the two-key arming law (FACTS B2).
6. Enable the routine for the canary window only; pause after (runbook §9 law).

## Human-only steps (reclassified per ADDENDUM §5: 6 person actions in 2 sittings, 2 agent-doable)

Person, in the Grok Bot app (one sitting):
1. Confirm/create the Secretary bot; local execution off; no share link.
2. Create the "Mastermind Bridge" webhook routine (inactive); hand URL+key over for 2b.
3. Add the custom-MCP connector to the bridge URL; complete OAuth consent; census = five.
4. Say the environment sentence ("I allow environment `<id>` for GBL team.message") and
   enable the routine for the canary window — same sitting; pause after.

Person, once, at a keyboard with existing sign-ins (one sitting):
5. Provider dashboard: create the named tunnel + public hostname.
6. Authorization-server tenant: create the OAuth client + scope (security-setting change).

Agent-doable (no new authority): 2b — move routine URL+key into the existing secret owner;
3a — install bridge + tunnel client on this Mac (launchd, config, rollback).
The 30-minute live-check script (A14 → A10 → A3) is in ADDENDUM §5, one sitting, with the
three lines to write down.

## Order

GBL-1 → GBL-2 → (GBL-3 ∥ GBL-4) → GBL-5 → panels → principal installs → proofs 1 and 2
(ARCHITECTURE §4.9) on dev, then one teammate at a time on the real server (the RF pattern),
plus the empty-allowlist `team.message` refusal proof (ADDENDUM §6).

## Explicitly not in this build

Slack option B and its ceremonies; any write into the Chairman's T3 app (team.message ships
with an EMPTY allowlist; switching a thread on is the principal's act); any use of the
incumbent Chisel/OS relay or the VPS; any write to the Executive OS events store (GBL's only
store is Paperclip, ADDENDUM §1); any new queue, registry, retry loop or store; any change
to `tools/mmos_teammate/*`, TeamLink PR #2419, the Executive MCP five-tool app, or the
consultation v1/v2/v3 contracts.
