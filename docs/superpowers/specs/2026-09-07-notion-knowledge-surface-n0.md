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

> Given one explicitly shared Notion parent page and a scoped Notion connection, a deterministic bootstrap creates the N0 workspace skeleton (Board Book, Programs, Decisions, Research Library, Product & Architecture, Operating Manual, Chairman Notes & Inputs, Archive) and returns external object identity for later idempotent canonical projections.

N0 does **not** sync canonical records yet and does not accept Notion content as execution authority.

### 1.1 Chairman Control Room precedence / Board Book boundary

Protected master now carries `docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md`, which has narrow precedence over the default current Chairman experience. Therefore `00 — Chairman Board Book` is a **periodic strategic/narrative knowledge package**, not a competing live executive dashboard. It may later synthesize durable weekly/monthly progress, decisions, research, and context with explicit as-of/provenance, but it must never compute or present coverage-qualified `CLEAR`/`ATTENTION`, become the current act/no-act default, rank operational priorities, mirror Job/Worker liveness, or replace Linear project-management. Any future N1 Board Book projection must defer current-action meaning to the decision-first Control Room and the underlying canonical owners.

## 2. Canonical ownership / no-rebuild boundary

| Concept | Canonical owner | Notion relationship |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, CEO admission | Executive OS | display/projection only later |
| Workstreams / decisions / discoveries / handoffs | Agent OS | human-readable projection only later |
| implementation / PR / CI / evidence | GitHub | links + summarized projection later |
| portfolio projection | Linear | optional links/projection only |
| hot transport/dialogue | Slack | no mirroring by default |
| current Chairman act/no-act/default decision compression | decision-first Chairman Control Room over existing canonical owners | `00 — Chairman Board Book` is periodic strategic/narrative synthesis only; never the live default |
| company priority ranking | Improvement Agenda / accepted strategy owners | display only; Notion never re-ranks |
| research/architecture governing artifacts | declared repository authority | browsable projection/index only |
| operating procedure / source law | protected repository owners / Skillpack | `05 — Operating Manual` is an index/presentation page only |
| Notion human-authored notes | Notion | candidate input only; no direct runtime authority |

Forbidden duplicate systems: `Notion Agent OS`, `Notion Executive OS`, a Notion task queue, a Notion worker-liveness model, a Notion retry/effect state machine, a Notion auth/identity registry, or a second ranked roadmap.

## 3. N0 workspace contract

One caller-supplied parent page is required. N0 creates exactly these children beneath it:

1. `00 — Chairman Board Book` (page)
2. `01 — Programs` (database)
3. `02 — Decisions` (database)
4. `03 — Research Library` (database)
5. `04 — Product & Architecture` (database)
6. `05 — Operating Manual` (page/index)
7. `06 — Chairman Notes & Inputs` (database)
8. `99 — Archive` (page)

The numbering is intentional and stable. N0 does not create a separate tasks database. `05 — Operating Manual` may later link/project governing procedures, but editing that Notion page can never amend the protected Skillpack or repository source law.

Each projected database reserves machine metadata fields from day one:

- `Canonical ID`
- `Canonical Source`
- `Source SHA`
- `As Of`
- `Last Synced At`
- `Projection Health`
- `Source URL`

Human-authored Chairman Notes instead use `Input State`, `Reviewed At`, and `Promoted Canonical ID`. A note is never authoritative merely because it is marked `NEW_INPUT`.

Every N0 database is a single-data-source database. Reuse requires the existing database to have exactly one data source and the exact reviewed property-name/type map. A same-named database with missing, extra, or wrong-type columns is a schema mismatch and blocks all writes rather than being silently adopted.

## 4. Idempotency and correction law

N0 bootstrap matching is exact and parent-scoped: `(parent_page_id, object kind, exact reviewed title)`. The manifest `key` is the stable internal contract key used to associate a planned child with later projector behavior; it is not inferred from arbitrary Notion content.

The implementation enumerates children of the exact parent page. Same-title objects under another parent do not match. A page does not match a database with the same title. Multiple exact matches under the parent are an ambiguity refusal, not an invitation to pick one.

Before the first write, every database selected for reuse is schema-proven through the current Notion database → data-source boundary. Every newly created or effect-unknown-reconciled database is schema-proven immediately before any later write, and all N0 databases are proven again in final reconciliation. The bootstrap never repairs an unknown pre-existing schema automatically.

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

