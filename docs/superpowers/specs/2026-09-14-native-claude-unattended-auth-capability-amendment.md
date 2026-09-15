# Native Claude Unattended Authentication Capability Amendment

**Date:** 2026-09-15  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Authority correction:** current provider documentation and installed-version observations are evidence for future requalification; they do **not** silently supersede protected PF1/OCR-1 authentication source law.

## Why this amendment exists

Cruise-mode autonomy adds requirements the realm/capacity contract alone cannot satisfy: a native Claude realm must survive process/host restart, remain on the intended subscription credential source, and surface credential failure before work is silently stranded.

Current Claude Code supports more than one subscription-auth mechanism, and recent versions expose stronger config-directory behavior than older source-law research observed. Those provider facts are useful, but Mastermind already has a narrower accepted first-production boundary. Family B must compose with that boundary first and requalify alternatives explicitly later.

## Current protected production auth law wins

Protected Mastermind source law freezes the first production Claude realm as:

```text
one opaque Executive/Capacity realm
+ one accepted host_ref
+ one dedicated OS principal
+ one macOS Keychain credential realm under that principal
+ one exact reviewed Claude Code binary/profile
+ native claude.ai subscription /login
+ worker-context proof that native Claude.ai auth wins credential precedence
```

Current protected `ops/executive_os/claude-worker-preflight.py` reinforces that law:

- public isolation basis includes `OS_PRINCIPAL_KEYCHAIN`;
- it allows only bounded `--version` and `auth status` observations;
- it rejects higher-precedence provider/API/cloud auth inputs including `CLAUDE_CODE_OAUTH_TOKEN`;
- it emits host/principal/auth readiness only and performs no login or model work.

Therefore **B6's first real native Claude canary remains `/login` + dedicated OS principal/Keychain** unless a separate accepted provider-source-law amendment explicitly changes that rule.

## What current provider evidence changes — and does not change

### `/login`

Current Claude Code documentation still makes `/login` the broad Claude.ai subscription credential. It supports richer provider-native capabilities such as Claude-in-Chrome that are unavailable to narrower token modes, subject to separate BrowserResource/OCR-4A gates.

Recent first-party documentation also says `CLAUDE_CONFIG_DIR` participates in credential storage/keying, and installed Studio Claude Code 2.1.259 showed a basic discriminator where the default config was logged in while a fresh alternate config was logged out. That is useful falsifier/requalification evidence.

It is **not** current Mastermind production proof that multiple config roots under one macOS user are independent durable credential realms across refresh, reboot, Keychain lock/unlock and concurrent use. Historical provider issue evidence shows this behavior has changed across Claude Code versions.

Accordingly:

- `CLAUDE_CONFIG_DIR` may be a host-local execution/config custody input;
- it is not canonical provider account identity;
- `config_custody_ref` in Family-B V2 is an opaque non-secret custody coordinate, not proof of independent authentication;
- on the first accepted macOS production path, `config_custody_ref` cannot substitute for the dedicated OS-principal/Keychain isolation basis.

### `claude setup-token`

Current provider documentation describes `claude setup-token` as a long-lived subscription OAuth mechanism intended for scripts/CI. It can support model requests and some local tool use, but has a narrower capability set than `/login`; for example Chrome and Remote-Control-style claude.ai surfaces are not generally equivalent.

`CLAUDE_CODE_OAUTH_TOKEN` also outranks saved `/login` credentials in auth precedence, so injecting it into a richer `/login` realm can silently change the credential mode.

Protected PF1/OCR-1 source law currently rejects setup-token/token injection as the default production worker mechanism. Family B therefore records setup-token only as a **future requalification candidate**, not an admitted B6 credential mode.

Do not:

- run `claude setup-token` under this architecture wave;
- read Macro `CLAUDE_CODE_OAUTH_TOKEN_N` values for Executive worker use;
- globally inject `CLAUDE_CODE_OAUTH_TOKEN`;
- treat setup-token as a second capacity identity or extra quota;
- weaken the current `/login` OS-principal boundary merely because setup-token has attractive lifetime characteristics.

## Generation and identity composition

Authentication mode/custody is execution evidence, not provider quota identity.

Family B uses:

```text
capacity_capability_id + capability_generation
  Macro Shared AI Provider Control provider-domain identity

host_ref + capacity_capability_id + realm_generation
  Mastermind provider-realm enrollment/custody identity
```

