# H5 — Exact-candidate CI observation and useful principal continuation

## Outcome and observed gap

A Claude principal must publish or identify an exact candidate, hand off observation, perform
useful independent work, consume the correct material result and advance a release gate or repair
an actual failure. A `gh pr checks --watch` loop is not this workflow.

The existing delivery law and observer design specify one observer per exact candidate [S26–S27].
This audit did not locate a production-proven observer registration/reconciliation/return API in
the bounded source paths inspected. That is a concrete unresolved integration fact, not evidence
that no such owner exists on another accepted surface. `executive_release_observation.py` observes
installed release/service identity; it must not be mislabeled as a GitHub CI observer.

## H5-A current source slice — pure candidate classifier, not an observer

The current branch now adds a source-only classifier inside the existing
`control_plane/github_release_assessment.py` owner. It consumes a caller-supplied, owner-native
snapshot for one repository / PR / exact candidate head and deterministically returns one of:

- `GREEN`: every exact required check's latest applicable generation is accepted success;
- `PENDING`: current-head checks are missing or still queued/running under a complete snapshot;
- `FAILED`: a current required check has a terminal disallowed conclusion;
- `UNKNOWN`: pagination/source identity/freshness/supersession evidence is incomplete or unsafe;
- `STALE`: the observed PR head no longer equals the frozen expected candidate.

The input binds the required-check policy revision, GitHub-owned complete source references, exact
check-run IDs, optional workflow-run IDs, attempt/sequence generations, producer identity and
applicability. Older failed attempts do not poison a later successful retry; a superseded latest
generation cannot become green. Skipped/neutral checks are accepted only when the required-check
policy explicitly permits that identity and the check is genuinely non-applicable.

This slice performs **zero polling, registration, persistence, wake, rerun, merge, deploy or lease
mutation**. It closes the deterministic classification seam only.

## H5-B1 current source slice — deterministic transition filter, not registration

The current branch now also adds
`control_plane/github_ci_candidate_observer.py` as a second pure layer over H5-A. It does not
sample GitHub. Instead, an existing Class-E/Class-T process owner may feed successive H5-A
observations through one deterministic observer key:

`repository + repository_id + PR + candidate_ref + expected_head_sha + required-check policy +
required-check identity set`.

That key produces one stable `github-ci-observer-...` identifier so an outer owner can coalesce one
observer per exact candidate without a new registry in this module.

The transition filter applies the protected watcher law directly:

- an initial exact PENDING sample establishes a quiescent baseline and does not wake reasoning;
- queued→running or partial required-check progress that leaves the overall candidate PENDING is
  suppressed as `NO_MATERIAL_CHANGE`;
- exact terminal GREEN / FAILED / STALE returns are terminal/material;
- UNKNOWN owner-native evidence is material when first seen or when its issue set changes;
- UNKNOWN→PENDING recovery is material so the owner can re-establish observer health;
- repeated UNKNOWN with the same issue set remains quiescent even when a fresh sample/digest moves;
- a terminal observer generation cannot be reused or resurrected;
- candidate/policy/required-check identity drift is a typed refusal, not implicit rebinding.

B1 validates the canonical digest of every supplied H5-A observation before consuming it. It imports
no network, subprocess, timer, persistence, MCP or scheduling owner and exposes no merge/deploy/rerun/
Wake operation. It therefore closes the **material-change filter and deterministic dedupe identity**
only. It still does not register a process, poll GitHub, own a return route, or wake/resume Claude.

## H5-B2-A current source slice — material return into existing Wake Fabric

The bounded owner census ruled out three tempting but incorrect compositions:

- Agent Dialogue's Class-E/Class-T turn observer is Slack/thread specific and would couple GitHub
  release state to dialogue semantics;
- Worker Capacity observation is provider-capacity specific and owns no generic scheduler;
- Executive Inbox admission accepts only Runtime-projected or Agent-OS decision attention, so
  projecting GitHub CI as Inbox attention would forge the source owner.

The source-safe composition is lower-level: the existing Wake Fabric gains one closed
`github_ci_candidate_observation` source kind and one `ci_candidate_material` wake kind.
`control_plane/github_ci_candidate_wake.py` projects only an H5-B1 decision that has already
validated as material/terminal. Quiescent samples cannot mint an obligation. The source reference is
`github_ci_candidate:<decision canonical digest>`, so a material event is source-anchored and route
changes cannot change its Wake identity.

