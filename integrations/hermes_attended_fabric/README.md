# M2 Hermes → Mastermind Capacity Fabric (native attended ingress)

**Status:** source implemented and hermetic test-qualified. **Not installed into the
M2 Hermes native session owner; no live worker START/return or paid-model
inference is claimed.**

## Goal and boundaries

The M2 already has NousResearch Hermes Agent v0.23.0, a working local
`qwen3:14b` inference backend, a loopback-only dashboard and
`mastermind-fabric-capacity` MCP providing two **read-only** tools:
`fabric_capacity_catalog` and `fabric_route_preview`. That connection lists
ten configured pools but is not a worker admission channel. The original
M2 state/proof is at `~/.hermes/bridges/MASTERMIND-FABRIC.md`.

This package is a separate **Hermes-origin attended worker** interface. It
does not replace the authenticated **Executive-selected-child** `mmx_delegate`
implementation in the active #2134 carrier, nor the merged #2120 foundation.
The selected-child path continues to bind one frozen Executive Job/Attempt
under its incumbent Control/App/MCP chain. No user, role string, pool name or
model-generated root may impersonate an Executive-selected child.

This module adds only the missing current native-session caller boundary and a
typed port to the already existing Fabric-only facade. Existing native Fabric
router, host placement, capacity/account limits, strict manual model selection,
controller, run ledger, result and acceptance remain the authoritative owners.

## Host composition — mandatory, never from the model

The trusted native Hermes host must provide:

1. A real session grant from its authenticated, current
   `profile_id`/`session_id`/generation and **verified** original root and
   immediate parent. Strings supplied by the LLM are not evidence.
2. An injected, enrolled synchronous Fabric-only `call_tool(name, arguments)`
   that speaks exactly `mastermind.fabric_mcp.v1`. No direct provider API key
   or self-created shadow MCP server.
3. `currentness_guard(SessionGrant)` that fails closed on revoked/rotated
   native principal, generation, source, grant, or session.
4. `authorize_new_run(SessionGrant, run_id)` from an **existing authoritative
   original-effect/admission owner**, which must prove a *fresh* permitted
   operation with no earlier submitted/uncertain attempt for that logical ID.
   A `fabric_status` `NOT_FOUND` alone is never this proof. No new
   coordinator ledger or invented durable permission token.
5. Optional strict manual provider/model grants frozen by that host. The
   model can request only allowlisted `pool` and exact `model` pairs;
   `auto` is the default. The typed Fabric facade independently
   rechecks native `--strict-manual-pin`, quota, entitlement, capability
   and provider consent. Experiential/uncensored routing is deliberately
   unavailable in this model schema.

