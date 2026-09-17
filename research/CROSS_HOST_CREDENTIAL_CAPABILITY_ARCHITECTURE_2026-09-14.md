# Cross-host credential capability architecture — hardened design freeze

Status: **DRAFT / RECORDS_ONLY / SPEC_ONLY / PRODUCTION_INERT**  
Authoring base: protected `bffe2ca8506346ea278c8ee469bf1ac30a4de008`  
Skillpack: `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1  
Date: 2026-09-14

## 1. Chairman outcome

Web CEO sessions and local operators must be able to complete approved work that requires API keys, OAuth sessions, provider logins, browser credentials, or machine-local privileged capabilities without stopping to ask the Chairman to find, paste, copy, or manually route secrets.

The target is **full autonomous credential use, not full model-visible secret disclosure**. An agent should discover that `openai.organization.tunnels.admin` is available, invoke it through the normal authority path, and receive a useful result. It should not need to know whether the underlying credential is a Keychain password, OAuth refresh token, browser session, service-account token, native client session, or remote capability proxy.

This program must work across multiple Macs whose credentials can have different semantics:

- the same external API key may lawfully be usable from several computers;
- two computers can use identical password bytes while those passwords still represent two different host-local administrative authorities;
- two computers can represent the same external account but hold different OAuth refresh tokens or browser sessions;
- some credentials are device-bound and must never be copied;
- some credentials are shared static secrets and should have one logical source of truth;
- some actions should not use a password at all because a fixed privileged actuator is safer.

## 2. Current estate and why the first sketch was insufficient

Protected Mastermind already contains the correct narrow pattern in several places:

- MAS-115 stores one fixed Multilogin credential through a secret-owning Security.framework helper; the model-visible coordinator never receives the value.
- The live-path helper wires Keychain output through an anonymous pipe into the secret-owning process rather than capturing the value in the coordinator.
- Workbench Action keeps host configuration, generation keys, credentials and absolute roots outside model-selected input.
- PR #613 merged a fixed-action privileged broker specifically to remove recurring administrator-password prompts without granting arbitrary root or storing a reusable sudo password.
- Open PR #633 uses fixed macOS Keychain custody plus a Codex `http_headers_helper` to obtain short-lived Executive Authorization headers rather than copying a ChatGPT credential.

Those are good local precedents, but they do not yet form a fleet-wide credential capability system. The original sketch also left four important questions under-specified:

1. **Credential identity versus secret equality.** Equal bytes do not imply the same authority. Different OAuth tokens can represent the same account.
2. **Cross-host residency and routing.** A caller on one Mac needs to know which host can lawfully service a capability without learning the secret.
3. **Shared-secret lifecycle.** Replicated API keys need generation/rotation semantics so local copies cannot silently drift.
4. **Unattended reboot behavior.** Login-Keychain success while a user session is unlocked is not enough for cruise-grade autonomy; every custody backend must be proven across the intended boot/login/service lifecycle.

## 3. Core ruling: separate five identities

Never model a credential as just `NAME=value`. Every credential use has five distinct identities that must not be collapsed.

### 3.1 Authority principal

`principal_ref` answers: **what authority does this credential ultimately represent?**

Examples:

- one OpenAI organization administrator principal;
- one GitHub account or GitHub App installation;
- one Claude subscription account;
- `root` / local administrator authority on one exact Mac;
- one Auth0 tenant administrator;
- one browser workspace identity.

This is semantic identity. Secret bytes are not identity evidence.

### 3.2 Credential issuance

`credential_ref` answers: **which issued credential is this?**

Examples:

- OpenAI API key generation 7;
- OAuth refresh token issued to the Studio client;
- OAuth refresh token issued separately to Admin Mini;
- local administrator password instance for Studio;
- local administrator password instance for Admin Mini.

Two host-local passwords that happen to contain the same characters remain two credential issuances because they authorize different host principals. We never infer equivalence by hashing or comparing secret material.

### 3.3 Host / runtime binding

`binding_ref` answers: **where and through which trusted runtime may this credential be used?**

A binding may include existing canonical identities for:

- host;
- boot/runtime generation;
- OS service principal;
- provider realm/account slot;
- browser profile;
- native client;
- Workbench channel / Executive Attempt.

The binding is what differentiates `sudo` on Studio from `sudo` on Admin Mini even if the human chose the same password on both machines.

### 3.4 Custody locator

`custody_ref` answers: **which secret-owning mechanism can resolve the material?**

Examples:

- fixed macOS Keychain service/account tuple;
- a native provider CLI session;
- an authenticated browser profile;
- a 1Password or Infisical item reference;
- a root-owned bootstrap identity used only by the credential executor.

The locator is non-secret metadata. The material is never stored in the Mastermind registry/projection.

### 3.5 Agent capability

`capability_ref` answers: **what useful operation may an authorized agent perform?**

Examples:

- `openai.organization.tunnels.list`;
- `openai.organization.tunnels.create`;
- `auth0.client.inspect`;
- `github.repo.publish` under an existing source-writer grant;
- `provider.claude.execute` in a specific worker realm;
- `host.executive.restart` through the privileged broker.

Agents should reason primarily in capabilities, not secret names.

## 4. Equality law: same bytes, same account and same credential are three different claims

The system must preserve these distinctions explicitly.

### Case A — same local password bytes on two Macs

```text
Studio local-admin principal
  -> credential_ref: macos-admin/studio/v3
  -> binding: host=studio

