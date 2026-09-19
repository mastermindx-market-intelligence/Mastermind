# ChatGPT Web Sol Exact-Surface Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every production behavior follows RED -> observed discriminating failure -> minimal GREEN -> exact-head hosted proof -> independent review -> Sol acceptance.

**Goal:** Build a production-inert, exact-target ChatGPT Web Sol surface adapter that can health-check and foreground one already-bound managed-browser conversation without transcript extraction, generic browser control, message submission, lifecycle authority, or OpenClaw dependence.

**Architecture:** Preserve `mastermind.surface_bindings.v1` as navigation-only identity. Add a profile-local Chrome-compatible extension and a local native-messaging bridge that exchange only closed S0/S1 surface messages. The first implementation PR stops at disposable-profile proof; OCR-6/Steward later consumes the sanitized observation/foreground receipt. OpenClaw stays fallback-only.

**Tech Stack:** Python 3.11+/3.12, Chrome-compatible Manifest V3 JavaScript, Chrome extension `tabs`/`windows`/`nativeMessaging`, existing `integrations/chairman_surfaces` patterns, pytest, existing MAS-115 disposable managed-browser canary substrate.

**Spec:** `docs/superpowers/specs/2026-08-29-chatgpt-web-sol-surface-adapter-amendment.md` on Mastermind PR #188.

## Global Constraints

- Existing workstream: `WS:CHAIRMAN-CONTROL-ROOM`; no new lifecycle/workstream/control plane.
- Existing `control_plane.surface_bindings` remains navigation only.
- Exact target is resolved before the adapter is called; URL/title/process recency never selects a target.
- Initial actions are exactly `INSPECT` and `FOREGROUND`.
- No transcript/model-output export, arbitrary DOM dump, cookie/storage/clipboard/proxy/fingerprint read, generic shell, arbitrary JavaScript, click/type/send, account switching, provider selection, Wake creation, retry/failover or persistent health store.
- Chairman production seats are not modified in the first implementation carrier. Use disposable/non-sensitive managed-browser proof only.
- Extension/native-host absence is typed unsupported/degraded; never silently fall back to OpenClaw.
- OpenClaw runtime work is outside this plan.
- S2 same-surface repair and S3 Web Sol message/wake submission are outside this plan.
- Re-pin protected Mastermind and inspect open-PR path collisions immediately before every modifying task.

---

### Task 1: Closed Web-Sol surface protocol

**Files:**
- Create: `integrations/chairman_surfaces/web_sol_protocol.py`
- Create: `tests/test_web_sol_protocol.py`

**Interfaces:**
- Produces `PROBE_SCHEMA = "mastermind.web_sol_surface_probe.v1"`.
- Produces `ACTION_SCHEMA = "mastermind.web_sol_surface_action.v1"`.
- Produces `RECEIPT_SCHEMA = "mastermind.web_sol_surface_receipt.v1"`.
- Produces `SurfaceAction` closed enum with `INSPECT`, `FOREGROUND` only.
- Produces `validate_request(dict) -> dict` and `validate_receipt(dict) -> dict` returning normalized validated copies or raising `WebSolProtocolError`.
- Request identity contains only an opaque adapter-local `binding_id`, exact conversation URL digest/fingerprint, binding revision/fingerprint, action, operation key, and freshness/nonce material mechanically provided by the caller. It contains no transcript, prompt, host/account selection or credentials.

- [ ] **Step 1: Write RED tests for the exact closed schemas.**

```python
def test_action_surface_is_exactly_inspect_and_foreground():
    assert {item.value for item in SurfaceAction} == {"INSPECT", "FOREGROUND"}


def test_transcript_and_generic_browser_fields_are_refused():
    request = valid_request() | {"transcript": "secret", "selector": "textarea", "script": "..."}
    with pytest.raises(WebSolProtocolError):
        validate_request(request)
```

Add mutation cases for `cookie`, `storage`, `clipboard`, `prompt`, `message`, `text`, `coordinates`, `shell`, `argv`, `host_ref`, `provider`, `account`, `profile_id`, `folder_id`, `url`, `retry`, `failover`, and unknown nested keys.

- [ ] **Step 2: Run the focused tests and record the intended missing-module RED.**

Run: `python3 -m pytest tests/test_web_sol_protocol.py -q`

Expected: collection failure because `web_sol_protocol` does not exist.

- [ ] **Step 3: Implement the minimal pure protocol module.**

Use standard-library-only validation, frozen key sets, bounded string lengths, canonical JSON, and SHA-256 helpers. Do not import browser, subprocess, filesystem, network, Slack, Wake or Executive modules.

- [ ] **Step 4: Run protocol tests and existing chairman-surface contract tests.**

Run: `python3 -m pytest tests/test_web_sol_protocol.py tests/test_chairman_surfaces.py tests/test_surface_bindings.py -q`

