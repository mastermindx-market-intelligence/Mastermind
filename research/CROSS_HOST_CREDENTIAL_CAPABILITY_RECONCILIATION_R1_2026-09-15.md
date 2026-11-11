# Cross-host credential capability — R1 current-source and sibling reconciliation

**Date:** 2026-09-15  
**State:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`  
**Parent carrier:** PR #634, `sol/cross-host-credential-capability-architecture-20260914`  
**Parent head before this record:** `91beb0052c13f482385a83e7f4ae869aa10b61df`  
**Current protected source / Skillpack:** `36f74c02edc938f7f5c41f38743f93ee34be2b2b`, `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap-major 1

## Mission

Reconcile the credential-capability architecture against current protected source and sibling work before any implementation. Preserve the useful cross-host credential identity/custody findings from PR #634 while refusing to create a second Sol capability plane, host scheduler, privileged-action plane, Workbench tunnel owner, OAuth enrollment owner, credential registry, secret store or retry mechanism.

This record changes no credential, Keychain item, provider account, browser session, tunnel, Executive state, Worker, RuntimeBinding, Capacity state, privileged service or production route.

## Executive ruling

The first PR #634 design had the right secret-handling direction but gave the proposed credential executor too much architectural prominence. Current protected source already owns the model-facing nervous system through **Sol Capability Fabric (SCF)**. Therefore:

> Credential custody/execution is an implementation detail behind owner-specific SCF capabilities, not a new model-facing credential fabric or company control plane.

Agents receive semantic capabilities, not raw secrets. Executive OS owns authority/effects; SCF exposes typed capability surfaces; Capacity/Fleet Placement chooses a lawful host; provider/realm owners own their native sessions; credential-owning helpers supply material only at the final fixed actuator boundary.

## Sibling / owner reconciliation

### Sol Capability Fabric — existing protected owner

Protected source already freezes `One Experience, Federated Authority`: broad governed operational reach through typed capabilities rather than ambient root. It rejects a super-MCP, generic shell/HTTP/browser/filesystem administration surface and universal administration token.

Credential/enrollment/policy/infrastructure administration is already the `A3_ADMIN` privilege class with a separate normally-disabled principal/app generation. Existing SCF common contracts already own capability status, per-owner prepare/commit semantics and `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN` reconciliation law.

The current pure `control_plane/sol_capability_status.py` already supplies the secret-free capability projection and owns no registry/lifecycle/credential. The credential program must feed owner facts into that projection rather than introduce a `CredentialRegistry` database or another global status store.

### PR #644 — Fleet Placement v2 leads physical host choice

PR #644 freezes the multi-host route from Executive Job through Model Router, provider/Worker facts, hard feasibility, Capacity preference, atomic claim/reservation, local/MH1 transport, begin-time recheck and provider effect. It explicitly keeps host-local provider credentials with their existing realm/provider-home owners and rejects credential sharing as placement authority.

Credential work therefore contributes **readiness facts**, never host ranking. It does not decide which Mac should run a Job. If a semantic capability requires credential-backed execution, Fleet Placement/Capacity filters to hosts with a fresh lawful capability binding and applies its own placement law.

### PR #641 — Workbench Astra Business leads its transport/admission path

The sibling Workbench carrier has built the modern MCP discovery compatibility path for the dedicated `Mastermind Workbench — Astra Business` Secure MCP Tunnel. A current Studio observation found its runtime alias ready and a dedicated tunnel identity present. The earlier screenshot claim that no dedicated Business/Astra Workbench tunnel existed is therefore superseded.

From this Web Sol surface, the Workbench app/tool schema is discoverable, but a real read-only `workspace_manifest` invocation currently returns `CHANNEL_ADMISSION_REFUSED`. That is the live boundary for the sibling owner to reconcile. Credential work must not create another tunnel, repurpose an Executive tunnel or race PR #641.

### PR #613 / current privileged continuation leads root effects

Merged privileged-action source owns the fixed, receipt-gated host administration pattern and explicitly avoids reusable administrator passwords or arbitrary model root shells. Current host work is continuing the install/readiness proof on its own carrier.

