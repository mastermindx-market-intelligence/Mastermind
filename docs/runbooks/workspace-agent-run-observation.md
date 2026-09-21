# Workspace Agent API trigger acceptance: no run-status API

Status: source correction / `BUILT_NOT_PROVEN` / production-disarmed.

## Current supported contract

OpenAI's current Workspace Agents product documentation states that an API
trigger queues the agent run and returns HTTP `202 Accepted` with **no response
body and no run id**. The agent's response cannot currently be retrieved through
the trigger API.

Mastermind therefore treats the provider API as a one-way attention edge:

```text
exact admitted event
-> durable Executive intent/effect identity
-> one Workspace trigger POST
-> provider accepted | rejected | EFFECT_UNKNOWN
-> candidate returns independently through the authenticated Workspace return MCP
```

A `202` proves provider queue acceptance only. It does not prove START, agent
execution, completion, useful output, Wake ACK, company result acceptance, or
permission to send another trigger.

The previously researched beta run-id/status contract is superseded for current
production planning. `decode_run` and `read_run_once` remain compatibility
surfaces only; they return `RUN_OBSERVATION_UNSUPPORTED` and perform zero
run-status network I/O.

Current product reference rechecked 2026-09-21:
https://help.openai.com/en/articles/20001143

## Read-only operator probe

Describe the supported source capability:

```sh
python3 scripts/workspace_agent_api_probe.py --describe
```

Decode an already-received trigger HTTP disposition without sending a request:

```sh
printf '%s' '' |
  python3 scripts/workspace_agent_api_probe.py --decode-trigger --http-status 202
```

The decode path never trusts a success body. Even if an intermediary or obsolete
endpoint supplies correlation-shaped bytes, a `202` remains
`ACCEPTED_UNCORRELATED`.

Legacy run flags fail visibly and perform no network I/O:

```sh
python3 scripts/workspace_agent_api_probe.py --read-run \
  --channel agtch_EXAMPLE --run apirun_EXAMPLE
```

Expected result: `RUN_OBSERVATION_UNSUPPORTED`.

## Dark trigger source

`build_trigger_plan` freezes the exact channel, bounded input, optional
conversation key, payload digest, and deterministic provider idempotency key
before I/O. `trigger_once` performs at most one POST to the fixed provider host,
never retries or redirects, and does not read a `202` response body.

Known provider rejection remains a known rejection. Any transport failure or
unknown HTTP disposition after the effect boundary remains
`TRIGGER_EFFECT_UNKNOWN`. Timeout/cancellation/silence never proves no effect.

The plan hides its request body from `repr`; token custody remains external.
Before any live use, the existing Executive operation/event owner must durably
bind the exact plan and economic authority before the POST, then reconcile that
same carrier after uncertainty. Do not create a Workspace-specific replay table.

The legacy compatibility header and the exact published trigger endpoint still
require qualification against the channel instructions produced by the actual
published agent. This source correction does not claim a live endpoint.

## Candidate return is the result edge

Because the trigger API exposes no answer, useful output must return through the
separately authenticated candidate-return MCP. That return is still only an
untrusted candidate until the current Mastermind owner reviews/accepts it.

Keep distinct:

- provider queue acceptance;
- candidate transport into Agent Dialogue;
- independent review;
- canonical result acceptance;
- Wake/target acknowledgement;
- next-child admission.

No one of these implies another.

## Remaining live qualification

1. Accept and install the current-target candidate-return chain.
2. Publish one reviewed Workspace Agent profile with only its approved read apps
   plus `submit_candidate`.
3. Provision the Workspace-scoped trigger token through existing secret custody.
4. Freeze one finite economic/authority envelope and one exact trigger event.
5. Bind the exact trigger plan in Executive Events, then issue one POST.
6. Observe only the HTTP disposition; do not poll a fabricated run-status API.
7. Require the useful candidate to return through the authenticated return MCP.
8. Verify stale/duplicate/late return refusal, result review, and truthful Control
   Room projection before any broader continuation.

No cancellation endpoint, response retrieval, run-status endpoint, exact-agent
attestation, concurrency guarantee, or credit ceiling is invented here.

## Supporting checks

```sh
python3 -m unittest discover -s tests -p test_workspace_agent_api.py -v
python3 -m unittest discover -s tests -p test_workspace_agent_trigger.py -v
```

These are hermetic protocol tests, not live Workspace Agent proof.
