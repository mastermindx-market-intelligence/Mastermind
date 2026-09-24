# Operator Continuity — Realm Preflight Must Not Execute a Model Turn

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This closes a predecessor-boundary defect found during Sol review of OCR-1 V2.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, compatible `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1.  
**Affected plan:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-native-realm-isolation-v2.md`  
**Existing provider predecessor preserved:** `docs/superpowers/plans/2026-08-27-hybrid-workforce-pf1-claude-worker.md`.

## 1. Defect found

OCR-1 V2 correctly narrowed Claude realm identity to native host + OS principal + Keychain/login realm, but its first draft still proposed a harmless `claude -p` health turn during realm census.

That is unnecessary for identity/isolation proof and would cause OCR-1 to become the first real Claude model-execution path before PF1, blurring the accepted provider rollout boundary.

## 2. Ruling

**OCR-1 V2 is strictly provider-work-free.**

A realm preflight may execute only read-only/native metadata and authentication-readiness commands proven by the installed provider version, such as:

```text
claude --version
claude auth status
bounded help/capability introspection when needed
```

It must not send a prompt, run a model turn, create a Claude session, invoke tools/MCP/browser, consume a provider work result or claim an Executive Job.

PF1 remains the first wave that proves a real subscription-backed Claude worker/model call through the accepted Executive Worker Harness.

## 3. OCR-1 wire correction

The public `mastermind.claude_native_realm_preflight.v1` receipt must not carry `workspace_probe_ok` or any model-turn result.

Its accepted readiness evidence is limited to closed non-secret facts such as:

```text
schema
realm_label
host_ref
os_principal_ref
observed_at
claude_binary_sha256
claude_version
auth_ready
auth_method (only if safely allowlisted)
auth_identity_confidence
macos_credential_isolation_basis
verdict
reason_codes
```

A future provider version may require a different exact read-only auth command; that is an installed-version preflight concern, not permission to use a work prompt.

## 4. Realm-set acceptance meaning

`DISTINCT_NATIVE_REALMS` means only:

- the intended opaque realm labels map to distinct accepted host/OS-principal authentication realms by construction;
- each candidate principal has a real installed Claude binary/profile and reports native auth readiness;
- no config-directory/account-PII/token shortcut was used;
- the receipts are current and secret-free.

It does **not** prove:

- a model call succeeds;
- exact requested model availability;
- subscription quota/headroom;
- Executive Worker claim/execution;
- PF1/HF1/CF2 production readiness.

Those remain separate owner proofs.

## 5. Explicit OCR-1 plan supersession

In `2026-08-27-operator-continuity-ocr1-native-realm-isolation-v2.md`, supersede:

- Task 1 receipt field `workspace_probe_ok`;
- Task 1 Step 5 `Implement harmless local workspace health turn`;
- Task 1 hostile tests for provider work-turn quota/rate-limit behavior insofar as they require a model prompt.

Replace with tests proving **zero model/provider work invocation**: subprocess argv allowlist permits only version/auth/read-only capability commands, and spies/AST/source fences prove no `-p`, `--print`, prompt, Agent SDK query or equivalent model-turn path exists in OCR-1 preflight.

## 6. No-rebuild proof

No new provider probe service is authorized. OCR-1 remains a bounded, read-only host/admin falsifier. PF1 owns first real Claude Worker execution.