A Mac login/sudo password remains a human/break-glass or host-local credential. Routine autonomous root actions go through the privileged broker, not through this credential program.

### PR #633 retains Astra external-Fabric OAuth enrollment

The existing Codex/Astra client-auth carrier retains its current DCR enrollment state and effect-safety ownership. Its prior `DCR_EFFECT_UNKNOWN` must not be retried, copied or failed over by credential work.

## Agent OS landmine consumed

Macro Agent OS records a verified security discovery: an authenticated third-party settings page can render a live credential into model-visible DOM/browser inspection output. Redaction after capture is too late because the secret already crossed the model boundary.

Consequences for this architecture:

- never use browser settings/DevTools/model-visible DOM to census or verify a live token/password;
- verification helpers emit only allowlisted non-secret metadata and fixed errors;
- browser/password automation must use a trusted autofill/grant actuator that prevents secret bytes entering the model/tool result in the first place;
- a `read-only` model-visible browser inspection is not automatically secret-safe.

## Identity model — retained, but backend-only

Credential identity is semantic and must never be inferred by comparing secret bytes or hashes.

```text
authority_principal_ref
  what human/service/external account authority is represented

credential_issuance_ref
  which particular password/key/token/session issuance exists

credential_binding_ref
  which host + OS/service principal + provider/browser realm may use it

custody_ref
  fixed local/native/backend coordinate known only to the trusted owner

capability_ref
  semantic SCF operation exposed to an authorized caller
```

Examples:

- the same sudo password characters on M1 and M2 are still two host-local credential bindings;
- one shared external API key intentionally installed on two Macs is one logical issuance with two separately enrolled host bindings;
- one external OAuth account logged in independently on two machines will normally have two session/refresh-token issuances and two bindings;
- Secure Enclave/device keys, browser cookies, passkeys and DPAPI machine credentials are device/profile bound even when the external account is shared.

No model-visible output needs to reveal `custody_ref` coordinates or secret-derived fingerprints.

## Residency classes

### `DEVICE_LOCAL`

Examples: host administrator credential, Secure Enclave key, DPAPI machine secret, browser cookies/device-bound passkey. Never fleet-synced by default.

### `PRINCIPAL_LOCAL_SESSION`

Examples: Claude/Codex/GitHub native login for a particular OS/service principal. Same external account label does not make sessions interchangeable.

### `SHARED_CENTRAL`

One external credential is held on one credential home and its semantic capability is remotely usable through existing Executive/Fleet routing. This is the default for shared high-privilege static secrets.

### `SHARED_REPLICABLE`

One logical external issuance deliberately has multiple enrolled host bindings for proven HA/locality need. A replica is not created merely because another Mac is online.

### `HUMAN_BREAK_GLASS`

Credential remains outside autonomous custody and is only used for an actual human recovery/consent boundary. It is not a hidden failure of autonomy when the upstream provider intentionally requires human presence.

## Canonical cross-host route

```text
Executive Job / admitted action
  -> SCF semantic capability requirement
  -> Fleet Placement / Capacity hard feasibility
  -> host with fresh capability binding
  -> already-owned local or MH1 transport
  -> owner-specific credential-backed actuator
  -> exact provider/native effect
  -> existing result / Wake / reconciliation owner
```

This architecture adds no credential scheduler. The capability owner reports readiness; Capacity owns selection.

Once an external request may have been dispatched, host loss or transport loss is `EFFECT_UNKNOWN` until the original effect is reconciled. Another credential replica or another host must not auto-replay it. Pre-effect/read-only work may be re-placed only after canonical no-effect proof.

## Credential-backed actuator contract

A credential-backed actuator is narrow and owner-specific. It is not `secret_get`, a shell wrapper or arbitrary HTTP client.

A production actuator binds:

- exact semantic action family and SCF privilege class;
- current Executive/owner authority;
- exact host/runtime/service-principal generation;
- fixed credential issuance/binding generation;
- fixed executable/library release and digest where relevant;
- fixed provider origin and allowed path/method family;
- redirect policy (normally none across origins);
- TLS/proxy/environment policy;
- bounded request and response schemas;
- pre-effect marker/reconciliation semantics for modifying calls;
- secret-free logs, receipts, exceptions and model-visible results.