Composition sketch (trusted host's **existing** owned native context only):

```python
from integrations.hermes_attended_fabric.native import (
    SessionGrant, register_native_tool,
)
from integrations.hermes_attended_fabric.facade_port import FabricFacadePort

# These bindings must arrive from actual installed owners. Never instantiate
# them using values invented by the model, an environment file, or a role name.
port = FabricFacadePort(
    incumbent_authenticated_fabric_call,
    authorize_new_run=incumbent_original_effect_eligibility,
    preview_route=incumbent_read_only_route_preview,
)
lease = register_native_tool(
    qualified_hermes_plugin_context,
    authorize_session=host_authorized_current_session,
    port=port,
    currentness_guard=host_current_session_and_generation,
)
# Retain the native lease under the same PluginManager/host lifecycle.
```

The package does not supply or substitute those five owners. Default
admission is unbound. The host must use its actual Hermes native PluginManager
registration and release/installation provenance; imported source is not a
registered tool.

## Installed Hermes native MCP client — verified on M2

The approved M2 diagnostic proved Hermes Agent v0.23.0, local checkout
`2bd378ed1b8d` (November 6, 2026). An additional read of the installed
`hermes_cli/plugins.py` verified
`PluginContext.call_mcp(server, tool, arguments, timeout)` uses Hermes's
**existing** MCP client, verifies the caller's per-plugin
`plugins.entries.<plugin_id>.mcp_allowlist`, and produces a normalized
`{ok, structuredContent?, result?, truncated?}` envelope. There is no need
to create a second MCP client, socket, OAuth login, request queue or retry
plane. The source adapter `hermes_mcp_client.py` binds precisely that API.

The M2's installed `config.yaml` currently configures only
`mastermind-fabric-capacity` under native MCP, and that server exposes only
`fabric_capacity_catalog` and `fabric_route_preview`: **read-only**.
It does NOT expose, authenticate or authorize `fabric_request`. The distinct
execution server `mastermind-fabric-exec` is therefore **not enrolled**.
The adapter default-refuses `HERMES_FABRIC_EXECUTION_NOT_ENROLLED` when its
host lacks the exact, *separately authorized* plugin allowlist entry. Nothing
copies or promotes the existing read-only server into execution authority.

A qualified incumbent host installer must enroll the **already existing**
Fabric-only execution MCP server under that exact profile-scoped name, establish
the actual private-channel authentication and consent, and grant only this
native plugin ID access to it using Hermes's normal profile configuration.
The plugin must call:

```python
from integrations.hermes_attended_fabric.hermes_mcp_client import bind_native_mcp_client
incumbent_authenticated_fabric_call = bind_native_mcp_client(qualified_hermes_plugin_context)
```

This call establishes only the native MCP *transport*. It is NOT itself the
`authorize_session`, `currentness_guard` or
`incumbent_original_effect_eligibility` required below. No configured
principal means no live submit, even when the package imports and unit tests
pass. The M2's native plugin isolation configuration was observed as default
in-process, but that is not evidence that a particular plugin or session is
currently loaded.

## Model-visible contract

Native tool `mmx_fabric_worker` (toolset `mmx_fabric`) accepts:

- `action: preview | submit | status | result`
- `task_key`: unique lowercase ID within the real native session
- for preview/submit: bounded `task_class`,
  `task_complexity` and optional factual `escalation_reason`
- for submit: a bounded `work_packet`; optional `pool` and `model`
  only when the authenticated session grant permits that exact choice

It deliberately accepts **no** model-supplied `root_id`, `parent_id`,
`session_id`, `run_id`, host, account, credential, arbitrary command,
reviewer, approval or acceptance. Auto routing is delegated to the original
Capacity Fabric. A granted manual route stays pinned to the original eligible
pool/model without cross-provider continuation.

A run ID is deterministic from the original profile+native session+task key.
A new native process generation cannot mint a replacement run for the same
logical task, although its own currentness proof must be refreshed. Status and
result read only that original run. The port additionally requires exact
canonical root and parent evidence before releasing bounded worker output.

A controller receipt is **not** worker START. The retained result must be
original-parent qualified and its complete bytes must match the original
SHA-256. This is a read, not approval or acceptance. A detached, partial,
unparseable or post-send reply retains `EFFECT_UNKNOWN`, the original run ID
and one original carrier. Native registration uses Hermes's incumbent profile
scope, collision lock, registered-entry readback and exact disposal lease.

The original session grant and the existing plugin MCP allowlist are checked
again after remote calls, before response release. A revoked or unreadable
grant withholds the returned output. If a matching submit control receipt was
already recorded, the parent receives only that fact with
`response_withheld=true` and `retry_authorized=false`; revocation cannot
turn a recorded effect into absence. A malformed or lost submit receipt stays
`EFFECT_UNKNOWN`. Result delivery also rechecks the original root, parent and
effective run after fetching the bytes. These observations do not create an
atomic owner seal or a new acceptance operation.

A retained `REQUEST_REFUSED_BEFORE_LAUNCH` is shown when the original request
run/root/parent and recorded controller return match. Its
`request_correlation_only=true`, `root_verified=false` and explicit false
retry/result-consumption flags prevent correlation from becoming worker
lineage or permission. The refusal cause remains unresolved unless the
incumbent owner supplies separate evidence. No replacement submit follows.

## Verification

Source tests (hermetic doubles, no provider execution):

```sh
python3 -m unittest discover -s integrations/hermes_attended_fabric/tests -p 'test_*.py' -v
python3 -m compileall -q integrations/hermes_attended_fabric
```

The return-recovery continuation adds regression coverage and exercises the
actual Node Fabric facade through the native Python handler, Hermes MCP client
and typed port. Only the final command engine and durable admission are
fixtures; no generated command is executed. Cases cover original-result
recovery across a simulated native restart, incumbent successors, lost submit
responses, refusal correlation, result size and permission/lineage changes.
The same cases are imported by `tests/test_hermes_attended_fabric.py` into the
existing protected pytest suite, including integrated merge-group CI.

Source qualification: **67 package tests passed**; **69 pytest tests and
63 subtests passed**, including the unchanged two escalation-length literal
sites under an updated exact-source review pin. This is author self-review,
not an independent reviewer or live M2 qualification. See
[the continuation](CONTINUATION.md) for the owning operation and exact commands.
Re-run on the exact final head in GitHub CI; fixture tests alone do not
establish live M2 native admission. Fixture tests are not proof that an
actual authorized M2 host connection exists.

## Remaining installed acceptance (blocking, not bypassable)

1. Qualify actual M2 native Hermes profile/session/grant and enroll the
   already-existing Fabric-only authenticated client under the host's scope.
   Neither the local read-only MCP nor a borrowed ChatGPT Web token supplies
   this authority. M2's prior remote start-process action received a platform
   safety refusal; do not rephrase or route around it.
2. Register through the real Hermes plugin lifecycle and verify the installed
   schema/handler/readback; do not replace the active #2134 selected-child
   writer. Preserve original live Fabric workers/tunnels and the preexisting
   Ollama listener pending its own consumer analysis.
3. Start **one** newly admitted task under a genuine host-issued root/parent.
   Prove actual qualified pool/model, Fabric worker START (not PID/controller),
   retained terminal output, original-parent consumption and the existing
   acceptance owner. Verify a separate authorized exact model pin.
4. Prove interruption/restart/original-run recovery, refused stale auth,
   quota/account limits and no duplicate effects. Observe installed release
   identity and the actual protected publication workflow. Hosted CI and
   production proof remain distinct.

Do not claim `PROVEN_LIVE`, make a model key visible to Hermes, create a
shadow router, bypass a safety refusal, or mark a controller PID as a
successful worker until those exact installed receipts exist.