The current canary `capacity_generation` remains a separate CapacityOwnerFact generation and is not provider subscription identity.

A credential mechanism never mints another `capacity_capability_id`, proves cross-domain quota independence, or authorizes placement by itself.

## Secret custody boundary

No credential mode changes the existing secret law:

- no token value/hash/fingerprint, account email/id/org, Keychain label, raw config path or reversible account fingerprint in GitHub, Agent OS, Slack, Capacity snapshots, Worker prompts or model-visible receipts;
- login/logout/setup-token creation are provisioning-owner operations, not Worker tool actions;
- ambiguous auth mutation remains on the same custody and is reconciled before any retry/rebind;
- preflight and real provider process must share the same reviewed environment-composition law, so a preflight cannot “pass” by temporarily hiding a stronger credential source that the Worker later inherits.

## Composition with canonical host recovery readiness

Family B consumes `mastermind.host_recovery_readiness/v1`; it does not create a Claude-specific power/reboot/FileVault/Remote-Login plane.

For the first accepted `/login` realm:

```text
HOST_RECOVERY_READY
  physical host is READY under the canonical role/profile

CLAUDE_COLD_BOOT_AUTH_READY
  after real boot/startup, the exact host + OS principal +
  capacity_capability_id/capability_generation + realm_generation
  passes the bounded native Claude worker-context auth preflight without Chairman interaction
```

Canonical host roles remain:

- Studio while it is Executive control host: `executive-control-host/v1`;
- M1/M6/other worker Macs: `home-mac-recovery-base/v1`.

Physical host recovery does not prove provider auth. Provider auth does not prove physical/network recovery. External reachability remains separately owned.

## Cruise-mode acceptance gates

Before a native Claude realm is called unattended-production eligible, require separate real evidence:

```text
RESTART_AUTH_PASS
  restart provider process under the same provider capability + realm generations and prove worker-context auth remains ready

COLD_BOOT_AUTH_PASS
  compose canonical HOST_RECOVERY_READY with a real post-boot Claude auth/readiness canary under the same OS principal/realm

AUTH_PRECEDENCE_PASS
  prove stronger API/cloud/token/profile sources cannot silently move execution off the admitted native subscription

EXPIRY_OBSERVABILITY_PASS
  prove healthy versus expired/not-ready can be observed without PII/secret inspection;
  expiring-soon is emitted only if a supported bounded source actually reports it

REALM_ISOLATION_PASS
  prove the selected production isolation basis survives concurrent use, refresh and restart without cross-realm credential collision

CAPABILITY_MODE_PASS
  prove later credential/surface profiles cannot be routed to capabilities they do not support
```

The earlier bounded Studio check of Claude Code 2.1.259 `auth status --json` exposed no machine-readable expiry timestamp. Therefore `expiring_soon` remains unknown under the current preflight; do not derive it from credential material or guessed login age.

## First-production preference

For B6 under current protected law:

```text
credential = native /login
isolation = dedicated OS principal + macOS Keychain
config custody = exact reviewed worker configuration under that principal
setup-token = NOT ADMITTED
same-user multi-config realm fanout = NOT ADMITTED as production isolation proof
```

This may be operationally heavier, but it is the current accepted security boundary and is compatible with the multi-Mac fleet. It is preferable to ship honest fewer realms than falsely count several config directories as independent production realms.

## Future auth-source requalification wave

After Family B core identity/capacity architecture is protected—or earlier only if it becomes a genuine B6 blocker—Sol may commission one bounded **Claude auth-source requalification** wave. It must not be hidden inside B1-B5.

The wave may evaluate:

1. installed-version `CLAUDE_CONFIG_DIR` Keychain namespacing across two controlled realms;
2. concurrent refresh/collision behavior;
3. restart and real cold-boot behavior;
4. Keychain locked/unlocked/headless security-session behavior;
5. setup-token secret custody, renewal/expiry and capability restrictions;
6. auth-precedence interaction with `/login`;
7. whether current preflight/isolation vocabulary needs a versioned successor;
8. whether a same-OS-principal multi-config mechanism can ever meet the existing isolation/threat model.

Only an explicit accepted source-law amendment may then admit a new production isolation/auth profile. Even then, extra credential modes or config roots never create extra quota.

## No effect

This amendment performs no login, setup-token generation, Keychain/file mutation, provider call, process restart, host reboot, route activation, Worker launch, browser/GUI action or runtime change.