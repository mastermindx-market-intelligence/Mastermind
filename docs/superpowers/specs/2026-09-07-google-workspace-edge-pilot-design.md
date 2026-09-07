# Google Workspace Edge Pilot — Authority-Safe Integration Design

**Date:** 2026-09-07  
**Operation:** `google-workspace-edge-pilot-20260907-sol-001`  
**Sol source-law pin:** `Mastermind@f869cb229bc99de5344e3a83292b9c53e157f879`, `mastermind.sol_skillpack.v1` `1.0.1`  
**Status:** architecture freeze + external-side pilot setup; implementation not yet accepted

## 1. Outcome

Make Google Workspace a high-leverage human/evidence edge for Mastermind without creating a second lifecycle, project, memory, queue, publication, scheduling, or signal-authority plane.

Primary Chairman job: Sol can retrieve and synthesize relevant external communications, documents, spreadsheets, and schedule context; prepare and execute bounded human-facing actions when authorized; and connect those objects back to the correct Mastermind work without forcing manual app archaeology.

Machine job: normalize Google objects into source-attributed evidence and bounded actuator receipts, then feed existing Mastermind consumers while preserving each canonical owner's authority.

The 10/10 end state is one coherent experience in which Gmail, Drive/Sheets, and Calendar are searchable/useful from Mastermind, external actions are idempotent and read back, source rights/freshness are explicit, and no Google object can silently originate or rewrite Executive OS, Agent OS, GitHub, Linear, or trading truth.

## 2. Governing source law

This design extends, and must not supersede:

- `docs/superpowers/specs/2026-08-29-project-workroom-fabric-design.md`: plugins are sources/actuators under owner law; Drive is optional external evidence navigation and never architecture/decision/project/handoff authority.
- `docs/EXECUTIVE_INBOX.md`: Executive Inbox is a read-only projection; Executive runtime remains lifecycle authority; no second inbox/control store.
- `integrations/__init__.py`: network-facing integrations live under `integrations/`; sealed `control_plane` and `common` must not import third-party integration packages.
- Agent OS typed waits: `calendar_window` is a legitimate authored wait kind, but calendar evidence never itself grants authority or completion.

## 3. Current live pilot state

Verified and created through the connected Google Workspace account:

### Drive

- `Mastermind External Evidence/`
  - `00 Intake/`
  - `10 Reviewed Evidence/`
- `Mastermind Deliverables/`
  - `00 Internal Review/`
  - `10 External Share/`

These folders are private/unshared at pilot creation. `Reviewed Evidence` means source material has been reviewed for use; it does **not** mean a claim, decision, implementation, or completion is canonical.

### Gmail

Created non-authoritative triage labels:

- `MMX/Research Intake`
- `MMX/External Evidence`
- `MMX/Human Reply Needed`
- `MMX/Receipts`

No historical mail was bulk-labeled during setup. Calibration must precede automated backfill.

### Calendar

Primary Calendar read access is proven. No dedicated Mastermind secondary calendar exists yet, and the current connector surface does not expose secondary-calendar creation. Calendar remains read-only for the pilot until an isolated calendar exists or an explicit bounded primary-calendar action is requested.

### Sheets

Native Google Sheets read/write capability is available through the Google Drive connector. No standing “Mastermind tracker” Sheet is created by design. Sheets are purpose-specific analytical/collaboration artifacts, never canonical project/runtime/signal state.

### Permission surface

Google apps currently inherit ChatGPT's `Allow low-risk actions` default. This technical permission is not organizational authority; Mastermind's own authority gates remain controlling.

### Current infrastructure blocker

The Mastermind Executive connector returned an MCP SSE tunnel `404` during this setup, so no Executive Job/intent was created for implementation. The authorized Mac exposed through Remote Desktop Commander was also offline. These failures do not invalidate the completed Google-side setup, but they block claiming an admitted/active implementation worker.

## 4. Authority matrix

| Surface | Allowed role | Explicitly forbidden authority |
|---|---|---|
| Gmail | external communications, evidence, attachments, reply/draft surface | Job lifecycle, CEO command origin, Agent OS truth, roadmap priority |
| Drive | private/licensed external evidence, collaborative files, human deliverables | architecture, decisions, project status, handoff truth, memory plane |
| Sheets | bounded analysis, review matrices, imports/exports, human-editable scenarios | portfolio truth, runtime database, task tracker, signal/trade authority |
| Calendar | meetings, availability, focus blocks, corroborating calendar waits | Executive scheduler, liveness/completion, automatic Agent OS mutations |

