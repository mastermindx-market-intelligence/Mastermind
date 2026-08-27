# Codex-Sol Technical Staff Conformance — Executive Source-Law Addendum

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** IMPLEMENTATION-CONFORMANCE CARRIER / PRODUCTION-INERT  
**Governing architecture:** Mastermind #172 / merge `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`  
**Carrier:** Mastermind #173  
**Operation key:** `codex-sol-technical-staff-conformance-20260827-sol-001`

## Ruling

The approved phrase **Codex-Sol technical staff** describes a bounded duty/embodiment of the existing Sol CEO responsibility. It does not create another executive identity.

The canonical composition is:

```text
Executive accountability     = existing Job owner_seat = ceo
Technical duty               = existing orchestration role where applicable
Permitted authority          = current commission + effective grant / parent subset law
Reasoning/execution surface  = codex when Codex is used
Worker/provider/account      = execution identity/capacity only
Runtime session/thread       = runtime evidence only
Slack principal              = communication only
```

No provider, model, Worker, RuntimeBinding, native thread, or Slack principal can promote a Job to `owner_seat=ceo`. Current Executive Runtime already requires typed CEO provenance for a CEO-owned Job. Provider/model constraints remain separate from that provenance.

## Relationship to Phase 1F orchestration law

This addendum does not change the accepted Phase 1F orchestration-role vocabulary. The existing closed duties remain:

```text
plan | work | review | repair | aggregation
```

`sol_technical_staff` must not be added as a sixth durable orchestration role merely for branding. A technical continuation uses the existing role that truthfully describes the bounded work plus the commission/effective grant that defines authority.

The existing shrink-only parent/child law remains controlling. A CEO-owned technical parent cannot delegate authorities, write paths, capabilities, cost/quality scope, escalation, review independence, merge/deploy authority, or other privileges beyond the accepted parent grant.

## Relationship to Model Router / RF1

Model Router remains a stateless suitability/execution-shape policy. A route such as `frontier.orchestrator`, a concrete model such as `gpt-5.6-sol`, or provider `codex` is not CEO provenance and cannot create/mutate an executive seat or effective grant.

Provider-neutral suitability/equivalence tiers are still owned by RF1 and remain dependency-gated by current Capacity Fabric law. This #173 carrier does not implement RF1 or change worker/provider ordering.

## Relationship to Wake Fabric

Wake delivery and runtime continuation are separate from role/accountability. Wake PR3 is the sole current implementation carrier for native Codex/Claude wake transport. #173 does not modify `control_plane/wake_*`, `control_plane/session_targets.py`, `control_plane/wake_transport.py`, Wake tests, or Wake documentation.

A Codex App Server thread/native handle may address a current reasoning surface through a `RuntimeBinding`; it never becomes the durable Sol identity.

## Relationship to Slack

ChatGPT1/2/3 are communication/cognition principals for Sol seats. Claude identities are communication principals for their sessions. Those usernames may be useful for human conversation but do not select Executive Worker, owner seat, provider account, or effective grant.

## Conformance tests

`tests/test_codex_sol_identity_conformance.py` must remain green and discriminating against these forbidden mutations:

1. Codex reasoning surface changes `target_seat` or Job ownership.
2. Provider/model identity creates a CEO-owned Job without typed provenance.
3. Slack-like prose or principal strings select an executive seat or Worker authority.
4. A new durable `sol_technical_staff` / `codex_sol` role field appears in Job/Attempt/Worker state.
5. A provider/session/native handle appears in Job-owner identity.
6. Model Router gains executive authority fields.
7. A technical child widens the parent grant.

## Capability classification

This carrier can become `BUILT_NOT_PROVEN` / conformance-complete after exact-head tests, hosted CI/CodeQL, independent adversarial review, and Sol acceptance. It makes no provider execution, Wake transport, multi-host route, or production autonomy capability live by itself.
