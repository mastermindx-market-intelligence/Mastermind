# Operator Continuity — Single Claude Worker Preflight Owner Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** CHAIRMAN-APPROVED ARCHITECTURE PROGRAM / CONTROLLING NARROW AMENDMENT. Records only.  
**Applies to:** OCR-1 V2, PF1 Claude Worker Task 4, OCR-4 worker-context auth, OCR-8 realm acceptance.  
**Protected source-law basis at ruling:** `Mastermind@ac1c045ed4cdf0b2b87fbc81760effa909271436`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1.

## Problem

The pre-existing PF1 Claude Worker implementation plan already reserved a future provider preflight path:

```text
ops/executive_os/claude-worker-preflight.py
tests/test_claude_worker_preflight.py
```

OCR-1 V2 was drafted later with a second path named `claude-native-realm-preflight.py`. Both would observe the same Claude binary/auth/runtime readiness boundary. Building both would create duplicate provider-preflight semantics, contradictory readiness receipts and an avoidable second identity seam.

Neither implementation exists on current protected Mastermind. Therefore the conflict must be resolved before either wave is commissioned.

## Ruling

There is exactly **one canonical Claude Worker preflight executable and one contract family**:

```text
ops/executive_os/claude-worker-preflight.py
tests/test_claude_worker_preflight.py
schema = mastermind.claude_worker_preflight.v1
```

OCR-1 V2 owns the first implementation because its provider-work-free realm/auth falsifier precedes PF1. PF1 Task 4 is not a second implementation task; when PF1 is released it consumes/extents the already-landed canonical preflight only if a separately reviewed PF1 capability requirement is absent from the accepted contract.

The older OCR-1 plan references to:

```text
ops/executive_os/claude-native-realm-preflight.py
tests/test_claude_native_realm_preflight.py
mastermind.claude_native_realm_preflight.v1
```

are **SUPERSEDED_BEFORE_IMPLEMENTATION / DO NOT CREATE**.

## One contract, two observation contexts

The preflight wire includes an exact execution-context discriminator rather than minting another schema:

```text
execution_context = INTERACTIVE_PRINCIPAL | WORKER_BROKER
```

The closed V1 receipt is the OCR-1 source law and contains only allowlisted non-secret fields:

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
auth_identity_confidence
macos_credential_isolation_basis
execution_context
worker_id          # nullable for INTERACTIVE_PRINCIPAL
quota_class        # nullable for INTERACTIVE_PRINCIPAL
verdict
reason_codes
```

Allowed verdicts include:

```text
INTERACTIVE_AUTH_READY
WORKER_CONTEXT_AUTH_READY
LOGIN_REQUIRED
WORKER_CONTEXT_AUTH_UNAVAILABLE
EXECUTION_CONTEXT_UNPROVEN
HOST_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_IDENTITY_SEAM_UNAVAILABLE
PRINCIPAL_CONTEXT_MISMATCH
BINARY_UNAVAILABLE
AUTH_STATUS_UNSUPPORTED
```

Exact final vocabulary is implemented closed/test-first; aliases or arbitrary provider prose are refused.

## Observation law

Both contexts use the same provider-work-free command allowlist:

```text
claude --version
claude auth status
```

No prompt, `-p`, `--print`, Agent SDK query/connect, session create/resume/fork/respawn, tool, MCP, browser or model inference call is permitted in this preflight. PF1 remains the first real Claude model/Worker call.

`INTERACTIVE_PRINCIPAL` proves only that the exact accepted principal can observe native Claude auth readiness. It is insufficient for PF1/OCR-4 execution.

`WORKER_BROKER` is produced only through the current dedicated worker broker/service execution-context class and must bind the exact Worker/quota realm plus accepted host/principal and binary/profile identity. It never falls back to a Chairman shell or another principal.

## Identity ownership

The preflight consumes accepted opaque `host_ref` / principal identity supplied by existing owners. It does not invent them. If current Capacity Fabric has no accepted concrete host identity beyond `local-unbound`, the truthful receipt is `HOST_IDENTITY_SEAM_UNAVAILABLE`; OCR-1 does not hash hostname/machine UUID to escape the gate.

The preflight never makes native realm readiness equal to provider capacity identity. OCR-2C remains required before automatic capacity placement.

## PF1 reconciliation

At PF1 commission time, the current PF1 plan's Task 4 must be read as:

```text
reuse current accepted ops/executive_os/claude-worker-preflight.py
require WORKER_CONTEXT_AUTH_READY
add no second preflight executable/schema
perform no login/credential handling inside the probe
```

If PF1 needs additional provider binary capability observations for the first foreground worker call, extend the same contract only after current-source review and only when those fields are non-secret, deterministic and still provider-work-free. Do not fork a new preflight merely because the historical plan listed a smaller field set.

## Realm-set verifier reconciliation

OCR-1's pure `claude-realm-set-verify.py` consumes sanitized `mastermind.claude_worker_preflight.v1` receipts. It counts a realm as PF1-executable only with a current `WORKER_CONTEXT_AUTH_READY` receipt. `INTERACTIVE_AUTH_READY` remains provisioning evidence only.

## No-rebuild fences

- No second Claude preflight script, daemon, auth service, host registry or readiness database.
- No provider credentials, Keychain contents, account PII or token fingerprints in receipts.
- No provider call merely to make a preflight look stronger.
- No host/principal identity minted locally.
- No capacity normalization/selection in the preflight.
- No Slack/native-app identity used as Worker/realm identity.

## Acceptance

This amendment is satisfied when OCR-1 implements the single canonical preflight test-first, PF1 later reuses it, worker-context readiness is separately provable from interactive readiness, and source census shows no competing Claude preflight executable/schema.