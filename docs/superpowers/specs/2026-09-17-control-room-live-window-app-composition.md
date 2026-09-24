# Control Room Live Window App Composition

Source operation:
`control-room-live-window-app-composition-source-20260917-sol-001`
(WS:CHAIRMAN-CONTROL-ROOM), durable spec comments 5712320999 (executable
source-import proposal, evidence hashes, caveats, acceptance contract) and
5712433075 (exported Reader CSP `connect-src 'none'` and the host-supplied
authenticated callback).

## Scope

The existing Steward application factory can now mount **one optional, fixed
Live Window read resource on its own existing host**. The mount is
**disabled by default**: with no `live_window` argument the Steward MCP policy,
verifier, routes, middleware order and lifespan are unchanged, and the factory
returns the same application it returned before this change.

The mount exists only through the real accepted seams:

- `integrations/mastermind_steward_app/app.py` — `build_authenticated_app(...,
  live_window=None)` prepends exactly one additional outermost middleware when
  (and only when) one complete `LiveWindowConfig` is supplied.
- `integrations/mastermind_steward_app/live_window.py` (new, the only new
  module) — the closed configuration object, the exact-path dispatch and the
  configuration refusals. It constructs the read resource **only** through the
  accepted Reader seam `from_existing_business_owner`, using the incumbent
  Business `JwtAuthenticator` bound to an explicit content policy, the current
  per-source access decision, the bounded source read and the caller's existing
  closed audit sink.

Nothing else is added: no listener, route table, redirect, proxy, token or
session store, permission or transcript store, classifier, OAuth store, static
asset, credential, enrollment, CLI flag, environment variable or activation.
The Reader, auth, broker and projection sources are read-only to this slice.

## Dispatch law

`LiveWindowDispatch` hands a request to the Reader's own checks **only** when it
is an HTTP request whose canonical raw path (the one existing
`_canonical_raw_path` normalizer the transport guard and the A1 gate already
share) is byte-equal to the exact configured content-resource path. Every other
request — any other path, a prefix or suffix of it, a query string or injected
`root_path`, any other method, and every non-HTTP scope including the lifespan —
reaches the original stack as the same `receive`/`send` objects, so non-window
responses stay byte-identical.

The Reader keeps its own ownership: Business token verification and claims
(audience, scope, principal), the current per-source access decision, the
same-origin host and `Origin` checks, the bounded window read, the last-instant
re-authorization, and the suppression of the entire response body on grant,
turn, policy or credential change (403 `access_changed`) or revocation (401
`authentication_required`). The composition adds no authorization decision and
no response body of its own.

Identity is deliberately absent from the mount: the exported Reader document
keeps `connect-src 'none'` and a host-supplied authenticated callback
(comment 5712433075). Mounting an API resource is not a browser binding, is not
a complete web journey, and does not close that separate gate.

## Configuration refusals (typed, fail-closed, before any reader exists)

| Refusal | Type |
| --- | --- |
| option is not a `LiveWindowConfig` | `TypeError` |
| any required field missing/`None` (incomplete) | `TypeError` |
| `source_kind` is not `live-window` (recorded/native-lane) | `ValueError` |
| content policy scope is not exactly the accepted content scope | `ValueError` |
| content resource host differs from the Steward host | `ValueError` |
| `allowed_origin` is not the Steward origin (cross-origin) | `ValueError` |
| window path would shadow `/healthz`, `/readyz`, the MCP resource path or the protected-resource metadata path (trailing slash included) | `ValueError` |

The Steward guard keeps requiring exactly `mastermind.steward.read` for its own
routes even when the mount is enabled; enabling the mount cannot widen, replace
or relax that scope, and the content policy can never be the Steward scope.

## Verification

- **RED-A** (tests only, no module): collection error
  `ModuleNotFoundError: integrations.mastermind_steward_app.live_window`.
- **RED-B** (option accepted and ignored scaffold): `48 failed, 46 passed`; the
  46 passes are the inert-mount controls (factory-default identity, byte-exact
  non-window paths, exact-path non-dispatch, structural non-claims) and the
  failures are the expected-refusal and window-behavior tests.
- **GREEN**: `94 passed` (new suite + `test_mastermind_steward_app_asgi.py`),
  then `186 passed` for the mandated regression set below,
  `python3 -B -m compileall -q integrations/mastermind_steward_app` exit 0.
- **Regressions**: `tests/test_mastermind_steward_app_asgi.py`,
  `tests/test_mastermind_steward_app_server.py`,
  `tests/test_mastermind_steward_app_static_fences.py`,
  `tests/test_mastermind_steward_app_projection.py`,
  `tests/mastermind_window_reader/test_existing_auth_composition.py`.
  The ASGI suite additionally pins the default route table and middleware order,
  so the mount can never become implicit.
- **Fixtures**: real `JwtAuthenticator` / `MastermindTokenVerifier`, real RS256
  signatures, real `BoundedJwksCache` parsing from in-memory synthetic JWKS, the
  real `WindowReader`/`VisibleTurnProjection` source, and the real
  `from_existing_business_owner` seam. No real credential, client, enrollment,
  grant, provider, network or browser is used.
- **Mutants** (hand-applied, each killed, then restored byte-exact):
  widen the Steward scope when the mount is enabled; dispatch on a path prefix;
  accept a recorded source kind; permit reserved-route shadowing; retain and
  replay a granted window body on a later refusal. Restoration hash
  `app.py=e8937f661d193904ff132dd52fe036a52dbc731c4cfccb7005b6636079f89964`,
  `live_window.py=465c742d9589a7100606a31bb03597d5a88e4916c7da392c0393170af39759d7`.

## Not done

- **No viewer enrollment, content grant or content-policy receipt.** The mount
  is constructed only when the application owner passes a complete configuration
  at build time; no default, no environment or CLI activation, no enrollment.
- **No installed #714 broker gate activation.** The accepted Reader/source chain
  is exercised hermetically; nothing is armed, deployed or scheduled.
- **No browser or host-binding proof.** A permitted native/embedded bridge or a
  separately reviewed same-origin hosted shell in the same application owner is
  still required to bind the real viewer; `connect-src 'none'` is untouched and
  no CSP is relaxed.
- **No production proof.** This slice is source-only: it does not claim an
  authenticated content read from a live provider, a real registered client, a
  real issuer trust chain, or any runtime effect.

## Hold

HOLD-FOR-SOL — DRAFT, do not mark Ready or merge; release condition = explicit
Sol ruling on the agent-fabric root C0BSBM78V1N/1789324397.992989.
