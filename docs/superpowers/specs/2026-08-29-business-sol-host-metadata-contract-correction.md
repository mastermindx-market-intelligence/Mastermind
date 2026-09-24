# Business Sol Surface Convergence — Host Metadata Contract Correction

**Date:** 2026-08-29  
**Architecture carrier:** Mastermind PR #234  
**Parent amendment:** `docs/superpowers/specs/2026-08-29-business-sol-surface-fabric-attestation-amendment.md`  
**Capability state:** `SPEC_ONLY / RECORDS_ONLY`

## Precedence

This correction supersedes any parent-architecture or amendment language that implies `_meta["openai/widgetSessionId"]` is delivered to an MCP server in client request metadata.

## Correct official contract

Current official OpenAI plugin reference distinguishes two surfaces:

### Client-provided request `_meta` available on initialize/tool calls

- `openai/locale` — BCP 47 locale;
- `openai/userAgent` — optional best-effort hint;
- `openai/userLocation` — optional coarse-location object;
- `openai/subject` — anonymized user correlate;
- `openai/session` — anonymized ChatGPT-session/conversation correlate;
- `openai/organization` — anonymized organization correlate when available.

### Host-provided tool-result metadata forwarded to a mounted component

- `openai/widgetSessionId` — stable only for the currently mounted widget instance, until that widget unmounts.

`openai/widgetSessionId` is not part of the documented client-provided request `_meta` table and is not available to a server-only HC0 probe merely because the call occurs in ChatGPT.

## HC0 ruling

The read-only server probe observes only documented request `_meta`.

It returns keyed fingerprints only for:

- `openai/session`;
- `openai/subject`;
- `openai/organization`.

It returns presence only, never values or fingerprints, for:

- `openai/locale`;
- `openai/userAgent`;
- `openai/userLocation`.

It does not include `openai/widgetSessionId`, does not degrade because it is absent, and does not claim widget continuity.

A later UI-specific experiment may observe widget-session behavior inside a mounted component. That would be a separate read-only research wave and would not create authorization, RuntimeBinding, lifecycle, or write authority.

## Unchanged safety law

All host metadata remains optional correlation or presentation evidence only. None of these fields authenticates Chris, assigns Sol/worker responsibility, proves a RuntimeBinding, authorizes an Executive Job, or permits a modifying tool call.