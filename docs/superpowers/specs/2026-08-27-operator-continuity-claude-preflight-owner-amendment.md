# Operator Continuity — Single Claude Worker Preflight Owner Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** CHAIRMAN-APPROVED ARCHITECTURE PROGRAM / CONTROLLING NARROW AMENDMENT. Records only.  
**Applies to:** OCR-1 V3, PF1 Claude Worker Task 4, OCR-4 worker-context auth, OCR-8 realm acceptance.  
**Protected source-law basis at ruling:** current protected Mastermind Skillpack `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1; re-pin exact protected SHA before action.

## Problem

The pre-existing PF1 Claude Worker implementation plan already reserved a future provider preflight path:

```text
ops/executive_os/claude-worker-preflight.py
tests/test_claude_worker_preflight.py
```

An early Operator Continuity draft independently named `claude-native-realm-preflight.py`. Both would observe the same Claude binary/auth/runtime readiness boundary. Building both would create duplicate provider-preflight semantics, contradictory readiness receipts and a second identity seam.

A second mismatch surfaced during current-source archaeology: the historical PF1 plan proposed additional binary execution-capability booleans such as safe mode / Chrome suppression / session persistence / structured output, while OCR-1 V3 freezes a closed V1 realm/auth receipt. A closed wire must not silently grow later merely because an older plan expected more fields.

## Ruling

There is exactly **one canonical Claude Worker preflight executable and one contract family**:

```text
ops/executive_os/claude-worker-preflight.py
tests/test_claude_worker_preflight.py
contract family = mastermind.claude_worker_preflight
```

OCR-1 V3 owns the first implementation because its provider-work-free realm/auth falsifier precedes PF1. PF1 Task 4 is not a second implementation task.

The historical Operator Continuity path/schema names:

```text
ops/executive_os/claude-native-realm-preflight.py
tests/test_claude_native_realm_preflight.py
mastermind.claude_native_realm_preflight.v1
```

are **SUPERSEDED_BEFORE_IMPLEMENTATION / DO NOT CREATE**.

## V1 is a closed realm/auth readiness wire

OCR-1 V3 implements:

```text
schema = mastermind.claude_worker_preflight.v1
execution_context = INTERACTIVE_PRINCIPAL | WORKER_BROKER
```

The closed V1 receipt contains only allowlisted non-secret fields:

```text
schema
realm_label
host_ref
os_principal_ref
observed_at
claude_binary_sha256
claude_version
auth_ready
auth_method
api_provider
auth_identity_confidence
macos_credential_isolation_basis
execution_context
worker_id          # nullable for INTERACTIVE_PRINCIPAL
quota_class        # nullable for INTERACTIVE_PRINCIPAL
verdict
reason_codes
```

Allowed verdicts are implemented as one exact closed vocabulary including at minimum:

```text
INTERACTIVE_AUTH_READY
WORKER_CONTEXT_AUTH_READY
LOGIN_REQUIRED
NATIVE_AUTH_NOT_SELECTED
WORKER_CONTEXT_AUTH_UNAVAILABLE
EXECUTION_CONTEXT_UNPROVEN
HOST_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_CONTEXT_MISMATCH
BINARY_UNAVAILABLE
AUTH_STATUS_UNSUPPORTED
```

Aliases or arbitrary provider prose are refused.

## Observation law

Both contexts use the same provider-work-free command allowlist whose V1 floor is:

```text
claude --version
claude auth status
```

No prompt, `-p`, `--print`, Agent SDK query/connect, session create/resume/fork/respawn, tool, MCP, browser or model inference call is permitted in V1 preflight. PF1 remains the first real Claude model/Worker call.

`INTERACTIVE_PRINCIPAL` proves only that the exact accepted principal can observe native Claude auth readiness. It is insufficient for PF1/OCR-4 execution.

`WORKER_BROKER` is produced only through the current dedicated worker broker/service execution-context class and binds the exact Worker/quota realm plus accepted host/principal and binary identity. It never falls back to a Chairman shell or another principal.

The selected auth source must be the intended native claude.ai subscription path under the same reviewed environment composition that the later Worker process will use; a preflight cannot pass by clearing higher-precedence credentials/configuration that PF1 would retain.

## Identity ownership

The preflight consumes accepted opaque `host_ref` / principal identity supplied by existing owners. It does not invent them. If current Capacity Fabric has no accepted concrete host identity beyond `local-unbound`, the truthful receipt is `HOST_IDENTITY_SEAM_UNAVAILABLE`; OCR-1 does not hash hostname/machine UUID to escape the gate.

The preflight never makes native realm readiness equal to provider capacity identity. OCR-2C remains required before automatic capacity placement.

## PF1 reconciliation and versioning law

At PF1 commission time, the historical PF1 Task 4 is interpreted as:

```text
reuse current accepted ops/executive_os/claude-worker-preflight.py
consume mastermind.claude_worker_preflight.v1 for native realm/auth readiness
require WORKER_CONTEXT_AUTH_READY
add no second preflight executable/schema family
perform no login/credential handling inside the probe
```

Historical PF1 fields such as:

```text
requested_model
safe_mode_supported
no_chrome_supported
no_session_persistence_supported
structured_output_supported
```

are **not silently added to V1**. Current first-party Claude documentation also warns that `claude --help` does not enumerate every supported flag, so help-string absence is not a safe generic capability detector.

At PF1 action time, current-source review must decide where each required execution capability is canonically proven:

1. Prefer existing adapter/profile/attestation tests when the fact belongs to the actual launch contract rather than host auth readiness.
2. If a genuinely provider-work-free host preflight observation is still required and the single preflight is the correct owner, evolve the **same executable and contract family** to a separately reviewed version such as `mastermind.claude_worker_preflight.v2`.
3. Never widen the accepted V1 closed object in place.
4. Never create a second Claude preflight executable merely to preserve a historical PF1 field list.

A V2, if ever needed, must define exact provider-supported observation sources, null/unknown semantics, compatibility/migration behavior and tests before implementation. V1 remains valid historical evidence for the fields it actually owns.

## Realm-set verifier reconciliation

OCR-1's pure `claude-realm-set-verify.py` consumes sanitized `mastermind.claude_worker_preflight.v1` receipts. It counts a realm as PF1-executable only with a current `WORKER_CONTEXT_AUTH_READY` receipt. `INTERACTIVE_AUTH_READY` remains provisioning evidence only.

A future preflight V2 may be accepted by the realm verifier only through an explicit versioned compatibility rule; do not assume superset JSON compatibility.

## No-rebuild fences

- No second Claude preflight script, daemon, auth service, host registry or readiness database.
- No in-place widening of an accepted closed preflight version.
- No provider credentials, Keychain contents, account PII or token fingerprints in receipts.
- No provider model call merely to make a preflight look stronger.
- No host/principal identity minted locally.
- No capacity normalization/selection in the preflight.
- No Slack/native-app identity used as Worker/realm identity.

## Acceptance

This amendment is satisfied when OCR-1 implements V1 test-first, source census shows no competing Claude preflight executable/schema family, worker-context readiness is separately provable from interactive readiness, PF1 later reuses the same seam, and any future capability-field expansion follows an explicit versioned contract rather than silently mutating V1.