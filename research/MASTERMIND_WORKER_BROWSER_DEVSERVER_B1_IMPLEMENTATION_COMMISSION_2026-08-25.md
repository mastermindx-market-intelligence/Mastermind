# Mastermind-X Worker Browser / DevServer Resource B1 — Implementation Commission

**Date:** 2026-08-25  
**Commissioner:** Sol, AI CEO  
**Chairman authority:** current Chairman directive to finish Autonomy V1 rapidly under Sol oversight  
**Operator:** one bounded Codex principal builder; use subagents only for independent tests/review, not for a second implementation carrier  
**Operation key:** `WORKER-BROWSER-B1-20260825`  
**Repository:** `mastermindx-market-intelligence/Mastermind` only  
**Carrier:** branch `sol/worker-browser-b1-20260825` / the draft PR opened from this branch  
**Pickup / protected basis:** `068125e3524eb1b327721f1e79a2338f3d367554`  
**Skillpack basis:** `mastermind.sol_skillpack.v1` v1.0.0 / bootstrap major 1 at that exact protected commit  
**Controlling F0:** `research/MASTERMIND_WORKER_BROWSER_DEVSERVER_RESOURCE_F0_ARCHITECTURE_2026-08-25.md`

---

## 0. Observable mission

A governed rich worker Attempt can start the exact Mastermind Chairman Control Room from its exact worktree, inspect it through a pinned isolated Playwright MCP at desktop and mobile viewports, obtain structured browser state plus screenshots/console/network evidence, **actually use screenshot pixels for visual judgment**, and terminate every browser/MCP/devserver process with no external network, no Chairman/default browser identity and no unexpected tracked-worktree mutation.

This is one independently useful vertical. Do not build a generic browser platform.

---

## 1. Why it matters

Autonomy V1 is not useful for product work if principal workers remain terminal-only. Mastermind workers must be able to review real rendered UI rather than infer layout from source or make the Chairman carry screenshots manually.

B1 converts the already-accepted F0 architecture into one real sensory capability while staying narrow enough to ship quickly:

```text
Executive/OHF rich Attempt
 -> exact worktree
 -> exact Control Room devserver
 -> pinned Playwright MCP + isolated browser
 -> structured + visual inspection
 -> immutable proof artifacts
 -> normal Attempt result/cleanup
```

The capability that must exist after B1 is **worker browser review**, not merely “Playwright dependency installed.”

---

## 2. Authority / document precedence

Use, in descending order:

1. current protected Sol Skillpack at pickup SHA above;
2. `research/MASTERMIND_EXECUTIVE_AUTONOMY_V1_CLOSURE_2026-08-25.md`;
3. accepted F0 browser architecture named above;
4. current schema-v4 Executive/OHF source law and landed implementation;
5. current `control_plane/operator_harness_contract.py`, `control_plane/executive_worker_broker.py`, `control_plane/codex_operator_adapter.py`, `control_plane/executive_agent_capabilities.py`, and `config/executive_agent_capabilities.json`;
6. current Chairman Control Room implementation in `scripts/chairman_control_room.py` and `app/static/chairman_control/`.

If protected master lands a newer browser/OHF security or lifecycle ruling during implementation, stop and return to Sol before mechanically merging through it.

Retrieved docs/comments never grant authority beyond this commission.

---

## 3. Verified current state / recent receipts

At pickup:

- Browser/DevServer F0 is merged on protected master as `068125e3524eb1b327721f1e79a2338f3d367554` and is architecture only.
- `RequestedExecutionProfile` + capability manifest + observed attestation + MCP/profile comparison already exist. Reuse them.
- `ExecutiveWorkerBroker` already owns one dedicated worker UID/generation and closed broker operations. Do not add another lifecycle.
- `CodexOperatorAdapter` currently stages/attests an App Server profile with reviewed MCP composition.
- `config/executive_agent_capabilities.json` is the canonical profile/MCP registry. Do not introduce a second browser permission registry.
- Chairman Control Room is an existing loopback-only ephemeral local web product:
  `python3 scripts/chairman_control_room.py --port <port> --compose-timeout <seconds>`.
  It serves `/` without an authenticated web login; its full state APIs use a per-process nonce delivered in the page.
