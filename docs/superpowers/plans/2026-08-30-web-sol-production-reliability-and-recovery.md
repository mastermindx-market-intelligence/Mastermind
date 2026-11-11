# Web-Sol Production Reliability and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every behavior follows RED -> observed discriminating failure -> minimal GREEN -> focused proof -> exact-head hosted proof -> independent review -> Sol acceptance. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Web-Sol S0/S1 adapter into a fleet-safe, self-reconstituting ChatGPT Pro-first CEO surface that can expose truthful health, foreground or repair one exact cockpit, issue one reconciled semantic wake, protect scarce Pro effort, and rotate an exhausted/dead conversation through canonical context without duplicating work.

**Architecture:** Extend the existing #219 extension/native-host/Python seam beneath the existing `surface_bindings`, RuntimeBinding, Wake, Capacity and Steward owners. Derive profile routing from the already-resolved managed-environment coordinate; never add another profile/session registry. Keep browser evidence descriptive, all modifying operations effect-reconciled, and all organizational truth outside the extension.

**Tech Stack:** Python 3.12+, Manifest V3 JavaScript, Chrome Native Messaging, private macOS AF_UNIX sockets, existing `control_plane.surface_bindings`, existing Wake/Capacity/RuntimeBinding/Steward contracts, pytest, Node behavioral harnesses, Multilogin Mimic 151/Chromium 151 installed-host validation.

**Spec:** `docs/superpowers/specs/2026-08-30-web-sol-production-reliability-and-recovery-amendment.md` on Mastermind PR #188, plus protected `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md`.

## Global Constraints

- Existing workstream only: `WS:CHAIRMAN-CONTROL-ROOM`; Linear projection `MAS-198`.
- Existing carriers remain authoritative: #188 architecture, #212 plan, #219 implementation, Macro #6636 Agent OS handoff.
- `COGNITION_ROUTE: CHAT_PRO_DEFAULT` is the default for Sol-class cognition. Metered/API/Workspace-Agent execution is exception-only and must never be silently substituted.
- Executive OS owns Job/Attempt/Worker/Event lifecycle and admission.
- Agent OS owns durable decisions, discoveries, continuation capsules and handoffs.
- Existing Capacity owns entitlement, model/effort availability, reservation and scarce-use budget.
- Existing RuntimeBinding/session-target/continuity owners select or transfer the one action-authoritative Sol.
- Existing Wake owns semantic delivery, effect reconciliation, target acknowledgement and source resolution.
- Existing `mastermind.surface_bindings.v1` remains navigation-only; adapter derivatives grant no authority.
- OCR-6/Steward consumes sanitized Web-Sol facts; #219 must not edit a concurrently owned #228 file.
- No transcript/model-output/raw-DOM export; no cookies, provider storage, clipboard, credentials, proxy or fingerprint data crosses the bridge.
- No fuzzy tab/profile/account selection, hidden provider endpoint, arbitrary JavaScript, selector, URL, shell, click, type, send or generic browser-control surface.
- Long healthy Pro reasoning is never classified stuck from time alone.
- `CONTEXT_LIMIT_REACHED` and `OOM_CONFIRMED` require explicit supported evidence. Otherwise preserve `UNKNOWN`, `UNRESPONSIVE` or `SUSPECTED_RESOURCE_FAILURE`.
- One logical modifying action uses one operation identity and one exact target until canonical reconciliation. `EFFECT_UNKNOWN` forbids blind retry or alternate-surface failover.
- Extension/native-host reconnection restores infrastructure only; it may never replay a browser effect.
- A prompt can request deep effort but cannot guarantee 60–120 minutes of provider runtime.
- Production means installed version/readback plus the real worker-return -> Sol attention -> exact cockpit -> governed Sol action journey, not merge/CI/extension presence.

## Program DAG

```text
current #219 S0/S1 hardening
        |
        v
WSX-F1 profile-derived fleet transport
        |
        v
WSX-F2 native/extension HELLO + install artifacts
        |
        +-------------------------------+
        |                               |
        v                               v
WSX-R1 MV3 self-reconstitution     WSX-T1 bounded transport deadlines
        |                               |
        +---------------+---------------+
                        v
                  WSX-H1 health v2
                        |
                        v
               WSX-CR1 Steward consumer
                        |
              +---------+---------+
              |                   |
              v                   v
       WSX-S2 exact repair    WSX-E1 Pro effort
              |                   |
              +---------+---------+
                        v
                 WSX-S3 semantic wake
                        |
                        v
                WSX-C1 continuation capsule
                        |
                        v
                WSX-C2 successor-chat rotation
                        |
                        v
              WSX-D1 two-profile host deployment
                        |
                        v
              WSX-D2 limited fleet -> production
```

