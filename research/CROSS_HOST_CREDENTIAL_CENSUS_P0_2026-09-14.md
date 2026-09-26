# Cross-host credential capability — P0 secret-free fleet census

Status: **PARTIAL / READ_ONLY_EVIDENCE / PRODUCTION_INERT**  
Architecture carrier: `research/CROSS_HOST_CREDENTIAL_CAPABILITY_ARCHITECTURE_2026-09-14.md`  
Protected base: `bffe2ca8506346ea278c8ee469bf1ac30a4de008`  
Date: 2026-09-14

## Mission

Determine whether the hardened cross-host credential architecture matches the actual fleet without reading any credential value, changing auth state, installing software, copying secrets, or claiming provider readiness from file presence alone.

P0 distinguishes:

- host and OS-principal reality;
- installed/native client surfaces;
- current non-secret authentication readiness where a client exposes a status command;
- known Mastermind Keychain item presence by fixed service/account coordinates only;
- shared-secret-manager availability;
- current Executive installation evidence;
- capability implications for the next build wave.

No password, API key, token, cookie, OAuth refresh token, private key, Authorization header, secret-derived digest, or Keychain payload was read or printed.

## Connected fleet observed

The current Remote Desktop Commander surface exposed four online devices and one offline WSL device. Three online Apple hosts were inspected plus the online Windows host.

| Host observation | Platform/model | Ordinary user observation | Important P0 implication |
|---|---|---|---|
| `Mac-Studio.ts.net lan` | macOS / Mac14,14 | `chriswong` | Current Executive/worker host; strongest candidate credential home. |
| `admins-Mini-652.ts.net lan` | macOS / Mac13,1 | `chriswong` | Distinct Mac despite same ordinary username; candidate HA/control host. |
| `MacBook-Pro-9.ts.net lan` | macOS / Mac15,6 | `chriswong` | Distinct portable Chairman host; should not inherit server credential semantics implicitly. |
| `winpc` | Windows / Alienware Aurora ACT1250 | current Windows user observed | Cross-platform executor/custody contract is required; macOS Keychain cannot be the architecture. |
| `WSL-Linux` | offline in current device surface | not inspected | Linux/WSL custody remains an explicit later census gap. |

Each Mac produced a different locally hashed platform-UUID observation during this pass. Those hashes are evidence that the machines are distinct, not canonical Mastermind host IDs and are intentionally omitted from this durable record.

### Host-identity ruling reinforced

The same username exists across three different Macs. Therefore `username`, hostname, IP, or password equality cannot identify a credential binding. The credential program must consume the existing opaque host identity from Capacity/RuntimeBinding once reconciled and use hardware/Tailscale observations only as enrollment/attestation evidence.

## Mac Studio observations

### Installed client surfaces

Observed on PATH:

- GitHub CLI;
- Claude CLI;
- Codex CLI;
- Cursor CLI;
- Tailscale CLI.

1Password CLI and Infisical CLI were not installed. The 1Password desktop app was not present in the earlier safe package check.

### Non-secret auth status

Status-only commands, with stdout/stderr discarded, reported:

- `gh auth status`: ready/exit 0;
- `claude auth status`: ready/exit 0;
- `codex login status`: ready/exit 0.

This proves only the ordinary-user client status at the time of observation. It does not identify account, scopes, token material, worker-realm identity, or suitability for a specific Executive Attempt.

### Mastermind native principals

The host currently contains these dedicated local accounts:

```text
_mastermind_codex_01
_mastermind_codex_02
_mastermind_codex_03
_mastermind_exec
_mastermind_executive_mcp
_mastermind_sol_relay
_mastermind_worker
```

This materially supports the architecture's principal-local credential model: ordinary-user auth is not interchangeable with worker/service-realm auth.

### Known fixed Mastermind Keychain coordinates

Presence checks were made with `security find-generic-password` while discarding all command output and without `-w`.

Observed present/in-scope for the ordinary user Keychain:

- `mastermind.mas115.multilogin.disposable` / fixed MAS-115 account coordinate;
- `mastermind-s0-fixture-slack-bot-token` / fixed S0 fixture account coordinate.

The values were not retrieved.

### Executive installation evidence

The following installed configuration filenames exist under `/Library/Application Support/MastermindExecutive/config`:

```text
control-env-canary
control.json
executive-mcp.json
sol-state-relay.json
sol-state-relay.token
worker-codex-pro-01.json
worker-codex-pro-02.json
worker-codex-pro-03.json
worker-codex.json
```