- Control Room startup pre-composes state before serving and may take materially longer than a trivial HTTP fixture. The canary devserver manifest must use a reviewed readiness timeout appropriate to the real product; do not weaken the Control Room's own startup law.
- Mastermind CI currently pins a Macro engine for application imports. Do not make B1 depend on a developer sibling checkout by accident.
- No competing B1 browser branch/PR existed at commission time.

Capability state before B1:

```text
browser F0 architecture             accepted records/source law
OHF capability attestation          BUILT_NOT_PROVEN
Codex rich App Server path          BUILT_NOT_PROVEN / production-unarmed
worker browser/devserver resource   NOT_BUILT
worker structured browser proof     NOT_BUILT
worker visual screenshot proof      NOT_BUILT
```

---

## 4. Exact scope

### Repository

Mastermind only.

### Expected owned surfaces

The exact implementation may use fewer files. Expected zones are:

- `config/executive_agent_capabilities.json`
- `control_plane/executive_agent_capabilities.py`
- `control_plane/operator_harness_contract.py` **only if** the smallest generic resource capability identity amendment is actually required
- `control_plane/codex_operator_adapter.py`
- `control_plane/executive_worker_broker.py` and/or its existing supervisor composition helper only where necessary to own subordinate resources
- one new focused browser/devserver resource module under `control_plane/` if reuse cannot keep responsibilities clear
- one reviewed Control Room devserver resource manifest under `config/` or another existing configuration home
- installation/provisioning scripts under `ops/executive_os/` only as required to install/pin browser runtime dependencies
- focused tests
- one bounded visual-only fixture under tests/fixtures or equivalent test-only location

### Protected / no-edit-by-convenience surfaces

Do not change:

- Executive SQLite schema / migrations;
- Job/Attempt/Worker/Event lifecycle semantics;
- CEO ingress / Slack / ASD;
- CF2 capacity placement;
- G7 receipt semantics except if a real existing runtime guard must be invoked at the already-required resource boundary;
- Chairman Control Room canonical behavior merely to make the browser test easier;
- provider credential-home isolation;
- normal Chairman Chrome/Multilogin profiles.

If the resource cannot be implemented without touching one of these, stop for Sol.

---

## 5. Explicit non-goals

Do **not** absorb:

- arbitrary internet browsing;
- authenticated production-site inspection;
- generic remote desktop/VNC;
- Chrome/Multilogin Chairman automation;
- Slack/GitHub/Linear web UI automation;
- CAPTCHA/login/password-manager integration;
- every Mastermind product repo;
- multi-host/VPS browser farm;
- dynamic arbitrary MCP/plugin install;
- Claude/Grok/Cursor provider integration;
- HF1 provider-neutral worker generalization;
- CF2 capacity work;
- Control Room feature redesign.

One local Control Room vertical is enough for B1.

---

## 6. Complete user / machine journey

### Normal journey

1. Executive/OHF receives a rich Attempt whose requested profile requires the accepted local-browser capability.
2. Before the provider turn, trusted code validates the exact execution profile, exact workspace identity and one reviewed Control Room devserver manifest.
3. Supervisor allocates one bounded loopback port without creating a persistent allocator.
4. Supervisor starts the Control Room from the exact worktree with direct argv, loopback host and the manifest's bounded readiness timeout.
5. Readiness is proven through the exact local origin.
6. Supervisor starts the **pinned** Playwright MCP and a fresh isolated headless browser/context under the same worker generation/resource realm.
7. MCP identity/version/tool-schema and network/browser isolation are attested against the requested profile before the first worker browser turn.
8. Worker navigates to `/`, obtains structured snapshot/accessibility state, performs one harmless local interaction, resizes to desktop/mobile, collects screenshots, console evidence and network evidence.
9. Worker demonstrates visual capability on the discriminating screenshot fixture and returns a judgment that cannot be derived from accessibility text alone.
10. Browser review receipt hashes screenshots/evidence in the normal Attempt artifact directory.
11. Provider/browser/MCP/devserver all terminate; existing generation/UID cleanup proves no orphan survives.
12. Git status/diff proves the resource itself produced no unexpected tracked source mutation.
13. Normal CandidateResult / artifact/result path continues. Browser proof itself does not mark a Job complete.

### Degraded/refusal journeys

