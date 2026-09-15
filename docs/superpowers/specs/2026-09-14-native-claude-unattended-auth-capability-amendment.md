# Native Claude Unattended Authentication Capability Amendment

**Date:** 2026-09-14  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`

## Why this amendment exists

Cruise-mode autonomy adds a requirement the realm/capacity contract alone cannot satisfy: a native Claude realm must still authenticate after ordinary process restarts and the fleet must surface credential expiry before work stalls. Current Claude Code documentation exposes two materially different direct-subscription credential modes. They must not be treated as interchangeable merely because both consume a Pro/Max subscription.

## Provider-supported credential modes

### Interactive subscription login

`/login` (or first-run login) is the normal Pro/Max Claude.ai credential. On macOS Claude Code stores credentials in the encrypted Keychain. If the Keychain rejects a write, such as in a locked SSH session, Claude Code documents a fallback to `<CLAUDE_CONFIG_DIR>/.credentials.json` (or `~/.claude/.credentials.json`) with mode `0600`. `CLAUDE_CONFIG_DIR` also keys the Keychain entry, so different config roots select different credential entries.

This login is the broad feature credential. Chrome integration explicitly requires `/login`. Provider-native background sessions and Remote Control can use it, subject to their own feature and session gates.

The login is not perpetual. Claude Code warns when a saved login is within three days of expiry, and once a login expires and cannot refresh, model requests fail until `/login` is renewed. Provider documentation explicitly warns that long-running background and Remote Control sessions stop making progress when this happens.

A read-only check of the currently installed Studio Claude Code 2.1.259 `auth status --json` schema exposed only these field names: `analyticsDisabled`, `apiProvider`, `authMethod`, `email`, `loggedIn`, `orgId`, `orgName`, `projectsDirectory`, and `subscriptionType`. The check emitted field names only; no PII values were recorded. There is **no machine-readable expiry field in the current installed auth-status contract**, so preflight cannot honestly predict the provider's three-day expiry warning from this command. Until a reviewed supported expiry signal exists, `expiring_soon` remains unknown; Provider Control may observe explicit provider warnings or failed/expired outcomes through a separate bounded source, but must not derive expiry from token contents, Keychain material, account PII, or guessed login age.

### Long-lived setup token

`claude setup-token` produces a one-year OAuth token for Pro/Max/Team/Enterprise subscriptions and is intended for CI, scripts and environments without interactive browser login. Claude Code does not save it; the runtime receives it as `CLAUDE_CODE_OAUTH_TOKEN`.

This token is **model-request-only**. Local MCP servers may still work, but it cannot establish Remote Control or fetch claude.ai connectors. Claude-in-Chrome explicitly stays disabled for setup-token authentication even if `--chrome` is passed.

`CLAUDE_CODE_OAUTH_TOKEN` ranks above saved `/login` credentials in Claude Code authentication precedence. Therefore a token must never be placed globally in a shell profile, launchd parent environment or shared settings file for a realm that is expected to retain `/login`-only capabilities.

## Frozen capability ruling

Authentication mode is an execution capability, not a quota/account identity.

Family B continues to use one Provider-Control-owned `capacity_capability_id + realm_generation` coordinate. The selected worker/operator binding must additionally prove the credential mode required by the task. No credential mode can mint another capacity identity or assert quota independence.

The initial implementation may support one or both profiles:

```text
CLAUDE_HEADLESS_SUBSCRIPTION
  auth: /login OR reviewed setup-token custody
  use: bounded model/tool Worker turns
  Chrome: not assumed
  Remote Control: not assumed
  computer use: not assumed

CLAUDE_INTERACTIVE_SUBSCRIPTION
  auth: /login
  use: persistent Operator sessions
  Chrome: separately eligible after BrowserResource proof
  Remote Control: separately eligible after OCR-4A proof
  computer use: separately eligible after host-resource proof
