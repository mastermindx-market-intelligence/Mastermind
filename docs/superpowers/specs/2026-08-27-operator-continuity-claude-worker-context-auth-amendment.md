# Operator Continuity — Claude Auth Must Be Proven in the Actual Worker Execution Context

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This adds a required host falsifier after current provider-source research exposed a gap between interactive macOS login and unattended worker execution.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, compatible Skillpack v1.0.0 / bootstrap major 1.  
**Affected waves:** OCR-1 V2, PF1 Claude Worker, OCR-4 sustained Claude, later Claude realm provisioning.

## 1. New falsifier

The accepted Claude V1 source law correctly prefers native subscription login in the dedicated worker principal's macOS Keychain. That does not by itself prove the unattended worker execution path can use the credential.

Current upstream Claude Code reports include at least these relevant macOS falsifiers:

- `anthropics/claude-code#77213`: `claude -p` reports not logged in when the process tree starts at launchd even though the same user/keychain credential works interactively;
- `anthropics/claude-code#88434`: current Keychain lookup can depend on the `USER` environment variable, so a deliberately minimal environment may make valid native auth appear absent;
- concurrent Keychain/auth-refresh issues such as `#80085` reinforce that exact installed-version/process-context proof is required rather than inferred from an interactive session.

These upstream issues are **adverse evidence/falsifiers**, not Mastermind authority and not proof every installed version/host fails. The response is to test the real worker context and fail closed.

## 2. Frozen ruling

A Claude realm is not routable merely because:

```text
native claude auth login completed interactively
claude auth status works in Terminal
Claude desktop/app is logged in
Keychain item exists
OCR-1 host/principal identity is distinct
```

Before PF1 or any sustained Claude adapter may make a real Worker call, Mastermind must prove **auth readiness from the same execution context class that will run provider work**.

For the current architecture this means a bounded preflight launched through the actual dedicated Worker broker/service principal and materially equivalent service ancestry/environment, with no provider work prompt.

The result must distinguish:

```text
INTERACTIVE_AUTH_READY
WORKER_CONTEXT_AUTH_READY
WORKER_CONTEXT_AUTH_UNAVAILABLE
EXECUTION_CONTEXT_UNPROVEN
```

Only `WORKER_CONTEXT_AUTH_READY` can release real provider execution.

## 3. Environment law

A minimal environment remains required to prevent secret inheritance, but "minimal" must not mean "break provider-native identity semantics."

The reviewed Claude worker environment may include non-secret OS identity/runtime variables proven necessary by the installed provider version, for example:

```text
HOME
USER
LOGNAME
TMPDIR
PATH (fixed reviewed safe value)
locale variables as needed
```

Each value must be derived from the exact current worker principal/process composition, not caller/model text.

Provider/auth secret variables remain forbidden:

```text
ANTHROPIC_API_KEY
ANTHROPIC_AUTH_TOKEN
CLAUDE_CODE_OAUTH_TOKEN
Slack/GitHub/Executive secret values
```

OCR-4's helper environment and PF1's foreground process environment must share the same reviewed non-secret identity-variable law rather than independently inventing allowlists.

## 4. OCR-1 correction

OCR-1 remains provider-work-free. It now has two levels of readiness:

### Host/principal/native-login readiness

Read-only probe executed as/against the exact candidate principal confirms:

```text
canonical host/principal identities
exact Claude binary/version
auth status ready in an allowed local context
```

This is necessary but not sufficient for routing.

### Worker-context auth readiness

After the relevant worker broker/service composition exists, a read-only broker operation or an exact service-shaped preflight executes only version/auth-status capability under the real worker context and returns a secret-free receipt.

If current architecture has no way to run that read-only preflight without arming provider work, add one bounded **read-only** broker/preflight seam under the same existing worker service. Do not send a model turn to test auth.

## 5. PF1/OCR-4 release gate

PF1's first real `claude -p` provider call and OCR-4's Agent SDK `connect` preflight both require a fresh `WORKER_CONTEXT_AUTH_READY` receipt for the exact:

```text
Worker / quota realm
host_ref
OS principal
Claude binary/version/profile
service/broker execution context
```

A receipt from another shell/user/process ancestry cannot substitute.

If interactive auth is ready but worker-context auth fails, classify the realm:

```text
DARK_OR_DISCONNECTED / WORKER_CONTEXT_AUTH_UNAVAILABLE
```

and return to Sol before provider execution. Do not copy credentials, read Keychain values, inject setup tokens or run provider work from the Chairman's interactive shell as a workaround.

## 6. Provisioning consequence

Do **not** bulk-provision five macOS Claude service users/brokers before one exact native-realm worker context has passed this falsifier on the intended host/service pattern.

Recommended sequence:

```text
one candidate native Claude realm
-> exact worker-context auth preflight
-> PF1 real one-shot proof
-> only then scale the accepted host/principal/service pattern to additional Claude realms
```

If macOS LaunchDaemon/native-Keychain execution is unsupported on the installed version, Sol must choose a separately reviewed supported topology (for example a user-session worker pattern or another OS/host/provider-supported auth mechanism). Do not silently redesign the service boundary inside an implementation wave.

## 7. No-rebuild proof

This amendment adds no credential daemon, Keychain reader, token cache, login manager or auth database. It requires the provider itself to prove native auth from the actual worker context and preserves credentials as provider-owned state.
