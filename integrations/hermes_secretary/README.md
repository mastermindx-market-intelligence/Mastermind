# Hermes secretary — WP5 shadow port

**Status:** `SOURCE-ONLY / SHADOW / PRODUCTION_INERT`. This directory ports Grok Secretary's skills, routines, and standing rules onto the Hermes harness qualified in PR #1865. It does not install Hermes, post to Slack, submit Fabric, approve, merge, or arm the `mmsecretary` / `mmmeta` profiles. Those profiles stay `clarify`-only. Slack transport is the single-app Executive Relay bridge (roster unit `hermes-mmrelay`); `relay_mux.py` plans DM/channel routing and per-role attribution and never writes.

Upstream pin: `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

## What is here

- `skills/` — three Hermes-format skills. Verbatim teaching snapshots live in each `references/grok-secretary-source.md`. The `SKILL.md` is the operative procedure.
- `roster.json` — Chairman `U0BRET6191C`, Grok Secretary `U0BTCHX8HMF` as a permanent peer, commissioners, watched channels, and the two post rooms. Each Hermes agent loads `self` from its own `HERMES_SLACK_BOT_USER_ID`. Slack ids are not code constants.
- `routines/jobs.json` — seven paused routines on one `America/Cancun` (UTC-5, no DST) profile clock. Original wall clocks are `wall_clock_intent`. The BLOCKED listener is a Slack keyword trigger because Hermes cron at this pin has no keyword trigger. `install_into_hermes_home()` refuses.
- `detect.py`, `shadow.py` — read-only Slack decisions written to a local JSONL. `would_post` is always false.
- `guards.py` — standing rules. Forbidden actions raise `GuardRefusal`.
- `wake_bridge.py` — mints an in-memory Wake obligation only for an already-canonical `agent_dialogue_attention` source ref. A Slack ts is not that identity. Nothing is written to the wake ledger.
- `native_dialogue_consumer.py` — opt-in, **host-composed** single-turn helper. For an already-authenticated native session and a current CEO CONTINUE supplied by the existing Agent Dialogue resolver, it reads the canonical original-parent thread, submits the instruction to a separately injected role-scoped text model function, and sends a bounded PROGRESS reply **only through the existing** `integrations.session_bridge.native_reply.NativeReplyWriter`. It has no Slack API, listener, direct post, new lifecycle/queue, Fabric submit or credentials. Neither a raw Slack ts nor a model reply can set the destination, actor or operation identity. Existing READY/COMMIT and EFFECT_UNKNOWN rules are unchanged.
- `parity.py` — compares a shadow JSONL with secretary posts over a window.
- `CUTOVER_AND_ROLLBACK.md` — the runbook. Cutover is not authorized by this package.
- `UNPORTED.md` — what the teaching snapshot needs before it can run.

Related candidate packages `integrations/hermes_runtime/`, `integrations/hermes_models/`, `integrations/hermes_delegate/` and the existing `integrations/session_bridge/` are present in this stacked release. This package does not enable or start those services.

**Host integration is still missing:** The authenticated native host must supply a real `NativeReplyWriter` with its actual Runtime/Agent Dialogue resolver, role-current source, a model backend operating under the installed role's provider/network confinement, and a current native-session UUID. The helper supports only canonical CEO CONTINUE -> bounded native PROGRESS, **not** unsolicited Secretary chat, arbitrary Slack messages, new user-facing Hermes bot identities, or production-inferred delivery. Synthetic tests use an injected no-network model and a fake relay. Any live Slack transport must use the approved incumbent Agent Dialogue/Relay owner and its existing qualified identity and credentials, with host integration, negative-path validation and observed original-parent roundtrips. Do not add a second Slack scanner, bot or token holder, or reuse Grok Secretary's token.

## Pre-inference currentness and remaining admission boundary

After reading the canonical request, the consumer re-resolves the existing
NativeReplyWriter's complete original binding identity and rechecks the current
role before entering the inference callback. Observed generation, process,
binding or role drift refuses without model entry or send. Missing evidence
fails closed; cancellation during these checks propagates before inference.
Existing post-inference and canonical READY/COMMIT checks remain in place.

These separate asynchronous reads are not an atomic admission claim. The
authenticated host still must join the canonical CONTINUE and NativeReplyBinding
to the original Runtime command and native finite admission before inference,
then recover that original result or retain its uncertain effect. The current
helper's sequential canonical reply dedup does not prevent concurrent model
entries or authorize reentry after cancellation or MODEL_TURN_EFFECT_UNKNOWN.
Native admission and APPLICATION ownership remain with their existing owners;
do not add a consumer-local lock, ledger, retry queue or prompt-derived identity.

NO INSTALL / DO NOT DEPLOY remains in force. Source tests do not establish live
native consumption, provider cancellation/settlement or original-parent
consumption.

## Tests

```sh
python3 -m unittest discover -s integrations/hermes_secretary/tests -v
python3 -m compileall -q integrations/hermes_secretary
```

No network, no Slack token, no PyYAML requirement.