Expected: PASS.

- [ ] **Step 5: Commit Task 1.**

Commit message: `feat(surface): add closed Web Sol adapter protocol`.

---

### Task 2: Profile-local Manifest V3 extension — S0 inspect only

**Files:**
- Create: `integrations/chairman_surfaces/web_sol_extension/manifest.json`
- Create: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Create: `integrations/chairman_surfaces/web_sol_extension/content.js`
- Create: `tests/test_web_sol_extension_static.py`

**Interfaces:**
- Extension host scope is only approved ChatGPT hosts required by existing `surface_bindings` law.
- Background service worker exposes no externally_connectable/public network interface.
- Native host communication uses one fixed native application name constant.
- Content script returns a bounded observation object only; no raw DOM/string text nodes are exported.

- [ ] **Step 1: Write RED static tests for the manifest and source fences.**

Assert:

```text
manifest_version == 3
permissions subset == {tabs, nativeMessaging}
host_permissions subset == exact ChatGPT hosts
no debugger permission
no scripting permission
no webRequest permission
no clipboard permission
no cookies permission
no downloads permission
no externally_connectable
```

AST/text fences refuse `innerText`, `textContent` export, `document.cookie`, local/session storage, clipboard APIs, `eval`, `Function`, arbitrary selector input, `fetch`, `XMLHttpRequest`, WebSocket, click, keyboard/input dispatch or form submission.

- [ ] **Step 2: Run RED before adding extension files.**

Run: `python3 -m pytest tests/test_web_sol_extension_static.py -q`

Expected: FAIL on missing files.

- [ ] **Step 3: Implement the minimal S0 extension.**

`content.js` may derive only booleans/enums from the current exact page, such as:

```javascript
{
  urlMatchesBoundConversation: boolean,
  documentReadyState: "loading" | "interactive" | "complete",
  visibility: "visible" | "hidden",
  composerAvailable: boolean | null,
  generationState: "active" | "idle" | "unknown",
  authRequired: boolean | null,
  providerErrorPresent: boolean | null
}
```

Do not return text content. Selectors used internally must be fixed constants in extension source, never caller supplied, and failures produce `unknown` rather than scraping fallbacks.

- [ ] **Step 4: Run JS parse/static tests.**

Run Node syntax checks plus `tests/test_web_sol_extension_static.py`.

- [ ] **Step 5: Commit Task 2.**

Commit message: `feat(surface): add read-only Web Sol extension`.

---

### Task 3: Native-messaging bridge — closed S0 transport

**Files:**
- Create: `integrations/chairman_surfaces/web_sol_native_host.py`
- Create: `config/web_sol_native_host_manifest.json`
- Create: `tests/test_web_sol_native_host.py`

**Interfaces:**
- Reads/writes Chrome native-messaging length-prefixed JSON on stdin/stdout only.
- Accepts exactly the Task-1 request schema.
- Returns exactly the Task-1 receipt schema.
- No generic subprocess, shell, network listener, filesystem browsing or durable queue.

- [ ] **Step 1: Write RED framing/schema/attack tests.**

Cover partial frame, oversized frame, multiple messages, unknown action, unknown extension/origin identity, forbidden fields, malformed UTF-8/JSON, stdout contamination, timeout/effect uncertainty, and secret-shaped values.

- [ ] **Step 2: Run RED.**

Run: `python3 -m pytest tests/test_web_sol_native_host.py -q`

Expected: missing module.

- [ ] **Step 3: Implement minimal native host.**

Use exact maximum frame size, deterministic JSON encoding and one-request/one-response behavior. The host never reads browser credentials; browser state arrives only as the bounded extension observation.

- [ ] **Step 4: Run focused and static security tests.**

Run protocol + native-host + chairman-surface tests and `python3 -m compileall -q integrations/chairman_surfaces/web_sol_native_host.py`.

- [ ] **Step 5: Commit Task 3.**

Commit message: `feat(surface): add bounded Web Sol native bridge`.

---

### Task 4: Exact-target S1 foreground inside the bound managed profile

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Modify: `integrations/chairman_surfaces/web_sol_extension/content.js` only if postcondition observation needs an additional boolean/enum
- Modify: `tests/test_web_sol_extension_static.py`
- Create: `tests/fixtures/web_sol_extension/` deterministic browser-message fixtures only if required

**Interfaces:**
- `FOREGROUND` receives no raw URL/profile/account target. It receives the exact Task-1 binding fingerprint and the extension compares it with the already-provisioned profile-local binding material/session.
- Selects the exact conversation by exact normalized conversation identity previously provisioned for this extension instance; never title/recency similarity.
- Uses only tabs/windows activation APIs; no navigation, typing or message submission in the first release.

