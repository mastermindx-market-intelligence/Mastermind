# Web-Sol Session Census Implementation Plan and Source Receipt

**Goal:** make every eligible open ChatGPT tab visible in a bounded, honest profile-local snapshot, then evolve that evidence through the existing native and Control Room owners into fleet-wide observability.

**Architecture:** the extension popup is a transient read-only consumer of a profile-scoped Chrome tab query and the existing v1 top-frame probe. It owns no lifecycle, target registry, saved snapshot, queue, quota counter, authority or provider action. Model/effort observation and fleet transport remain separate bounded follow-on capabilities; this first view does not pretend to be the finished fleet.

**Tech stack:** Manifest V3, dependency-free browser JavaScript, Node's built-in test runner, Python/pytest; optional isolated Chromium/Playwright fixture proof.

**Spec:** Mastermind issue #501; current live Chairman instruction to advance Web-Sol telemetry and route browser-dependent Codex work through Secretary.

**Operation:** `web-sol-session-census-c1-20260906-sol-001`  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM` / MAS-198  
**Branch:** `sol/web-sol-session-census-c1-20260906`  
**Protected source and atomic Skillpack pin:** `467a81e84b08a7f1c3cdb9a410b2f7857816675d`  
**Skillpack:** `mastermind.sol_skillpack.v1`, version 1.0.1, bootstrap major 1  
**Authoring GitHub principal observed:** `mastermindx-3`  
**Source state:** `BUILT_NOT_PROVEN / DRAFT / HOLD-FOR-INDEPENDENT-REVIEW`  
**Provider/model/fleet production state:** not proven; no release, account, host or provider modification.

## 1. Full end-state and ownership

The Chairman should ultimately see all **enrolled and currently observable** Web-Sol profiles in the existing Control Room. Each surface should distinguish browser presence, visible generation cues, selected-next-turn model/effort, any separately supported turn evidence, current observation age, unknown coverage and exact binding status. A missing profile must be shown as missing, not silently omitted from an allegedly complete fleet.

Chrome tab activity is not execution. A stopped or hidden page is not proof a server-side computation stopped. Model-picker configuration is not proof of the model that actually served a turn. Observed activity is not total account usage or remaining quota. These distinctions are product requirements, not optional diagnostic labels.

| Fact | Owner |
|---|---|
| Current Job/Attempt/Worker execution | Executive OS |
| Organizational responsibility and durable continuation | Agent OS |
| Exact organizational session binding | existing RuntimeBinding / SessionTarget owner |
| Browser navigation coordinate | existing surface binding |
| Provider capacity/quota | Macro Shared AI Provider Control |
| Scope-limited browser cues | Web-Sol adapter |
| Fleet presentation | existing Control Room |
| Source, review and proof | GitHub |
| Placement, messages and hot state | Secretary / existing Slack transport |

The local popup is a diagnostic projection inside the already-owned extension, not a second Control Room or Session OS. It never elects a primary chat, assigns an operation, chooses a duplicate tab, or transfers a runtime binding.

## 2. Evidence corrections and collisions

The earlier chat proposed request/stream interception and treated actual served-model visibility as highly likely. That was not established by current primary-source or installed-browser proof. It is not adopted here. Private provider endpoints, hidden request metadata, request/response interception, MAIN-world network hooks, model self-identification, or inferred effort from duration cannot supply this program's evidence.

Existing owners, observed before source creation:

- PR #364, Q0 usage/capacity source law, remained Draft/HOLD at `505d5910b18c991aaa0627d6855699227683883d`. Its proposal is not protected procedure, but its ownership/privacy boundary is preserved; no quota implementation or eight Q0 paths are modified here.
- #480 already owns BRA-S0 model-selection/persistence falsification. #473 owns its separate BRA-F0 architecture gate. No duplicate mode investigation is commissioned by CENSUS1.
- #359 owns disposable profile/account readiness, #340 installed two-profile proof, #338 continuation falsification and #355 ChatGPT binding/readiness. Current Secretary work on those resources is not restarted or absorbed.
- Current protected `content.js` blob `b687f983ce025248a7b050ae2e784f05c86ad4d9` and manifest blob `c8f5f2ea51b0727d0ecb2db1757cfb181a925135` were reproduced locally and Git-blob-verified for the partial-source tests. The manifest change is only the new popup action registration.

Official documentation checked on 2026-09-06:

- https://developer.chrome.com/docs/extensions/reference/api/tabs — matching host permissions permit the scoped query; selected-tab, discarded and frozen are distinct browser facts. This does not attest provider execution.
- https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts — ordinary isolated scripts and extension messaging are sufficient for the current bounded DOM-cue probe.
- https://help.openai.com/en/articles/20001354-gpt-56-and-gpt-6-pro-in-chatgpt — model/effort controls are product- and plan-sensitive. Documentation is not a per-tab selection receipt or proof of actual backend routing.

No provider model name, UI label mapping, account limit or billing period is hard-coded from these time-sensitive documents.

## 3. CENSUS1 exact file and effect boundary

Modified: `integrations/chairman_surfaces/web_sol_extension/manifest.json`, only `action.default_title` and `action.default_popup`.

Added:

- `census_core.js` in that directory: collect, validate, redact, compare boundaries and derive counts.
- `census.js`: real local UI consumer and manual refresh, with safe text nodes.
- `census.html` and `census.css`: popup interface.
- `tests/web_sol_session_census.test.cjs`: Node behavior and controller fixtures.
- `tests/test_web_sol_session_census.py`: source fences, Node entrypoint and optional isolated browser fixture harness.
- this plan/source receipt.

No changes to `background.js`, `content.js`, native host/client, deployment renderer, protocol, capacity, RuntimeBinding, Wake, Control Room or other active source carriers. Native action v1 remains exactly `INSPECT | FOREGROUND`. No new permission, externally connectable endpoint or web-accessible resource is added.

The unchanged `0.1.0` transport/package pins do **not** prove installed freshness. This source adds a local surface without changing the wire handshake; the installation owner must prove exact source/artifact bytes, including the four new assets. If packaging or release-version policy requires a coherent package generation change, return that specific same-carrier decision request. Do not silently change host/client/version fences or install mixed assets. Independent review and installation proof remain held.

## 4. Journey and contract

The user opens the extension action. The local page calls:

```javascript
const snapshot = await MMXWebSolCensus.collect(
  chrome.tabs,
  MMX_WEB_SOL_INSTANCE.instanceId,
);
```

The collector queries only the two existing ChatGPT host patterns, excludes private/incognito tabs explicitly, takes a bounded sample, sends only the existing top-frame `MMX_WEB_SOL_REPROBE`, compares before/after locators, then performs one final inventory check. The popup renders rows and counts. Refresh replaces them. Closing the popup disposes of local state.

The `mastermind.web_sol_local_census.v1` object is **local diagnostic data**, not a new native receipt or Executive event. It must not be inserted into the closed native v1 schema or accepted as an organizational binding.

### Scope and coverage

`scope=CURRENT_PROFILE_NORMAL_CHATGPT_TABS`.

`inventory_coverage` is `COMPLETE_IN_SCOPE`, `PARTIAL` or `UNAVAILABLE`. Completeness means the eligible inventory was returned without truncation/malformed identities and remained equal at the two boundary checks. It is not an atomic snapshot, all account history, all devices, or all backend tasks.

`probe_coverage` is separate. Six known tabs with four successful probes are six inventory rows, not four total sessions. Initial query failure yields a null count, not zero. Final failure retains dated observations but makes coverage partial. New tabs during a sweep are counted as unobserved additions; disappearing/replaced rows lose stale cue evidence. Returned inventory over the limit is explicit rather than silently sliced.

Limits: at most 128 sampled rows, at most 4096 processed inventory entries, eight unresolved content probes per popup/API object, 800 ms per call, and a 5000 ms total sweep budget with final-query reserve. The eight-slot guarantee survives timeout and manual refresh: a timeout does not cancel Chrome's original message. A popup-lifetime weakly keyed pending-count semaphore prevents accumulating additional requests while those reads remain unresolved. It owns no target identities, saved observations or queue and never retries.

### Identity and time

The profile coordinate is the existing opaque adapter instance. Each row's slot number is local to that snapshot, not a durable tab identity. Conversation fingerprints preserve the existing canonical path/origin convention; titles, recency and tab order never elect a target.

Two views of one fingerprint remain two rows and one observed locator. Conflicting known generation cues are flagged on both rows; neither wins. Unknown members remain unknown.

Per-row UTC observation time and snapshot start/completion/duration remain explicit. A v1 probe does not bind Chrome `documentId`, so every row retains `document_binding=UNVERIFIED`. Before/after URL matching is not presented as an ABA-safe document-generation or runtime attestation. Future action-capable consumers cannot rely on this read-only diagnostic object.

### Generation and model facts

- `PRESENT`: the current v1 probe reported a generation UI cue.
- `NOT_OBSERVED`: the probe reported a composer without that cue. It does not mean proven idle or spare capacity.
- `UNKNOWN`: no defensible cue observation.

Browser selection, visibility, discarded/frozen state, auth cue and error cue remain separate. Frozen/discarded/loading/unreachable/non-conversation surfaces are not dropped or counted as idle.

`selected_model=null`, `selected_effort=null`, `served_model=null`, `model_evidence=UNVERIFIED` for this slice. These fields cannot be upgraded through model prose, duration, URL guesses, documentation-only mappings or raw provider metadata.

No raw URL, title, profile path, account identifier, DOM, transcript, prompt, output, token, cookie, storage value, clipboard data or free-form exception enters the normalized snapshot. No provider submit, model selection, tab/window foreground, reload, close, account change, native request or saved counter occurs.

## 5. Implementation and verification sequence

- [x] Write failing Node tests before creating `census_core.js`; initial run failed 27/27 on the missing capability.
- [x] Implement the bounded collector; initial behavior run passed 27/27.
- [x] Write UI/manifest source tests before wiring the consumer; initial Python run failed the missing popup and missing consumer checks.
- [x] Implement the popup and manifest registration without permission or native-action changes.
- [x] Add adversarial tests for timeout pressure, late replies, final replacement, malformed fields, contradictory duplicates and repeated-refresh pressure. The timeout/refresh tests reproduced 16 outstanding requests where the intended ceiling was eight; fix by retiring slots and preserving popup-lifetime unresolved-message backpressure.
- [x] Execute the actual popup controller in a DOM fixture with the real collector, proving row consumption, refresh, conflict rendering and fixed safe error output. This is not a visual-browser test.
- [x] Local Node suite: 35 passing, zero failures/skips. Python entrypoint/source tests: 3 passing, including the Node suite. Syntax checks passed. The local workspace is a **partial source reproduction**, not a complete repository checkout; full repository regression is not claimed.
- [ ] Full exact-head repository CI/security and non-author review.
- [ ] Browser visual and Chrome Tabs/content-script integration proof.
- [ ] Current installed-generation/profile proof through existing #340 owner.
- [ ] Separate release/expected-head merge and production acceptance.

Commands:

```bash
node --test tests/web_sol_session_census.test.cjs
python -m pytest -q tests/test_web_sol_session_census.py
node --check integrations/chairman_surfaces/web_sol_extension/census_core.js
node --check integrations/chairman_surfaces/web_sol_extension/census.js
python -m py_compile tests/test_web_sol_session_census.py
python tests/test_web_sol_session_census.py --browser-proof /approved/disposable/evidence
```

The optional browser harness uses wholly synthetic pages, offline contexts, temporary profiles/configuration and a fixture manifest that omits the native background. It is designed to exercise the real popup/content script and Chrome Tabs boundary; it cannot prove native-host deployment, production provider behavior or account eligibility.

### Actual browser attempt result in this session

The first synthetic ChatGPT-origin navigation returned `net::ERR_BLOCKED_BY_ADMINISTRATOR`. A separate local-file renderer attempt returned the same error. Neither reached the proof assertions. Browser policy was not changed, and no further policy workaround was attempted. **There is no passing browser screenshot, native/profile proof, current-model proof or installed-product proof from this session.** The independent host operator must run those checks where permitted and return a typed blocker rather than bypass a policy gate.

## 6. Secretary / Codex handoff

**Observable mission:** independently review the sole CENSUS1 source PR and obtain permitted synthetic Chrome integration/visual evidence, or identify the exact blocking source/policy condition without production effects.

**Why:** the local source/tests make the census concrete; the remaining meaningful uncertainty is browser execution/packaging and the current provider's model UI, not another generic architecture essay.

**Preferred avenue:** `CTO Sol` (Codex-backed); `CAPACITY_SELECTABLE` before START. `WHY NOT FABLE`: bounded JS/Chrome observation, concurrency and privacy review after Sol has specified and implemented the slice; sustained principal-level ambiguity is not needed. No paid API or automatic Pro-mode exception is requested.

**Exclusion:** source author is `mastermindx-3` / this source-writing Sol. An independent review must be genuinely non-author; another credential for the same author does not establish independence.

**Authority:** current live Chairman intent; current re-pinned Skillpack/source laws; current existing workstream/carriers; issue #501 and this packet. Re-pin at pickup and inspect material movement. Q0/BRA proposals are adjacent ownership evidence, not self-granting instructions.

**Ordered receiver work:**

1. Secretary reconciles exact existing carriers and places a concrete eligible session, or records `WAITING_CAPACITY / needs_placement`. No invented receiver, OPEN_PICKUP, runtime Job or execution claim.
2. Receiver reads the full exact Slack root, reports actual identity/PICKUP_ACK and effect=NONE, arms the accepted continuation path or reports its checked typed unavailability, and separately STARTs only the bounded source review.
3. Fresh-read the PR exact head/tree/base/diff, source receipts, current checks and all eight changed paths. Do not alter the source branch during read-only review.
4. Run full applicable repository tests and the independent adversarial suite. Verify schema/privacy, immutable v1 behavior, missing/degraded rows, bounded outstanding requests across refresh, duplicate disagreements and source/package integration.
5. In a policy-approved isolated synthetic browser, exercise the popup with multiple tabs, duplicate locators, discarded/frozen states, loading/unreachable probes, model UNKNOWN and responsive widths. Do not use a Chairman account, real conversation, live credential, installed legacy profile, or browser-policy bypass. Report the manifest/background difference in the fixture proof.
6. Return exact-head findings and actual evidence in the same carrier. Do not merge, install, select models, submit prompts, create realms, modify RuntimeBinding, or start a successor implementation.
7. Await an explicit Sol continuation/repair ruling or terminal STOP. A STOP removes only this child's watcher source, not Secretary's aggregate principal/seat watcher.

**Stop/return packet:** source head/tree/paths; base and current-source compatibility; command-backed test outcomes; each proof's exact class; observed failures; installed/model/fleet claims still unproven; exact next action. If a code defect or packaging path widening is needed, return it rather than quietly becoming the writer.

**Continuation availability:** no host-native Task/Automation/condition-watch tool is exposed in this ChatGPT tool surface. Installed Mastermind Executive metadata was discoverable, but an actual tool-discovery attempt returned only the current GitHub/Slack/etc. namespaces, not an Executive or browser/watcher action. Do not claim a Sol watcher is armed. Secretary must use an already accepted aggregate continuation path and return its actual receipt, or state the concrete missing capability. Slack delivery alone remains delivery.

## 7. Follow-on ledger; not hidden implementation scope

### Existing BRA-S0 / #480: visible model/effort evidence

Extend that existing investigation, not a new one. Required evidence is a per-control allowlist of non-secret DOM/accessibility attributes and normalized visible labels, observed on an approved disposable profile/account after its current gates. Capture only the relevant model-control region, not account/settings/sidebar/transcript content. Test ordinary and Project chats, initial/continued turns, changed selection before submit, already-generating state, reload/reopen, menu hidden, unavailable/disabled modes, duplicate views, old/new picker rollout and ambiguous/changed targets.

Separate three questions: selected-next-turn UI state; any supported per-turn product annotation; actual backend routing. Each unsupported field remains UNKNOWN. Do not map a generic Pro label to one actual backend model, assume effort persists per conversation, or use private networking to fill gaps. Mode modification/persistence experiments remain inside #480's original effect/gate boundary; this document grants no early SELECT/SEND path.

### C2: existing native path into existing Control Room

After C1 review and the applicable installed/identity gates, a separately commissioned vertical should transport a versioned read-only census through the existing profile-local native adapter and render it in the existing Control Room. The v1 action/receipt contract must not be widened in place. That vertical includes producer, native validation/bounds, real compositor consumer, missing-profile coverage, source freshness and installed proof. No independent fleet server, durable browser registry, account quota store or task election is allowed.

### M1: event-driven visible mode/cue upgrades

Only after #480 supplies accepted fixtures: add a bounded provider-UI observer and a versioned observation contract. Separate current selection from immutable turn-time observations, use explicit document/boot generations and stale-event rejection, surface conflicts, and invalidate on unknown layouts rather than guess. Scoped observers and backpressure are preferred to constant all-tab polling. Extension service-worker suspension/frozen tabs must yield stale/unknown state rather than fake completion.

These follow-ons preserve the full fleet vision. CENSUS1 is not the completed autonomy, model-telemetry, quota or global Control Room program.
