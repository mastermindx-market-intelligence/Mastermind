# Meta-CEO read-first product slice

This composition implements the content hierarchy of Paper's current Daily
Office (DJ1/DJ1M) and Meta-CEO office (MC2/MC2M) inside the existing React product.
It is a source candidate. The incumbent shell does not import it yet; route,
browser, native, authentication and production acceptance remain separate gates.

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
remains `WORK_PENDING_CUSTODY` until the released Work adapter can be consumed.
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
Observed target snapshot: `d30579fa90752a3623d8562574b7f224916666d55b77fc04a17b8e7c04fd1a17`.
This identifies the guarded design observation, not a collaboration lock.

| Current design | Consumer surface |
| --- | --- |
| DJ1 / GVE-0; MC2 / G0S-0 | Answer-first heading, movement, returns, next action, journal gap, bottom direction preview |
| BG2 / GE2-0 | Typed source qualification, provenance, independent receipts |
| BG3 / GJE-0; BG5 / H2Y-0 | Existing readers, missing producers, new-only component files, preview `NONE` |
| BG6 / HB7-0 | Future five-route shell integration; no legacy route removed in this change |

`office.css` uses the current Noir palette with scoped classes. The sidebar and
global navigation remain with the incumbent shell. Display font fallbacks do not
establish font-asset or pixel parity; real browser comparison is still required.

## Verification and integration

From `app/mastermind_os`, run:

```sh
npm test -- src/meta-ceo
npm run typecheck
npm test
npm run build
npm run build -- --mode native
```

Before connecting the shell, reconcile the incumbent #1046 / #1150 Work and
LAUNCH stack, #1132 host cancellation and #956 Work/Mission link. No source in
those lanes is replaced here. After integration, render the actual product and
verify desktop, 390px, 320px, 200% text, keyboard/focus, all six source states,
unknown effect, draft retention and auth invalidation. Installed authenticated
owner data and the final Chairman journey are required for product acceptance.
