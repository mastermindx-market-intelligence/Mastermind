# Executive OS Personal-Pro C1 — Production SOL_STATE Read Lane Implementation Commission

**Date:** 2026-08-25  
**Commissioner:** Sol, AI CEO  
**Chairman authority:** current directive to finish Autonomy V1 rapidly with Sol program ownership and reduced permission loops  
**Operation key:** `PERSONAL-PRO-C1-SOL-STATE-20260825`  
**Repository:** `mastermindx-market-intelligence/Mastermind` only  
**Carrier:** branch `sol/personal-pro-c1-sol-state-production-20260825` / its draft PR  
**Protected pickup / Skillpack basis:** `cdfecc6f6b382862238c15fe1d5bd646eb62213c`  
**Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1, loaded atomically from that exact commit  
**Linear projection:** MAS-109  
**Controlling source law:** `research/EXECUTIVE_OS_PERSONAL_PRO_RELAY_STATE_TRANSPORT_AMENDMENT_2026-08-20.md`

---

## 0. Observable mission

Make the already-built development-unarmed Executive hot-state + `MMX/SOL_STATE_V1` publisher a real production **read-only** Personal-Pro surface:

> the dedicated Relay service reads the existing CeoIngress state frame, maintains exactly one current Relay-bot-authored `MMX/SOL_STATE_V1` message in private `#sol-runtime`, all three Personal-Pro Sol seats can read/recover it, stale/unavailable Executive state visibly degrades, and restart/update/ACK-loss recovery creates no duplicate state message or hidden cursor/database.

C1 stops there. It does **not** install inbound Socket Mode command handling or make any CEO write path live.

---

## 1. Why this matters

B2 cannot safely accept a modifying Personal-Pro CEO request until Sol has fresh canonical Executive grounding/readiness. Today the channel exists but has no Relay bot and no SOL_STATE publication, so the product shell is still blind.

C1 turns the existing state projection into one useful machine/human capability:

```text
existing dedicated CeoIngress state frame
        -> production Relay read client
        -> existing SolStatePublisher
        -> one private #sol-runtime state message
        -> all three Personal-Pro Sol seats can read current/stale/degraded truth
```

No new lifecycle authority is required.

---

## 2. Authority / precedence

Use, in descending order:

1. current protected Sol Skillpack at the pickup above;
2. `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`;
3. `research/EXECUTIVE_OS_PERSONAL_PRO_RELAY_STATE_TRANSPORT_AMENDMENT_2026-08-20.md`;
4. accepted PR-A/R0/B1 CeoIngress/hot-state/publisher source law and landed implementation;
5. current `control_plane/executive_ceo_ingress.py`, `control_plane/executive_service.py`, `control_plane/executive_hot_state.py`, `common/executive_hot_state_contract.py`, and `integrations/slack_executive/sol_state.py`;
6. current host/launchd/bootstrap law under `ops/executive_os/`.

A newer protected security/ingress/service law landing during implementation returns to Sol before merge-through.

---

## 3. Verified current state

At commission time:

### Slack hot state

- private `#sol-runtime` exists as channel `C0BSGABKBFY`;
- current members are exactly Chairman + ChatGPT1 + ChatGPT2 + ChatGPT3;
- there is no Relay bot/app member;
- history contains membership events only; there is no `MMX/SOL_STATE_V1` message.

### Built code

The following are already merged and must be reused:

- `mastermind.executive_hot_state.v1` deterministic projector;
- the no-input `mastermind.executive_ceo_ingress_state.v1` frame on the existing dedicated CeoIngress boundary;
- `integrations/slack_executive.sol_state.SolStatePublisher` and its storeless one-message recovery/update law;
- strict `MMX/SOL_STATE_V1` wrapper, 4,500-byte bound, stale/degraded handling, `do_not_submit=true`, and `command_transport=NOT_INSTALLED`.

`sol_state.py` explicitly remains development-unarmed and has no real Slack client, token, app, principal or host service.

### Runtime dependency estate

- project already has hard runtime dependency `httpx>=0.27`;
- there is no hard `slack_sdk` dependency today;
- C1 is outbound Web API only, so it does not need to import Socket Mode/B2 merely to fetch private-channel history and create/update one message.

### Collision census

No open C1/SOL_STATE production branch/PR existed before this carrier was created. B2/C2 remain held. Browser B1 and CF2 touch disjoint authority/code paths.

---

## 4. Exact scope

Mastermind only.

Expected implementation surfaces, builder may use fewer:

