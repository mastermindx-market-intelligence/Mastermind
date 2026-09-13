# Workspace Agent run observation: one read, not an execution engine

Status: source candidate / `BUILT_NOT_PROVEN`. No published agent, Workspace token,
Executive registration, provider-trigger effect, unattended continuation or production
acceptance is established by this code. Integration direction: Mastermind PR #603.

## Observable capability

An operator can decode the real provider's trigger response without confusing
acceptance with correlation, and can inspect one exact published run through a
bounded read-only CLI. Provider completion is not a returned answer, canonical
result, independent review, Wake consumption, or company acceptance.

Existing owners remain: Executive admission/lifecycle/results; RuntimeBinding and
Wake; Capacity; current app authentication; Macro Agent OS; GitHub evidence.
This module registers no transport, adds no Executive tool, opens no listener,
persists no token or result, and has no loop, queue, retry or POST method.

Contract checked 2026-09-13:
https://developers.openai.com/workspace-agents/trigger-runs
https://developers.openai.com/workspace-agents/authentication

## Use

Describe the source capability without a token or network:

```sh
python3 scripts/workspace_agent_api_probe.py --describe
```

Decode an already-received response from the existing dispatch owner, without
sending a request. Never repeat a trigger because its response is malformed:

```sh
printf '%s' '{"conversation_url":"https://chatgpt.com/c/synthetic"}' |
  python3 scripts/workspace_agent_api_probe.py --decode-trigger --http-status 202
```

For an actual published run, the existing secret owner supplies
`WORKSPACE_AGENT_ACCESS_TOKEN` privately in the process environment. Do not put it
in arguments, a prompt, a GitHub comment, or a log. The channel and run below must
come from the actual owner receipt, not from these synthetic examples:

```sh
python3 scripts/workspace_agent_api_probe.py --read-run \
  --channel agtch_ACTUAL_CHANNEL --run apirun_ACTUAL_RUN
```

`--expected-conversation-url` additionally checks the already-observed conversation.
IDs are path components, not user-supplied URLs. The only network destination is
TLS `api.chatgpt.com`, with one GET, no redirects and a capped response body.
`--timeout` is a finite connection/socket timeout (maximum 30 seconds), not an
end-to-end process deadline or cancellation of provider compute.

Exit 0 means a parsed observation (or accepted trigger receipt), never company
completion. Exit 2 is invalid input/missing credential. Exit 3 means unavailable
status or uncertain trigger effect. A missing/bad 202 body remains accepted with
unavailable correlation; there is deliberately no automatic resend advice.
Unknown provider states, malformed JSON, identity mismatch and HTTP failure stay
unavailable with null state/terminal fields. Error bodies and vendor prose are
not emitted. Unknown additive JSON fields are ignored, not treated as authority.

## First real qualification and exact next integration

1. The existing workspace owner enables the published API channel and provisions
   the Workspace-scoped token through its existing secret owner. This source does
   neither and adds no admin permission. Existing spending controls still apply.
2. Obtain one already-authorized run receipt from the owning invocation ceremony.
   Read that exact run and compare observed channel/run/conversation with the real
   Workspace UI. Check the actual seat and beta contract; documentation is not proof.
3. Qualify suspended, failed, unavailable and identity-mismatch behavior. Preserve
   provider status separately from the actual answer and responsibility result.
4. The native parent must consume a candidate through the already-reviewed result
   or dialogue owner. The public status API does not retrieve the answer. Do not
   widen #599's five-tool contract or synthesize a trusted current-worker Wake ACK.
5. Only after the current-target, return and budget seams are reviewed may an
   admitted Executive caller use a separately implemented trigger transport.
   Native fabric execution and Workbench proof continue through their incumbents.

No cancellation endpoint, workspace-agent creation endpoint, exact-agent attestation,
seat concurrency guarantee or hard credit cap is invented here. A process exit,
provider-terminal state and accepted capability remain different facts.

## Checks actually supporting this candidate

```sh
python3 -m unittest discover -s tests -p test_workspace_agent_api.py -v
```

The test suite exercises the actual CLI, a single injected HTTP connection, exact
GET path, bounded reads, no redirects/retries, error redaction and correlation.
Its synthetic server response is not live Workspace Agent proof.

Two prompt-only helpers were run through the existing Studio engineering broker.
The Flash artifact was rejected (invalid JSON, swapped identifiers and foreign URLs);
one new bounded GLM-5.3 correction produced five exact, independently validated
fixtures. Both processes ended, with no tools or nested subagents. Their raw result
hashes are recorded in the parent source receipt. CLI dollar estimates had unknown
cost basis and are not reported as subscription charges. This is a small task-specific
observation, not a model-quality benchmark or governed Executive fleet proof.
