# Operator Continuity — One Rich Adapter Factory Per Worker Realm

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This corrects an over-generalization found during Sol review of OCR-4A.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, compatible Skillpack v1.0.0 / bootstrap major 1.  
**Affected plan:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr4a-provider-neutral-rich-harness.md`  
**Existing implementation preserved:** `control_plane.executive_worker_broker.WorkerBroker` / `OperatorAdapterFactory`.

## 1. Defect found

OCR-4A's first draft proposed changing the existing worker broker to carry an immutable registry keyed by `(provider, harness_kind)` and select a provider adapter from the sealed `RequestedExecutionProfile`.

Current architecture is already safer and more realm-specific: one worker broker runs under one dedicated worker UID/principal and receives **one** pre-composed `OperatorAdapterFactory`. The factory constructs the rich adapter for that worker realm. The broker already passes the sealed requested profile to that factory, but it does not own a provider catalog.

A multi-provider registry inside one dedicated worker principal would make it possible for one broker/account realm to become a cross-provider launcher and would blur the exact provider/auth-home boundary that Worker identity and independent-review law rely on.

## 2. Frozen ruling

**Keep one immutable rich adapter factory per worker-broker process / Worker realm.**

Provider-neutrality means:

```text
one common OperatorHarnessAdapter / OperatorAdapter protocol
one common broker wire/lifecycle
one common Executive supervisor/orchestrator/port
one provider-neutral factory TYPE
many worker realm processes, each configured with exactly one reviewed concrete factory
```

It does **not** mean one worker principal chooses among provider adapters at runtime.

Examples:

```text
codex-pro-01 broker under Codex worker principal
  -> operator_adapter_factory = CodexOperatorAdapter factory

claude-pro-02 broker under Claude worker principal
  -> operator_adapter_factory = ClaudeOperatorAdapter factory
```

Executive OS/CF2-I selects the Worker/realm **before** the broker request exists. The broker never performs provider selection.

## 3. Required realm pinning

The concrete factory must fail closed unless the sealed `RequestedExecutionProfile` matches the broker's configured realm contract, including at least the reviewed:

```text
provider
harness_kind
worker_id / process principal expectations
harness identity/version/digest
execution capability/profile law
auth realm requirement
```

The exact validation may remain inside the provider factory/adapter and existing TX-4 attestation path, but no arbitrary requested provider may cause that broker to construct another provider implementation.

A broker configured for Claude must refuse a Codex requested profile. A Codex broker must refuse a Claude profile. There is no fallback factory.

## 4. OCR-4A implementation correction

Supersede OCR-4A Task 2's proposed `OperatorAdapterRegistry` / `(provider,harness_kind)->factory` registry.

Preferred implementation sequence:

1. Generalize the **control-side** `RemoteCodexOperatorAdapter` into a provider-neutral remote OHF proxy while preserving a Codex compatibility wrapper.
2. Preserve the existing worker-broker `OperatorAdapterFactory` single-factory constructor seam. Rename/type/generalize only where needed; do not add a provider registry.
3. Add tests proving a concrete realm factory refuses the wrong provider/harness profile.
4. Generalize `ExecutiveOperatorSupervisor` profile resolution and control-side adapter factory typing so the same supervisor can drive the currently claimed Worker realm.
5. Provider-specific process/session mechanics stay in the concrete adapter/helper behind that realm's broker.

If the current single-factory seam proves insufficient for a specific provider lifecycle, return to Sol with the exact falsifier rather than adding a runtime provider catalog to the broker.

## 5. Multi-host compatibility

MH1 remains unchanged. A host may run multiple distinct worker broker services only when each has its own accepted Worker/principal/realm boundary. The remote transport routes to the Worker already claimed by Executive OS; it does not send one request to a generic host broker and ask that host to choose a provider.

## 6. No-rebuild / security proof

This ruling preserves:

- dedicated worker UID isolation;
- one Worker/account realm per broker process;
- provider selection exclusively above the broker in Executive/Capacity Fabric;
- one common broker protocol;
- no provider-specific broker fork;
- no hidden provider fallback inside a Worker realm.