The GitHub-CI source cannot mint dialogue/runtime/consultation wake kinds and cannot claim a Job or
Attempt as its source. An optional root Job is correlation/routing only. The current H5 adapter is
COO-bound and leaves SessionTargetRegistry/Wake Fabric to resolve the actual session target; it does
not accept a session alias, native handle, provider, account or transport.

This slice adds **no sampler, GitHub client, timer, persistence, watcher registry, retry loop, Wake
delivery call, merge, rerun or deploy operation**. It closes the material-result → existing-Wake
obligation seam only.

## H5-B2-B1 current source slice — process-local exact-candidate waiter

The current branch now adds `control_plane/github_ci_candidate_waiter.py`. This is the bounded
Class-E/Class-T process primitive missing from B1; it still does **not** own GitHub transport.

One process-local `CandidateWaiterRegistry` registers the deterministic B1 observer identity before
sampling. A duplicate registration for that exact candidate fails with zero displacement. Registration
tokens are opaque, never reused for the process lifetime, and cleanup is compare-and-delete so an old
`finally` cannot clear a newer registration. Restart intentionally loses the registration: it is hot
process evidence, not durable watcher/lifecycle truth.

`wait_for_candidate_material` accepts only:

- a previously classified exact-candidate baseline;
- an injected owner-native `sample()` callback;
- an injected blocking/cadence `wait()` callback;
- the process-local registry; and
- a bounded sample count.

A PENDING baseline may arm the waiter. A terminal or already-UNKNOWN/material baseline must be consumed
before waiting. Each sample goes through H5-B1; PENDING progress and unchanged state stay inside the
blocking call, while GREEN/FAILED/STALE or observer-health transitions return exactly once. Identity
drift refuses and cleanup still unregisters the incumbent. Exhausting the bounded sample budget returns
a typed quiescent result with no Wake or reasoning claim.

This module imports no GitHub/network, timer, persistence, MCP, Wake, Runtime, subprocess or release
owner. The injected wait function controls Class-E/Class-T cadence; the reasoning model never receives
unchanged samples. Tests cover duplicate registration, stale compare-delete, token reuse, terminal and
UNKNOWN returns, identity drift, cadence failure, bounded exhaustion and guaranteed cleanup.

## H5-B2-B2 remaining host/source composition

The remaining H5 process work is narrower. One accepted host composition must:

- obtain complete owner-native GitHub PR/check snapshots for the frozen candidate;
- provide the current required-check policy/source reference used by H5-A;
- feed those snapshots into H5-A through the injected B2-B1 `sample()` seam;
- supply the accepted Class-E/Class-T blocking/cadence primitive through `wait()`;
- reconcile ambiguous host registration/delivery state by the exact observer identity rather than
  starting a second process;
- send only a B1 material/terminal decision through B2-A into existing SessionTargetRegistry/Wake
  Fabric; and
- retire the process-local waiter when the bounded call exits.

The repository already has a hardened GitHub GET-only transport in Source Continuity, but it is a
script-private adapter with Source-Continuity-specific budgets and conditional-revalidation semantics.
H5 must not import that private script backwards into Executive code or clone a looser API client merely
for convenience. Either factor an accepted shared read-only GitHub transport from its existing owner or
compose H5 from another already-accepted owner-native GitHub read surface.

No production-proven generic GitHub-CI sampler/host composition has yet been located in the bounded
current source. That absence blocks unattended/native H5 claims; it does not justify a Claude plugin
database, persistent watcher table or misuse of the Slack/capacity observers.

## Resolve the existing owner first

The next implementation unit obtains the canonical process/CI owner's current accepted contract
and one actual available read-only observer handle. Verify these operations by their exact API,
not proposed names: register-or-reuse; read current observation; reconcile registration after
response loss; deliver a material result through the established return route; retire the obsolete
candidate subscription. Do not require the Chairman to pick a provider/session for routine placement.

If only design exists, implement the bounded observer adapter **inside that existing owner**.
Use its current process lifetime, cancellation, persistence and return/Wake mechanisms. Do not
create a Claude CI daemon, plugin database, per-conversation scheduler or another queue. Missing
unattended return blocks unattended claims, not permitted foreground work or one status read at a
real integration boundary.

## Candidate identity contract

The observer must bind the repository, PR identity, exact head SHA, relevant workflow/check-run
identities, required-check policy and return target through their existing owners. Include the
source/merge context the actual GitHub check evaluates; a PR-head check and a synthetic-merge check
are not interchangeable evidence. Use the release owner's accepted association rules rather than
inventing a permissive match based only on branch name.

