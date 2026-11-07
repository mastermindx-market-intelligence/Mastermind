# Live progress metadata

The Codex collector uses the existing App Server demultiplexer and
`VisibleTurnProjection`. It performs no provider reads, creates no event ledger,
and does not change the retained `read_events` or Runtime candidate/terminal
collection contracts. Observations exist only in the bounded hot turn window.
There is no replay of activity emitted before explicit viewer enrollment.

The existing sealed `ContentObserverProfile` authorizes visible response text with
`allowed_visible_response`. That decision does **not** authorize progress.
An installation wishing to release progress must separately qualify and seal
`allowed_visible_response_and_progress_metadata` through the same Content profile
owner. The profile digest binds that decision, the original Runtime join and
before/after access ticket still apply, and each viewer's grant independently
filters metadata items and metadata-attributable gaps. Source support does not grant permission to update a profile.
No installed profile, client grant or deployment is changed by this source work.

The first source-qualified vocabulary is Codex App Server `codex-cli 0.159.2`:

| Observation | Released representation | Withheld data |
| --- | --- | --- |
| `turn/plan/updated` | Authored step counts by pending/inProgress/completed; explicitly non-executable | Step prose, explanation and all unknown fields |
| Allowlisted `item/started`, `item/completed` tool categories | Fixed category and observed lifecycle; completion outcome unverified | Raw item identity (replaced by a hash for upserts), command, arguments, result, paths, tool/server names and arbitrary nested fields |
| Reasoning or unsupported item type | Nothing | Entire payload |

Hashes preserve stable item identity; they are not a secrecy guarantee for
predictable native IDs. Retention budgets are shared across viewers, so metadata
can cause visible-text eviction; the original response loss remains observable
to a response-only viewer, while metadata parser gaps do not force its resync.
Combined pages preserve existing source display order; local publication order
is the update/cursor clock and is the appropriate clock for an activity timeline.

These summaries use the existing bounded visible-item wire envelope and renderer.
`completed` is an observed item lifecycle state; it does not mean a successful tool,
an accepted deliverable, a completed Job or an admitted executable plan. An authored
plan remains partial even when all authored steps claim completion. The publication
sequence is local observation order, not a provider-authored plan revision number.
The provider schema supplies no plan revision clock, so delivery order cannot prove
which of two replayed authored plans is newer.

Only an exact current attempt/epoch/generation/worker/local/native turn grant can
read. Progress additionally matches the bound provider thread and turn. Foreign
threads/turns, unsupported collectors and unqualified Codex versions cannot enable
this path. Existing revoke, generation invalidation, cursor/epoch and retention-gap
behavior applies; post-terminal events cannot extend the window. Gaps indicate
missing observations, never successful work. Cancellation only closes observation;
Runtime continues to own cancellation, uncertain IO and accepted completion.

Provider coverage is deliberately limited. Claude's current helper does not collect
these tool events; ACP's admitted tool observations do not add plan support.
Neither is silently enabled by the Codex profile. A future provider requires its
own source/schema qualification through the existing collector and permission owner.

Release obligations remain: proportionate independent privacy/authorization review,
required hosted checks, normal protected integration, explicit data-release profile
qualification and sealing, then separately authorized real provider/Web/native proof.
Synthetic source tests are not live emission, installed-profile permission or user
acceptance evidence.
