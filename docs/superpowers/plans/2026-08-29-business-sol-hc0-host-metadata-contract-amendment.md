# BSC-HC0 — Host Metadata Contract Amendment

**Date:** 2026-08-29  
**Plan carrier:** Mastermind PR #236  
**Parent plan:** `docs/superpowers/plans/2026-08-29-business-sol-hc0-host-context-falsifier.md`  
**Architecture correction:** `docs/superpowers/specs/2026-08-29-business-sol-host-metadata-contract-correction.md` on PR #234  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY`

## Precedence

This amendment supersedes the parent HC0 plan anywhere it includes `openai/widgetSessionId` in MCP request `_meta`, the server output, degradation codes, tests, or the live matrix.

## Correct HC0 request fields

Identifier-like fields, fingerprinted when present:

```text
openai/session       → openai_session
openai/subject       → openai_subject
openai/organization  → openai_organization
```

Presentation/analytics hints, presence only:

```text
openai/locale        → openai_locale
openai/userAgent     → user_agent_hint
openai/userLocation  → user_location_hint
```

`openai/userLocation` is an object. HC0 validates only that the present value is a bounded mapping with bounded primitive fields; it never returns, fingerprints, logs, or persists any city, region, country, timezone, longitude, or latitude value.

`openai/widgetSessionId` is excluded because the official contract places it in host-provided tool-result metadata forwarded to a mounted component, not client request `_meta` received by the MCP server.

## Correct output rows

`host_context` has exactly:

```text
openai_session
openai_subject
openai_organization
openai_locale
user_agent_hint
user_location_hint
```

Each row contains:

```text
present: boolean
fingerprint: string or null
usable_for_authorization: false
```

Only session, subject, and organization may have non-null fingerprints.

## Correct degradation enum

```text
OPENAI_SESSION_ABSENT
OPENAI_SUBJECT_ABSENT
OPENAI_ORGANIZATION_ABSENT
OPENAI_LOCALE_ABSENT
USER_AGENT_HINT_ABSENT
USER_LOCATION_HINT_ABSENT
UNKNOWN_HOST_META_IGNORED
TUNNEL_ATTESTATION_UNAVAILABLE
OAUTH_NOT_CONFIGURED
```

There is no widget-session degradation.

## Correct live proof boundary

HC0 proves server-visible request metadata behavior only.

A widget-session experiment is out of scope and cannot be inferred from HC0. If later required, it receives a separate UI-specific plan, app generation, and evidence carrier.

All other HC0 mission, TDD, no-authority, no-persistence, beta-upgrade, and stop conditions remain unchanged.