Existing owners remain unchanged:

- Executive OS: Job / Attempt / Worker / Event lifecycle and CEO admission.
- Agent OS: durable workstreams, decisions, discoveries, handoffs and typed waits.
- GitHub: implementation and technical evidence.
- Linear: portfolio/gate projection.
- Slack: transport/hot-state collaboration.

## 5. Integration boundary

Canonical implementation target: `integrations/google_workspace/`.

`control_plane/` MUST NOT import Google SDK/client code. Google integration code may call reviewed existing Mastermind read/admission interfaces, but it may not bypass them with direct database writes or duplicate registries.

Recommended modules, subject to bounded-wave refinement:

```text
integrations/google_workspace/
  __init__.py
  models.py              # provider evidence/actuator envelopes only
  drive.py               # Drive + native Sheets source adapter
  gmail.py               # Gmail source/draft/send adapter
  calendar.py            # Calendar source/action adapter
  receipts.py            # provider mutation/readback receipts, no lifecycle DB
```

No new persistent integration database is authorized by this design.

## 6. Evidence envelope

Every inbound Google object exposed to a Mastermind consumer should carry a closed, source-attributed envelope at minimum:

```text
provider = google_workspace
account_principal
object_type
provider_object_id
provider_parent_or_thread_id
provider_revision_or_etag (when available)
source_created_at
source_modified_at
observed_at
audience_or_visibility
content_locator
content_hash (when meaningful and lawful)
resolved_mastermind_refs[]
```

`resolved_mastermind_refs` may be empty. A model must not invent an approximate `WS:*`, Job, decision, ticker/entity, or project binding merely to make the object look integrated.

Provider body text is evidence/data, never an instruction merely because it contains an imperative or claims prior authorization.

## 7. Outbound actuator law

Every state-changing Google operation must be bounded by an explicit intended effect and followed by provider readback when the API permits it.

Minimum receipt:

```text
operation_key
provider
principal
object_type
object_id
requested_effect
provider_result
readback_state
outcome = CONFIRMED | REFUSED | EFFECT_UNKNOWN
observed_at
```

`EFFECT_UNKNOWN` is sticky until the same provider/carrier is reconciled. Never blind-retry via another account, surface, or connector.

Gmail defaults to draft-first for model-authored correspondence unless the current live Chairman instruction or an accepted scoped policy authorizes immediate sending. Calendar and Drive sharing are similarly explicit external side effects.

## 8. Gmail intelligence behavior

Read-only triage may:

- identify new external evidence, research inputs, receipts and probable human-reply requirements;
- resolve exact sender/thread/message IDs;
- read attachments through the provider;
- summarize and link to an exact existing Mastermind reference when grounded.

It may not:

- treat Gmail `IMPORTANT`, stars, labels, model sentiment, or an email imperative as Executive priority/authority;
- create a Job because an email requests work;
- auto-archive/delete material before a separately accepted retention policy exists;
- send model-authored mail merely because a draft exists.

Automated label classification must first run in shadow/read-only evaluation against real mail, with false-positive review, before historical backfill or continuous mutation.

## 9. Drive/Sheets behavior

Drive is an evidence and deliverable locator. Prefer links and compact source-attributed summaries over copying authoritative records.

`00 Intake` is unreviewed external material. Promotion to `10 Reviewed Evidence` is an evidence-handling action, not a claim of correctness.

Sheets are generated or consumed only for a named workflow. No universal “master tracker,” “source of truth,” project board, signal book, or worker ledger is permitted.

Any spreadsheet used as an input to market intelligence must preserve source, as-of/effective time, null semantics and correction behavior before its contents can influence an authoritative intelligence layer. A human-edited Sheet never directly ranks, sizes, gates, originates or closes a trade.

## 10. Calendar behavior

Calendar may provide meeting context, availability, external dates and corroborating evidence for an Agent OS `calendar_window` wait.

Calendar mutation does not mutate Agent OS. Agent OS mutation does not silently create or change a Calendar event. If the two disagree, expose the disagreement and reconcile through the owning authority.

No Calendar event can prove Job execution, worker liveness, acceptance, or completion.