The implementation follows current Notion API boundaries: a page child uses the page-only `title` property shape; a database is created under the parent page with its initial data-source property schema; database schema verification retrieves the container and its one data source separately. No provider token is persisted by the bootstrap.

The client paces request starts at a conservative default interval rather than depending on write retries. Read-only `429` responses may honor one bounded `Retry-After`; mutating calls are never automatically retried.

## 7. Deterministic method

N0 is deterministic. No language model chooses names, schemas, parents, or whether an existing object is "close enough." The manifest in `config/notion_knowledge_surface_n0.json` is the reviewed workspace contract.

A later model may summarize canonical research for human consumption, but generated prose will carry source/provenance metadata and zero lifecycle/priority/trading authority.

## 8. Failure states

The bootstrap fails closed on:

- missing token or parent ID in apply mode;
- parent page not visible to the connection;
- parent mismatch;
- duplicate exact child identities;
- a reused database with zero/multiple data sources or a mismatched property-name/type schema;
- 401/403 authorization refusal;
- 404 parent/object visibility failure;
- 429 rate limit after bounded `Retry-After` handling on reads;
- malformed/unexpected API response;
- unsupported Notion API version or schema drift;
- ambiguous effect after a write response cannot be reconciled.

Mutating requests are never automatically retried. A transport failure, malformed success response, or non-definitive mutation HTTP response is treated as effect-unknown. The bootstrap reconciles by re-reading the exact parent's children. If the exact intended child is observed, the receipt records `reconciled`; otherwise the effect remains unknown and the operation stops rather than issuing another create.

## 9. N0 implementation order

1. Freeze this architecture and the manifest.
2. Implement pure manifest validation and plan generation.
3. Implement a minimal Notion REST client using the pinned API version.
4. Add exact-parent discovery, schema proof, and ambiguity refusal.
5. Add paced `--apply` creation of missing children only.
6. Add unit tests with no real network calls, including current request-payload and schema-proof behavior.
7. Run CI and adversarial Sol review of the diff.
8. Only after a real connection/root page is reachable: perform live dry-run, apply, rerun, and prove zero duplicate creates.

## 10. Acceptance / production proof

Repository acceptance requires:

- manifest validation tests;
- dry-run produces the eight exact children and no network writes;
- `05 — Operating Manual` is present as a page/index, not a second procedure authority;
- exact existing child under the parent resolves to reuse;
- same title with wrong object kind does not resolve;
- duplicate exact matches refuse;
- a wrong-schema reused database refuses **before any write**;
- apply is impossible without explicit `--apply` plus required environment;
- page/database request payloads match the pinned Notion API contract;
- simulated effect-unknown never blindly retries a create.

`PROVEN_LIVE` additionally requires real Notion evidence:

1. live dry-run against the intended parent;
2. one live apply creates/reuses exactly the eight N0 objects and proves all five database schemas;
3. immediate second live apply creates **zero** objects;
4. human inspection confirms the workspace is usable;
5. object IDs + parent identity are recorded in a non-secret receipt;
6. no Executive/Agent OS/priority state changed as a side effect.

Until those steps pass, capability state is `BUILT_NOT_PROVEN` at best.

## 11. Held future waves

**N1 — canonical projector:** Programs, Decisions, Research, Product/Architecture and Operating Manual projections/indexes with canonical IDs/SHA/freshness and correction behavior.

**N2 — Chairman input intake:** signed Notion webhooks into a quarantine/candidate-input seam. Webhook activity may surface attention but cannot create/dispatch Executive Jobs directly.

**N3 — governed worker capability:** only through the existing `ExecutionCapabilityRegistry` / provider capability-attestation architecture. Ambient Notion workspace access for every worker is not authorized by N0.

## 12. Current external gates (2026-09-07)

- This ChatGPT session can discover the official Notion plugin but does not currently expose an invokable Notion connector surface.
- The authorized Mac Studio is registered with Remote Desktop Commander but is currently offline, so an already-authenticated local Notion browser/app session cannot be used from this session.
- Executive OS MCP degraded from a tunnel `429` probe to a later tunnel `404`; therefore no new Executive Job is claimed/admitted by this N0 operation.

These are capability facts, not reasons to weaken the design. Repository implementation can proceed. Live Notion proof requires one exact authorized Notion execution path to become reachable; it must not be simulated by calling source presence "installed" or "live."
