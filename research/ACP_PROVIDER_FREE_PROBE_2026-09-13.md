# ACP provider-free qualification slice

Operation: `acp-provider-free-probe-20260913-sol-001`.
Source basis: Mastermind `d94a47acb60de6ce8af712fbef4aa294dbf94df3`.
Procedure: same-commit Sol Skillpack 1.0.1 / bootstrap 1.
State: **source candidate; not a registered WorkerExecutionAdapter; no production proof**.

## Capability and scope

This slice gives the existing provider-neutral harness program one executable,
provider-free qualification path for the official ACP Python SDK. A real SDK
client exchanges initialize/new-session/prompt/update/permission/cancel messages
with a fixed, inert subprocess fixture. A borrowed input guard prevents malformed,
duplicate-key, non-finite, oversized, over-budget, and wrong-session frames from
being silently accepted or queued without a bound. The deny-only callback client
never exposes filesystem, terminal, extension, credential or MCP capabilities.

It does not select a provider, read credentials, enroll a realm, call a model,
change routing/capability registries, install a host service, persist sessions,
create a Job/Attempt/Event, release capacity, retry, resume, or fail over.
`OBSERVED_END_TURN` and `OBSERVED_CANCELLED` describe fixture protocol evidence,
not Executive acceptance or remote process cleanup. Outer caller cancellation
propagates as cancellation; it does not fabricate a terminal receipt.

The existing `ops/executive_os/grok-build-preflight.py` retains all ownership of
Grok binary/authentication preflight. This fixture never replaces or invokes it.
Codex cancellation, PF455, C1, their retained writers, and their source branches
are untouched.

## Governing boundary

`research/MASTERMIND_EXECUTIVE_CURSOR_GROK_AUTH_ACP_SOURCE_LAW_2026-08-25.md`
sections 6 and 8 permit deterministic fake fixtures in parallel. They continue
to gate core registration, real Cursor/Grok canaries and production enablement
on their accepted predecessors, including the first Claude common-harness proof.
This slice neither supersedes that sequencing nor claims those gates passed.

## Upstream reuse, rather than another protocol stack

The driver uses official SDK `connect_to_agent`, `NdjsonTransport`,
`MessageSender`, and `TaskSupervisor`; it does not implement request IDs,
JSON-RPC dispatch, pending-request correlation, SDK schemas, or protocol routing.
The fixture's tiny scripted peer is a test oracle, not an alternative transport
service. The source client/observer is test support, not another runtime.

Pinned SDK distribution: `agent-client-protocol==0.12.1`.
Expected wheel SHA-256:
`aaf3cc301ed87d9e2c4ccb91adfe1cd58784355f6ce7e513f50e7ca2391862ef`.
The SDK is optional to the sealed Executive runtime; no project dependency or
production import is added. No automated SDK installation or execution workflow is added. The local execution
surface lacks this SDK, and native execution was refused by the tool surface.
No alternate-host run is used to route around that refusal. Dependency and actual
SDK execution qualification remain explicit gates, not implied by unit tests.

Primary sources inspected:
- https://pypi.org/project/agent-client-protocol/0.12.1/
- https://github.com/agentclientprotocol/python-sdk/blob/0.12.1/src/acp/_transport.py
- https://github.com/agentclientprotocol/python-sdk/blob/0.12.1/src/acp/client/connection.py
- https://github.com/agentclientprotocol/python-sdk/blob/0.12.1/src/acp/task/sender.py
- https://github.com/agentclientprotocol/python-sdk/blob/0.12.1/src/acp/task/supervisor.py

The earlier research pin `c1004f8c...` belongs to the later release-candidate
source epoch. It is **not** asserted to be the source of the stable 0.12.1 wheel.

## Why the extra boundary is needed

SDK 0.12.1 `NdjsonTransport._read_line` drains `LimitOverrunError` chunks and
concatenates them. Setting `StreamReader.limit` alone therefore does not enforce
an application frame ceiling. Its JSON parser also logs and skips malformed
frames. The borrowed reader translates an overrun into a distinct closed error,
validates strict bounded JSON, and forwards the original valid bytes unchanged.
This prevents those permissive paths without copying the SDK's JSON-RPC engine.

The `StreamReader._limit` and SDK transport/task imports are explicitly qualified
implementation seams, not promised version-independent APIs. An upgrade requires
this same conformance gate against its actual distribution. Raw-frame limits bound
admitted frame size and count, not a universal process-memory bound: asyncio and
OS pipe buffers still exist.

A cancellation notification completing is not evidence that the original prompt
returned `cancelled`. The observer waits for that original response under one
finite delivery-plus-terminal budget. A missing terminal or transport ambiguity
remains `INCONCLUSIVE`; a second prompt on the same probe refuses before dispatch.
All observation receipts are secret-free counters/digests and fixed reason codes.
No raw text, provider exception prose or account information is projected.

## Proof ledger

At local authoring, CPython 3.13.5 passes **42 unittest methods**, including
parameterized subtests. Eight separate guard-removal mutations fail on behavioral
assertions, with no import/setup error substituted for a kill. The source bytes
are unchanged by the mutation campaign. The initial missing-module run is only
scaffolding evidence, **not** a behavioral RED result.

The explicit real-SDK gate currently exits 2 locally with `SDK_NOT_INSTALLED`.
It does not silently skip. The 13 wire cases remain unexecuted and must not be
reported as passing. Any future authorized run must retain its exact source/SDK
identity, actual terminal logs, and cleanup result. The ordinary existing repository
CI is unchanged and remains a separate source integration gate.

## Commands

```sh
python -I -B tests/test_acp_probe_boundary.py
python -I -B tests/acp_sdk_conformance.py
```

The second command requires the exact qualified SDK distribution. It spawns only
the fixed Python fixture with a closed scenario list and empty provider context.
No arbitrary provider executable, URL, authentication method or workspace grant
can be supplied. The fixture has no network or model implementation. Forced
fixture termination or nonempty stderr fails the wire qualification.

## Remaining integration and stop boundary

First consume real-SDK wire proof and required source CI, then independent review.
Any defect stays on this source carrier. Do not promote a fixture receipt into
`adapter_descriptor("acp").implemented`, register an ACP surface, broaden provider
permissions, or enable routes from this result.

After the existing provider predecessor gates are accepted, the existing harness
owner can consume this qualified reader/callback/terminal behavior inside the one
ACP adapter and bind it to the canonical Attempt/OHF/broker/result owners. That
later vertical still owes real binary/realm/configuration attestation, cancellation
and process cleanup, independent result review, exact parent consumption, and
visible machine/browser proof. No new broker, lifecycle, retry, queue, credential
or organizational memory plane is authorized by this test slice.