Admin Mini local-admin principal
  -> credential_ref: macos-admin/admin-mini/v2
  -> binding: host=admin-mini
```

Even if both password values are identical, these are **not one shared credential**. Rotation of one host does not imply rotation of the other. Health is independent. The agent never needs to know that the bytes match.

### Case B — one external API key usable from several hosts

```text
OpenAI org-admin principal
  -> credential_ref: openai-org-admin/key-generation-7
      -> binding: Studio
      -> optional binding: Admin Mini
```

This is one logical credential issuance with multiple eligible bindings. All bindings must report the same credential generation, but Mastermind never compares the secret bytes.

### Case C — same external account, different OAuth tokens

```text
Claude account 8 principal
  -> credential_ref: claude8/studio/oauth-session-A
  -> credential_ref: claude8/admin-mini/oauth-session-B
```

These are different credential issuances under one account principal. One can expire or be revoked without declaring the other stale.

### Case D — device-bound material

Tailscale machine/node private keys, Secure Enclave keys, many browser sessions, passkeys and some provider device sessions are **local/non-exportable**. They have one host binding and no replication path.

## 5. Do not build a new authority plane

This architecture adds a **subordinate credential-use actuator**, not a new scheduler, Job store, permission database or identity authority.

Existing owners remain controlling:

- Executive OS: Job / Attempt / Worker / Event, CEO admission, leases/fences and effect lifecycle;
- Capacity / RuntimeBinding: eligible host/worker/provider placement and current runtime identity;
- existing provider identity/readiness owners: provider account enrollment and native session validity;
- Workbench / Company capability surfaces: supported agent-facing tools;
- privileged broker: fixed host-administration effects;
- Agent OS: organizational decisions/discoveries/handoffs;
- native custody backend: secret material.

A credential backend's RBAC is a defense-in-depth custody restriction. It never grants organizational authority merely because it would release a secret.

## 6. Cross-computer topology

The fleet design is **capability routing first, secret replication second**.

```text
Web Sol / Astra / Fable / local worker
                |
        existing admission
                |
       Executive / Workbench
                |
     Capacity + RuntimeBinding
                |
        target capability host
                |
       credential-use actuator
        /        |         \
   Keychain   native auth   shared-secret backend
        \        |         /
          fixed domain adapter
                  |
             external service