---

### Task 1: WSX-F1 — Profile-derived adapter identity and socket routing

**Files:**
- Create: `integrations/chairman_surfaces/web_sol_instance.py`
- Modify: `integrations/chairman_surfaces/web_sol_client.py`
- Modify: `integrations/chairman_surfaces/web_sol_native_host.py`
- Create: `tests/test_web_sol_fleet_transport.py`

**Interfaces:**
- Consumes one already-validated `chatgpt_managed_env` binding.
- Produces `adapter_instance_id(binding: dict[str, Any]) -> str`, a 64-character lowercase SHA-256 routing derivative.
- Produces `socket_leaf(instance_id: str) -> str` and `socket_path(instance_id: str, *, root: Path | None = None) -> Path`.
- Produces `validate_instance_id(value: Any) -> str`.
- Client derives its exact socket from the binding; caller cannot supply an alternate socket/profile/host.
- Native host receives one wrapper-fixed expected instance ID and binds only its derived socket.

- [ ] **Step 1: Write RED tests for canonical instance identity.**

```python
def test_multilogin_instance_identity_uses_vendor_folder_and_profile_not_conversation():
    first = multilogin_binding(url="https://chatgpt.com/c/alpha")
    second = multilogin_binding(url="https://chatgpt.com/c/beta")
    assert adapter_instance_id(first) == adapter_instance_id(second)


def test_different_profiles_have_different_socket_paths():
    assert socket_path(adapter_instance_id(binding_a())) != socket_path(adapter_instance_id(binding_b()))
```

Also prove: canonical key order is irrelevant; GoLogin excludes `folder_id`; Multilogin requires folder+profile; malformed/other-provider bindings refuse; seat/work/conversation changes do not change the environment instance; raw profile/folder IDs never appear in the output; path leaf length is bounded; two full digests with the same shortened leaf are refused by handshake later rather than treated identical.

- [ ] **Step 2: Run focused RED.**

Run: `python3 -m pytest tests/test_web_sol_fleet_transport.py -q`

Expected: collection failure because `web_sol_instance` does not exist.

- [ ] **Step 3: Implement the pure canonical derivative.**

Canonical payload:

```python
{
    "schema": "mastermind.web_sol_adapter_instance.v1",
    "env_manager": "multilogin" | "gologin",
    "folder_id": str | None,
    "profile_id": str,
}
```

Serialize with sorted keys, UTF-8, compact separators, `allow_nan=False`; SHA-256 the exact bytes. Never include URL, account title, seat label, proxy, fingerprint or credentials.

- [ ] **Step 4: Route the client to the derived socket.**

Replace the global `WEB_SOL_SOCKET_PATH` action path with:

```python
instance_id = adapter_instance_id(binding)
path = socket_path(instance_id)
_exchange_web_sol_socket(request, path=path, expected_instance_id=instance_id)
```

Keep a test-only injected root/path seam. Do not expose a production caller-selected path.

- [ ] **Step 5: Parameterize native host startup by wrapper-fixed instance ID.**

`run_native_host(..., expected_instance_id: str, socket_root: Path | None = None)` validates the ID and derives the destination. Remove the single production socket constant as action routing authority.

- [ ] **Step 6: Run focused tests.**

Run: `python3 -m pytest tests/test_web_sol_fleet_transport.py tests/test_web_sol_chatgpt_extension.py tests/test_web_sol_native_host.py -q`

Expected: PASS.

- [ ] **Step 7: Commit.**

Commit message: `feat(wsx): route each managed profile to an exact adapter instance`.

---