Secret injection preference:

1. provider-native OS credential/session API that never materializes raw bytes in the caller;
2. inherited file descriptor/stdin or equivalent one-child secret channel;
3. exact child-only environment variable only when the fixed provider client requires it.

Command-line secret arguments, shell interpolation, ambient exported credentials and generic environment inheritance are prohibited.

### Service-principal isolation

Where practical, the secret-owning helper and credentialized child run under a dedicated service principal/UID rather than the same ordinary UID as model-facing workers. This reduces same-user inspection/debug/process-environment risk.

Child-only environment injection is a compatibility boundary, not a blanket claim that environment variables are secret-safe. Core/crash dumps, debug attachment and telemetry that can capture child environments must be disabled or proven unable to cross the boundary.

## Secret-free capability readiness

Do not add a credential readiness database. Owner facts should project through existing `mastermind.sol_capability_status.v1` / SCF capability status.

Useful dependency facts can include, without revealing secret material:

```text
capability name
authoritative owner
privilege class
source/proof state
production armed/read-only state
required capability scopes
host/runtime binding generation
credential-binding generation (opaque)
actuator release/generation
native-session readiness
human-presence requirement
last current production proof
issues / typed refusal
```

The projection should not reveal Keychain service names, file paths, account emails, raw external account labels when unnecessary, token hashes or a fleet-wide secret inventory.

Credential/backend readiness vocabulary should distinguish at least:

```text
READY
NOT_ENROLLED
STALE_GENERATION
EXPIRED
REVOKED
REQUIRES_USER_UNLOCK
REQUIRES_HUMAN_MFA
BACKEND_UNAVAILABLE
NATIVE_SESSION_INVALID
HOST_UNREACHABLE
```

Those owner-specific facts feed capability availability/proof; they do not create a second company capability-state enum.

## Rotation and replica generation

Replica semantics must not be hidden behind “same password/key.”

### Provider supports overlapping generations

```text
enroll issuance g+1 on intended host bindings
 -> prove each binding with a safe canary
 -> promote g+1 active generation
 -> revoke issuance g
 -> old binding generation becomes invalid
```

### Provider performs single/in-place rotation

After rotation, any host not proven updated is immediately `STALE_GENERATION`; it must not remain an eligible fallback merely because its local secret file/Keychain item exists.

Changing a host-local administrator password advances only that host credential binding, even if another Mac happened to use the same old characters.

Lost/retired hosts require per-host binding revocation without invalidating unrelated device-local credentials.

## Browser/password workflows

Some administrative surfaces cannot be replaced by APIs. They still must not devolve into model-readable passwords.

The target original Mastermind pattern is an owner-specific ephemeral grant/autofill capability:

```text
prepare exact login target + browser/profile realm
 -> authority/origin/profile recheck
 -> trusted native credential owner grants one bounded fill
 -> trusted actuator fills exact fields directly
 -> optional human/secure verification step
 -> result reports AUTHENTICATED / refusal only
 -> release/expire grant
```

The model sees a grant reference and non-secret state, never the credential. This resembles a password-manager/autofill user experience but must be implemented from Mastermind's own contracts and current platform primitives; no proprietary harness implementation is copied.

Model-visible browser inspection must not be used to “verify” that a credential exists.

## Cold-boot / cruise readiness

Presence in a logged-in user's Keychain today is not unattended proof. Every critical capability binding must survive the actual recovery path expected while the Chairman is away.

A host is not cruise-ready until a cold/reboot scenario proves:

- service principal starts under the supported boot/login boundary;
- required custody becomes available without forbidden interactive unlock;
- capability status reports truthfully after restart;
- stale or unavailable native sessions refuse rather than falling back to ambient credentials;
- remote Executive/Fleet invocation reaches the same capability;
- revocation/rotation still works;
- no secret enters logs, process arguments, model output or crash evidence.

If the OS/security design intentionally requires user unlock, report `REQUIRES_USER_UNLOCK`; do not weaken Keychain policy to manufacture a green result.

## OpenAI Secure MCP Tunnel correction

