# Dot Compass R0 — authenticated owner-bound read families

**Scope:** source implementation and hermetic tests. `BUILT_NOT_PROVEN`, **not installed**, not selected by Dot, not a live data service. Existing public Dot Operator plugin is a separate private skills package and grants no access.

## User capability

Give an approved Dot current source-attributed company orientation, code/CI diagnosis, fleet telemetry, product verification and point-in-time market evidence without direct Studio Direct/Desktop Commander, shell, SSH, arbitrary filesystem, generic HTTP/SQL, credentials or browser access.

## Owner and source

Protected Skillpack: `mastermind.sol_skillpack.v1` v1.0.1, `Mastermind@732cf7be88e7159b4995a8885fbd381cd1484e3e`. Parent architecture: `docs/superpowers/specs/2026-08-30-sol-capability-fabric-design.md` and `docs/superpowers/plans/2026-08-30-sol-capability-fabric-tool-catalog.md`. This implementation creates no new truth store or orchestration owner.

Five fixed *read-only* profiles: `compass`, `code_ci`, `ops`, `product`, `market`. Each is a separate host-selected app/profile. The server never lets a model select profile, connector, project root, host, credential, executable or data source; tool names are static. The host may advertise only actually connected owner-read ports, not silently stub unavailable tools.

| Profile | Tools | Canonical provider |
| --- | --- | --- |
| compass | `dot_company_snapshot`, `dot_attention_snapshot`, `dot_operation_context`, `dot_capability_health`, `dot_changed_since` | Executive, Agent OS, CAP1, current source owner |
| code_ci | `dot_code_impact`, `dot_ci_diagnosis` | CodeIntel, GitHub |
| ops | `dot_fleet_health`, `dot_runner_diagnosis` | Fleet/Runner |
| product | `dot_product_proof` | Existing Browser evidence owner |
| market | `dot_signal_evidence` | Data OS |

The only included concrete owner adapter routes `dot_company_snapshot` -> existing `executive_state` and `dot_attention_snapshot` -> `executive_inbox` through a host-supplied `ExecutiveMcpGateway`, with immutable Mastermind SHA evidence and `PARTIAL` degradation. Other domain ports must be composed by their real owners; no simulated data or substitute filesystem collector is provided.

## Admission, security and failure

- Existing authenticated MCP host must supply one request-bound verified principal and an independent `reauthorize(principal, required_scope)` callback. The callback must check resource, issuer, subject, client, token lifetime, scopes and organizational authorization through the *incumbent* policy owner. It runs before and after the owner read, and binding changes refuse the result. The gateway itself neither mints nor verifies bearer tokens.
- Scope labels in this contract are **requirements**, not granted permissions. They must be explicitly enrolled in their actual resource policy before a profile can be exposed. Do not co-opt Executive read scope for the other domains.
- Every port must provide fresh `OwnerEvidence(owner, observed_at, source_refs, capability_state, data, issues)`. Mismatched owners, malformed timestamps, missing source references, secret-like fields, output over 16 KiB, non-JSON data, nonfinite floats and excessive nesting refuse. Returned owner text is untrusted data, never instructions.
- Tool input schemas are `additionalProperties: false`; no `cmd`, `path`, URL, root, SSH, host, account, principal or arbitrary query parameter exists. MCP annotations truthfully declare zero mutation; enforcement is in the gateway and host policy.
- Cancellation propagates; read failures never retry. No modifying tools, new action registry, scheduler, queue or retry owner exist in R0.
- A plugin name or merged source does not authorize API calls. Platform/organizational refusals cannot be rephrased through another transport or action.

## Installation gate and future closure

1. Review exact source under original PR/current master, validate tests and frozen profile digests. Code in `integrations/dot_compass` must not be silently inserted into the existing Executive seven-tool catalog or the Session Bridge source carrier.
2. Existing Executive app owner supplies the real verified principal resolver and read resource policy; compose the exact `compass` subprofile with two Executive owner adapters. Preserve all existing Executive tool schemas and auth semantics. Add the other profiles only in their own resource-authorized hosts.
3. Verify a genuine single-account remote ChatGPT MCP call with actual authenticated resource and source SHA, including revoked token, source movement, oversized output, and missing backend. Publish/installation/selection are separate observations.
4. For each additional profile, bind actual canonical owner ports, prove data freshness/negative cases, independently enroll the resource and replay no prior rejected host operation.
5. Validate per-Dot account connection and actual user workflow, not a package-install claim. Prove current context / code evidence / ops diagnosis / product proof / market evidence separately.

## Test

`python -m unittest discover -s tests -p 'test_dot_compass.py' -v` from a checkout with the first-party package on Python path. The `mcp_tools` SDK import is lazy; gateway/contract tests are Python-standard-library only.