### Task 2: WSX-F2 — Closed client/native/extension HELLO and deployment artifacts

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_protocol.py`
- Modify: `integrations/chairman_surfaces/web_sol_native_host.py`
- Modify: `integrations/chairman_surfaces/web_sol_client.py`
- Modify: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Create: `integrations/chairman_surfaces/web_sol_deployment.py`
- Create: `tests/test_web_sol_handshake.py`
- Create: `tests/test_web_sol_deployment.py`

**Interfaces:**
- `HELLO_SCHEMA = "mastermind.web_sol_transport_hello.v1"`.
- `HELLO_ACK_SCHEMA = "mastermind.web_sol_transport_hello_ack.v1"`.
- Closed fields: schema, protocol_major, client/native/extension package version, full adapter instance ID, boot nonce, capability digest.
- Host opens its action socket only after the profile-local extension proves the wrapper-fixed instance/config match.
- Client performs AF_UNIX HELLO/ACK before sending an action. A different instance, boot, protocol major or capability digest refuses before action bytes.
- Deployment generator produces per-profile `instance_config.js`, unique native-host name, native-host manifest and executable wrapper from one validated binding/release description.

- [ ] **Step 1: Write RED handshake tests.**

Prove exact-key validation; wrong instance/protocol/capability refusal; boot nonce match; action before successful HELLO refusal; stale ACK refusal; no profile coordinates in ACK; and a different profile cannot use another profile's socket even when the extension ID is the same.

- [ ] **Step 2: Write RED deployment tests.**

```python
def test_generated_wrapper_fixes_instance_and_does_not_accept_runtime_override():
    bundle = render_bundle(binding(), release())
    assert bundle.wrapper_argv[-2:] == ("--instance-id", adapter_instance_id(binding()))
    assert "profile_id" not in bundle.public_receipt
```

Prove deterministic bundle bytes, exact host-name leaf, exact extension ID allowlist, absolute executable path, secret/profile redaction, dry-run diff, idempotent readback and adapter-only rollback manifest.

- [ ] **Step 3: Implement protocol validators and handshake state machine.**

Keep handshake state in one native-host process boot only. Do not persist it. Generate a cryptographic boot nonce with the standard library at process start. An ACK never authorizes organizational work.

- [ ] **Step 4: Generate profile-local extension config and native wrapper.**

`instance_config.js` defines only immutable public routing constants:

```javascript
globalThis.MMX_WEB_SOL_INSTANCE = Object.freeze({
  instanceId: "<sha256>",
  nativeHost: "com.mastermind.web_sol_surface.<bounded-leaf>",
  protocolMajor: 1,
  packageVersion: "<reviewed-release>"
});
```

The generated wrapper accepts Chrome's origin/parent-window arguments but no caller-provided instance override.

- [ ] **Step 5: Run focused tests and static leakage scan.**

Run: `python3 -m pytest tests/test_web_sol_handshake.py tests/test_web_sol_deployment.py tests/test_web_sol_protocol.py tests/test_web_sol_native_host.py -q`.

- [ ] **Step 6: Commit.**

Commit message: `feat(wsx): negotiate exact instance transport and render install artifacts`.

---

### Task 3: WSX-R1 — MV3 startup hydration and bounded native reconnection

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_extension/manifest.json`
- Modify: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Modify: `integrations/chairman_surfaces/web_sol_extension/content.js`
- Create: `tests/test_web_sol_extension_reconstitution.py`

**Interfaces:**
- Service-worker restart rebuilds exact-profile tab mappings from exact ChatGPT host permissions only.
- Route/move/remove/replace events invalidate or refresh mappings.
- One bounded alarm-based native-port reconnect schedule restores transport only.
- No pending action is retained or replayed across a disconnect or worker restart.

- [ ] **Step 1: Write Node behavioral RED scenarios.**

Scenarios: service-worker boot with two existing exact ChatGPT tabs; SPA route change; moved tab; removed/replaced tab; content script unavailable; native host absent; port disconnect after idle; port disconnect after request bytes; reconnect ceiling; and startup with no ChatGPT tabs.

- [ ] **Step 2: Add least-privilege manifest support.**

Add only permissions actually required by tested behavior, normally `nativeMessaging` and `alarms`; exact ChatGPT host permissions remain. Do not add `debugger`, broad `<all_urls>`, `cookies`, `storage`, `webRequest` or generic scripting.

- [ ] **Step 3: Implement `hydrateTargets()` and event listeners.**

Use `chrome.tabs.query({url: [exact host patterns]})`, then send the fixed reprobe message. A failed reprobe removes/omits that mapping and surfaces unknown/unavailable; it does not inject code or scrape fallback content.