- [ ] **Step 1: Add RED tests for target ambiguity and binding drift.**

Required cases:

```text
two similar-looking tabs -> exact identity wins
no exact tab -> TARGET_NOT_FOUND
binding revision changed -> TARGET_CHANGED
wrong ChatGPT host/path -> refuse
exact tab in background window -> activate tab then focus its window
FOREGROUND never calls navigate/update-url APIs
```

- [ ] **Step 2: Run RED against S0-only extension.**

Expected: S1 cases fail because no foreground action exists.

- [ ] **Step 3: Implement the smallest S1 handler.**

No `chrome.tabs.update(..., {url: ...})`; activation/focus only. Return postcondition receipt with the exact observed binding fingerprint and `FOREGROUNDED_VERIFIED` only after the extension confirms the active exact tab.

- [ ] **Step 4: Run all extension/protocol/native-host tests.**

Expected: PASS.

- [ ] **Step 5: Commit Task 4.**

Commit message: `feat(surface): foreground exact Web Sol conversation`.

---

### Task 5: Keep existing `chatgpt.py` fail-closed until disposable proof

**Files:**
- Modify only after Task 4 GREEN and current-path collision review: `integrations/chairman_surfaces/chatgpt.py`
- Test: existing ChatGPT chairman-surface tests plus new focused adapter tests

**Interfaces:**
- Existing `open_surface()` behavior must not silently change to the extension path before the extension/native bridge is explicitly attested available.
- Add an adjacent explicit adapter seam such as `inspect_via_extension(binding, bridge)` / `foreground_via_extension(binding, bridge)` rather than turning the current generic runner into browser authority.
- `open_surface()` may remain the legacy refusal path until a later reviewed composition change.

- [ ] **Step 1: Write RED proving default behavior stays refusal and explicit adapter succeeds only with attestation.**
- [ ] **Step 2: Implement the smallest explicit bridge seam.**
- [ ] **Step 3: Run full chairman-surface/surface-binding matrix.**
- [ ] **Step 4: Commit Task 5.**

Commit message: `feat(surface): expose explicit Web Sol extension seam`.

---

### Task 6: Disposable managed-browser canary — no Chairman seat

**Files:**
- Prefer extending existing inert MAS-115 disposable canary helpers only if current owner/path collision review permits; otherwise add a new isolated test/probe module under `integrations/chairman_surfaces/` and do not edit protected canary paths.
- Add sanitized immutable evidence under the currently accepted evidence location only after Sol reviews raw proof.

**Interfaces:**
- One disposable/non-sensitive Multilogin or GoLogin profile.
- Install/load extension through a documented profile mechanism.
- Register native host without exposing secrets.
- No Chairman `chatgpt1/2/3` profile modification.

- [ ] **Step 1: Prove extension actually loads in the installed managed-browser core.**
- [ ] **Step 2: Prove native messaging reaches the exact local host and S0 returns only bounded booleans/enums.**
- [ ] **Step 3: Open two safe ChatGPT test tabs and prove exact S1 foreground without title/recency selection.**
- [ ] **Step 4: Adverse canaries: extension absent, native host absent, auth wall, provider error, binding drift, duplicate-looking tab, browser restart, OpenClaw absent.**
- [ ] **Step 5: Scan receipts for transcript/model-output/cookie/clipboard/proxy/fingerprint leakage.**
- [ ] **Step 6: Return to Sol; do not install into Chairman Sol seats.**

**Stop condition:** one exact-head PR proves the closed production-inert S0/S1 adapter on a disposable managed-browser environment, with zero Chairman-seat mutation, zero message submission and zero OpenClaw dependency. Real Chairman-seat installation, OCR-6 Steward composition, S2 repair and S3 Web Sol wake are separate waves.

---

### Task 7: OCR-6 integration handoff only — no implementation in this carrier

**Files:** none in the S0/S1 PR.

- [ ] Return the final protocol/receipt schema digest, exact adapter function names, disposable proof, install requirements and adverse results to the sole OCR-6 owner.
- [ ] OCR-6 later maps S0 receipts into `mastermind.surface_health_observation.v1` and consumes S1 only through its already-resolved exact `surface_ref`.
- [ ] Do not create a second Steward, health store, watcher, Wake path or OpenClaw bridge from the extension PR.

## Final acceptance for this plan

The S0/S1 implementation is accepted only when a fresh Sol can prove all of the following from the exact final head:

```text
closed protocol
+ extension static security
+ native host framing/security
+ exact-target foreground semantics
+ legacy adapter default remains fail-closed
+ disposable managed-browser live proof
+ zero Chairman-seat mutation
+ zero transcript/output extraction
+ zero generic browser/computer control
+ zero message submission
+ zero OpenClaw dependency
+ explicit OCR-6 continuation handoff
```
