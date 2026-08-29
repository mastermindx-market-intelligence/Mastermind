# Web-Sol Native Messaging Ingress — Directionality / Private IPC Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Parent architecture carrier:** Mastermind PR #188  
**Current protected source basis:** `Mastermind@801f8e5b1de0f4866414f670d5612d1dd45de208`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.  
**Capability state:** `SPEC_ONLY`. This record creates no installed extension, native host, socket, Wake obligation, browser actuation, Job/Attempt/Worker state, queue, retry, credential, or production capability.

## 1. Primary-source discovery

Chrome's documented Native Messaging contract is directional in a way the earlier Web-Sol plan did not make explicit enough:

- the extension calls `runtime.connectNative()` / `runtime.sendNativeMessage()`;
- Chrome starts the registered native host process;
- Chrome owns the host's stdin/stdout pipes;
- messages in both directions use 32-bit native-endian length-prefixed UTF-8 JSON;
- Chrome passes the calling extension origin as the host's first argument;
- with `connectNative()`, the host stays alive only while the port remains connected.

Primary source: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging

Therefore a Chrome Native Messaging stdio process **is not by itself an external OCR-6 command ingress**. Pretending that `web_sol_native_host.py` can simply be called by OCR-6 over the same stdin/stdout while Chrome owns those pipes would produce a disconnected implementation.

## 2. Chairman outcome preserved

The user outcome does not change:

> a deterministic Mastermind attention/Steward path can inspect and foreground the exact action-authoritative Web-Sol conversation without OpenClaw, transcript extraction, generic browser control, or a second control plane.

The adapter must be usable by the future OCR-6 `SurfaceActuator`; a browser-internal demo that cannot receive an exact Mastermind action request is insufficient.

## 3. Corrected transport composition

The profile-local extension remains the browser-side exact-surface adapter and still initiates one fixed Native Messaging connection.

The Chrome-started native host becomes a **storeless transport bridge** with two fixed boundaries:

```text
OCR-6 / explicit Web-Sol bridge seam
        |
        | fixed private AF_UNIX request/receipt
        v
Chrome-started Web-Sol native host
        |
        | Chrome Native Messaging stdio
        v
profile-local Web-Sol extension
        |
        v
exact already-open ChatGPT conversation tab
```

### 3.1 Private local command endpoint

While—and only while—the Chrome Native Messaging port is alive, the native host may expose one fixed user-local AF_UNIX socket:

```text
~/Library/Application Support/Mastermind/control-room/web_sol_surface.sock
```

This socket is **transport only**. It is not a new supervisor, queue, lifecycle, watcher, session, health, retry, identity, or memory authority.

Required properties:

- parent directory private to the current user (`0700` or stricter accepted existing owner mode);
- socket owned by the current user and mode `0600`;
- no TCP/HTTP listener;
- no externally supplied socket path;
- no filesystem mailbox or command file;
- no durable cursor, queue, replay log, cache or pending-command database;
- socket exists only while the exact native-host process / extension port is alive and is removed on clean shutdown;
- stale/non-socket/path-owner/mode ambiguity fails closed; never unlink an unrelated object merely because the pathname collides.

A future OCR-6 process may connect as a client. The native host never chooses which responsibility, Sol, provider, profile, account or surface should be targeted.

### 3.2 One in-flight exact action

The first S0/S1 release permits at most one in-flight action per native-host process.

The AF_UNIX client supplies the already-frozen `mastermind.web_sol_surface_action.v1` request. The host:

1. validates the request with the single `web_sol_protocol` owner;
2. validates the exact Chrome caller origin against the deterministic extension ID;
3. forwards the request to the extension over the existing Native Messaging port;
4. accepts only a matching nonce/operation/binding receipt;
5. validates the returned `mastermind.web_sol_surface_receipt.v1`;
6. returns that receipt to the waiting AF_UNIX client.

A second concurrent client/request is refused; it is not queued. No automatic retry exists.

