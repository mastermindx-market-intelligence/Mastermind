# Hermes Steward read bridge (WP3)

Offline consumer that lets a pinned Hermes profile see company state only
through the existing six read-only Steward MCP tools. Scope is
`mastermind.steward.read`. There is no write method, no second Steward, and
no credential in git.

Upstream pin inspected for the `mcp_servers` shape:
`NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.

`hermes.mcp.yaml` is a Hermes config:

- native toolsets stay `clarify` only, with the qualification denylist intact
- one server, `mastermind_steward`
- `tools.include` is exactly `list_responsibilities`, `get_responsibility`,
  `get_attention`, `get_current_runtime`, `explain_blocker`, `resolve_surface`
- resources and prompts are off
- the URL and bearer token are `${ENV}` references

`StewardReadClient` checks the bearer token against the existing Business MCP
claims policy, then forwards one allowlisted read to an injected transport.
`DEGRADED` and `UNKNOWN` payloads are copied through. Missing facts are not
filled in. A disappeared source becomes `UPSTREAM_UNAVAILABLE` with `data: null`.

## Exact responsibility brief (source-only consumer)

The **historical** `StewardReadClient.read()` intentionally remains a
verbatim upstream passthrough for existing offline consumers. A new
`read_grounded()` method performs the same one authenticated, allowlisted
request, then independently checks the *entire* response using the existing
`mastermind.secretary_grounding_mcp_result.v2` schemas. It rejects
wrong-tool envelopes, unknown fields, missing mandatory predicates, cross-owner
or subject-identity mismatches, malformed/oversized data, and disguised errors
with `UPSTREAM_INVALID` and no exposed data. Source/freshness metadata and
`UNKNOWN`/`DEGRADED` states remain unchanged; no attempt is made to repair
or invent missing facts. A credential rejection is returned before the source
is read; no retries or provider fallback occur.

`brief.responsibility_brief(client, responsibility_ref=...,
authorization=...)` is the first product-facing, **pure read-only**
consumer. It reads the *exact caller-specified* responsibility with three
existing approved tools: `get_responsibility`,
`get_current_runtime`, and `explain_blocker`. Its result includes each
predicate, exact source receipt, freshness and grounding reason, without
choosing a task, person, conversation or transport. It returns `PARTIAL` or
`UNKNOWN` when source coverage is missing; a late authentication/refusal
discards any earlier partial card. `company_completion_proven` is always
false; the consumer has no authority to infer a Job/WorkerResult or completion.

The new method and briefing function **are not automatically installed as
native Hermes tools**. They require the original, independently approved
receiving-owner Steward/authenticated tool binding before a real model or
Chairman Office may consume them. The shipped native MCP configuration stays
disabled, no Company/Executive credential is enrolled, and this package
does not create a queue, cache, secondary auth owner or scheduled watcher.
Model prompt text cannot grant execution authority merely by appearing in a
fact description.

This package does not start Hermes, open a socket, or admit an Executive
write. `PASS_OFFLINE_STEWARD_READ_CONFIG` is a static config result.

```sh
python3 -m unittest discover -s integrations/hermes_steward/tests -p 'test_*.py' -v
python3 -m compileall -q integrations/hermes_steward
python3 integrations/hermes_steward/config_guard.py \
  --config integrations/hermes_steward/hermes.mcp.yaml
```