- bad devserver manifest -> refuse before process start;
- no port in bounded range -> refuse;
- readiness timeout -> stop owned devserver, refuse;
- MCP version/tool schema drift -> refuse before provider browser turn;
- browser external egress succeeds -> **security failure / refuse**, not warning;
- screenshot/image output generated but model cannot consume/judge it -> `BROWSER_VISUAL_CAPABILITY_UNPROVEN`, no B1 acceptance;
- unexpected tracked worktree mutation -> refuse/hold evidence;
- cleanup/orphan identity uncertain -> remain uncertain under existing OHF reconciliation; do not launch a second generation blindly.

---

## 7. Devserver manifest for the canary

Implement exactly one `mastermind.devserver_resource/v1` manifest for Chairman Control Room.

The reviewed effective command should be equivalent to:

```text
<exact reviewed Python executable>
scripts/chairman_control_room.py
--port
{port}
--repo-root
<exact Attempt worktree>
--compose-timeout
240
```

Do not include `--open`.

The worker/model cannot author executable, script, cwd, repo-root, timeout or readiness URL.

Readiness origin is loopback and readiness path may be `/` because the index page is login-free. The supervisor must still verify status/content at the correct origin rather than merely assuming a listening PID is ready.

The Control Room can resolve Macro state through its own existing rules; missing/degraded organizational data does not by itself invalidate the browser resource if the product server legitimately renders its degraded state.

The resource must not write surface bindings during the canary; browser interactions are limited to read-only/local presentation behavior unless a specific harmless UI action is proven not to invoke a write endpoint.

---

## 8. Browser / Playwright MCP capability profile

Extend the canonical `config/executive_agent_capabilities.json`; do not create a parallel browser policy file.

Create one reviewed profile conceptually named:

```text
operator.browser.local-review.v1
```

The profile should inherit current rich-operator restrictions and add only the exact pinned Playwright MCP/resource capability.

### MCP pinning

- official Playwright MCP implementation only for B1;
- exact package/version, not floating latest;
- deterministic install lock/checksum as available through the chosen package mechanism;
- exact MCP server identity/version and normalized tool-schema digest included in current requested/observed capability attestation;
- missing/extra MCP/tool capability fails closed;
- model cannot install/enable additional MCP servers.

### Browser identity

Every Attempt generation receives:

- fresh isolated browser/context;
- no persistent user-data-dir;
- no prior cookies/local storage/session storage;
- no Chairman Chrome/Multilogin profile;
- no browser password manager;
- no clipboard/session inheritance.

### Tool allowlist

Expose the minimum useful local-review surface:

- navigate local origin;
- accessibility/browser snapshot;
- screenshot / element screenshot;
- viewport resize;
- bounded wait/tab operations;
- console messages;
- network request inspection;
- bounded local click/hover/form interaction required by the proof.

Default-refuse:

- arbitrary unsafe Playwright code execution;
- arbitrary file upload;
- storage/auth import/export;
- arbitrary file URLs;
- extensions;
- external navigation;
- dynamic browser/runtime installation by the model.

If the official server cannot be reduced to the required surface through its reviewed configuration/tool controls, return to Sol; do not expose everything for convenience.

---

## 9. Network law

The first B1 browser profile may reach **only the leased local Control Room origin**.

Playwright's own allowed-origin configuration is defense in depth, not the accepted security boundary.

The implementation must choose the smallest host-enforcing mechanism and prove it black-box. Acceptable architecture shapes include a supervisor-owned enforcing loopback proxy plus locked browser proxy config, or an equivalent process/network sandbox already available on the host. Do not build a general proxy service or persistent network policy daemon.

Must prove:

- local leased origin succeeds;
- direct external HTTP and HTTPS navigation fails;
- external redirect fails;
- external subresource/fetch fails;
- external WebSocket fails;
- model/MCP cannot alter the browser's network/proxy launch configuration;
- `file://` navigation fails;
- operator shell/network remains governed by its existing separate requested profile.

If macOS production cannot enforce this outcome with a bounded subordinate resource, stop and return the exact falsifier to Sol rather than weakening to “Playwright allowOrigins is probably enough.”

---

## 10. Structured vs visual proof

Treat these as separate capabilities.

### `browser.structured.v1`

The worker can consume accessibility/browser snapshots and console/network state to locate and reason about elements.

### `browser.visual.v1`

The selected Codex App Server/harness can consume screenshot image output and use pixels for judgment.

Create one discriminating **test-only** visual fixture where:

- accessibility/text content is intentionally the same between A and B;
- one version has an obvious pixel-only defect (e.g. clipped/occluded/overlapping element or off-canvas critical content);
- the worker must correctly identify which screenshot is defective and why;
- passing cannot be achieved from filename/text/DOM semantics alone.