The required-check set is not "all rows currently returned by a status endpoint." Missing expected
checks, inaccessible results, incomplete pagination or checks under an old policy cannot yield
PASS. Bind producer identity where the existing branch/ruleset owner requires it. Do not fetch or
interpret a permission-denied policy through an alternate credential. Refusal is a gate, not a
reason to assume an empty check set.

Observation identity is separate from operation identity. A new head gets a successor candidate
observation; it does not become a new source-writing mission or erase the prior head's evidence.
A repeated registration for the same candidate must reuse the original owner handle. A lost
registration response requires reconciliation by that exact candidate before any repeat.

## Selected flow

1. **Freeze candidate:** record exact source/PR head and the existing review/release prerequisites.
   Branch-local write permission alone does not imply publication permission [S31]. Use the
   source publication owner for push/open-PR effects.
2. **Register or reuse:** obtain one canonical observer, bound to the candidate and eligible exact
   principal return target. A registration receipt is not proof of an observed PASS or a wake.
3. **Continue useful work:** choose a path-disjoint design, review, test investigation or integration
   unit whose result cannot change the frozen candidate being reviewed. Do not duplicate a worker,
   rebase for appearance, push empty commits or repeatedly ask the status tool for no change.
4. **Consume material return:** validate candidate identity, expected checks and terminal outcomes,
   source revision and current return binding. Re-read the current PR head at the release decision
   boundary. A stale return remains historical evidence and never passes the successor head.
5. **On real failure:** fetch bounded exact failing step/log evidence, classify code defect versus
   environment/dependency issue, repair the scoped defect under the existing writer, and test it.
   A changed candidate gets a newly bound observation. The observer does not rerun jobs or repair.
6. **On exact PASS:** the release owner separately checks independent review, custody, permission,
   current head and any product/production acceptance prerequisites. No observer merge/deploy.
7. **Retire only the candidate subscription:** preserve its final evidence, avoid duplicate
   observers and do not stop an aggregate watcher still serving valid sibling work.

Polling, when required, is bounded and owned by the existing Class-T process policy, not by the
Claude reasoning turn. Event delivery is preferred when already supported. No guessed universal
interval or new retry budget is introduced. Throttling or outage uses that owner's existing backoff
and explicit unavailable status. Elapsed waiting is not useful principal work.

## Result handling without a new lifecycle

Use the observer/release owner's actual statuses. At the presentation layer, distinguish pending,
terminal failure, terminal required-check success, unavailable/incomplete evidence and stale
candidate. Do not collapse cancellation, neutral or skipped outcomes into success unless the
accepted required-check policy explicitly does so. A green optional check cannot replace a missing
required test.

The return route may notify only; native principal resumption must be proven separately through
existing RuntimeBinding/SessionTargetRegistry and Wake. If no exact eligible target is bound, retain
the result for ordinary authenticated retrieval and report delivery as unconsumed. Never route it
to the newest chat, launch a new Job or treat arbitrary Slack prose as acceptance.

## Failure and race cases

| Case | Required behavior |
| --- | --- |
| Head moves between observe and release | Old evidence stays attributed; release fails current-head comparison. |
| Two observers requested concurrently | Existing owner deduplicates the same candidate; no new plugin lock table. |
| Registration applied but response lost | Reconcile original candidate/handle; do not blind-register a second watcher. |
| Check name reused by wrong producer | Apply current required-check identity rules; refuse ambiguous evidence. |
| Required check never appears | Pending or explicit unavailable/timeout under existing policy, never PASS from an empty set. |
| Cancellation/re-run while return is in flight | Bind run/attempt identity and consume only the current applicable result. |
| Wrong native return target or closed child | No cross-session delivery; preserve result and the exact binding gate. |
| Observer unavailable while other work is ready | Continue independent work; no fictitious background monitoring claim. |
| Failed candidate needs repair | Existing source owner writes; observer retains read-only authority. |

## Acceptance experiment

Use a real disposable or appropriately authorized PR with an exact head and required checks. The
principal identifies the candidate, obtains a reusable observer handle and performs another useful
independent phase. The observer returns the matching material result, and the principal either
repairs a real scoped failure or truthfully advances the candidate's release prerequisite.

Test stale-head and duplicate-registration behavior with disposable cases before production use.
Do not manufacture a failing production build or change required checks to make the canary pass.
A read-only status sample from this planning session is not the native acceptance experiment.
Cases H5-01 through H5-12 cover the scenarios.

Completion evidence includes exact candidate/run/check identities, observer handle and owner,
useful independent work artifact, consumed return, current-head validation and lawful release or
repair decision. Separate observer registration, result delivery, native pickup and acceptance.
No autonomous merge/deploy or unattended Web reasoning is implied by successful observation.