- `integrations/slack_executive/` — one narrow real outbound Web API adapter for the existing `SlackStateClient` protocol;
- one focused Relay service/process composition module or script;
- `ops/executive_os/` — dedicated principal/bootstrap, root-owned config/secret path, launchd service and install/status helpers;
- tests for Slack adapter, state-read local client, service loop, restart/ACK-loss/degradation and host security;
- existing service config only where the dedicated CeoIngress state-reader peer must be admitted.

Do not widen:

- Executive SQLite schema;
- CeoIngress submit/status/state schemas;
- generic Operator socket authority;
- B2 inbound transport;
- Slack command discriminator/events;
- provider/worker credentials;
- Agent OS/GitHub/Linear mutation authority;
- ASD Agent Relay.

---

## 5. Explicit non-goals

C1 does not include:

- Socket Mode / WebSocket connection;
- inbound `EXECOS/CEO_REQUEST_V1` messages;
- `#ceo-control-room` command handling;
- Slack message receipts for writes;
- B2 history reconciliation/bridge epoch;
- worker execution, fan-out or provider routing;
- Agent Relay/ASD;
- broad Operator/MCP access;
- Control Room product redesign;
- browser automation;
- arbitrary Slack workspace/channel administration.

---

## 6. Production Relay principal and secret boundary

Use exactly one dedicated non-login service principal for the Executive SOL_STATE/CEO Relay family. For this implementation freeze the host short name as:

```text
_mastermind_sol_relay
```

Before creation, installer must refuse if the identity already exists with unexpected UID/GID/home/shell/groups; if an accepted existing equivalent Relay principal is discovered on the host, stop for Sol reconciliation rather than creating a duplicate.

The principal:

- is not Chairman/user/worker `_mastermind_exec`;
- is not a member of Codex worker groups;
- cannot read Executive SQLite directly;
- cannot connect to the broad Operator socket;
- may connect only to the dedicated CEO-facing local ingress/state listener required for C1;
- owns no GitHub/Linear/Agent OS/provider credential authority;
- has no interactive login shell.

### Token storage

The Slack bot token is never repository content, model-visible config, argv, environment, log or receipt.

Use one root-managed fixed secret file readable only by the Relay principal, with exact owner/type/mode/symlink/ACL checks before read. The installer/service docs may name the fixed path; they must never serialize the value.

Model/tests use fakes or inert placeholder files. Production token enrollment remains a native action-time credential ceremony and must not require pasting the token into chat.

---

## 7. Slack app/channel authority

C1 uses one dedicated Mastermind Executive Relay Slack app/bot. Do not reuse the S0 fixture or ASD Agent Relay.

Minimum C1 bot scopes:

```text
groups:history
chat:write
```

No DMs, files, admin, user impersonation or unrelated channel scopes.

Production config fixes:

```text
workspace: T0BRD2AQXQV
channel:   C0BSGABKBFY  (#sol-runtime)
bot user:  <native action-time verified Executive Relay bot user id>
```

The bot must be a member of `#sol-runtime`; after enrollment membership must be exactly Chairman + ChatGPT1/2/3 + Executive Relay bot. Any extra automated integration/principal is a production-proof failure.

The configured workspace/channel/bot identity is root-owned configuration, not request/model input.

---

## 8. Outbound Slack Web API adapter

Implement the existing `SlackStateClient` protocol only:

```text
fetch_history(channel_id, limit)
create_message(channel_id, text)
update_message(channel_id, message_ts, text)
```

Use the existing `httpx` dependency unless a concrete implementation falsifier requires another reviewed client.

Allowed Slack API methods are exactly the equivalents of:

```text
conversations.history
chat.postMessage
chat.update
```

No generic `api_call(method, payload)` is exposed above the private adapter.

Rules:

- fixed HTTPS Slack API origin only;
- bounded connect/read/write/overall timeouts;
- no redirects to foreign origins;
- strict successful JSON shape validation;
- author identity on returned message must resolve to the configured bot user;
- history result is `complete=true` only when the requested bounded window was completely traversed; if Slack indicates more history than the C1 bound permits, return incomplete and let `SolStatePublisher` fail closed;
- raw Slack response/error text is never forwarded to model-visible output/Executive Events;
- 429/network/auth failures become fixed adapter failure classifications and C1 degrades/fails closed according to publisher/service law;
- token never appears in exception text or HTTP debug logs.

C1 should not add `slack_sdk` just for convenience if the narrow `httpx` adapter suffices.

---