```

Each Mac may run the same subordinate executor implementation, but each instance is bound to that Mac's existing host identity and local OS service principal. The executor owns no queue and chooses no host. It accepts only an already-authorized, exact-host operation.

For cross-host calls, reuse the existing Executive/agent-fabric transport and Tailscale connectivity. Do **not** invent a second cross-machine RPC fabric only for credentials.

## 7. Host identity rule

Credential bindings need a stable host identity, but this program must consume the existing Capacity/RuntimeBinding/physical-host identity owner rather than create another host registry.

Do not use any of the following alone as canonical host identity:

- hostname;
- IP address;
- Tailscale IP;
- local username;
- MAC address;
- hardware UUID;
- Remote Desktop Commander device ID.

They are observations, not company authority.

Tailscale node identity is excellent transport-attestation evidence because it is cryptographically tied to a device; Apple hardware identifiers can be additional enrollment evidence. A company `host_id` remains the canonical opaque reference and can update its attestations after Tailscale key rotation, hostname rename or network change.

A reinstall or hardware replacement must perform an explicit host re-enrollment/rebind. Old credential bindings never silently follow a hostname to a different machine.

### 7.1 Live census made during this architecture pass

Without reading any credential values, the currently connected Macs were independently observed as distinct hardware:

- `Mac-Studio.ts.net lan` — Mac14,14;
- `admins-Mini-652.ts.net lan` — Mac13,1;
- `MacBook-Pro-9.ts.net lan` — Mac15,6.

All three currently run under the same ordinary username, which is exactly why username cannot be the credential-host discriminator. Distinct local hardware fingerprints were observed but are intentionally not promoted to authority by this record.

## 8. Residency classes

Every credential issuance must declare exactly one residency class before it can be consumed by autonomous work.

### `HOST_LOCAL`

Material belongs to one host and must never be copied automatically.

Examples: host-local administrator password, browser profile cookie store, device-bound key.

### `PRINCIPAL_LOCAL`

Material belongs to one OS/provider worker principal on one host.

Examples: Claude/Codex provider login for a dedicated worker UID.

### `SHARED_CENTRAL`

One shared credential is held at a designated custody home. Other hosts invoke its capabilities remotely instead of receiving a copy.

Default for cloud-admin API keys because it minimizes blast radius.

### `SHARED_REPLICABLE`

One logical credential may have allowlisted replicas on more than one host because execution locality or high availability requires it. Replicas carry the same logical `credential_ref` and generation but separate `binding_ref`s.

Replication is explicit enrollment, never an agent-selected `copy_secret` operation.

### `NATIVE_SESSION`

The actual credential is owned by a provider/native client or browser session. Mastermind records readiness and binding metadata only.

### `NON_EXPORTABLE`

Private material is device-bound or hardware-backed. The only supported operation is use through its native signer/session.

### `HUMAN_PRESENCE`

The provider requires a passkey, biometric, MFA approval, or other human action that cannot lawfully be made unattended. The system records a precise external gate rather than pretending autonomy exists.

## 9. Preferred residency by credential family

| Credential family | Default residency | Autonomous use path |
|---|---|---|
| macOS sudo/admin password | `HOST_LOCAL`, but **not model-usable** | replace routine need with `mmx-admin` fixed privileged effects |
| OpenAI/Auth0/Cloudflare/Tailscale admin API key | `SHARED_CENTRAL` | domain adapter on credential home; optional HA replica later |
| ordinary SaaS API key needed by local process | `SHARED_CENTRAL` first; `SHARED_REPLICABLE` only if locality proves necessary | fixed executable or SDK adapter |
| Claude/Codex/GLM/Grok subscription login | `PRINCIPAL_LOCAL` / `NATIVE_SESSION` | provider adapter in exact worker realm |
| OAuth account used on multiple computers | one `principal_ref`, separate credential/session refs by client/device unless provider explicitly supports one portable refresh credential | native OAuth helper |
| browser login/session | `HOST_LOCAL` / `NATIVE_SESSION` | exact browser-profile adapter; prefer persistent session over password reuse |
| SSH private key | `NON_EXPORTABLE` where possible | SSH agent/signer; never raw key return |
| Tailscale node/machine keys | `NON_EXPORTABLE` | Tailscale itself |
| GitHub Actions / repo secrets | service-owned | GitHub workflow/service, not copied into local agent context |

## 10. Sudo is not a credential-distribution problem

The fleet must **not** solve autonomous `sudo` by storing a password and teaching agents to run `sudo -S`.

Reasons:

- it converts host privilege into reusable plaintext material;
- shell/stdin/log/process mistakes can expose it;
- identical passwords across Macs encourage false shared-identity assumptions;
- once a model can retrieve it, a prompt-injected task can attempt arbitrary root activity;
- it duplicates the problem already addressed by the privileged-action broker.

The correct path is the existing fixed-action root actuator. Each host has its own privileged executor registration. An authorized operation names the exact host and fixed effect. No password appears in the agent, request, environment, argv, logs or receipt.

A local-admin password may still exist in a human recovery vault, but that is **break-glass recovery custody**, not an autonomous agent capability.

## 11. Secret custody backends — hardened choice

### 11.1 macOS Keychain remains the device-local primitive

For host/principal-local secrets, keep using Security.framework rather than `.env`, plaintext config or shell variables.

New implementation should prefer modern Data Protection Keychain behavior (`kSecUseDataProtectionKeychain`) unless compatibility with an already-reviewed legacy item requires otherwise. Items are non-synchronizable by default.

Do not use iCloud Keychain synchronization as the fleet secret-distribution mechanism. Apple's synchronization semantics deliberately update/delete every synchronized copy and change the access-control model. That is useful for a human intentionally sharing one password across personal devices, but wrong as the implicit rule for mixed shared and host-local machine credentials.

### 11.2 Shared secret manager is a custody backend, not Mastermind authority

For genuinely shared static secrets that must exist on multiple machines, use a mature secrets backend rather than inventing encrypted replication in Mastermind.

Two viable candidates:

- **1Password Secrets Automation / Service Accounts** — low operational burden, vault-scoped machine access, mature CLI/SDK; cloud dependency and a per-machine bootstrap/service-account credential must be handled.
- **Infisical** — machine identities, short-lived access tokens, OIDC/SPIFFE/Universal Auth options, self-hostable if local control is preferred; higher operational burden if we self-host it.

HashiCorp Vault can satisfy the same role but is probably excessive for the current fleet unless other company needs justify its operational complexity.

Do not freeze a vendor before P0 proves the actual credential inventory and locality requirements. The execution contract must be backend-agnostic.

### 11.3 Immediate path does not need a shared-secret product

The current OpenAI tunnel/admin blocker can be solved sooner:

1. keep the OpenAI admin credential on one approved credential home (Studio);
2. expose fixed OpenAI admin operations through the credential-use actuator;
3. let Web Sol or another host call the capability through existing transport;
4. add an Admin Mini replica only after the basic path is proven.

This gets useful autonomy without waiting for fleet replication infrastructure.

## 12. Unattended boot/restart is a first-class acceptance gate

A credential path is not cruise-ready merely because it works while `chriswong` is logged in and the login Keychain is unlocked.

For every backend we must prove the intended lifecycle:

```text
clean shutdown
-> cold boot / service start
-> no interactive desktop unlock assumption unless explicitly accepted
-> credential executor starts
-> exact capability health reports READY
-> real canary succeeds
-> no secret bytes in logs/results
```

If the custody mechanism fundamentally requires a user unlock after reboot, the binding must report `REQUIRES_USER_UNLOCK`, not READY.

Preferred unattended composition is a dedicated non-login service principal with narrowly readable machine bootstrap material and a native secret backend, or another reviewed service mechanism that remains available at the required boot phase. Do not weaken the Chairman user's login Keychain or grant worker UIDs broad Keychain access merely to make boot easier.

## 13. Local executor boundary

The local component should be a small subordinate actuator, conceptually `credential-use-agent`, installed once per eligible host.

It must **not** expose:

```text
get_secret(name)
list_secrets()
dump_keychain()
read_password()
run_shell_with_all_credentials()
```

Its inputs are closed capability requests such as:

```text
capability_ref
operation_ref / Attempt binding
exact target host
adapter + action
bounded non-secret arguments
credential generation requirement
idempotency/effect key
```

It resolves custody only after authority, host, generation and adapter policy pass.

It owns no durable queue. For effectful operations it writes only the minimum effect/receipt evidence required by the existing action owner so a lost response can be reconciled without blind replay.

## 14. Agent-facing surface

### 14.1 Discovery

Agents need a **capability census**, not a secret census.

Example result:

```json
{
  "capability_ref": "openai.organization.tunnels.admin",
  "state": "READY",
  "eligible_hosts": ["host:<opaque>"],
  "actions": ["list", "inspect", "create", "bind_workspace"],
  "credential_generation": 7,
  "human_gate": null
}
```

No secret name, Keychain account, token prefix, password length, value digest or backend locator needs to be model-visible.

### 14.2 Execution

Prefer domain tools:

```text
openai_admin.list_tunnels
openai_admin.create_tunnel
openai_admin.bind_workspace
auth0_admin.inspect_client
```

A generic internal prepare/commit/reconcile protocol can back them, but the public model surface should stay semantic and closed-world.

### 14.3 Local workers

A worker inside an exact Executive Attempt receives only the capabilities admitted for that Attempt and RuntimeBinding. It never inherits a shell containing all fleet credentials.

When a third-party CLI requires an environment variable, the secret-owning helper may provide it only to the exact child process after executable/hash/arguments/destination policy passes. Environment injection is a compatibility fallback, not the preferred route.

## 15. Injection order

Use the narrowest possible secret delivery mechanism in this order:

1. secret-owning SDK/HTTP adapter constructs the authenticated request in-process;
2. OS pipe / inherited file descriptor / stdin directly into a fixed executable;
3. native client or browser session owns authentication without Mastermind reading it;
4. one-child environment injection when a reviewed client provides no safer interface;
5. temporary secret file only if a vendor absolutely requires it, with dedicated secure lifecycle and deletion proof;
6. **never** argv, shell interpolation, model-visible stdout, clipboard relay, repository file or generic `.env` inherited by the agent.

The child environment must be closed/scrubbed, executable path and hash pinned where practical, shell expansion disabled, core dumps disabled, and stdout/stderr treated as potentially hostile until sanitized.

## 16. Destination binding prevents exfiltration

A credential capability is not complete until its **network/application destination** is constrained.

Giving a model a token plus arbitrary `curl URL` lets prompt injection send the token to an attacker. Therefore each adapter declares:

- exact provider origins / API hosts;
- allowed HTTP methods and bounded path families;
- allowed executable/client identity;
- request fields in which the credential may be inserted;
- response fields that may be returned;
- redirect policy;
- maximum response size/time;
- whether the operation is read-only or effectful.

Unexpected redirect, DNS/host drift, proxy override, caller-selected CA bundle, or unreviewed destination fails closed.

## 17. Browser credential use

For sites without suitable APIs:

- bind a credential capability to an exact browser profile + origin;
- prefer an existing persistent authenticated session;
- if password fill is required, the secret-owning browser helper fills it directly into the approved origin/field without returning the password to the model;
- cookies/local storage are session custody and never generic secrets for model inspection;
- passkeys/biometric/MFA remain `HUMAN_PRESENCE` unless the provider offers a lawful service-account or device-flow alternative;
- prompt content from the webpage never authorizes credential disclosure or a different origin.

## 18. Shared-secret generation and replicas

For `SHARED_REPLICABLE`, one logical credential has a monotonically identified **credential generation** from its custody owner.

Each host binding reports only:

```text
credential_ref
generation
host_id
binding_ref
health
last_canary_at
expiry / rotation metadata if authoritative
```

Do not record or compare value hashes across hosts. Equality of secret bytes is both unnecessary and a potential information leak.

A host is eligible only when its binding reports the active generation and has passed the required native/provider canary.

## 19. Rotation protocol

Rotation is an effectful operation and must preserve one-carrier/effect-unknown law.

Preferred sequence when the provider supports overlapping generations:

1. create generation N+1 at the provider through one authorized operation;
2. record provider-issued identity/version metadata without the secret value;
3. enroll N+1 into allowed custody bindings;
4. prove each required binding with a real canary;
5. switch routing/readiness to N+1;
6. revoke N at the provider;
7. verify N is rejected and N+1 remains healthy;
8. retain secret-free receipts.

If the provider allows only one live secret, use a fenced maintenance sequence and accept temporary reduced availability rather than inventing dual-generation truth.

`HOST_LOCAL` credentials rotate independently per host and never participate in a fleet convergence check merely because their values used to match.

## 20. High availability and failover

Capability availability should be projected into existing Capacity routing.

Example:

```text
openai.organization.tunnels.admin
  Studio: READY generation 7
  Admin Mini: READY generation 7
  MacBook: NOT_ENROLLED