Timeout or pipe loss after a mutating `FOREGROUND` request is **effect-unknown for that action**. The caller keeps the same operation/target and reconciles with a read/inspect path; neither host nor extension retries, picks another tab, invokes OpenClaw, or falls back to another Sol.

## 4. Exact browser target remains extension-local and volatile

The extension may keep only ephemeral in-memory mappings from a sanitized conversation fingerprint to the browser-local tab/window handle observed from its own fixed content script.

It must never select by:

- title text;
- recency;
- newest active tab;
- provider/account guess;
- transcript/output content;
- fuzzy URL similarity.

The Python caller resolves the canonical `surface_ref` / current binding before issuing the action. The extension receives only the exact conversation fingerprint + binding identity material in the closed request.

If no exact fingerprint exists -> `TARGET_NOT_FOUND`.

If more than one live tab presents the same exact fingerprint -> `AMBIGUOUS_TARGET`; do not choose one.

Binding revision/fingerprint drift -> `TARGET_CHANGED` before foreground success is claimed.

## 5. S0/S1 actuation only

This correction does not widen the action surface.

Allowed:

```text
INSPECT
FOREGROUND
```

`FOREGROUND` may activate the exact tab and focus its containing browser window only. It may not navigate, reload, click, type, submit, execute arbitrary JavaScript, inspect content, change accounts, or send a ChatGPT turn.

S2 repair and S3 Web-Sol wake/message submission remain separate future architecture/release gates.

## 6. Native-host manifest / origin law

The native host manifest has one fixed application name and one deterministic extension origin. Wildcards are forbidden.

The host independently validates the caller-origin argv supplied by Chrome; the manifest allowlist alone is not treated as runtime proof.

The checked-in config is an install template/contract. Disposable proof renders/installs an exact absolute executable path in the disposable managed profile environment; no Chairman seat is modified in this carrier.

## 7. No-duplicate-control-plane ruling

The AF_UNIX endpoint is permitted only because it is a **stateless subordinate transport seam** for the existing OCR-6 SurfaceActuator owner.

Reject the implementation if it gains any of the following:

- persistent command state;
- request queue;
- retry/failover logic;
- responsibility/session/surface selection;
- Wake authority;
- a second health store;
- generic browser/computer control;
- generic shell/process execution;
- public/TCP/HTTP exposure;
- provider/account routing.

Deleting the socket or killing the native host must change no canonical company state. It may only make the Web-Sol surface adapter temporarily unavailable.

## 8. Implementation-plan precedence correction

For the Web-Sol S0/S1 plan on PR #212:

- Task 2 remains the profile-local S0 extension.
- Task 3 now implements **Chrome stdio framing + exact origin validation + the fixed private AF_UNIX request/receipt bridge**, not an impossible external caller sharing Chrome-owned stdio.
- Task 4 implements exact `INSPECT`/`FOREGROUND` handling in the service worker over the already-open Native Messaging port, with volatile exact-fingerprint tab mapping.
- Task 5's explicit `chatgpt.py` seam is the first Python-side client of the private socket; legacy `open_surface()` remains fail-closed.
- Task 6 disposable proof must demonstrate the full caller -> AF_UNIX -> native host -> Native Messaging -> extension -> exact tab -> validated receipt round trip.

No new implementation carrier is authorized; Mastermind PR #219 remains the single S0/S1 implementation carrier.

## 9. Acceptance additions

Disposable proof must now include:

1. exact extension origin accepted; wrong/wildcard origin refused;
2. private AF_UNIX owner/mode/path safety;
3. no listener when extension/native host is absent;
4. exact `INSPECT` round trip from Python client to extension and back;
5. exact `FOREGROUND` round trip for one safe tab;
6. duplicate exact-fingerprint tabs -> `AMBIGUOUS_TARGET`;
7. client timeout/native disconnect -> no retry/failover;
8. socket removal/native-host kill changes zero canonical company state;
9. OpenClaw absent throughout the successful path.

This amendment preserves the existing architecture while making the Web-Sol adapter actually callable by Mastermind rather than merely observable inside the browser.
