# Hermes secretary — WP5 shadow port

**Status:** `SOURCE-ONLY / SHADOW / PRODUCTION_INERT`. This directory ports Grok Secretary's skills, routines, and standing rules onto the Hermes harness qualified in PR #1865. It does not install Hermes, post to Slack, submit Fabric, approve, merge, or arm the `mmsecretary` / `mmmeta` profiles. Those profiles stay `clarify`-only.

Upstream pin: `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

## What is here

- `skills/` — three Hermes-format skills. Verbatim teaching snapshots live in each `references/grok-secretary-source.md`. The `SKILL.md` is the operative procedure.
- `roster.json` — secretary id, commissioners, watched channels, and the two post rooms. `CHRIS_SLACK_USER_ID` is required and fails closed while unset. Slack ids are not code constants.
- `routines/jobs.json` — seven paused routines on one `America/Cancun` (UTC-5, no DST) profile clock. Original wall clocks are `wall_clock_intent`. The BLOCKED listener is a Slack keyword trigger because Hermes cron at this pin has no keyword trigger. `install_into_hermes_home()` refuses.
- `detect.py`, `shadow.py` — read-only Slack decisions written to a local JSONL. `would_post` is always false.
- `guards.py` — standing rules. Forbidden actions raise `GuardRefusal`.
- `wake_bridge.py` — mints an in-memory Wake obligation only for an already-canonical `agent_dialogue_attention` source ref. A Slack ts is not that identity. Nothing is written to the wake ledger.
- `parity.py` — compares a shadow JSONL with secretary posts over a window.
- `CUTOVER_AND_ROLLBACK.md` — the runbook. Cutover is not authorized by this package.
- `UNPORTED.md` — what the teaching snapshot needs before it can run.

Sibling paths `integrations/hermes_runtime/`, `integrations/hermes_models/`, and `integrations/hermes_delegate/` are not on this head. This package does not import them.

## Tests

```sh
python3 -m unittest discover -s integrations/hermes_secretary/tests -v
python3 -m compileall -q integrations/hermes_secretary
```

No network, no Slack token, no PyYAML requirement.