```

Capacity may select either READY host **before effect**. Once an effect is submitted to one host, that logical operation remains bound to that host/carrier until terminal reconciliation. Timeout or lost reply is not permission to try the replica.

A shared backend outage and a credential-home host outage are distinct health states. The system should surface which dependency is unavailable rather than saying simply "missing credential."

## 21. Failure vocabulary

Credential capability health needs explicit states such as:

```text
READY
NOT_ENROLLED
MISSING_LOCAL_BINDING
STALE_GENERATION
EXPIRED
REVOKED
REQUIRES_USER_UNLOCK
REQUIRES_HUMAN_MFA
BACKEND_UNAVAILABLE
NATIVE_SESSION_INVALID
HOST_UNREACHABLE
EFFECT_RECONCILIATION_REQUIRED
```

These are capability-health observations, not new Job lifecycle states.

For an action itself, continue using the existing owner vocabulary (`NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`, or the exact incumbent equivalent). Do not invent a credential-specific retry state machine.

## 22. Secret-zero problem

A shared secrets backend moves the problem; it does not eliminate it. Each machine still needs a way to authenticate to that backend.

The bootstrap credential must be:

- machine-specific or service-principal-specific;
- unreadable to ordinary worker UIDs;
- never model-visible;
- revocable independently per host;
- narrow enough that theft of one host bootstrap cannot expose every company secret;
- replaceable without changing the public agent interface.

Where the backend supports workload identity (OIDC/SPIFFE or similar), prefer short-lived tokens minted from machine/workload identity over one fleet-wide static bootstrap token.

Tailscale node identity can secure transport and provide device attestation, but it should not silently become Mastermind action authority or secret-backend authorization without an explicit reviewed binding.

## 23. OS-principal isolation

Run secret resolution under a dedicated service principal rather than under the general `chriswong` user or the same UID as arbitrary workers whenever the platform permits.

Conceptually:

```text
_mastermind_credential
  can resolve approved custody bindings
  cannot create Executive Jobs
  cannot run arbitrary shell
  cannot modify repositories
  cannot choose provider accounts
  cannot grant itself new capabilities

