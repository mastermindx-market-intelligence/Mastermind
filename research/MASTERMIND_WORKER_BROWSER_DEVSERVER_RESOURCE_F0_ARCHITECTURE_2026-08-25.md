# Mastermind-X Worker Browser / DevServer Resource Fabric F0

**Date:** 2026-08-25  
**Owner:** Sol, AI CEO  
**Status:** SOL ARCHITECTURE FREEZE / RECORDS ONLY  
**Protected Mastermind basis:** `eff2033c639cb25f8b4a2a4e5f90e1a4a6002138`  
**Protected Skillpack:** `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1, loaded atomically from that exact commit.  
**Autonomy V1 parent law:** `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`  
**Completion law:** F0 merge freezes the resource architecture only. It does not give any worker live browser access and does not satisfy the Autonomy V1 browser proof gate.

---

## 0. Observable mission and CEO ruling

Give governed COO/worker sessions a real rendered-web sensory and interaction surface—accessibility/DOM snapshots, screenshots, viewport control, console/network evidence and bounded interaction—plus a supervised local devserver for the exact worktree they are reviewing, without giving them the Chairman's desktop/browser identity or creating another scheduler/resource database.

The architecture ruling is:

> **Browser review is an Operator Harness capability, not a desktop account. The official Playwright MCP is the model-facing browser tool surface; the existing Executive/Operator Harness supervisor owns the Attempt-bound browser/MCP/devserver process realm, resource configuration, cleanup and proof.**

V1 starts with an isolated **local-devserver browser profile**. Arbitrary internet browsing and authenticated Chairman-seat browsing are not prerequisites for the first Autonomy V1 proof.

---

## 1. Why this matters

A principal builder that can only read files and run terminal commands is materially weaker at Mastermind product work. It cannot reliably judge:

- actual responsive layout;
- clipped/overlapping UI;
- chart rendering;
- desktop/mobile composition;
- browser console failures;
- network failures;
- hover/tab/accordion/filter behavior;
- screenshot-visible regressions;
- DOM/accessibility states that differ from source assumptions.

The Chairman should not need to become the visual proof courier. A real COO should be able to commission implementation, inspect the rendered product, collect browser receipts, repair it and return evidence to Sol.

---

## 2. Current estate and capability ledger

| Capability | State | Current truth |
|---|---|---|
| Operator Harness requested/observed capability attestation | `BUILT_NOT_PROVEN` | `RequestedExecutionProfile`, `CapabilityManifest`, MCP/plugin/skill census, sandbox/network/auth/workspace comparison and refusal law exist. |
| Codex App Server operator adapter | `BUILT_NOT_PROVEN` / production-unarmed | Real adapter exists, currently attesting a network-disabled read-only operator profile. |
| Governed MCP composition | `PARTIAL` | Exact read-only MCP composition exists for the docs lane; arbitrary browser MCP is not granted. |
| Browser/DevServer Resource Fabric | `NOT_BUILT` | Explicitly excluded from the earlier OHF P1B wave. |
| Repo-local Playwright/test estate | `PARTIAL` | Macro/Terminal contain existing Playwright/test tooling, but none is a canonical Executive worker resource. |
| Official Playwright MCP browser automation | external dependency / available | Official Playwright MCP exposes structured accessibility snapshots, browser actions, screenshots, console/network/devtools capabilities and supports MCP clients including Claude Code/Codex-class clients. It is not yet pinned or governed by Mastermind. |
| Worker visual-image consumption | `NOT_PROVEN` across final worker profiles | Browser screenshot generation is not enough; V1 must prove the selected provider/harness can actually use image output for visual judgment or explicitly degrade to structured-only review. |

The missing product capability is therefore integration and proof, not invention of browser automation itself.

---

## 3. Canonical ownership and no-rebuild law

### Executive OS

Remains sole Job/Attempt/Worker/Event lifecycle authority. It owns which Attempt requested a browser-capable execution profile and the normal result/artifact lifecycle.

It does **not** gain a second `BrowserJob`, `PortLease`, `DevServerTask`, browser queue or resource database.

### Operator Harness supervisor

Owns composition and cleanup of subordinate processes/resources required by one rich Attempt generation:

- provider App Server / harness;
- approved MCP sidecars;
- isolated browser process/context;
- approved local devserver;
- bounded artifact/output directory;
- exact capability attestation and cleanup.

These are subordinate execution resources, not independent Jobs.

### Product repository

Owns the reviewed devserver manifest for that product/worktree. Mastermind Executive code does not hard-code every product's framework command.

### Playwright MCP

Is the model-facing browser tool surface only. It does not own Executive lifecycle, worktree identity, permission policy, provider credentials or final proof acceptance.

### GitHub / Agent OS

GitHub remains implementation/browser-evidence truth through exact artifacts/PRs. Agent OS records durable organizational outcomes/handoffs. Browser screenshots do not create another memory store.

---

## 4. Resource composition model

A browser-capable rich Attempt is conceptually:

```text
Executive Job / Attempt
      |
      v
