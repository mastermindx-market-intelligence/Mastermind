# Web-Sol Native Ingress Correction — Implementation Plan Amendment

> **For agentic workers:** this amendment has precedence over Task 3/Task 4/Task 5 transport wording in `2026-08-29-chatgpt-web-sol-surface-adapter.md`. Keep the same PR #219 implementation carrier and the same operation key.

**Goal:** make the S0/S1 Web-Sol adapter externally callable by Mastermind while preserving Chrome Native Messaging's real directionality and avoiding a second control plane.

**Architecture:** Chrome still launches the native host from the profile-local extension and owns the host's stdin/stdout. The live native-host process exposes one fixed private user-local AF_UNIX request/receipt socket while the Native Messaging port exists. This socket is a storeless OCR-6 SurfaceActuator transport seam only: one request in flight, no queue, no persistence, no retry/failover, no target selection.

**Spec precedence:** `docs/superpowers/specs/2026-08-29-web-sol-native-messaging-ingress-amendment.md` on PR #188.

## Global correction

Do not implement a standalone stdio CLI and call it a Chrome bridge. Do not add localhost HTTP/TCP, a command file/mailbox, another daemon or another MCP server.

The full first-release path is:

```text
explicit Python Web-Sol seam
-> private AF_UNIX socket
-> Chrome-started native host
-> Chrome Native Messaging port
-> MV3 service worker
-> exact volatile fingerprint->tab mapping
-> INSPECT / FOREGROUND
-> validated receipt back along the same path
```

## Corrected Task 3 — native host + private IPC

**Files remain:**

- `integrations/chairman_surfaces/web_sol_native_host.py`
- `config/web_sol_native_host_manifest.json`
- `tests/test_web_sol_native_host.py`

**Required contract:**

- Chrome stdio framing: 32-bit native-endian length + UTF-8 JSON, with a stricter Mastermind message cap below Chrome's documented maximum.
- exact caller origin: `chrome-extension://kmpbpccecbofdnhpcmjogofgmdodpnko/` only.
- native host app name: `com.mastermind.web_sol_surface`.
- fixed socket path: `~/Library/Application Support/Mastermind/control-room/web_sol_surface.sock`.
- private parent/socket owner/mode checks; never unlink an unknown regular file/symlink/socket owned by another process.
- one AF_UNIX client/request in flight; concurrent request -> typed busy/refusal, never queue.
- request validated through `web_sol_protocol.validate_request` before forwarding.
- receipt must match operation key, nonce, binding identity/revision/fingerprint and action before returning to client.
- one timeout budget; no automatic resend.
- no filesystem browsing, network listener, subprocess launcher, credentials, provider/account selection or persistent state.

**RED cases:**

- wrong Chrome origin;
- partial 4-byte header;
- length 0 / over cap;
- truncated payload;
- invalid UTF-8 / duplicate JSON key / non-object JSON;
- forbidden request field;
- wrong receipt nonce/operation/binding/action;
- second simultaneous client;
- stale path is regular file/symlink/wrong-owner object;
- socket parent mode too broad;
- timeout after FOREGROUND -> effect-unknown typed return, no retry;
- stdout contamination / extra bytes;
- no TCP/HTTP/subprocess/persistence imports.

## Corrected Task 4 — extension receives native commands

`background.js` must listen on the already-open Native Messaging port for one closed Task-1 action request.

It keeps only volatile in-memory fingerprint -> `{tabId, windowId}` observations learned from content-script probes. The map is cleared naturally with the service worker/browser lifecycle and is never persisted.

For `INSPECT`:

1. require exactly one live tab mapping for the requested conversation fingerprint;
2. ask that exact content script for a fresh bounded probe;
3. bind the receipt to the request identity;
4. return typed not-found/ambiguous/changed instead of guessing.

For `FOREGROUND`:

1. do the same exact-target resolution;
2. activate the exact tab and focus its exact window only;
3. perform a fresh postcondition probe;
4. claim `FOREGROUNDED_VERIFIED` only if the same exact fingerprint is still loaded.

Forbidden remains: URL navigation/update, reload, text/DOM extraction, arbitrary selectors, scripting/CDP, click/type/send.

## Corrected Task 5 — Python socket client seam

The explicit adjacent `chatgpt.py` extension seam becomes the AF_UNIX client. Legacy `open_surface()` remains fail-closed.

The new seam may:

- load/validate the existing private `surface_bindings` row;
- mechanically derive the exact conversation fingerprint and binding fingerprint/revision;
- compose a closed Task-1 request with fresh nonce/deadline;
- connect only to the fixed private socket;
- send one framed request and wait once;
- validate the exact matching receipt.

It may not start the browser, install the extension, select another seat, retry, invoke OpenClaw, or fall back to another target.

## Corrected Task 6 disposable proof

The canary is incomplete unless the request starts **outside** the browser from the Python seam and returns through the full socket/native/extension round trip.

Required success path:

```text
Python INSPECT -> exact bounded S0 receipt
Python FOREGROUND -> exact disposable tab/window -> FOREGROUNDED_VERIFIED
```

Required adverse path includes wrong origin, socket unavailable, duplicate exact fingerprint, binding drift, native host death, browser restart and OpenClaw absent.

## Stop boundary

PR #219 still stops production-inert after disposable-profile S0/S1 proof. Chairman-seat installation, OCR-6 production composition, S2 repair and S3 message/wake remain separate.