No file contents were read in this P0 census. A filename containing `.token` is not evidence that any model can or should access that token.

### Privileged broker installation state

The earlier bounded probe found no installed `mmx-admin` executable on the Studio and no obvious privileged broker launch service. Protected source #613 is merged, but the observed host path therefore remains **not proven installed/armed**. Do not solve this gap by storing the administrator password for agents.

## Admin Mini observations

### Installed client surfaces

Observed on PATH:

- GitHub CLI;
- Claude CLI;
- Codex CLI.

Cursor CLI, 1Password CLI and Infisical CLI were not observed on PATH. The safe package check found no 1Password desktop app.

The `tailscale` CLI was not on PATH through this process even though the device is reachable through its current Tailscale/Remote Desktop surface. PATH absence is not evidence that Tailscale itself is absent.

### Non-secret auth status

- `gh auth status`: ready/exit 0;
- `codex login status`: ready/exit 0;
- `claude auth status`: not ready/exit 1 for the ordinary user.

This is a concrete example of why same username and similar CLI installation do not mean equal credential readiness across hosts.

### Known fixed Mastermind Keychain coordinates

Both fixed Mastermind items probed above were absent or inaccessible from the ordinary user Keychain. No value lookup was attempted.

### Executive / service-principal evidence

No files were observed in `/Library/Application Support/MastermindExecutive/config`, and no `_mastermind*` service accounts were returned by the narrow local-account census.

This host is not currently equivalent to Studio as an Executive/credential home merely because it is online.

### Privileged broker installation state

No installed `mmx-admin` executable or matching obvious launch service was observed in the earlier bounded check.

## MacBook observations

### Installed client surfaces

Observed on PATH:

- GitHub CLI;
- Claude CLI;
- Codex CLI.

1Password CLI and Infisical CLI were not observed. The safe package check found no 1Password desktop app.

### Non-secret auth status

- `gh auth status`: ready/exit 0;
- `codex login status`: ready/exit 0;
- `claude auth status`: not ready/exit 1 for the ordinary user.

### Known fixed Mastermind Keychain coordinates

Both fixed Mastermind Keychain coordinates were absent or inaccessible from the ordinary user Keychain.

### Executive / service-principal evidence

No installed Mastermind Executive config files and no `_mastermind*` service accounts were observed by the bounded census.

The MacBook should therefore remain a separately enrolled recovery/operator host rather than being treated as a silent replica of Studio credentials.

## Windows host observations

The connected Windows machine was reachable and identified as an Alienware Aurora ACT1250. Current PATH census found the Tailscale CLI but did not find GitHub, Claude, Codex, Cursor, 1Password or Infisical CLIs in that shell. `.ssh`, `.config`, and `.claude` directories existed; their contents were not read.

No secret-like environment-variable names were present in the inspected process environment.

### Cross-platform consequence

The local custody interface must support platform adapters rather than hard-code macOS Keychain semantics:

- macOS: Security.framework / Keychain plus provider-native sessions;
- Windows: Credential Manager and/or DPAPI-backed service storage where appropriate, plus provider-native sessions;
- Linux/WSL: reviewed local secret-service/keyring or shared-backend machine identity, selected after the offline host is inspected.

Windows DPAPI is naturally user/machine scoped, which reinforces the architecture's rule that local credential binding is semantic and host-specific. A machine-scoped DPAPI blob is not a portable fleet secret.

## Ambient environment finding

The inspected Mac and Windows process environments contained no variable names matching the bounded secret-like census (`TOKEN`, `KEY`, `SECRET`, `PASSWORD`, `PASS`, `AUTH`, `COOKIE`, `CREDENTIAL`).

This is desirable. Fleet autonomy should not be implemented by globally exporting long-lived credentials into ambient shells.

It also means the motivating OpenAI admin capability cannot be assumed to exist merely because a generic shell is available. It needs explicit custody/enrollment and a capability adapter.

## Shared-secret backend finding

Neither 1Password CLI nor Infisical CLI was observed on the three Macs, and neither was present on the inspected Windows PATH. Therefore a shared-secret backend is **NOT_BUILT / NOT_ENROLLED** in the current fleet from the perspective of this architecture.

This supports the architecture's delivery order:

1. do not block P1 on choosing/installing a shared secrets product;
2. prove central capability execution on Studio first;
3. add a shared backend only if P0/P1 locality/HA requirements justify it.

## Credential/capability classes now grounded by evidence