RequestedExecutionProfile
      |
      +-- ordinary sandbox / approval / network / auth / workspace law
      +-- required capability: governed Playwright MCP
      +-- required capability: local devserver resource
      +-- optional capability: visual image-result consumption
      |
      v
Operator Harness supervisor / one worker UID + generation realm
      |
      +-- exact product worktree
      +-- repo-owned devserver process on loopback leased port
      +-- pinned Playwright MCP sidecar
      +-- isolated headless browser/context
      +-- Attempt artifact directory
      |
      v
provider session uses bounded MCP tools
      |
      v
structured snapshot + screenshots + console/network receipts
      |
      v
normal CandidateResult / artifact digest / Executive result path
```

No resource above outlives the owning generation except immutable result artifacts already governed by the normal Attempt result path.

---

## 5. Existing OHF contract is extended, not replaced

`RequestedExecutionProfile` already carries:

- workspace identity;
- sandbox policy;
- approval policy;
- network policy;
- required/ambient/forbidden capability manifest;
- auth realm requirement;
- exact harness/config identity;
- write paths.

F0 does **not** create a parallel resource profile system.

### 5.1 Capability identity use

The existing `CapabilityIdentity.kind` / `ObservedCapabilityIdentity.kind` vocabulary may be extended by accepted implementation to represent:

```text
kind = mcp       -> official Playwright MCP identity/tool schema
kind = resource  -> supervisor-owned devserver/browser resource contract identity
```

If landed comparator/wire code cannot safely carry a generic `resource` kind without ambiguity, B1 must make the smallest reviewed additive OHF contract amendment. It must not create a second capability manifest.

### 5.2 Requested profiles

The first accepted browser profile is conceptually:

```text
operator.browser.local-review.v1
```

It inherits the current rich-operator authority/sandbox/workspace rules and adds only the exact browser/devserver capabilities required for one local UI proof.

Provider/model choice remains separate from the capability profile. Codex and later Claude may implement the same profile when their adapters can truthfully attest it.

---

## 6. Devserver resource contract — `mastermind.devserver_resource/v1`

Each product repository that is allowed to participate provides one reviewed manifest on its exact tested tree.

Closed conceptual fields:

```json
{
  "schema_version": "mastermind.devserver_resource/v1",
  "resource_id": "product-web",
  "cwd": ".",
  "argv": ["<reviewed executable>", "<reviewed args>", "{port}"],
  "host": "127.0.0.1",
  "readiness_path": "/",
  "readiness_timeout_seconds": 60,
  "shutdown_grace_seconds": 5,
  "allowed_generated_paths": ["<ignored cache/output paths>"]
}
```

Rules:

- manifest lives in the product repo and is part of exact workspace SHA identity;
- no shell string; argv is executed directly;
- only `{port}` is a runtime placeholder in V1;
- caller/model cannot author executable, cwd, readiness URL or output paths;
- cwd must resolve inside the exact Attempt worktree;
- generated paths must already be intentionally ignored/disposable and may not hide tracked source changes;
- devserver never receives provider credentials or Chairman browser state;
- no public bind: host is exact loopback;
- no background daemon survives the Attempt generation.

If a repo cannot express its real devserver through this shape, it needs a repo-specific reviewed adapter later; do not widen the generic manifest to arbitrary shell.

---

## 7. Port allocation without another allocator service

V1 creates no persistent port registry.

The supervisor:

1. derives a deterministic starting point in one reviewed local high-port range from `(attempt_id, resource_id)`;
2. probes a bounded sequence of candidate loopback ports;
3. temporarily reserves the selected socket while staging the resource where practical;
4. releases immediately before the owned devserver bind;
5. if bind/readiness fails before any external effect, stops the owned process and tries the next bounded port;
6. records the final port only in the Attempt-local resource receipt/artifact, not in a new database.

Maximum V1 attempts: **16 ports**. Exhaustion is a bounded resource refusal, not permission to use a public/random external service.

A crash/restart does not recover a `PortLease`; the existing worker-generation/UID process reconciliation proves old subordinate processes dead or cleans them before a replacement generation may start.

---

## 8. Browser MCP choice and pinning

Use the official Microsoft Playwright MCP implementation as the initial browser tool surface rather than writing a custom browser automation protocol.

Implementation law:

- pin an exact reviewed package/version and dependency lock; never `@latest` in production profile;
- record exact server identity/version and normalized tool-schema digest through the existing MCP attestation path;
- launch in **isolated** mode with a fresh browser/context for every Attempt generation;
- do not reuse default persistent session/cookie state;
- do not load a Chairman Chrome/Multilogin/user-data directory;
- do not enable unrestricted file access;
- browser output directory is the Attempt artifact directory, not the repo source tree;
- block service workers for the first profile unless a product falsifier proves they are required;
- headless is the production default; headed mode is operator/debug only and not required for worker capability;
- browser/client package downloads are provisioning/install-time work, not an on-demand model action.

The Playwright MCP origin allow/block configuration is useful defense in depth but, per upstream documentation, **is not accepted as the sole security boundary**. B1 must prove actual egress behavior at the resource-process layer.

---

## 9. V1 browser network boundary: local devserver only

The first production profile is intentionally narrow:

```text
browser network: only the leased loopback devserver origin
operator shell/network: keep the existing reviewed command-network policy
external public internet: refused
file:// navigation: refused
Chairman/authenticated browser state: absent
```

This is sufficient to prove real rendered product review while avoiding a week-long browser-security project.

### 9.1 Enforcement outcome

B1 may choose the smallest host-supported mechanism—e.g. supervisor-enforced process sandbox, an enforcing local proxy plus locked browser launch policy, or another reviewed host control—but it passes only if black-box tests prove:

- the page can reach the exact leased loopback origin;
- arbitrary external HTTP/HTTPS fetch/navigation is refused;
- redirects cannot escape to an external origin;
- WebSocket/subresource requests cannot escape the local origin;
- the model cannot change proxy/network launch settings through MCP tools;
- shell/tool network remains within its separately requested Operator Harness policy.

Playwright `allowedOrigins` alone does not satisfy this gate.

### 9.2 Later production-inspect profile

A separate later profile may allow exact company-owned production origins for read-only inspection. It is **not** required to make the first Autonomy V1 browser resource live and must not silently reuse Chairman cookies/login state.

---

## 10. Tool surface: useful but bounded

The first local-review profile should expose only tools needed for product review.

### Required tool families

- navigate to the leased local origin;
- accessibility/browser snapshot;
- take screenshot / element screenshot;
- viewport resize / device-size proof;
- tabs where needed;
- wait-for/load state;
- console messages;
- network request inspection;
- bounded click/hover/form interaction on the local devserver.

### Forbidden by default

- arbitrary unsafe Playwright code execution;
- arbitrary file upload;
- persistent auth/storage export/import;
- user-data-dir/session reuse;
- secret injection;
- unrestricted file URLs;
- extension loading;
- arbitrary external navigation;
- browser download/executable installation initiated by the model.

If one forbidden capability later becomes necessary, create a narrower reviewed profile; do not turn the default browser lane into a general desktop.

---

## 11. Structured browser understanding and true visual understanding are distinct

Playwright MCP's accessibility snapshots are excellent for deterministic element discovery and interaction. They are **not** a substitute for pixel-level visual review.

F0 therefore separates:

```text
browser.structured.v1
  -> accessibility snapshots / DOM-like state / console / network

