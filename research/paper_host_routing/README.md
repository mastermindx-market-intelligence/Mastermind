# Paper host-routing prototype - quarantined, not integrated

This directory preserves an unfinished prototype and its negative test evidence.
It is not imported or staged by the live Paper service. Do not install or enable it.
The production candidate remains the host-bound-snapshot implementation at
`cf6e9c954fc34d3b7f3f0dfffef6a022652afab2` in PR #1017; that candidate's full CI passed.

## What happened

Seven structural configuration/SSH-command tests passed. Eleven additional
in-memory, no-network adversarial probes found nine passes, one failure and one
error. The two release-blocking defects are:

1. Actual mcp==1.30.0 tool registration raises InvalidSignature because the
   postponed CallToolResult return annotation cannot resolve the function-local import.
2. A lost local modifying-call response is incorrectly labeled EFFECT_NONE by
   the prototype router; it must retain EFFECT_UNKNOWN and original target identity.

Static compatibility finding: asyncio.timeout requires Python 3.11+, while the
existing service documents Python 3.10+. Compatibility was not tested on 3.10.

The platform blocked the attempted integration patch before tool execution.
Readback proved mcp_server.py and direct_service.py remained byte-identical to
cf6e9c9. The blocked patch was not retried, split, rephrased, or delegated.
Quarantining this unconnected prototype is containment and evidence preservation,
not another route for performing the denied integration.

## Design under evaluation

One stdio tunnel client per seat; host selection inside the existing Paper service.
Only configured opaque fleet host references are public inputs. Proposed remote
calls use existing SSH key/known-host references, strict host verification and a
pinned guarded backend. No new public listener, auth store, queue, retry ledger,
worker Job, automatic failover or duplicate tunnel is introduced.

This is a proposed transport binding, not proof of an accepted fleet interface,
actual host qualification, native worker admission, account access or production readiness.
Native worker Paper grants are a separate integration from attended interactive routing;
they must not become an invented prerequisite for ordinary ChatGPT Paper calls.

## Validation

`validation_basic.py` contains the seven structural tests. The eleven additional probes are preserved in validation_adversarial.py;
their observed outcomes are recorded in evidence.json and the existing PR checkpoint.
They used synthetic hosts and fake client sessions only. No real SSH, Paper document,
credential or tunnel was contacted. Passing structural tests do not offset the
observed protocol/effect failures. These prototype files are deliberately outside
the production source and ordinary test-collection paths; they are not a CI acceptance gate.

## Continuation

Preserve the platform restriction on the denied integration action. A future
permitted continuation must reconcile current access, custody and effects first;
neither this file nor a new account/session is permission to bypass the restriction.
Any later implementation must resolve the named failures, pass real SDK wire tests,
receive independent review, and prove qualified-host/per-account operation before rollout.
