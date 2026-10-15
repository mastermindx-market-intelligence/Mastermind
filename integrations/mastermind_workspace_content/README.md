# Mastermind workspace content resource

This package is the first source-controlled consumer for one existing managed
turn's visible hot window. It composes existing owners; it is not another agent
runtime, transcript store, authorization server, queue, router, or lifecycle.

## Data path

```text
existing VisibleTurnProjection + existing reader grant
    -> ManagedTurnWindowSource
    -> LiveWindowReader + owner-supplied content classification
    -> existing Business JWT policy and current source permission
    -> fixed GET WorkspaceContentResource
    -> stateless Starlette resource app
```

The consumer never mints or revokes the internal projection grant. The Browser or
HTTP caller cannot provide a filesystem path, provider identifier, native turn
identifier, source URL, or source reference. Those are fixed by the application
owner during construction.

## Claims deliberately withheld

The wire document says `history=NOT_PROVEN` and
`acceptance=NOT_PROJECTED`. `terminal=true` means the observed provider turn is
terminal; it does not mean work or product acceptance. Send, provider control,
and history capabilities remain false.

Owner classification decides whether each source item is visible, filtered, or
withheld. Source text is data. The read resource rechecks current authorization
after source work and safe serialization before releasing bytes.

## Primary components

- `ManagedTurnWindowSource`: adapts one existing projection, full `TurnKey`, and
  already-issued reader grant. It performs no grant or provider effects.
- `BrokerTurnWindowSource`: validates the existing `ohf-observe-turn` wire result
  and supplies the same reader without exposing broker/native identifiers to the caller.
- `LiveWindowReader`: drains bounded pages, preserves correction identity,
  discloses gaps, applies content decisions, and emits a strict public document.
- `build_business_workspace_content_resource`: composes the current Business JWT
  verifier, separate content scope, current source permission, audit sink, and
  qualified source callback.
- `build_workspace_content_app`: mounts one fixed resource plus protected-resource
  metadata and process health/readiness. It starts no listener or background work.
- `WORKSPACE_HTML`: source-free conversation UI. An approved host supplies its
  authorized reader callback; the page embeds no source content or bearer token and
  exposes no send/provider-control operation.

## Capability state

Source implementation and controlled integration tests are `BUILT_NOT_PROVEN`.
The production capability remains unproven until the incumbent application/content
owners enroll the resource and scope, bind the actual broker/content callbacks,
and demonstrate one real provider response in the browser before terminal
completion while the original controller consumes terminal exactly once.