## 9. Dedicated Executive state reader

Implement one tiny local client for the existing dedicated CeoIngress state frame:

```json
{"schema":"mastermind.executive_ceo_ingress_state.v1"}
```

It must:

- connect only to the reviewed dedicated CEO-facing Unix listener/socket activated by the existing Executive service composition;
- send exactly the no-input state frame;
- bound request/response bytes and timeouts;
- parse/validate only the accepted state response/hot-state contract;
- never send submit/status or broad Operator commands;
- never open Executive SQLite or inspect Runtime paths directly;
- map local transport/refusal failures to `None`/fixed safe C1 state-read classification so publisher emits a degraded SOL_STATE rather than replaying stale green data.

If current host composition has not yet exposed the dedicated listener to the Relay principal, add the smallest peer-UID/config/install change under the existing dual-listener service law. Do not create another Executive service/listener.

---

## 10. Relay service loop

Create one long-lived C1 publisher process under `_mastermind_sol_relay`.

Engineering defaults remain source law:

```text
Executive poll:        30 s
semantic change:       publish immediately
unchanged heartbeat:   60 s
max Executive age:     120 s
history limit:         100 messages
SOL_STATE hard size:   4,500 UTF-8 bytes
```

Service startup:

1. validate root-owned config + token metadata without logging token;
2. validate principal/groups;
3. verify expected Slack workspace/bot identity through a safe native API identity call or equivalent bounded qualification;
4. recover exactly 0/1 active state message via existing `SolStatePublisher.recover()`;
5. read current Executive state;
6. publish current/degraded SOL_STATE;
7. enter bounded poll/heartbeat loop.

The service owns no database, message-ts file, cursor, queue or retry ledger.

### Update logic

- semantic hash changed -> publish immediately;
- unchanged semantic state -> heartbeat update no more often than the 60-second default;
- Executive read failure/stale/invalid -> overwrite with degraded document + `do_not_submit=true`;
- Slack publication failure -> state is not falsely refreshed; retry only under bounded non-modifying service policy after re-recovering when create effect may be unknown.

### Create effect unknown

The existing publisher already invalidates its in-memory create receipt on exception so a later create requires fresh history recovery. Preserve that exactly. A lost `chat.postMessage` reply may not create a second active state message.

---

## 11. Data / time / null / correction law

- Executive hot state is canonical runtime truth; Slack is only current transport projection.
- Relay wrapper clocks never refresh stale embedded Executive state.
- missing/unavailable state -> `executive=null`, explicit Relay degradation, `do_not_submit=true`.
- stale state over 120 s -> degraded; do not copy old OK content under a fresh timestamp.
- one active state message only; >1 exact bot+discriminator matches is `STATE_MESSAGE_AMBIGUOUS` and service refuses publication until corrected.
- message edits/deletes by humans do not mutate Executive state; if state message disappears, next bounded recovery may create one replacement.
- historical Slack content is never copied into a local persistence store.
- later B2/C2 may change `command_transport`/submit readiness through accepted source law; C1 itself keeps `command_transport=NOT_INSTALLED` and `do_not_submit=true`.

---

## 12. Deterministic vs model-generated behavior

All C1 behavior is deterministic first-party code.

No model decides:

- Slack workspace/channel/bot identity;
- state freshness;
- relay health;
- whether to submit;
- token/scopes;
- which Slack API method to call;
- Executive status;
- message dedupe/recovery.

Models only consume the final SOL_STATE as evidence later.

---

## 13. Failure states

At minimum distinguish/falsify:

```text
wrong relay principal / group drift
secret file missing/symlink/wrong owner/mode/ACL
wrong Slack workspace
wrong bot user
bot not a member of #sol-runtime
extra active SOL_STATE messages
history incomplete
Slack auth failure
Slack 429 / transport timeout
create effect unknown
update failure
CeoIngress socket unavailable
peer UID denied
invalid/oversize Executive state
stale Executive state
SOL_STATE oversize
service restart during create/update
unexpected channel membership/integration
```

None authorizes a second Relay app/principal, SQLite state store or fallback transport.

---

## 14. Ordered implementation sequence

