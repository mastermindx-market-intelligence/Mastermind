# Studio Output Budget Implementation Plan

> Execute task-by-task in the existing isolated workspace; current Chairman has authorized implementation.

**Goal:** reduce oversized tool-result ingestion without losing result integrity or repeating effects.
**Architecture:** pure text-result paging attached to existing BackendOwner; one read-only tool and installer manifest integration, no new control plane.
**Tech Stack:** Node.js built-ins, existing MCP SDK/gateway, existing Python installer.
**Spec:** `docs/superpowers/specs/2026-09-17-studio-output-budget.md`.

## Global constraints
Preserve parent PR696 and installed service. Preserve PR706 dirt. Keep 16 KiB serialized tool-result payloads, eight retained results / 8 MiB per existing owner, exact original error truth, no backend retries, and explicit media/schema exclusions.

## Task 1 — Executable output contract
- [x] Write 18 tests for integrity, serialized byte accounting, Unicode, errors, privacy, eviction, closure, arguments, and schema/media exclusions.
- [x] Observe all 18 fail because component is absent, then implement and observe 18 pass in isolated Node 22 development checks.
- [x] Transfer component/tests to canonical source workspace; rerun on host Node.

## Task 2 — Real consumer and lifecycle
- [x] Write failing real MCP tests on the parent gateway for bounded output, no replay, principal isolation, and shared-owner frontend continuity.
- [x] Wire projection into backend result return, local tool catalog, backend owner/session lifetime and cleanup; do not alter timeout/effect handling.
- [x] Include new module in existing installer manifest; run its adjacent tests.

## Task 3 — Qualification and durable publication
- [x] Run focused + existing gateway tests, adversarial/fuzz and observed RED-to-GREEN falsifiers, and diff/installed-service nonmutation checks.
- [ ] Commit and push exact isolated child; publish a clearly stacked Draft PR against PR696, retaining current release gates.
- [ ] Record exact evidence, remaining gates, and do-not-redo in the existing operation and parent issue carriers. No merged/live/accepted claim from fixtures alone.