```

A setup-token-backed process can never satisfy an operation requiring Chrome or Remote Control. A `/login` realm does not become unattended merely because authentication works before a reboot.

## Secret custody boundary

Neither OAuth credential mode changes the existing secret law:

- no token value, token hash/fingerprint, account email/id/org, Keychain label, or raw config path in GitHub, Agent OS, Slack, Capacity snapshots, Worker prompts or model-visible receipts;
- `CLAUDE_CODE_OAUTH_TOKEN`, when admitted, is injected only inside the exact selected provider process after placement/admission and never on argv;
- ordinary Worker/Operator tool policy denies auth-changing commands; login/logout/setup-token creation are provisioning-owner operations;
- ambiguous auth mutation is reconciled on the same custody; it is never retried by changing accounts.

## Composition with canonical host recovery readiness

Protected Mastermind advanced during this architecture wave with the accepted `mastermind.host_recovery_readiness/v1` read-only departure gate. Family B consumes that owner rather than creating a second cold-boot or fleet-recovery checker.

For an unattended native Claude realm, `COLD_BOOT_AUTH_PASS` requires **both**:

```text
HOST_RECOVERY_READY
  correct `mastermind.host_recovery_readiness/v1` role/profile is READY for the physical host

CLAUDE_COLD_BOOT_AUTH_READY
  after an actual boot/startup path, the exact worker principal + capability generation + credential custody
  can authenticate and run the bounded native Claude readiness/canary without Chairman interaction
```

The canonical host recovery roles remain authoritative:

- Studio, while it is the canonical Executive control host: `executive-control-host/v1`;
- M1, future M6, and other worker/capacity Macs: `home-mac-recovery-base/v1`.

The base host-recovery profile explicitly proves physical/local recoverability only; it is **not** Worker/Fabric/provider acceptance. Conversely, a working Claude credential does not prove the Mac will recover after power loss, FileVault preboot, or Remote Login failure. Family B must compose both pieces and must not add a Claude-specific replacement for host power/reboot/FileVault/Remote-Login readiness.

Network/bastion/tunnel reachability remains a separate accepted journey as the host-recovery owner already states. A READY local host plus an unreachable external path is not cruise-ready.

## Cruise-mode acceptance gates

Before any native Claude realm is counted as unattended-production eligible, require separate evidence for:

```text
RESTART_AUTH_PASS
  kill/restart the provider process under the same realm generation and prove auth remains usable

COLD_BOOT_AUTH_PASS
  compose HOST_RECOVERY_READY with a real post-boot Claude auth/readiness canary for the same host/principal/realm

EXPIRY_OBSERVABILITY_PASS
  prove provider-health observation distinguishes healthy from expired/not-ready without provider PII;
  expiring-soon may be emitted only when a supported bounded source actually reports it

AUTH_PRECEDENCE_PASS
  prove an injected stronger credential source cannot silently move the realm off the admitted subscription mode

CAPABILITY_MODE_PASS
  prove setup-token cannot be routed to Chrome/Remote-Control-required work and `/login` capability claims remain
  separately gated by BrowserResource/OCR-4A rather than inferred from auth presence
```

A green source test is not any of these production receipts.

## Initial preference

Do **not** choose setup-token or Keychain-backed `/login` globally in architecture. B6 provisioning should run the smallest real unattended-auth canary and choose the narrowest supported custody mode that satisfies the lane:

- bounded headless workers may prefer `setup-token` if its one-year lifetime and process-local custody materially improve restart reliability;
- persistent/browser operators require `/login` for the richer provider-native surfaces;
- if a `/login` realm can pass cold-boot unattended proof under the dedicated principal using provider-supported storage, it may serve both headless and interactive roles and avoid a second credential modality.

Any later attempt to bind multiple credential modes to one underlying subscription must be conservative: it may share one Provider-Control capability/quota domain when explicitly provisioned that way, but it can never create extra aggregate quota from extra credentials.

## No effect

This amendment performs no login, setup-token generation, Keychain/file mutation, provider call, process restart, host reboot, route activation, Worker launch, browser/GUI action or runtime change.