browser.visual.v1
  -> screenshot image output can actually be consumed by the selected model/harness
     and used for visual judgment
```

Autonomy V1 UI proof requires both for the selected primary UI worker profile.

Generating a PNG file without proving the worker can interpret image content does not satisfy `browser.visual.v1`.

B1 must prove visual consumption with a discriminating fixture whose important defect is visible in pixels but not inferable from accessibility text alone.

---

## 12. Browser proof artifact — `mastermind.browser_review_receipt/v1`

No new lifecycle store is created. The browser lane emits an immutable artifact under the normal Attempt artifact/result path.

Closed conceptual receipt:

```json
{
  "schema_version": "mastermind.browser_review_receipt/v1",
  "attempt_id": "...",
  "workspace_base_sha": "...",
  "devserver_manifest_digest": "...",
  "browser_profile_digest": "...",
  "playwright_mcp_identity": "...",
  "playwright_mcp_version": "...",
  "playwright_tool_schema_digest": "...",
  "local_origin": "http://127.0.0.1:<port>",
  "viewports": [],
  "screenshots": [],
  "console_summary": {},
  "network_summary": {},
  "external_egress_observed": false,
  "tracked_workspace_changes_after_review": false
}
```

Each screenshot row contains at minimum viewport identity, relative artifact path, byte length and SHA-256. Screenshot bytes stay in the Attempt artifact directory and are not embedded into Executive SQLite Events.

The existing CandidateResult/result envelope carries the final artifact digest/reference. The browser receipt cannot mark the Job complete by itself.

---

## 13. Resource lifecycle and cleanup law

Browser, MCP and devserver processes are subordinate to one existing Operator Harness generation.

### Start order

```text
validate exact RequestedExecutionProfile
-> validate devserver manifest against exact worktree
-> allocate loopback port
-> start devserver under worker principal/generation resource realm
-> wait bounded readiness
-> start pinned Playwright MCP + isolated browser
-> attest exact resource/MCP identity and network falsifier
-> start/continue provider turn
```

No provider work turn begins if required browser/devserver attestation fails.

### Stop order

```text
stop provider turn/generation under existing OHF law
-> close browser context/browser
-> stop Playwright MCP
-> stop devserver
-> prove subordinate process death / whole-worker-principal cleanup
-> seal browser artifact receipt
-> release normal generation writer only under existing OHF law
```

If graceful cleanup fails, existing hard process-death / writer / reconciliation law governs. Do not invent browser-specific retry or orphan tables.

### Restart / effect unknown

A controller restart does not blindly launch another devserver/browser beside an uncertain existing generation. Existing OHF process/generation reconciliation first proves the old generation/subordinates dead or holds the Attempt uncertain.

---

## 14. Workspace and source integrity

The devserver runs against the exact Attempt worktree already bound by `WorkspaceIdentity`.

Rules:

- browser may not mount or inspect other worktrees through file URLs;
- output/screenshots go outside tracked source paths;
- devserver-generated caches are permitted only in reviewed ignored paths;
- after browser proof, a Git status/diff receipt must prove no unexpected tracked mutation from the browser/devserver resource;
- the browser cannot be used to edit GitHub/Slack/Linear or production admin consoles in the local-review profile;
- the normal code-writing worker may still modify authorized source paths through its existing write authority; browser resource authority does not widen them.

---

## 15. Failure vocabulary

Browser resource failures should map into existing `AdapterFailureClass` where truthful, with bounded resource subcodes in redacted evidence rather than a new lifecycle taxonomy.

Required resource subcodes:

```text
DEVSERVER_MANIFEST_INVALID
DEVSERVER_PORT_EXHAUSTED
DEVSERVER_START_FAILED
DEVSERVER_READINESS_TIMEOUT
BROWSER_MCP_IDENTITY_MISMATCH
BROWSER_MCP_START_FAILED
BROWSER_TOOL_SCHEMA_MISMATCH
BROWSER_START_FAILED
BROWSER_NETWORK_ESCAPE
BROWSER_EXTERNAL_REDIRECT
BROWSER_ARTIFACT_OVERSIZE
BROWSER_SCREENSHOT_FAILED
BROWSER_VISUAL_CAPABILITY_UNPROVEN
BROWSER_ORPHAN_PROCESS_UNCERTAIN
BROWSER_WORKSPACE_MUTATION
```

Resource/MCP start/transport failures generally remain `MCP_OR_TOOL_TRANSPORT_FAILURE` or `CAPABILITY_ATTESTATION_FAILURE`; actual model work failure remains separate.

---

## 16. Security redlines

The first browser profile must never receive or inherit:

- Chairman Chrome profile;
- Chairman Multilogin profile;
- normal personal browser cookies;
- Keychain/session cookies copied into the worker;
- ChatGPT/Slack/GitHub/Linear web login state;
- provider auth homes beyond the worker provider realm already required by the operator harness;
- browser password manager state;
- clipboard history;
- arbitrary filesystem mounts;
- public bind address;
- unrestricted outbound network;
- arbitrary MCP/plugin installation.

Browser access does not mean “desktop access.”

---

## 17. B1 implementation wave — one useful vertical

After F0 acceptance, commission exactly one B1 implementation carrier in Mastermind plus the minimum canary product-repo manifest needed for real proof.

Observable mission:

> A governed rich worker Attempt can start an exact local product devserver, inspect it through a pinned isolated Playwright MCP at desktop and mobile viewports, consume a screenshot visually, capture console/network/screenshot receipts, and terminate all browser/devserver resources with no external network, Chairman browser identity or tracked-worktree side effects.

### Expected Mastermind scope

Likely existing surfaces to extend, not duplicate:

- `control_plane/operator_harness_contract.py` only if the generic capability identity needs the smallest resource-kind amendment;
- `control_plane/executive_agent_capabilities.py` / config for the reviewed browser profile;
- Operator Harness supervisor/orchestrator composition path;
- Codex adapter/App Server config staging for exact Playwright MCP attachment;
- browser/devserver resource helper module;
- tests and install/provisioning scripts.

### Product-repo scope

Exactly one real product repo receives one `mastermind.devserver_resource/v1` manifest for the canary. Do not migrate every repo in B1.

---

## 18. B1 acceptance tests and real proof

### Contract/profile

- exact required resource/MCP identity accepted;
- missing/extra/forbidden browser capability refuses before first provider turn;
- unpinned/changed Playwright package/tool schema refuses;
- model cannot widen browser tools or network in its prompt/config.

### Devserver

- manifest path/cwd traversal refused;
- shell strings refused; exact argv only;
- loopback-only bind proven;
- port collision bounded recovery works without persistent allocator;
- readiness timeout stops the owned process;
- devserver starts from the exact worktree SHA;
- no tracked workspace changes after clean review.

### Browser isolation

- fresh isolated browser context per Attempt;
- no cookies/storage from a prior Attempt;
- no Chairman/default browser profile access;
- file:// and out-of-workspace access refused;
- external HTTP/HTTPS/WebSocket/redirect egress falsifier passes;
- local origin works.

### Useful UI proof

On a real Mastermind product page through the local devserver:

- worker obtains structured snapshot;
- worker navigates/uses at least one bounded local interaction;
- worker captures desktop screenshot;
- worker captures mobile screenshot;
- worker reads console evidence;
- worker reads network evidence;
- worker detects one intentionally seeded visual-only fixture defect from screenshot content and distinguishes corrected output;
- final browser receipt hashes every proof artifact.

### Cleanup/recovery

- graceful browser/MCP/devserver stop leaves zero owned child processes;
- forced provider/controller failure does not allow a second generation until old browser/devserver state is proven dead/cleaned under existing OHF law;
- no browser resource DB, queue, lease table or daemon exists.

Only after the real worker uses the real resource and Sol sees the resulting product/browser proof may the capability become `PROVEN_LIVE`.

---

## 19. Follow-on B2 production inspection profile

After B1 is production-proven, a narrow B2 may add read-only inspection of exact company-owned production origins if it materially reduces product QA friction.

B2 must separately freeze:

- exact allowed company origins;
- network enforcement stronger than Playwright allowOrigins alone;
- whether authenticated QA/test identities are needed;
- read-only interaction restrictions;
- no Chairman cookie/session inheritance;
- production-side-effect falsifiers.

B2 is not required to finish the first Autonomy V1 browser proof.

---

## 20. Explicit non-goals

F0/B1 do not include:

- generic remote desktop/VNC control;
- Chairman browser automation;
- Personal-Pro Multilogin canary machinery;
- Slack/Linear/GitHub web UI automation;
- arbitrary public web research browsing;
- CAPTCHA/login automation;
- credential vault/browser password integration;
- multi-host/VPS browser farm;
- arbitrary dynamic MCP install;
- provider-neutral HF1 implementation;
- CF2 capacity placement;
- ASD dialogue transport.

Those remain distinct programs/waves.

---

## 21. Stop condition and continuation handoff

### F0 stop

Stop after this architecture/source law is independently reviewed and accepted. Do not implement the browser resource in the same carrier.

### B1 stop

Stop after one real governed worker/browser/devserver vertical is production-proven with structured + visual proof and cleanup. Do not absorb every product repo, production browsing, remote desktop or provider into B1.

### Return to Sol if

- a real provider/harness cannot consume MCP image output;
- secure local-only browser networking cannot be falsifier-proven without a materially larger host subsystem;
- the existing OHF capability contract cannot represent the resource without semantic abuse;
- browser sidecars cannot be reconciled through the existing generation/worker-principal cleanup law;
- the selected product repo cannot express a bounded devserver manifest.

On PASS, the exact next action is a fresh B1 implementation commission. CF2-F/CF2-I, Personal-Pro ingress, ASD and host-readiness lanes continue independently.
