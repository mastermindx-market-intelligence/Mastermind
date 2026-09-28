# Native Claude Unattended Authentication Capability Amendment

**Date:** 2026-09-15  
**Parent operation:** `ocr2c-family-b-native-claude-realm-capacity-architecture-20260914-sol-001`  
**Status:** `RECORDS ONLY / SPEC_ONLY / PRODUCTION INERT`  
**Authority correction:** current provider documentation and installed-version observations are evidence for future requalification; they do **not** silently supersede protected PF1/OCR-1 authentication source law.


## 2026-09-27 unattended permission-mode requalification

Native Claude Worker autonomy is a property of the canonical worker launch contract,
not a remembered interactive-user preference or project-local setting. Executive
workers launch noninteractively with `-p --permission-mode dontAsk`.
The serialized policy must keep `permissions.ask = []`,
`permissions.defaultMode = "dontAsk"`, and
`disableBypassPermissionsMode = "disable"`; hooks and project MCP discovery are
also disabled. Claude Code's `dontAsk` contract converts every action that would
otherwise request permission into a deterministic refusal, so a headless worker
never waits for Chairman input.

Do not replace this profile with `bypassPermissions` merely to remove prompts.
Claude Code documents that allow rules have no effect in bypass mode. This worker's
reviewed authority-to-tool projection uses narrow allow rules, including scoped
file-edit grants, so bypass could silently widen the effective write surface.
`dontAsk` preserves those grants while refusing everything outside them.

Existing protected-path denies, exact-model fencing, no-network sandbox,
fail-if-sandbox-is-unavailable behavior, no session persistence, and explicit
MCP/subagent/Web tool denials remain controlling. `AskUserQuestion` and
`ExitPlanMode` are explicitly denied in the worker tool policy. Interaction-
requiring MCP calls and other would-be prompts are refusals, not Chairman gates;
the worker must replan or return through the existing Job/Attempt lifecycle.

No new permission broker, approval queue, retry plane, lifecycle, identity, or
credential owner is created here. This source amendment is a durability contract,
not by itself installed-host or production proof; the exact accepted head still
requires normal source checks/review and a real worker-path canary before the
capability is called live.

## 2026-09-27 native storage requalification

This delivery amendment supersedes the Keychain-only **storage** requirement in
this document's historical baseline below. It preserves a dedicated OS principal,
one isolated persistent provider home/config directory, native `auth login --claudeai`,
credential-precedence checks, and the existing canonical host/principal owner.
It does not admit setup-token, API credentials, copied credentials, or several
account realms sharing one mutable auth file.

The first-party [credential management documentation](https://code.claude.com/docs/en/authentication#credential-management)
now documents native macOS OAuth fallback to a mode0600 `.credentials.json` when
Keychain rejects a write, and `CLAUDE_CONFIG_DIR` namespacing of both stores. Claude
Code alone creates and refreshes that file; Executive does not read its contents,
seed it from another account, or replace it after refresh.

The canonical preflight adds `observe_native_credential_storage`: a metadata-only,
no-follow directory-descriptor walk on canonical absolute coordinates. The dedicated
home and `.claude` directory must be mode0700 and owned by the bound principal;
a file observation requires a mode0600, single-link regular file with that owner.
A missing file yields `UNKNOWN`, never an inferred Keychain proof. The observer
never opens the credential file for reading: it uses a metadata-only handle
and the existing filesystem ACL observer, refusing extended ACLs. `OS_PRINCIPAL_NATIVE_PRIVATE_FILE` is an allowed
isolation-basis value, not an enrollment or readiness grant. File presence does
not identify which native credential store the CLI selected. Native auth status
must separately establish claude.ai/firstParty in the actual worker context.

The installed CLI2.1.275 additionally requires OS username environment for native
macOS credential lookup: the same closed environment reported logged out without
USER/LOGNAME and native authenticated with them. Preflight derives those fields
from `pwd.getpwuid(os.geteuid())`, never caller-supplied account names. Its exact
`auth status --json` wire includes safe-mode diagnostics and organization aliases;
these are validated as bounded discard-only inputs and never enter public receipts.

This source amendment alone does not prove a production realm, token renewal,
concurrent-account isolation, restart or cold-boot recovery. The unchanged
worker-context, precedence, expiry, isolation and recovery gates below still need
actual evidence. It does not remove the canonical identity-owner refusal or
create another identity authority. Runtime owns connecting that existing seam.

## Historical baseline (2026-09-15)

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