worker UIDs
  can request admitted capabilities
  cannot read credential storage
```

Root privilege remains in the separate privileged-action broker. Do not combine root execution and broad secret custody into one daemon unless a specific fixed capability demonstrably requires it.

## 24. Output and telemetry safety

Every credentialized adapter must prove:

- raw credential bytes never enter stdout/stderr;
- authorization headers are stripped from request/response debug logs;
- provider error bodies are bounded and sanitized before model return;
- stack traces do not serialize request headers/environment;
- audit records contain opaque credential/binding refs and generations only;
- no secret-derived digest/prefix is exposed unless the provider itself defines a public credential identifier;
- child processes have core dumps disabled;
- retained process artifacts are secret-scanned before publication.

Use synthetic sentinel credentials in adversarial tests to detect accidental propagation through logs, exceptions, subprocess inheritance and receipts.

## 25. Proposed non-secret binding projection

Do not create a new credential database. Extend the appropriate existing configuration/readiness owner with a projection equivalent to:

```json
{
  "schema": "mastermind.credential_capability_binding.v1",
  "capability_ref": "openai.organization.tunnels.admin",
  "principal_ref": "principal:<opaque>",
  "credential_ref": "credential:<opaque>",
  "credential_kind": "api_token",
  "residency": "SHARED_CENTRAL",
  "generation": 7,
  "binding_ref": "binding:<opaque>",
  "host_id": "host:<opaque>",
  "executor_ref": "executor:<opaque>",
  "custody_kind": "macos_keychain",
  "custody_locator_ref": "locator:<opaque>",
  "health": "READY"
}
```

`custody_locator_ref` is a digest/opaque ID interpreted only by the trusted executor; the actual Keychain service/account or vendor-secret path need not be given to the model.

The final schema location is owned by the incumbent host/provider readiness layer. This document does not claim the example is a new canonical store.

## 26. Web CEO path

The desired end-to-end path for the screenshot blocker is:

```text
Web Sol
 -> asks capability census for OpenAI tunnel administration
 -> existing authority/admission verifies current CEO operation
 -> Capacity selects credential-capable host (initially Studio)
 -> Workbench/Company adapter invokes fixed OpenAI admin action
 -> credential executor resolves local custody
 -> adapter calls only OpenAI's approved admin endpoint
 -> secret-free tunnel/workspace result returns
 -> effect receipt/reconciliation remains on that same carrier