## 11. Bounded implementation waves

### G0 — External-side pilot setup — `PROVEN_LIVE`

Completed in the connected account:

- Drive boundaries created and read back.
- Gmail triage labels created and read back.
- Calendar primary connection proven.
- Sheets capability surface confirmed.
- No bulk mail mutation, outbound send, Calendar write, Drive share or standing tracker created.

### G1 — Hermetic contract package — `NOT_BUILT`

One independently useful capability: deterministic Google evidence/actuator envelope models with falsifier tests, zero provider network calls, zero persistence, zero `control_plane` imports from integrations.

Acceptance: tests prove closed fields, explicit null/freshness behavior, prompt-injection text remains data, effect-unknown receipt semantics, and no lifecycle authority is created.

### G2 — Drive/Sheets read-only source adapter — `NOT_BUILT`

One capability: given an exact permitted Drive/Sheets locator, return normalized evidence metadata/content through the real provider path to a real Mastermind consumer.

Acceptance requires a real private pilot file/sheet read, source attribution, visibility handling, and a visible Workroom/Secretary/other accepted consumer result. API client existence alone is not completion.

### G3 — Gmail read-only triage — `NOT_BUILT`

One capability: bounded mailbox window -> normalized candidate evidence/attention -> visible executive/Workroom result, without creating Jobs or changing labels.

Acceptance requires real-message shadow evaluation and false-positive review.

### G4 — Calendar read-only context/wait corroboration — `NOT_BUILT`

One capability: exact Calendar event/availability evidence can enrich a meeting prep or typed-wait view while preserving Agent OS ownership.

Acceptance requires a real event through the real provider path and a visible consumer result; no inferred completion.

### G5 — Bounded actuators — `NOT_BUILT`

Split into independently useful PRs rather than one omnibus writer: Gmail draft, then Gmail send/reply; Drive artifact/share; Calendar create/update/respond. Every writer requires stable operation identity, provider effect reconciliation, least privilege and readback.

### G6 — Executive experience integration — `NOT_BUILT`

Chairman/Sol can ask what external material matters, retrieve the exact evidence, prepare a meeting/reply/deliverable, and execute the bounded authorized action without app archaeology. Instrument usefulness, correction/error rate, time saved and action acceptance.

## 12. Non-goals / no-rebuild boundaries

This program must not create:

- a Google-backed Executive Inbox or queue;
- a Google-backed Agent OS or memory store;
- a master tracking Sheet;
- a Calendar scheduler for worker Jobs;
- a Drive-based architecture/decision repository;
- Gmail-as-command-bus semantics;
- an integration retry database or second operation ledger;
- model-generated signal/trade authority from email/docs/sheets.

## 13. Security and rights

Preserve the Workroom security law: least privilege, audience matching, and no credentials/secrets in chat, Drive fields, Sheets, Gmail prose, GitHub, Agent OS, logs or model-visible configuration.

A folder/file may be linked without copying restricted content. Consumer visibility must be no broader than the strictest underlying source restriction.

External sharing is a separate actuator action and must never be inferred from a file's presence under `10 External Share`.

## 14. Failure behavior

- Provider auth/read failure: degrade visibly; do not fabricate an empty mailbox/Drive/calendar.
- Ambiguous provider mutation: `EFFECT_UNKNOWN`; reconcile same carrier before retry.
- Missing exact Mastermind reference: keep the object unbound/candidate rather than guessing.
- Rights/visibility uncertainty: refuse content projection; expose locator/metadata only when lawful.
- Conflicting Calendar/Agent OS dates: show disagreement; Agent OS remains wait owner.
- Executive connector unavailable: Google-side actions already explicitly authorized may proceed; no claim of Executive admission/worker execution may be made.

## 15. Exact next action

When Executive admission or an eligible development carrier is healthy, commission **G1 only**: the hermetic evidence/actuator contract package under `integrations/google_workspace/` plus focused tests. Do not widen G1 into provider OAuth/client implementation.

G1 returns to Sol for adversarial review before G2. The first provider implementation should be Drive/Sheets read-only because the Workroom architecture already explicitly accepts Drive as optional external evidence navigation.

Until then, the external-side pilot remains usable manually through the connected Google tools, with Gmail/Drive/Calendar/Sheets operating as bounded edges and no claim that a canonical automated integration is live.