- [ ] **Step 4: Implement bounded reconnect.**

Use named alarms with finite attempts such as 1, 5 and 15 minutes. Encode attempt in the alarm name rather than creating a persistent retry store. HELLO_ACK resets infrastructure attempt state. Reconnect never retains or re-sends an action.

- [ ] **Step 5: Run behavioral/static tests.**

Run: `python3 -m pytest tests/test_web_sol_extension_reconstitution.py tests/test_web_sol_extension_static.py tests/test_web_sol_extension_s1_static.py tests/test_web_sol_reliability.py -q`.

- [ ] **Step 6: Commit.**

Commit message: `feat(wsx): reconstitute profile mappings and native transport`.

---

### Task 4: WSX-T1 — Deadline-bounded framing, concurrency and socket lifecycle

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_native_host.py`
- Modify: `integrations/chairman_surfaces/web_sol_client.py`
- Create: `tests/test_web_sol_transport_hardening.py`

**Interfaces:**
- Every header/payload read and complete write consumes one monotonic deadline.
- One host permits at most one in-flight browser action; a second client receives typed busy/unavailable without a durable queue.
- Slow/malformed clients cannot terminate the long-running host loop.
- Socket cleanup unlinks only the inode this process created; a replacement/live host socket is never removed.

- [ ] **Step 1: Write RED tests using real socketpairs/temp AF_UNIX sockets.**

Prove partial header/payload timeout, oversized frame, duplicate keys, stalled writer, malformed first client followed by healthy second client, concurrent second client, Chrome disconnect, host restart, symlink parent/socket refusal, stale non-socket refusal, path-length ceiling, and replacement-inode cleanup safety.

- [ ] **Step 2: Introduce an injected monotonic deadline object.**

```python
@dataclass(frozen=True)
class Deadline:
    ends_at: float
    def remaining(self, monotonic: Callable[[], float]) -> float: ...
```

No action caller selects the ceiling. Tests inject the clock.

- [ ] **Step 3: Isolate per-client refusal from host termination.**

Catch validated client/frame errors at the accept loop, close only that client, and continue. Chrome protocol failure remains host-terminal because the extension channel is no longer trustworthy.

- [ ] **Step 4: Add inode-bound cleanup.**

Capture `(st_dev, st_ino, st_uid, mode)` after bind. On close, unlink only when the current path still matches that exact created socket.

- [ ] **Step 5: Run tests and commit.**

Run focused transport suite, then commit `fix(wsx): bound transport and preserve live socket ownership`.

---

### Task 5: WSX-H1 — Versioned truthful surface health and diagnostics

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_protocol.py`
- Modify: `integrations/chairman_surfaces/web_sol_extension/content.js`
- Modify: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Create: `integrations/chairman_surfaces/web_sol_health.py`
- Create: `integrations/chairman_surfaces/web_sol_extension/popup.html`
- Create: `integrations/chairman_surfaces/web_sol_extension/popup.js`
- Create: `tests/test_web_sol_health.py`
- Create: `tests/test_web_sol_popup_static.py`

**Interfaces:**
- Observation v2 contains only bounded deterministic evidence: detector version, transport state, route match, document state, visibility, frozen/discarded when supported, composer presence+enabled state, generation state, explicit auth/provider/network/usage/context-limit evidence, probe latency and observed time.
- `classify_health(observation, *, now, effort_context=None) -> HealthConclusion` returns a closed conclusion and evidence codes.
- Closed conclusions: `RESPONSIVE_IDLE`, `GENERATING`, `LONG_RUNNING`, `UNRESPONSIVE`, `FROZEN`, `DISCARDED`, `CONTEXT_LIMIT_REACHED`, `AUTH_REQUIRED`, `PROVIDER_ERROR`, `NETWORK_ERROR`, `TARGET_MISSING`, `AMBIGUOUS_TARGET`, `SUSPECTED_RESOURCE_FAILURE`, `UNKNOWN`.
- Popup displays adapter diagnostics only; canonical attention is shown only when supplied by Steward.

- [ ] **Step 1: Write RED truth-table tests.**

Required falsifiers: long active Pro run stays `LONG_RUNNING`; missing selectors become `UNKNOWN`; hidden/disabled composer is not available; timer alone never becomes context limit/OOM; explicit context-limit UI becomes `CONTEXT_LIMIT_REACHED`; discarded flag becomes `DISCARDED`; renderer probe plus no backend evidence does not claim provider progress; host sleep evidence stays distinct.