```

The Web session never asks the Chairman for `OPENAI_ADMIN_KEY`, never learns the Keychain coordinates, and never needs filesystem access to the secret.

## 27. Local-agent path

For Claude/Codex/GLM/Grok/local operators:

```text
Executive Attempt + RuntimeBinding
 -> worker discovers admitted capability
 -> local or remote target host selected by existing Capacity
 -> credential executor validates exact Attempt/host/generation/action
 -> secret-owning adapter/native client performs operation
 -> bounded result + evidence returns to existing Attempt
```

A worker cannot broaden its authority by naming another credential, another host or another provider account.

## 28. Provider subscriptions are not normal API keys

Do not centralize provider subscription identities into one shared token vault merely because we can.

Claude, Codex, GLM, Grok, Alibaba, MiniMax and similar worker seats often have provider-native account/session/client semantics. Preserve the exact provider realm and worker binding. The credential capability layer should answer “this provider realm is READY on this host” and invoke its native adapter. It should not copy opaque provider auth files between unrelated UIDs or machines unless the provider explicitly documents that workflow and the provider-owner architecture approves it.

## 29. Human passwords versus service credentials

Where possible, replace human passwords with provider-supported service credentials for autonomous operations:

- OAuth refresh/service tokens;
- service accounts;
- GitHub Apps;
- provider admin API keys;
- machine identities;
- persistent native/browser sessions;
- device authorization flows.

A password remains useful for enrollment/recovery, but it should be the exception in steady-state autonomous execution.

## 30. Backend comparison and ruling

### Keychain-only fleet

**Reject as the full solution.** Excellent local custody, poor shared-secret source-of-truth/rotation story.

### iCloud-synchronized Keychain

**Reject as the machine-autonomy distribution default.** Synchronization deliberately couples copies and is not suitable for mixing host-local and shared semantics.

### Custom encrypted secret sync built inside Mastermind

**Reject.** This would create a new encryption/key-distribution/replication/control subsystem that we do not need to own.

### 1Password service accounts

**Viable default managed backend** if Chairman prefers minimal operations. Use separate least-privilege machine/service identities or otherwise revocable machine bindings; keep service-account bootstrap outside worker reach.

### Infisical

**Viable default machine-centric backend** if local/self-hosted control and workload identity matter enough to justify operating it. Machine identities and short-lived tokens fit the design well.

### Vault

**Capable but currently disproportionate** unless a broader company program already requires it.

### Final backend ruling

Freeze the **backend interface**, not the vendor. P0 inventory determines whether enough secrets actually require replication to justify adding a shared backend. Until then, central capability execution on Studio plus local native/Keychain custody is the least-complex useful vertical.

## 31. Threat model and required negatives

The system is not accepted until it survives at least these failures:

1. prompt-injected worker asks to list/read/export secrets;
2. worker names a credential not admitted to its Attempt;
3. worker names a different host after START;
4. executable path/hash changes between prepare and execution;
5. provider redirects to an unapproved origin;
6. DNS/proxy/environment attempts to reroute a credentialized request;
7. child process prints its environment;
8. provider error echoes an Authorization header/token;
9. secret backend returns malformed/oversized data;
10. host has stale credential generation;
11. one OAuth session is expired while another session for the same account remains valid;
12. two host-local passwords happen to be equal;
13. shared credential rotated on one binding but not another;
14. credential-home host dies before effect;
15. credential-home host dies after effect with response lost;
16. service restarts after a cold boot with login Keychain locked;
17. browser page attempts to exfiltrate a filled password to another origin;
18. agent tries to use sudo password instead of the privileged broker;
19. shared-backend machine bootstrap token is revoked;
20. audit/result persistence fails after the external effect may have happened.

## 32. Delivery waves

### P0 — Credential/capability census and semantics freeze

Read-only inventory of required capabilities and their current custody **without reading secret values**. For each, classify:

- principal/account;
- credential kind;
- residency class;
- current host/realm bindings;
- whether execution locality really requires local material;
- human-presence requirements;
- rotation/expiry evidence source;
- desired capability operations.

Output is a non-secret matrix and backend decision. Do not migrate credentials yet.

### P1 — One Studio credential-use actuator + OpenAI admin vertical

Build one fixed OpenAI tunnel/admin adapter using a fixed local secret-owning custody binding. Expose list/inspect and one bounded modifying operation through the existing Web CEO/Workbench authority path. Prove no raw credential enters the model.

This is the first independently useful capability because it removes the current tunnel blocker.

### P2 — Host-binding projection into existing Capacity/RuntimeBinding

Make credential capability readiness visible to the current placement owner. Prove one caller on another Mac can be routed to Studio to use the OpenAI capability without receiving the key.

No secret replication yet.

### P3 — Local provider/native-session consumption

Generalize the executor contract for one provider worker realm where authentication already belongs locally. Prove a local worker consumes a provider capability without copying its session/token to another principal.

### P4 — HA replica / shared-secret backend

Only after P0 demonstrates the need, select 1Password, Infisical or another reviewed backend. Enroll one shared credential on Studio + Admin Mini with one logical generation and separate host bindings. Prove per-host revocation and rotation without value comparison.

### P5 — Browser credential/session adapter

Bind one browser/admin capability to an exact host/profile/origin. Prefer persistent session; prove password fill, if required, never becomes model-visible.

### P6 — Fleet reboot/recovery/revocation proof

Cold boot, service restart, host loss before/after effect, backend outage, stale generation, revoked machine identity, RuntimeBinding change and secret rotation.

### P7 — Cruise-grade acceptance

From a fresh Web CEO session and a fresh local operator session, complete a substantive credential-requiring task across machines with:

- zero Chairman secret relay;
- zero raw secret returned to a model;
- exact host/account selection;
- real visible result;
- effect-safe interruption/reconciliation;
- restart recovery;
- per-host revocation;
- no duplicate authority/queue/identity/state plane.

Only then is the fleet credential capability `PROVEN_LIVE`.

## 33. Immediate acceptance contract for P1

P1 is complete only when all are true:

1. exact protected source reviewed;
2. installed on the actual Studio host under the intended service principal;
3. one capability-health call returns `READY` without exposing custody coordinates or material;
4. one read-only OpenAI admin call succeeds;
5. one bounded modifying tunnel operation succeeds through the actual Web/Workbench path;
6. a fresh session can reconcile the result without replay;
7. synthetic secret-leak tests prove no secret in model result, logs, artifacts, process argv or inherited unrelated environment;
8. wrong host, wrong Attempt, wrong generation and unapproved destination all refuse before secret acquisition;
9. no new Executive lifecycle/queue/identity store exists;
10. the current manual Chairman step shown in the motivating failure is no longer required for that operation.

## 34. Non-goals

This architecture does not authorize:

- a generic raw-secret MCP tool;
- arbitrary shell with credentials;
- copying provider auth directories between worker principals;
- storing the Chairman's sudo password for autonomous `sudo -S`;
- iCloud Keychain as an implicit fleet secret bus;
- a new scheduler/host registry/retry plane;
- a new provider account selector;
- auto-failover after ambiguous external effects;
- bypassing MFA/passkey/provider consent when the provider genuinely requires human presence.

## 35. Evidence and external design references

Official design references reviewed for this freeze:

- Apple Security.framework generic-password and Data Protection Keychain documentation (`kSecClassGenericPassword`, `kSecUseDataProtectionKeychain`, `kSecAttrSynchronizable`, access-control attributes);
- Tailscale identity/node-key documentation: node identity is cryptographically bound to a device and private node/machine keys remain local;
- 1Password Secrets Automation / CLI documentation: Service Accounts and narrow secret injection into subprocesses;
- Infisical machine-identity documentation: machine principals, scoped roles, short-lived access tokens and OIDC/SPIFFE/Universal Auth options.

These products supply custody/identity patterns. None becomes Mastermind organizational authority by itself.

## 36. Exact next action

**P0 is next.** Produce a read-only fleet credential/capability census across Studio, Admin Mini, MacBook and current provider worker realms without reading any secret values. Classify every discovered requirement under the identity/residency model above, identify which shared secrets truly require local replication, and select the first fixed OpenAI admin capability for P1.

P0 must return to Sol if it finds an incumbent canonical credential/readiness owner that this design would duplicate, a host identity that cannot be grounded in the current Capacity/RuntimeBinding owner, or a provider credential whose terms/native client prohibit the proposed use path.

The existing privileged-execution program may continue independently because it replaces sudo-password use rather than competing with credential custody. PR #633 may continue on its existing carrier; this design consumes its Keychain/header pattern but must not take over or retry its `DCR_EFFECT_UNKNOWN` enrollment.