| Capability family | Current observation | Residency decision | Next action |
|---|---|---|---|
| OpenAI organization/tunnel admin | motivating Web session lacks autonomous admin path; no ambient env credential observed | `SHARED_CENTRAL` initially | enroll fixed Studio custody + domain adapter; do not expose raw key |
| host privileged administration | #613 source merged, `mmx-admin` not observed installed on Studio/Admin Mini | no model-usable password | finish privileged broker install/proof on its existing program |
| GitHub ordinary-user client | status ready on all three Macs | `NATIVE_SESSION` per host/user | preserve native session; do not copy token |
| Codex ordinary-user client | status ready on all three Macs | `NATIVE_SESSION` per host/user; worker realms remain separate | consume exact provider/runtime binding, not ordinary-user status alone |
| Claude ordinary-user client | ready on Studio, not ready on Admin Mini/MacBook | host/principal local | no fleet equality assumption; enroll only where required |
| MAS-115 Multilogin canary credential | known fixed Keychain item present on Studio only | `HOST_LOCAL` / capability-specific | keep narrow existing owner; do not generalize its fixed coordinates |
| S0 Slack fixture credential | known fixed Keychain item present on Studio only | capability-specific local custody | preserve current narrow owner |
| browser sessions/cookies | not enumerated by design | `HOST_LOCAL` / `NATIVE_SESSION` | future exact-profile census, no cookie export |
| shared secret manager | none observed | absent | backend bake-off only after P1 proves need |

## Material design corrections from P0

### 1. Credential fabric must be cross-platform at the interface, not at the storage primitive

The architecture should define one capability/executor contract with OS-specific custody providers. macOS Keychain is an implementation, not the company-wide abstraction.

### 2. Studio is the only grounded initial credential home

Current installed Executive configuration, dedicated Mastermind service principals, known Keychain custody and ready ordinary-user provider clients all concentrate on Studio. Admin Mini and MacBook are not equivalent yet.

The first OpenAI admin vertical should therefore target Studio. Cross-host proof should call the Studio capability from another machine rather than prematurely replicating the key.

### 3. HA is enrollment work, not a routing flag

Admin Mini cannot become a fallback merely because it is online. It needs:

- canonical host identity/binding;
- executor installation;
- service principal;
- custody enrollment or shared-backend machine identity;
- real capability canary;
- generation/readiness projection.

Only then may Capacity treat it as a credential-capable replica.

### 4. Ordinary-user provider auth and worker-realm auth must remain distinct

Studio has several `_mastermind_codex_*` service principals. The status of `codex login` as `chriswong` cannot authorize those workers. P1/P3 must inspect current provider-owner readiness metadata rather than copy ordinary-user auth files.

### 5. No need for a generic fleet secret sync yet

The observed blockers are better solved by a fixed remote capability on Studio than by installing a password manager everywhere first. This materially lowers implementation and blast-radius risk.

### 6. Windows/WSL must be included before calling the fleet layer complete

The current architecture is valid for Macs but `PROVEN_LIVE` fleet acceptance requires at least one non-macOS custody/provider path or an explicit design rejection for that host class. Windows is online now; WSL is currently offline and remains uninspected.

## Remaining P0 gaps

P0 is not complete yet because this pass deliberately did not inspect secrets or broaden into provider-owned auth files. The following remain:

1. reconcile the canonical host identity/RuntimeBinding owner for the four online devices;
2. inspect provider-owner **metadata/readiness only** for dedicated worker UIDs/realms on Studio;
3. enumerate required admin capabilities (OpenAI, Auth0, Cloudflare/Tailscale/GitHub/etc.) from current autonomy workflows, without looking for raw values;
4. determine whether any current provider/admin operation genuinely requires credential material on a non-Studio host;
5. inspect WSL when it returns online;
6. decide shared-secret backend only from that locality/HA evidence.

## Exact next action

Proceed with the first P1 design/implementation slice around **OpenAI organization tunnel administration on Studio** while the remaining P0 metadata census continues in parallel.

P1 must expose capability health plus fixed OpenAI tunnel list/inspect/create/bind operations through the existing Web/Workbench authority path, with exact destination binding and secret-free receipts. It must use a dedicated fixed custody coordinate and never read or reuse either MAS-115 or S0 fixture credentials.

Before the modifying canary, reconcile the exact OpenAI organization/workspace/tunnel authority and current Business/Astra tunnel collision described by the active Web session. Do not guess which existing `chatgpt3` tunnel/workspace is safe to repurpose.

The privileged broker remains a separate dependency for host-admin effects and should continue on its existing owner; do not store a sudo password as a shortcut.
