# Meta-CEO read-first product slice

This composition implements Paper's Meta-CEO office (AT08/AT08M) inside the
existing React product. DJ1/DJ1M and MC2/MC2M retain the behavior references.
It is now composed into the existing App Today route. All nine legacy routes remain
reachable. Browser, native, authentication and production acceptance remain separate
gates; the source candidate includes explicit unmerged dependency ancestry.

## Data boundary

`projectOffice(input, context)` accepts decoded Mission, Programs, Result and
Current Window values from the existing `MissionHost` boundary. `ReadSnapshot`
adds presentation provenance and the context captured when the read started;
it is not a wire schema, owner, cache, authorization token or read client.

The caller must capture the actual auth/invalidation generation, exact selection,
session/binding and owner revision at read start. It must provide the currently
observed context at render time. Never construct an old snapshot using a newly
selected context to make it pass. Unknown provenance stays null. Do not derive
source revisions from a title, wall clock or UI counter.

The projection clears values on identity or source-revision changes. A source
explicitly labeled STALE may retain same-context historical facts; the consumer
marks them stale and makes no current-attention claim. Partial mission facts keep
their section coverage and missingness. Result details require the exact indexed
five-key tuple and runtime observation; window association reuses the existing
`observedMissionAssociation` function. No join is inferred from titles or timing.

Delivery, pickup, START, effect, transport return, review and acceptance remain
independent. A completed result is not a transport return or acceptance. Work
remains unadapted in this projection; the legacy Work route and its released source
are retained in the integrated App. The existing `WORK_PENDING_CUSTODY` label is a
projection gap, not a claim that the original source writer is still active.
Direction, critical-path, journal and missing attention producers stay explicit
gaps; the component never creates their facts from model prose.

## Draft and preview boundary

`MetaCeoOffice` receives a parent-owned `OfficeDraft` with its original context.
Evidence and preview inspection leave that draft untouched. A different identity,
selection, session or binding masks the old draft without retargeting it. The
existing shell must retain the draft for its original context and clear protected
state on sign-out; this component creates no transcript or draft database.

`createDirectionPreview` creates a deeply frozen, inert preview. It contains the
draft, exact context and qualified source references. Permissions are
`NOT_PROJECTED`, effect expectation is `NONE`, and there is no submission callback
or command import. A changed context invalidates the preview synchronously.

## Paper to React crosswalk

Canonical file: `01M3NRCX55B452A12819WNE1RH`, Mastermind OS.
Initial behavior snapshot: `d30579fa90752a3623d8562574b7f224916666d55b77fc04a17b8e7c04fd1a17`.
Fresh visual observation: `2ccdbcd528a0990e8be40376b658f19d8059b50407d4f1ddc24b666a5468114d`.
During implementation the live Start Here directory added page 12, Canonical
Atelier, and retained the earlier boards as behavior references. AT00 / KSB-0
now directs visual composition. These are guarded observations, not locks.

| Current design | Consumer surface |
| --- | --- |
| AT08 / L9V-0; AT08M / MNS-0 | Spacious office heading, direction row, answer and movement, attention companion, champagne preview action |
| DJ1 / GVE-0; MC2 / G0S-0 | Answer-first behavior, returns, next owner, journal gap and inert direction preview |
| BG2 / GE2-0 | Typed source qualification, provenance, independent receipts |
| BG3 / GJE-0; BG5 / H2Y-0 | Existing readers, missing producers, new-only component files, preview `NONE` |
| BG6 / HB7-0 | Future five-route shell integration; no legacy route removed in this change |

`atelier-office.jpg` is the original decorative asset used by AT08, acquired from
`https://app.paper.design/file-assets/01M3NRCX55B452A12819WNE1RH/0JC5MFZZJX2JDQMABG8XK2BF63.jpg`.
It is decorative and carries no product-state claim. Illustrative Paper names,
counts, direction and approval facts are never copied into live values.

`office.css` uses the current Noir palette with scoped classes. The sidebar and
global navigation remain with the incumbent shell. Display font fallbacks do not
establish font-asset or pixel parity; real browser comparison is still required.

## Remaining host integration gaps

