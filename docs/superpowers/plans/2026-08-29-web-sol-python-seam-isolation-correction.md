# Web-Sol Python Seam Isolation — Task 5 Correction

**Date:** 2026-08-29  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Operation:** `web-sol-surface-adapter-s0s1-20260829-sol-001`  
**Implementation carrier:** Mastermind PR #219  
**Current protected basis:** `Mastermind@adccc544509aaa0ef7c0bb4f8bdbbfab19cf85e2`, Skillpack v1.0.1.

## Discovery

The current protected `integrations/chairman_surfaces/chatgpt.py` carries an intentionally strong historical invariant: it is the fail-closed managed-browser vendor adapter and its existing regression suite proves that generic `open_surface()` never acquires unofficial browser-control machinery.

The Web-Sol S0/S1 bridge is a new explicit exact-surface capability with a different transport contract. Adding AF_UNIX/socket client behavior directly into the legacy vendor module would unnecessarily weaken the clarity of that invariant and enlarge the shared-path collision surface.

## Corrected Task-5 ownership

Create a sibling explicit adapter module:

```text
integrations/chairman_surfaces/web_sol_client.py
```

It owns only:

- validation of one existing `mastermind.surface_bindings.v1` ChatGPT binding;
- canonical conversation identity + SHA-256 fingerprint;
- deterministic binding fingerprint over stable binding identity only;
- v1 `binding_revision = 0` because the current binding schema has no revision field; locator/identity drift is detected by the binding fingerprint rather than a new revision store;
- closed `INSPECT` / `FOREGROUND` request composition;
- one fixed private AF_UNIX exchange to the Chrome-started native host;
- exact receipt identity validation and stable error laundering.

`integrations/chairman_surfaces/chatgpt.py` remains **byte-identical** to protected source in PR #219. Its `open_surface()` continues to refuse closed on every path. There is no automatic fallback from the legacy adapter to the Web-Sol client.

OCR-6 later imports/calls the explicit `web_sol_client` seam after resolving an exact `surface_ref`; it does not call legacy `open_surface()` expecting hidden promotion.

## Canonical fingerprint rule

The conversation identity used by both Python and the extension is:

```text
https://<lowercase-host><exact-path-with-one-trailing-slash-removed>
```

The current binding validator already forbids query strings/fragments and requires an exact conversation path. `/c/x` and `/c/x/` therefore produce the same conversation fingerprint. The extension must use the same normalization before hashing.

The binding fingerprint is SHA-256 over deterministic canonical JSON containing only:

```text
binding_id
work_ref
role
seat_ref
provider
locator_kind
locator
```

with the locator URL replaced by the same canonical conversation identity. `observed_at` / `last_verified_at` are evidence timestamps and do not change exact surface identity.

## Public API

Exactly:

```python
inspect_via_extension(
    binding,
    *,
    operation_key,
    issued_at,
    expires_at,
    nonce,
) -> dict

foreground_via_extension(
    binding,
    *,
    operation_key,
    issued_at,
    expires_at,
    nonce,
) -> dict
```

No public `socket_path`, bridge, provider/account/profile/url, retry or fallback parameter.

## Transport law

The private client:

- connects only to the fixed `web_sol_surface.sock` path;
- requires private current-user parent/socket ownership and mode;
- writes one closed frame once;
- waits once for one receipt;
- never retries;
- treats a post-send FOREGROUND timeout/pipe ambiguity as `foreground_effect_unknown`;
- validates the receipt and exact binding/action/operation/nonce identity before returning;
- never returns or embeds raw URL/profile/seat values in errors.

## Task-5 regression

The legacy `chatgpt.py` tests remain part of the acceptance matrix and must prove that `open_surface()` still refuses and never touches the explicit Web-Sol transport.

This correction supersedes the earlier Task-5 file-location wording in the Web-Sol plan and native-ingress correction. It changes no user outcome, action vocabulary, authority, S2/S3 boundary, or implementation carrier.
