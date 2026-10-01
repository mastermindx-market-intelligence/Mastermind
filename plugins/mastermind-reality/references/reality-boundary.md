# Mastermind Reality Boundary

This reference defines the authority, evidence, privacy, correction, and completion boundary for one Reality observation. It is packaged procedure, not live company state.

## Purpose

Reality answers one question: can a named persona complete one meaningful task in one approved Mastermind product state, and what directly inspectable evidence supports that conclusion?

The package coordinates current owners. It creates no new browser registry, trace engine, evidence database, runtime, lifecycle, queue, scheduler, retry service, identity system, authorization system, transcript store, memory plane, or control plane.

## Canonical owners

- Current Chairman intent and protected operating law define the permissible outcome and authority ceiling.
- Executive OS owns Job, Attempt, Worker, Event, admission, effect, and runtime lifecycle facts.
- Agent OS owns durable responsibilities, decisions, discoveries, and handoffs.
- GitHub owns source, pull-request, review, CI, and implementation evidence.
- Linear is a portfolio projection.
- Slack is transport and hot-state evidence.
- The existing browser owner owns browser target qualification and interaction capability.
- The existing trace owner owns trace capture and retention.
- The existing observability owner owns logs, metrics, runtime facts, and their coverage.
- The existing evidence owner retains artifacts according to its own policy.

This package may cite owner-native facts. It may not copy them into a replacement authority or promote a convenient projection above its owner.

## Target boundary

Allowed target classes are:

- `APPROVED_PRODUCT`: one specifically authorized Mastermind product environment.
- `TEST_FIXTURE`: one bounded synthetic target used only to discriminate a contract or failure.

The managed Chairman account surfaces, Web-Sol provider-control surfaces, password managers, browser settings, authenticated vendor settings, cookies, storage, tokens, and unrelated browser profiles are outside this round. A generic browser or shell capability does not authorize them.

There is no credential passthrough and no credential inheritance from another plugin. Never collect raw process arguments, browser-profile contents, account tokens, session cookies, passwords, API keys, or secret-bearing settings.

## Evidence boundary

A visual claim requires:

1. an approved target;
2. actual PNG bytes;
3. a cryptographic digest of those bytes;
4. exact viewport and data-state identity;
5. proof that the intended model consumed the bytes;
6. corresponding semantic or accessibility evidence where available;
7. relevant runtime or trace evidence with explicit coverage;
8. a recorded capture window.

A path, URL, hash, file-exists result, HTTP success, DOM node, or worker statement does not prove visual consumption. Screenshots alone do not prove backend truth. Semantic evidence alone does not prove visual usability. Runtime evidence alone does not prove the user completed the task.

A bare boolean is not consumption proof. The screenshot receipt must identify the intended consumer and delivery method, bind a safe owner-relative reference plus digest for the retained consumption evidence, and expose any missing provider-native timestamp or identity as a limitation.

Semantic and runtime evidence are explicit sets. `AVAILABLE` requires at least one consumed artifact; `PARTIAL` requires retained artifacts plus a concrete limitation; absence is explicitly `UNAVAILABLE` with a concrete reason and zero artifacts. Unavailable is never encoded as an empty available array.

Use the smallest evidence needed to make or falsify the claim. Keep private evidence in its approved private owner; public source may contain schemas, sanitized findings, and digests only when policy permits.

## Data, time, null, and coverage

Keep these clocks distinct:

- source event time;
- deployed or release observation time;
- capture start and completion time, both as UTC RFC 3339 values ending in `Z`;
- evidence `recorded_at`.

Capture completion must not precede capture start. A newer `recorded_at` does not make older source current. A matching title does not establish build identity. `MATCH requires identical` source revisions and an exact comparison receipt. `DIFFERENT requires distinct` source revisions and an exact comparison receipt. When the deployed revision cannot be observed, the relation and comparison are `UNKNOWN`/`UNOBSERVABLE`; do not manufacture equality.

The data rule is explicit: unknown is not zero. Unavailable is not empty. Partial coverage cannot prove global absence. Every runtime or trace reference states what it covered. Every model finding retains material unknowns.

Viewport and data-state identity are part of the observation. Evidence from a different viewport, dataset, account, release, or observation window may be comparison evidence, but cannot silently substitute for the frozen journey.

## Deterministic and model responsibilities

Deterministic code may establish target identity, origin, source and deployed revisions, timestamps, viewport, data-state labels, artifact bytes and digests, schema validity, negative-control outcomes, and cleanup evidence.

The frontier model may interpret hierarchy, clarity, accessibility, workflow coherence, visual quality, usability, and plausible causes. Model output has zero authority to assert execution, security, deployment, completion, measured user impact, or canonical company state unless the proper owner supplies that fact.

A finding records one of `DETERMINISTIC_OBSERVATION`, `MODEL_INFERENCE`, or `MIXED`, exact evidence references, and explicit unknowns.

## Effect and retry law

Keep response status separate from effect:

- `NOT_APPLIED`: the owner proves no modifying effect occurred.
- `APPLIED`: the owner proves the intended effect occurred.
- `EFFECT_UNKNOWN`: the effect boundary cannot be established.

Refusal, process exit, timeout, cancellation request, permission expiry, and lost transport are not additional effect states. Under `EFFECT_UNKNOWN`, retain the original operation and carrier and perform only owner-native read reconciliation. Never retry through a different browser, account, session, service, or carrier for a cleaner result.

Every return records effect and cleanup as separate closed objects. Effect states what the owning operation proves; cleanup states temporary-process, temporary-profile, and shared-resource disposition. Cleanup success never converts missing effect evidence into `NOT_APPLIED`, and effect success never proves cleanup.

## Negative controls

A complete round-one record addresses:

- wrong target;
- stale capture;
- different build;
- different viewport or data state;
- missing screenshot bytes;
- broken browser connection;
- excluded account surface.

Each control is `DETECTED`, `REFUSED`, or `NOT_EXERCISED`, with a concrete reason. Controls are evidence about the bounded observation, not a claim that every provider or product state was tested.

## Correction and supersession

Evidence is immutable historical observation. A correction creates a new owner-native record that identifies the earlier observation, changed input, affected finding, and revised conclusion. Do not overwrite historical artifacts or refresh old evidence by changing its wrapper timestamp.

If source or deployment changes after capture, the observation remains valid for its recorded epoch and must not be described as current. If a target identity, build relationship, or effect is ambiguous, fail closed rather than selecting the newest-looking candidate.

## Completion law

The completion rule is explicit: source green is not production proof. A manifest, schema, skill, fixture, passing contract test, merged pull request, installed package, authenticated provider, captured screenshot, and successful journey are distinct states.

Use:

- `SPEC_ONLY` for architecture or procedure without implementation;
- `BUILT_NOT_PROVEN` for source that has not passed the required installed real-path proof;
- `PARTIAL` when only part of the journey or evidence seam works;
- `DARK_OR_DISCONNECTED` when a built capability cannot reach its intended consumer;
- `BROKEN` when an expected live path demonstrably fails;
- `PROVEN_LIVE` only for the exact approved target, account, package generation, journey, and proof epoch actually demonstrated.

One successful journey does not prove every product, viewport, account, data state, or provider.

## Rollback and cleanup

Before installation, rollback closes or reverts only the source carrier. After installation, rollback removes only the package mapping or generation owned by that operation. Do not delete historical evidence, disable shared browser or observability services, close unrelated sessions, or modify another plugin.

Temporary capture processes and isolated profiles must be absent at return. Cleanup failure is reported explicitly and never converted into permission for a retry, broader shutdown, or false terminal state.