- [ ] **Step 2: Implement fixed detector bundle.**

Selectors and recognized error tokens live in one versioned constant bundle. Inspect only application chrome/status controls and bounded attributes. Never export matching text or scan transcript/body content. Unknown DOM shapes produce null/unknown.

- [ ] **Step 3: Implement pure classifier.**

It consumes evidence; it does not read Job/Attention/Slack/GitHub or choose an action. Effort context changes grace/suspicion only and cannot transform a responsive generator into stuck.

- [ ] **Step 4: Implement popup.**

Show instance leaf, extension/native versions, compatibility, last observation age, evidence/conclusion, requested/observed effort if available, and adapter pause/diagnostic state. No private URL/profile ID/credential is rendered.

- [ ] **Step 5: Run tests and commit.**

Commit message: `feat(wsx): expose truthful versioned cockpit health`.

---

### Task 6: WSX-CR1 — Existing Steward/Control Room consumer

**Files:**
- Determine the current accepted Steward composition path after #228 is accepted; do not edit a concurrent writer's files.
- Expected additive adapter: `control_plane/web_sol_steward_adapter.py`
- Expected tests: `tests/test_web_sol_steward_adapter.py`

**Interfaces:**
- Consumes existing canonical responsibility/attention/surface binding facts plus one sanitized Web-Sol observation/conclusion.
- Produces one composite descriptive recommendation such as `WAKE_ELIGIBLE`, `SURFACE_REPAIR_REQUIRED`, `AUTH_REQUIRED`, `HUMAN_DRAFT_BLOCKS_ACTION`, `UNKNOWN`.
- Browser state never elects owner, responsibility, Job state or successor.

- [ ] **Step 1: Reconcile #228 exact accepted interface and collision state.**
- [ ] **Step 2: Write RED composite truth-table tests.**
- [ ] **Step 3: Implement one pure adapter into the existing Steward consumer.**
- [ ] **Step 4: Prove deletion/unavailability of Web-Sol facts leaves canonical company truth unchanged.**
- [ ] **Step 5: Commit on the lawful current Steward carrier or a fresh disjoint child after current writer termination.**

Stop and return to Sol if #228 remains under an active writer or its interface is not accepted. Do not duplicate Steward.

---

### Task 7: WSX-E1 — Capacity-owned Pro effort selection and protection

**Files:**
- Extend the current accepted Capacity/cognition-route owner only after exact owner reconciliation.
- Expected additive protocol: `control_plane/sol_cognition_request.py`
- Expected tests: `tests/test_sol_cognition_request.py`
- Web-Sol projection adapter may live under `integrations/chairman_surfaces/web_sol_effort.py`.

**Interfaces:**
- Requested effort: `STANDARD | PRO_DEEP`.
- Observed mode: exact supported provider/model/effort evidence or `MODEL_MODE_UNVERIFIED`.
- One canonical logical run gets at most one reservation. Cockpit rotation preserves the reservation through existing owner state.
- No hardcoded monthly balance, no purchase/account switch, no silent metered fallback.

- [ ] **Step 1: Identify the existing Capacity reservation/entitlement contract.**
- [ ] **Step 2: Write RED tests for unknown entitlement, exhausted budget, duplicate reservation, lost submit receipt, cockpit rotation and metered-exception refusal.**
- [ ] **Step 3: Implement the smallest request/projection adapter in the existing owner.**
- [ ] **Step 4: Add Web-Sol readback of requested versus observed mode without making the extension a quota ledger.**
- [ ] **Step 5: Prove a healthy long-running generator cannot be repaired or duplicated by the health/recovery path.**
- [ ] **Step 6: Commit and independently review.**

---

### Task 8: WSX-S2 — Closed same-surface repair

**Files:**
- Modify: `integrations/chairman_surfaces/web_sol_protocol.py`
- Modify: `integrations/chairman_surfaces/web_sol_extension/background.js`
- Modify: `integrations/chairman_surfaces/web_sol_client.py`
- Create: `tests/test_web_sol_s2_repair.py`