1. Freeze exact changed files and principal/config paths in a short implementation plan; no architecture redesign.
2. Add pure strict `httpx` Slack adapter with fake transport tests, secret redlines and exact method/channel identity.
3. Add dedicated no-input CeoIngress state client + contract tests.
4. Add Relay config/principal/token-file validation and launchd service loop using existing `SolStatePublisher`.
5. Extend existing host bootstrap/install/status path for `_mastermind_sol_relay`, its secret/config directories and exact CEO-ingress peer permission; do not create a broad service account.
6. Add restart, duplicate-message, create-ACK-loss, stale/degraded and no-persistence tests.
7. Run hosted exact-head CI/security tests and independent review.
8. Prepare production install with no token value in model-visible surfaces.
9. At native action time, provision/verify the dedicated Executive Relay Slack app/token with exact C1 scopes, invite bot to `#sol-runtime`, and write token only through the approved secret-owning host ceremony.
10. Install/start exact merged release and prove the production matrix below.
11. STOP for Sol REVIEW_RETURN. Do not begin B2.

Independent test/review tasks may run in parallel after interfaces freeze. One implementation carrier only.

---

## 15. Acceptance tests

### Adapter

- only three allowed Web API methods callable;
- channel cannot be caller-overridden beyond fixed injected config;
- foreign redirect/origin refused;
- malformed/oversize/`ok=false` results refuse without raw error leakage;
- token absent from logs/errors/receipts;
- complete/incomplete history correctly mapped;
- post/update result author/text/ts validated by existing publisher.

### State reader

- exact state schema only;
- cannot submit/status/broad Operator command;
- wrong socket/peer/oversize/malformed response becomes safe unavailable state;
- no direct SQLite access/import/path discovery.

### Service/recovery

- 0 history matches -> exactly one create;
- 1 -> update same ts;
- >1 -> fail closed;
- create ACK loss + remote commit -> fresh history recovery finds existing message, zero duplicate;
- update failure never changes remembered canonical state incorrectly;
- restart uses Slack history, no local cursor/message-ts persistence;
- stale/unavailable Executive read overwrites with degraded state;
- semantic change immediate vs unchanged heartbeat behavior discriminated;
- hard 4,500-byte ceiling refuses, never truncates.

### Host/security

- dedicated principal non-login and minimal groups;
- cannot read Executive DB/provider homes;
- cannot connect broad Operator socket;
- token file exact owner/type/mode/no ACL/symlink;
- service argv/env/logs contain no token;
- launchd only starts exact root-owned release/config paths.

---

## 16. Real production proof

C1 is not accepted from CI alone.

On the real primary Executive host and real Slack workspace:

1. exact C1 release installed under the dedicated Relay principal;
2. dedicated Executive Relay app/bot native identity and exact scopes verified without exposing token;
3. `#sol-runtime` membership verified as Chairman + ChatGPT1/2/3 + Relay bot only;
4. service starts with zero state messages and creates exactly one `MMX/SOL_STATE_V1`;
5. all three Personal-Pro Sol seats independently read the same message/document identity;
6. a real Executive state semantic change updates the same Slack message promptly;
7. unchanged state heartbeat updates wrapper health without falsifying Executive freshness;
8. force an Executive read unavailable/stale condition and prove the same message becomes DEGRADED + `do_not_submit=true`, never stale-green;
9. restore Executive read and prove recovery on the same message;
10. restart Relay and prove it recovers the existing message ts from bounded history, zero duplicate;
11. simulate/observe one safe create/update reply-loss fixture and prove duplicate prevention;
12. prove no new Relay DB/cursor/message-ts store exists and no inbound command is processed.

Only then can MAS-109/C1 be `PROVEN_LIVE` for the production read lane.

---

## 17. Stop conditions / return-to-Sol

Stop rather than widen if:

- current Executive service cannot expose the accepted state frame to a dedicated peer without another listener/service;
- Slack C1 requires scopes broader than private history + own message write;
- token secrecy would require env/model-visible configuration;
- exact channel membership cannot be constrained;
- one-message recovery cannot be bounded without persistence;
- C1 implementation collides with a newer B2/Relay source law;
- production proof requires inbound Socket Mode.

---

## 18. Required continuation handoff

Return:

- exact PR/head/base and changed files;
- exact Relay principal/config/secret paths and permission receipt (never secret value);
- exact Slack app/bot user ID and scope names only;
- state-reader socket/peer composition receipt;
- hosted CI/security tests;
- independent review;
- production message ts/state hash/byte count and readback identities;
- three-seat read receipts;
- stale/degrade/recover/restart/ACK-loss receipts;
- proof of zero local replay/cursor/message-ts DB;
- anything unproven;
- exact next action.

Keep the carrier DRAFT/HOLD-FOR-SOL until exact-head review + real production proof. Do not start B2 from this branch.
