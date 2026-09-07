# Mastermind-X Notion Knowledge Surface N0 — Architecture Freeze

**Date:** 2026-09-07  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** SOL ARCHITECTURE FREEZE / N0 BOOTSTRAP IMPLEMENTATION AUTHORIZED / NOT PRODUCTION-PROVEN  
**Operation key:** `notion-knowledge-surface-n0-20260907-sol-001`  
**Protected Skillpack basis:** `f869cb229bc99de5344e3a83292b9c53e157f879`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1.

## 1. Outcome

Create a premium human-facing Mastermind knowledge and collaboration surface in Notion without creating a second lifecycle, memory, priority, identity, publication, or control authority.

The first useful vertical is deliberately narrow:

> Given one explicitly shared Notion parent page and a scoped Notion connection, a deterministic bootstrap creates the N0 workspace skeleton (Board Book, Programs, Decisions, Research Library, Product & Architecture, Chairman Notes & Inputs, Archive) and records enough external object identity to allow later idempotent canonical projections.

N0 does **not** sync canonical records yet and does not accept Notion content as execution authority.

## 2. Canonical ownership / no-rebuild boundary

| Concept | Canonical owner | Notion relationship |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, CEO admission | Executive OS | display/projection only later |
| Workstreams / decisions / discoveries / handoffs | Agent OS | human-readable projection only later |
| implementation / PR / CI / evidence | GitHub | links + summarized projection later |
| portfolio projection | Linear | optional links/projection only |
| hot transport/dialogue | Slack | no mirroring by default |
| company priority ranking | Improvement Agenda / accepted strategy owners | display only; Notion never re-ranks |
| research/architecture governing artifacts | declared repository authority | browsable projection/index only |
| Notion human-authored notes | Notion | candidate input only; no direct runtime authority |

Forbidden duplicate systems: `Notion Agent OS`, `Notion Executive OS`, a Notion task queue, a Notion worker-liveness model, a Notion retry/effect state machine, a Notion auth/identity registry, or a second ranked roadmap.

## 3. N0 workspace contract

One caller-supplied parent page is required. N0 creates exactly these children beneath it:

1. `00 — Chairman Board Book` (page)
2. `01 — Programs` (database)
3. `02 — Decisions` (database)
4. `03 — Research Library` (database)
5. `04 — Product & Architecture` (database)
6. `06 — Chairman Notes & Inputs` (database)
7. `99 — Archive` (page)

The numbering is intentional and stable. N0 does not create a separate tasks database.

Each projected database reserves machine metadata fields from day one:

- `Canonical ID`
- `Canonical Source`
- `Source SHA`
- `As Of`
- `Last Synced At`
- `Projection Health`
- `Source URL`

Human-authored Chairman Notes instead use `Input State`, `Reviewed At`, and `Promoted Canonical ID`. A note is never authoritative merely because it is marked `NEW_INPUT`.

## 4. Idempotency and correction law

Bootstrap identity is `(parent_page_id, stable child key)`. The implementation must discover an existing exact child under the exact parent before creating anything. Same-title objects under another parent do not match. Multiple exact matches are an ambiguity refusal, not an invitation to pick one.

Later projection identity will be the canonical record ID (`WS:*`, `DEC:*`, `DSC:*`, repository artifact ID, etc.) plus its declared canonical owner. Notion page/database IDs are external addresses, not authority.

Manual edits to machine-owned projection properties never mutate canonical truth. A later projector either repairs the projection from canonical state or marks it degraded/conflicted.

## 5. Data/time/null behavior

- Canonical timestamps remain ISO-8601 and retain their source meaning.
- `As Of` means the source record's semantic time where available.
- `Last Synced At` means projector observation time, never source freshness.
- Missing canonical values stay null/empty; no model fills facts to make a page look complete.
- `Projection Health` is descriptive only (`CURRENT`, `STALE`, `DEGRADED`, `CONFLICT`, `SOURCE_MISSING`). It cannot gate runtime work.
- Corrections flow canonical source → projection. Notion cannot overwrite a repository decision or Executive state.