The earlier P1 feasibility record remains useful evidence for how to safely wrap the installed OpenAI tunnel client, but **creating a dedicated Astra Business tunnel is no longer the immediate product gap**.

The sibling Workbench path now has a dedicated ready tunnel. Therefore:

- do not create a second Astra Business Workbench tunnel;
- do not use admin-key availability as permission to alter tunnel associations;
- keep OpenAI admin CRUD disabled for this credential program unless a new owner-authorized admin requirement appears;
- a later read-only A3 observation can still be a useful credential-actuator canary if it solves an unsatisfied operational need, but not merely to prove the architecture.

The current Workbench gap is sibling-owned channel admission, observed as `CHANNEL_ADMISSION_REFUSED`, not missing tunnel creation.

## Revised delivery waves

### R1 — current-source reconciliation — this record

Consume SCF, Fleet Placement, Workbench, privileged broker, OAuth carrier and Agent OS landmine. Remove duplicate-plane assumptions and correct the stale OpenAI-tunnel next action.

### R2 — secret-free readiness composition

Define the smallest owner-fact adapter necessary for one real credential-backed capability to project through existing `sol_capability_status`; no registry/database/store. Prove wrong host, stale generation, missing custody, human-gated and ready states hermetically.

### R3 — select one still-needed vertical

Select from current operational blockers, not from an architecture demo. Preference order:

1. a read-only provider/admin operation whose credential already has lawful custody and whose semantic result is useful;
2. an existing native-session capability needed on another host;
3. a browser/autofill flow only when an API/native client cannot solve the job.

Do not select Workbench tunnel creation unless current owner state once again proves it missing.

### R4 — one-host production canary

On the canonical credential home, prove the exact owner-specific actuator from real authorized input to useful semantic result with zero model-visible secret material and exact release/destination binding.

### R5 — cross-host use without secret replication

Invoke the same semantic capability from a non-credential host; Fleet Placement/Capacity must select/route to the credential-capable host. Prove the caller never receives the credential or custody coordinate.

### R6 — HA only if required

Only if an accepted resilience requirement remains, enroll a second host binding, prove cold-boot serviceability, generation/rotation semantics, per-host revocation and no blind failover after possible effect.

### R7 — browser grants / shared backend only when demanded

Add an owner-specific browser grant/autofill capability and/or mature shared-secret backend only for workloads whose locality/HA requirements cannot be satisfied by central capability execution. Mastermind does not build an encrypted secret-sync product.

## Adversarial review checklist

Reject an implementation if any answer is yes:

- Does the model receive raw secret material or a generic `get_secret` capability?
- Is there a new credential registry/state DB when SCF/owner facts can project readiness?
- Does the credential layer rank/select hosts rather than Capacity/Fleet Placement?
- Does a replica multiply provider economic capacity?
- Can one host's local password/session be silently substituted for another host binding?
- Can a lost response trigger a second host/credential/provider attempt before reconciliation?
- Can caller input change provider base URL, executable, proxy/TLS trust or arbitrary request path?
- Can model-visible browser inspection encounter a live credential before redaction?
- Does an ordinary-user login status authorize a dedicated Worker/service principal?
- Does a Keychain item existing while logged in become a false cruise-readiness claim?
- Does a provider rotation leave stale replicas eligible?
- Does a secret-owning helper share an inspection domain with untrusted/model-facing processes without explicit risk proof?
- Does credential work race PR #641, PR #644, privileged-action continuation or PR #633?

## Capability state and exact next action

This program remains `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`. No credential-backed execution layer is production-proven by this record.

**Exact next credential-program action:** implement/review only the minimum secret-free readiness composition required to project one owner-specific credential-backed capability through existing SCF `capability_status`, using Fleet Placement/Capacity only as a consumer of host feasibility. Before choosing a modifying actuator, reconcile current operational blockers and select a still-needed vertical.

**Independent sibling continuation:** PR #641 owns the Astra Business Workbench modern-MCP/channel-admission proof; PR #644 owns multi-host placement; privileged-action work owns routine root execution; PR #633 owns its current OAuth enrollment/effect reconciliation. Credential work must consume their accepted results, not replace them.