Do not pollute the production Control Room UI with a fake defect just for the test.

After this synthetic visual gate, run the real Control Room desktop/mobile proof.

---

## 11. Browser review receipt / artifacts

Implement the F0 `mastermind.browser_review_receipt/v1` as a normal Attempt artifact, not an Executive Event table.

Receipt must bind at least:

```text
attempt_id
workspace base SHA / workspace identity
exact devserver manifest digest
exact browser capability/profile digest
Playwright MCP identity/version/tool-schema digest
local origin
viewports
screenshot relative paths + bytes + SHA-256
bounded console summary/evidence digest
bounded network summary/evidence digest
external_egress_observed=false
tracked_workspace_changes_after_review=false
```

Never embed screenshot bytes in SQLite Events.

Artifact paths must resolve inside the Attempt artifact directory and not inside tracked source.

Put explicit byte/count ceilings on screenshot count/size, console rows and network rows. Oversize evidence refuses rather than silently truncating evidence that the final receipt claims complete.

---

## 12. Process/resource lifecycle

Browser, Playwright MCP and Control Room devserver are subordinate to the existing worker generation.

### Start

```text
validate requested profile/workspace
-> validate manifest
-> choose bounded port
-> start devserver
-> prove readiness
-> start MCP/browser
-> attest resource + MCP + network law
-> only then allow first provider browser turn
```

### Stop

```text
finish/interrupt provider turn under existing OHF law
-> close browser/context
-> stop MCP
-> stop devserver
-> prove subordinate death / whole worker UID cleanup
-> seal artifact receipt
-> continue existing CandidateResult/Attempt transition
```

No browser-specific Job, lease database, retry table or orphan registry.

A restart or timeout with uncertain subordinate state uses existing generation/process reconciliation before replacement. Never launch a second browser/devserver generation because a response was lost.

---

## 13. Time / null / correction behavior

- Port is Attempt-local ephemeral evidence, never canonical resource identity.
- Browser/process timestamps are UTC and evidence-only.
- Missing required capability/receipt field is refusal, not false/empty success.
- Console/network absence must distinguish “observed empty” from “capture unavailable.”
- A later rerun creates new artifacts/receipt under the new Attempt/generation; never mutate an older receipt.
- Screenshot hashes are immutable evidence for that proof only; they are not a long-lived visual baseline system.
- Resource failure before any provider/browser turn may be retried only within the bounded start law when effect is proven absent (e.g. next port). After an uncertain provider/browser effect, reconcile instead of blind retry.

---

## 14. Deterministic vs model-generated method

Deterministic first-party code owns:

- profile/resource admission;
- path/manifest validation;
- port selection;
- process launch/cleanup;
- MCP identity/tool-schema attestation;
- network confinement;
- screenshot/console/network artifact hashing;
- workspace mutation checks;
- failure classification.

Model judgment is allowed only for the **content** of visual/product review, e.g. “this panel overlaps at mobile width.” It cannot widen tool/network/auth permissions or mark resource/security gates passing.

---

## 15. Ordered implementation sequence

1. Freeze exact expected B1 files from the current repo and create a short implementation plan; do not redesign F0.
2. Add pure devserver manifest parser/validator and discriminating hostile tests.
3. Add subordinate devserver start/readiness/cleanup helper using the existing generation/workspace boundary.
4. Add pinned Playwright MCP definition to the existing capability registry/profile path and exact tool allowlist.
5. Add browser resource composition/attestation with fresh isolated context and artifact root.
6. Add external-egress confinement and black-box falsifiers before allowing the worker browser turn.
7. Add browser receipt/artifact hashing + bounded console/network capture.
8. Add structured browser fixture tests.
9. Add visual-only screenshot consumption fixture and prove the actual Codex operator can discriminate it.
10. Add Control Room manifest and run the exact local real-product proof at desktop/mobile widths.
11. Add forced-failure cleanup/restart tests and prove zero owned orphan processes/tracked source mutations.
12. Run full exact-head CI/security checks, independent review, then STOP for Sol. Do not merge autonomously unless a later explicit Sol review releases the carrier.

Work on independent tests/fixture design may be delegated in parallel after the interface is frozen. Do not have two writers implement the same resource manager/profile code.

---

## 16. Acceptance tests