**Interfaces:**
- Closed actions only: `RELOAD_EXACT_SURFACE`; optionally `REOPEN_EXACT_BOUND_SURFACE` only after a real supported implementation is separately proven.
- No caller-supplied URL, selector, JavaScript or profile target.
- Requires exact current binding/instance, allowed health evidence, no healthy active generation and positively known no human draft.
- Receipt records pre-evidence, effect-boundary state and post-evidence without content.

- [ ] **Step 1: Write RED safety cases.**

Active generation, unknown draft, known non-empty draft, auth/rate/usage restriction, target ambiguity, stale evidence, changed binding and uncertain prior repair all refuse before effect.

- [ ] **Step 2: Implement pre-actuation reread and one reload call.**
- [ ] **Step 3: Implement postcondition reprobe.**
- [ ] **Step 4: Treat lost acknowledgement after reload boundary as `REPAIR_EFFECT_UNKNOWN`; never repeat automatically.**
- [ ] **Step 5: Run tests and commit.**

---

### Task 9: WSX-S3 — One reconciled semantic WAKE_SOL action

**Files:**
- Extend the existing Wake action/effect owner after exact interface reconciliation.
- Modify Web-Sol protocol/client/extension only with the closed wake actuation envelope.
- Create: `tests/test_web_sol_s3_wake.py`

**Interfaces:**
- Caller supplies opaque canonical references only: operation identity, surface reference/binding token, canonical attention reference, target responsibility epoch, wake template version and effort reservation reference.
- Browser payload is rendered from one fixed reviewed template; no arbitrary prompt string crosses the public/worker surface.
- Distinguish `INPUT_ATTEMPTED`, `SUBMIT_BOUNDARY_CROSSED`, `PROVIDER_GENERATION_OBSERVED`, canonical Sol `ACK`, and source resolution.

- [ ] **Step 1: Reconcile current Wake owner and exact target-enforcement law.**
- [ ] **Step 2: Write RED tests for stale attention/epoch, active generation, human draft, auth/provider error, wrong effort, changed binding, duplicate wake and lost submit receipt.**
- [ ] **Step 3: Implement fixed wake-template renderer and closed composer insertion/submission path.**
- [ ] **Step 4: Immediately pre-commit reread the canonical target/attention/binding through existing owners.**
- [ ] **Step 5: Emit effect receipts into the existing Wake owner; no extension-local durable dedup store.**
- [ ] **Step 6: Prove timeout after submit never presses send again or starts another Pro run.**
- [ ] **Step 7: Commit and independently review.**

---

### Task 10: WSX-C1 — Canonical continuation capsule

**Files:**
- Extend the existing Agent OS handoff/context-bundle owner; do not create a chat transcript database.
- Expected schema module only if no accepted one exists: `control_plane/sol_continuation_capsule.py`
- Tests: `tests/test_sol_continuation_capsule.py`

**Interfaces:**
- Capsule fields: original outcome, current responsibility+authority epoch, exact operation/carrier, source revisions, material decisions, capability ledger, effect reconciliation, outstanding returns, next action, unresolved gaps and predecessor surface reference.
- Excludes private chain-of-thought, entire transcript, browser storage/cookies, credentials and copied output corpus.

- [ ] **Step 1: Reconcile existing Agent OS handoff/context schema.**
- [ ] **Step 2: Write RED closed-schema, correction, stale-source and secret/content-exclusion tests.**
- [ ] **Step 3: Implement deterministic capsule construction from existing owners.**
- [ ] **Step 4: Prove a fresh Sol can recover the next action using only canonical sources/capsule references.**
- [ ] **Step 5: Commit in the owning carrier.**

---

### Task 11: WSX-C2 — Predecessor fencing and successor-chat rotation

**Files:**
- Extend current SessionTargetRegistry/RuntimeBinding/continuity owner.
- Web-Sol extension receives only the exact provisioned successor action after owner admission.
- Tests: `tests/test_web_sol_successor_rotation.py` plus current continuity tests.

**Interfaces:**
- Rotation causes: explicit context-limit evidence, irrecoverable exact-surface failure or deliberate authorized rotation.
- Sequence: reconcile in-flight effect -> fence predecessor modifying authority -> provision one exact successor -> initialize with capsule references -> verify exact surface -> bind/ACK successor -> only then make successor current.
- Old chat remains read-only history. Missing inaccessible predecessor context remains a named gap.

- [ ] **Step 1: Write RED state-machine tests.**