The optional Programs host companion now retains its source-observation envelope
from the same raw acquisition, while the legacy method keeps its old return shape. Result keeps
source digests but has no observation timestamp; auth display state is not a
session identity. Keep missing provenance UNKNOWN or UNAVAILABLE. Do not invent
revisions, timestamps or session bindings to make the component show CURRENT.
A Mission-only adapter can retain its decoded owner observation and exact
selection, check the host invalidation epoch across acquisition, and label its
local acquisition time explicitly. Full Result integration additionally needs
an unmodified producer-compatible Mission v3 / Result pair or an authenticated
host test; the mutated pairs in unit tests qualify mismatch logic only.

`mission-adapter.ts` supplies that pure Mission presentation seam. Call
`captureMissionOfficeRead` before the existing host read, using the host's actual
`invalidationGeneration()` and the exact current selection. After the host read
and existing decoder complete, call `completeMissionOfficeRead` with a fresh
host/selection context and the local acquisition-completion timestamp. It does
not acquire, cache, authorize or submit anything itself.

An `observed` result supplies a snapshot and context that must be committed
together. A `discarded` result never replaces the current view: auth/target
changes and a newer accepted owner revision fence the old response. Invalid or
unavailable current-context observations clear the source revision and protected
value. This prevents an old failure or response from overwriting newer evidence.

The reference is the owner's Control Room document digest, explicitly labelled
as such. The revision is a tagged, ordered tuple of the decoded owner observation,
including Control Room and runtime identity/generation/digests. Local acquisition
time, title and UI counters do not contribute to revision identity. The source
inspector labels that local time separately from an owner-reported clock.
Programs, Result, Conversation and all unsupplied session/binding identity remain
with their existing qualification gates; this adapter does not fill those gaps.

## Verification and integration

From `app/mastermind_os`, run:

```sh
npm test -- src/meta-ceo
npm run typecheck
npm test
npm run build
npm run build -- --mode native
```

The candidate preserves exact source ancestry from #1046 / #1150 Work and
LAUNCH plus #1132 cancellation. Their protected landing gates remain independent.
The unaccepted #956 Work/Mission link is not imported. Render the actual product and
verify desktop, 390px, 320px, 200% text, keyboard/focus, all six source states,
unknown effect, draft retention and auth invalidation. Installed authenticated
owner data and the final Chairman journey are required for product acceptance.

## Programs receipt companion

`decodeProgramsObservation` in `../programs-observation.ts` retains a detached Programs
receipt and Control Room from one authenticated fixed-service response. It delegates
closed-envelope and owner-observation validation to the existing canonical decoder;
only its known unavailable/unqualified source results become negative-state data.
Legacy `decodeProgramsEnvelope` and `MissionHost.readPrograms` are unchanged. This
companion has no network, storage, command or provider access.

`captureProgramsOfficeRead` and `completeProgramsOfficeRead` apply the actual host auth
generation, selected context and winning Programs revision to that decoded observation.
Only a complete collection-scoped SAME receipt plus a valid strict Programs projection
can produce CURRENT. Collection coverage is `SUPPLIED_COLLECTION`, never a company total.
UNAVAILABLE clears content and source provenance; unknown/conflicting receipts do not
release content. Preserve the returned reason codes alongside the snapshot.

The digest is an **authenticated service-attested reference**. The frontend validates
its shape and the fixed service's receipt, and does not recompute a canonical content
hash. Tests use injected consumer fixtures under that same trust boundary, not live
service attestation. No Mission/runtime receipt, generated_at field or UI clock is
substituted for collection provenance; local observation time is labeled acquisition.

`MissionHost.readProgramsObservation` now performs the existing raw Programs read
once with the same before/after auth-epoch checks, then uses the companion decoder.
App selects it instead of the legacy reader, retains request-token/abort fencing,
and feeds the result to `useOfficeProjection`. That hook performs no acquisitions.
Both native transport gates accept a companion-only typed host. A changed Project
waits for its own collection acquisition before starting the exact Mission read;
reopening the same pair preserves its collection receipt without a duplicate read.

The hook captures presentation context before each existing read and commits the
accepted context/snapshot together. Discarded replies cannot replace a winner.
Legacy hosts supplying only bare Control Room data remain unqualified for Office
provenance. Result and Window snapshots are not yet fed into this hook.

App auth invalidation synchronously clears Office snapshots, private inspection
and draft state before passive reacquisition. Drafts remain ephemeral and scoped
to auth, exact selection and supplied session/binding fields; the latter remain
null when absent. Evidence and route detours do not destroy an unsent direction.
This is source integration, not authenticated native acceptance.