At minimum, discriminate:

### Manifest / resource

- exact valid Control Room manifest accepted;
- unknown keys / shell strings / relative escape / symlink escape / non-loopback host refused;
- model/caller cannot choose argv/cwd/timeout/readiness path;
- occupied port uses bounded next candidate; 16 exhausted ports refuse;
- readiness timeout kills/reaps owned devserver;
- exact worktree SHA is the served repo root;
- generated output stays in reviewed ignored/artifact paths.

### Capability / MCP

- exact pinned MCP/profile accepted;
- missing/extra MCP/tool/skill/plugin refused;
- package/version/tool-schema drift refused;
- dynamic install or model-authored MCP override refused;
- browser starts with no inherited cookies/storage/profile.

### Network

- local origin allowed;
- external HTTP/HTTPS refused;
- redirect/subresource/WebSocket escape refused;
- `file://` refused;
- changing browser proxy/network through tools refused.

### Structured + visual

- structured snapshot drives a bounded element interaction;
- desktop screenshot receipt valid;
- mobile screenshot receipt valid;
- console capture is explicit and bounded;
- network capture is explicit and bounded;
- visual-only defect fixture cannot be solved from text/accessibility state and is correctly judged by the actual Codex operator path.

### Cleanup / integrity

- normal stop leaves zero owned browser/MCP/devserver processes;
- forced error leaves zero after existing cleanup law;
- uncertain generation blocks replacement until reconciled;
- no Chairman browser state accessed;
- no unexpected tracked worktree mutation;
- no new SQLite schema/table/queue/daemon/port registry.

---

## 17. Real production proof

Tests are not completion.

On the real primary Executive host, using an isolated Personal-Pro Codex worker realm and the real installed B1 release:

1. start one rich local-review Attempt on an exact Mastermind worktree;
2. start real Chairman Control Room via the manifest;
3. successfully navigate/read structured browser state;
4. perform one harmless local interaction;
5. capture desktop proof (recommend 1440x900 or current product desktop breakpoint);
6. capture mobile proof (recommend 390x844 or current product mobile breakpoint);
7. inspect actual console + network evidence;
8. prove the same worker previously passed the visual-only image fixture;
9. produce and hash `mastermind.browser_review_receipt/v1`;
10. stop and prove zero browser/MCP/devserver children remain;
11. prove worktree has no unexpected tracked mutation;
12. return screenshots + receipt/evidence to Sol for acceptance.

The proof may be run production-unarmed first only if it exercises the exact installed resource/harness path allowed by current host law; **Autonomy V1 final acceptance still requires the armed Executive journey later.** Do not conflate the two.

---

## 18. Failure states / stop-to-Sol conditions

Stop and return before widening if any is true:

- official Playwright MCP cannot expose a sufficiently bounded tool surface;
- actual Codex App Server cannot consume screenshot/image results through the governed path;
- local-only network enforcement cannot be proven without a materially new long-lived host service;
- safe implementation requires Chairman browser cookies/profile;
- Control Room cannot be served from an exact worker worktree without mutating canonical state;
- existing OHF generation/cleanup cannot own browser/MCP/devserver children safely;
- implementing browser resource requires a second capability registry/lifecycle/store;
- a newer protected source law collides with the changed paths.

A failure here is an architecture falsifier, not permission to remove the redline.

---

## 19. Stop condition

Stop when exactly one real governed **Codex + Chairman Control Room** local-review vertical has passed exact-head tests and the real browser proof above, with independent review complete.

Do **not** continue into:

- production-site browsing;
- every product repo;
- Claude/provider-neutral browser parity;
- arbitrary web research;
- remote browsers/VPS;
- CF2/ASD/ingress work.

Return to Sol for final acceptance and B2/V1 integration sequencing.

---

## 20. Required continuation handoff

Return one concise durable packet containing:

- exact PR/head and protected pickup;
- exact changed files;
- exact package/browser/MCP versions + tool schema digest;
- capability/profile/resource digests;
- tests and hosted CI receipts;
- external-egress falsifier results;
- visual-only fixture result proving image interpretation;
- real Control Room desktop/mobile screenshot artifact paths + hashes;
- console/network receipt summary;
- process cleanup receipt;
- git/workspace integrity receipt;
- anything still unproven;
- any architecture/security falsifier;
- exact next action.

Keep the PR held for Sol review. Merge is not production proof.