## 6. Security and connection boundary

N0 assumes an internal/scoped Notion connection or equivalent authorized connection with access only to the selected Mastermind parent subtree. Secrets never enter Git, prompts-as-memory, PR bodies, logs, or generated receipts.

Required runtime inputs are external configuration only:

- `NOTION_API_KEY`
- `NOTION_PARENT_PAGE_ID`

The client pins `Notion-Version: 2026-03-11`. Network writes are only allowed when the explicit `--apply` flag is present. Default mode is read-only planning.

## 7. Deterministic method

N0 is deterministic. No language model chooses names, schemas, parents, or whether an existing object is "close enough." The manifest in `config/notion_knowledge_surface_n0.json` is the reviewed workspace contract.

A later model may summarize canonical research for human consumption, but generated prose will carry source/provenance metadata and zero lifecycle/priority/trading authority.

## 8. Failure states

The bootstrap fails closed on:

- missing token or parent ID in apply mode;
- parent page not visible to the connection;
- parent mismatch;
- duplicate exact child identities;
- 401/403 authorization refusal;
- 404 parent/object visibility failure;
- 429 rate limit after bounded `Retry-After` handling;
- malformed/unexpected API response;
- unsupported Notion API version or schema drift;
- ambiguous effect after a write response cannot be reconciled.

An effect-unknown create is reconciled by read/search against the exact parent and title before any retry. It is never blindly created again.

## 9. N0 implementation order

1. Freeze this architecture and the manifest.
2. Implement pure manifest validation and plan generation.
3. Implement a minimal Notion REST client using the pinned API version.
4. Add exact-parent discovery and ambiguity refusal.
5. Add `--apply` creation of missing children only.
6. Add unit tests with no real network calls.
7. Run CI and review the diff.
8. Only after a real connection/root page is reachable: perform live dry-run, apply, rerun, and prove zero duplicate creates.

## 10. Acceptance / production proof

Repository acceptance requires:

- manifest validation tests;
- dry-run produces the seven exact children and no network writes;
- exact existing child under the parent resolves to reuse;
- same title under another parent does not resolve;
- duplicate exact matches refuse;
- apply is impossible without explicit `--apply` plus required environment;
- simulated effect-unknown never blindly retries a create.

`PROVEN_LIVE` additionally requires real Notion evidence:

1. live dry-run against the intended parent;
2. one live apply creates/reuses exactly the seven N0 objects;
3. immediate second live apply creates **zero** objects;
4. human inspection confirms the workspace is usable;
5. object IDs + parent identity are recorded in a non-secret receipt;
6. no Executive/Agent OS/priority state changed as a side effect.

Until those steps pass, capability state is `BUILT_NOT_PROVEN` at best.

## 11. Held future waves

**N1 — canonical projector:** Programs, Decisions, Research, Product/Architecture projections with canonical IDs/SHA/freshness and correction behavior.

**N2 — Chairman input intake:** signed Notion webhooks into a quarantine/candidate-input seam. Webhook activity may surface attention but cannot create/dispatch Executive Jobs directly.

**N3 — governed worker capability:** only through the existing `ExecutionCapabilityRegistry` / provider capability-attestation architecture. Ambient Notion workspace access for every worker is not authorized by N0.

## 12. Current external gates (2026-09-07)

- This ChatGPT session can discover the official Notion plugin but does not currently expose an invokable Notion connector surface.
- The authorized Mac Studio is registered with Remote Desktop Commander but is currently offline, so an already-authenticated local Notion browser/app session cannot be used from this session.
- Executive OS MCP read was rate-limited (`429`) during this rollout, so no new Executive Job is claimed/admitted by this architecture PR.

These are capability facts, not reasons to weaken the design. The repository slice can proceed; live Notion proof waits for one exact connection path to become available.