Prove no successor before effect reconciliation; no simultaneous current predecessor/successor; ambiguous creation cannot be repeated; stale predecessor wake/action refuses; unsupported old-chat retrieval is not asserted; successor ACK failure leaves transfer incomplete and predecessor fenced according to owner law.

- [ ] **Step 2: Implement owner-side transition using current RuntimeBinding/session-target primitives.**
- [ ] **Step 3: Add exact browser provisioning/postcondition action only after owner admission.**
- [ ] **Step 4: Run cross-owner continuity and Web-Sol tests.**
- [ ] **Step 5: Commit and independently review.**

---

### Task 12: WSX-D1 — Mac installer and two-profile deployment validation

**Files:**
- Create reviewed installer under the existing deployment/ops owner, likely `ops/web_sol/install.py` and `ops/web_sol/uninstall.py` after collision review.
- Add automated validation harness `scripts/web_sol_deployment_validate.py`.
- Store only sanitized receipts under the accepted evidence location.

**Interfaces:**
- Dry-run first; exact release SHA/digests; absolute wrapper/native paths; exact managed profile assignment/readback; adapter-only rollback.
- Use two approved non-sensitive Mimic profiles simultaneously.
- Existing Grok Secretary -> Mac local-exec is the proved host path; OpenClaw MCP is not required.

- [ ] **Step 1: Designate/create two non-Chairman validation profiles through an explicitly authorized host operation.**
- [ ] **Step 2: Install the exact release into both profiles with distinct instance configs/host names/sockets.**
- [ ] **Step 3: Prove simultaneous HELLO/INSPECT/FOREGROUND without cross-profile collision.**
- [ ] **Step 4: Prove worker/service/native/browser restarts, route changes, malformed client isolation, extension/native absence and rollback.**
- [ ] **Step 5: Prove zero transcript/cookie/storage/proxy/fingerprint/credential leakage.**
- [ ] **Step 6: Remove validation artifacts or preserve only the explicitly approved validation profiles.**
- [ ] **Step 7: Return sanitized exact release/profile-vendor/receipt digests to Sol.**

---

### Task 13: WSX-D2 — Limited fleet and production acceptance

**Files:**
- Existing deployment configuration and Control Room/Steward projection only.
- Update #219/#212 and existing Macro #6636 handoff with immutable release/proof receipts.

- [ ] **Step 1: Select one approved low-risk real Sol seat and capture pre-install rollback/readback.**
- [ ] **Step 2: Install S0/S1+health only; observe stability before S2/S3 arming.**
- [ ] **Step 3: Prove one real worker return creates canonical Sol attention and the exact cockpit becomes available without Chairman tab hunting.**
- [ ] **Step 4: Arm S2 and S3 only after their exact accepted versions and effect owners are present.**
- [ ] **Step 5: Prove one governed wake, Sol canonical rehydration/action and explicit continuation or STOP.**
- [ ] **Step 6: Prove one deliberate/context-limit successor rotation, including predecessor fencing and successor ACK.**
- [ ] **Step 7: Expand to the limited fleet with per-seat rollback and no account/target guess.**
- [ ] **Step 8: Hold/rollback only the affected surface on provider-specific failure; disjoint seats remain operational.**
- [ ] **Step 9: Sol reviews exact release, real product journey and negative/failure evidence.**
- [ ] **Step 10: Update durable owners and mark only actually proven capabilities `PROVEN_LIVE`.**

## Completion Ruler

Web-Sol is production-complete only when all of the following are true:

```text
fleet-safe profile-derived routing
+ exact HELLO/version/instance handshake
+ self-reconstituting MV3/native transport with zero effect replay
+ bounded framing/concurrency/socket cleanup
+ truthful health and long-run classification
+ existing Steward/Control Room consumer
+ Capacity-owned Pro effort reservation and observed-mode honesty
+ closed S2 repair with uncertainty handling
+ closed S3 semantic wake through existing Wake effect owner
+ canonical continuation capsule
+ predecessor-fenced successor-chat rotation
+ two-profile installed proof
+ one real worker-return-to-governed-Sol-action journey
+ controlled real-seat rollout and rollback
+ durable closeout in #219/#212/Macro #6636
```

Green CI, a merged spec, successful extension load, Slack delivery, foregrounding, provider spinner, or a queued wake is not production completion by itself.
