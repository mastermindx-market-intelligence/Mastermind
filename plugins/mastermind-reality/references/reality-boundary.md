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

Every record carries one closed `revision` object. The `ORIGINAL` form is explicit and empty: no predecessor observation, no changed input references, no affected finding identities, no reason, and no revised conclusion. The correction form is not free prose. It names the predecessor observation identity, the changed input references, the affected finding identities, the reason, the revised conclusion, and it binds an explicit owner-relative predecessor-record reference together with that record's SHA-256.

A predecessor observation identity alone proves nothing about changed evidence. The bound predecessor record is resolved under the same owner-qualified evidence root supplied to the verifier, its bytes must match its declared digest, and its own observation identity must match the named predecessor. There is no identity lookup, no registry, no path guessing, and no implicit current record.

A correction is refused when it references its own observation, when the bound predecessor record is missing or its digest mismatches, when a changed input reference does not resolve to a declared artifact, when an affected finding identity is not present in the observation, when the changed or affected set is empty, or when nothing but the wrapper timestamp changed. A correction may not silently upgrade the capture epoch of its predecessor, and it may not change the effect state without changed effect evidence. A correction never rewrites the historical artifacts it corrects.

If source or deployment changes after capture, the observation remains valid for its recorded epoch and must not be described as current. If a target identity, build relationship, or effect is ambiguous, fail closed rather than selecting the newest-looking candidate.

## Unresolved artifact identity

Public source may be unable to supply the expected digest of an owner-native artifact. That fact is disclosed, not hidden. An effect or cleanup evidence descriptor may carry an explicit null digest with `identity_status` `UNRESOLVED` and a concrete reason. The closed shape may represent a disclosed unavailable identity; executable acceptance stays fail-closed.

A record that carries an unresolved artifact identity can never return a valid verification receipt, whether or not the artifact happens to be present on disk. The owner's separately reported effect is retained as attribution and is never converted into a current verification.

## Cleanup grounding

Cleanup states temporary-process, temporary-profile, and shared-resource disposition separately. A `CLEAN` state requires absent temporary processes and unchanged shared resources. A `REMOVED` temporary profile additionally requires owner-grounded evidence: the retained cleanup artifact must identify the profile and carry both pre-removal and post-removal evidence. A `NOT_CREATED` profile requires an owner-grounded profile identity and pre-creation evidence. Zero matched processes and zero matched workspace paths are absence counters, not proof that a named profile was removed. When the receipt proves only the counters, record the profile as `UNKNOWN` and the cleanup state as `INCOMPLETE`.

## Deterministic verification seam

The package ships one pure, stateless verifier at `scripts/verify_reality_observation.py`. It reads one observation record, one owner-qualified evidence root supplied by the caller, and the packaged schema, and it returns one closed receipt containing exactly the schema, verdict, observation identity, observation digest, artifact count, checks, and errors. It performs no write, no network access, no subprocess, no repository or filesystem search, and it creates no database, evidence store, browser registry, lifecycle, identity, retry, queue, or control plane. The caller supplies the evidence root; the API grants no authority over it.

The verifier enforces the closed schema, strict JSON with duplicate-key and non-finite refusal, real UTC calendar parsing and ordering, source-revision sibling equality and difference, root-contained regular-file resolution with absolute, traversal, and symlink-escape refusal, existence, exact byte count, digest and unique identity for every declared artifact, actual PNG structure and dimensions with bounded reads and decompression, consumption-proof binding to the intended consumer and the exact screenshot identity, resolution of every finding and negative-control reference against the declared artifacts, negative-control method and signal meaning, capability, target, journey, and control consistency, honest cleanup, secret-shaped value refusal across every public text field, and the closed correction semantics above.

A valid verdict proves exactly one thing: the supplied record and the supplied artifacts are mutually consistent. It does not prove newly authenticated model consumption, a real-product success, installation, deployment, or runtime authority.

## Completion law

The completion rule is explicit: source green is not production proof. A manifest, schema, skill, fixture, passing contract test, merged pull request, installed package, authenticated provider, captured screenshot, and successful journey are distinct states.

Use:

- `SPEC_ONLY` for architecture or procedure without implementation;
- `BUILT_NOT_PROVEN` for source that has not passed the required installed real-path proof;
- `PARTIAL` when only part of the journey or evidence seam works;
- `DARK_OR_DISCONNECTED` when a built capability cannot reach its intended consumer;
- `BROKEN` when an expected live path demonstrably fails;
- `PROVEN_LIVE` only for the exact approved target, account, package generation, journey, and proof epoch actually demonstrated.

`PROVEN_LIVE` is refused when it coexists with a `TEST_FIXTURE` target, a `FAILURE`, `UNKNOWN`, or `PARTIAL` journey outcome, a required negative control that was not exercised, an unresolved evidence identity, an unknown architecture binding, or an observed surface state that is not `LIVE`. The completion claim is consistent with the evidence it cites, or it is refused.

One successful journey does not prove every product, viewport, account, data state, or provider.

## Rollback and cleanup

Before installation, rollback closes or reverts only the source carrier. After installation, rollback removes only the package mapping or generation owned by that operation. Do not delete historical evidence, disable shared browser or observability services, close unrelated sessions, or modify another plugin.

Temporary capture processes and isolated profiles must be absent at return. Cleanup failure is reported explicitly and never converted into permission for a retry, broader shutdown, or false terminal state.


## Qualified bytes and explicit witness facts

Verification uses one call-local byte snapshot per distinct declared reference. Observation, schema, predecessor and artifact files must be bounded regular files. Descriptor-relative, no-follow directory walks and before/after descriptor and pathname identities refuse symlink traversal, file replacement and mutation during a read. Digest, byte count, PNG interpretation and JSON facts all use the same captured buffer; a helper does not reopen a pathname after qualification. This cache exists only for the invocation and is not an evidence store.

The existing per-input limits remain: observation 8 MiB, schema 4 MiB, artifact 32 MiB, PNG compressed image data 16 MiB and decoded raster 64 MiB. Retained artifact buffers additionally have a 128 MiB aggregate limit. Strict JSON traversal is limited to 64 levels and 100,000 nodes; receipts contain at most 256 bounded errors. An unreadable, changing or oversized observation has a null observation digest; a truncated prefix is never identified as the complete observation.

The supplied schema must use the packaged Draft 2020-12 dialect and closed observation envelope. Reference-bearing schemas, including nested `$ref`, `$dynamicRef` and `$recursiveRef`, are refused before schema validation. The `$id` URI identifies the schema and grants no permission to retrieve it. Malformed nested records return closed errors before semantic traversal. Secret-shaped keys and values are scanned; output paths do not reproduce untrusted keys or artifact references, and redaction precedes truncation. An invalid or secret-shaped observation identity is returned as null.

PNG verification checks critical chunk order and CRCs, legal color/depth combinations, palette rules, exact bounded raster length, filters 0–4 and all Adam7 pass dimensions, including empty passes. Indexed pixels are checked against the actual palette after reversing their filters. Valid ancillary chunks, split or empty consecutive IDAT chunks, unused packed-sample padding bits and permitted padding after the zlib stream remain representable. Unknown critical chunks, an unfinished stream, extra decoded raster data and bytes after IEND are refused. This verifies the default PNG image; it does not claim interpretation of ancillary metadata or animation frames. Format references: [W3C PNG3](https://www.w3.org/TR/2025/REC-png-3-20250624/) and [Python 3.14 zlib](https://docs.python.org/3.14/library/zlib.html).

### Negative-case witness format

An exercised method/signal label must agree with identity-qualified evidence bytes. A JSON witness places its facts under `negative_controls.<control_name>` inside a referenced artifact, leaving the closed observation evidence descriptor unchanged. Each such fact object identifies:

- `control` and a nonempty `case_ref`;
- the original `operation_ref` and `carrier_ref`;
- `observed_at` within the original capture interval;
- the specifically attempted `target_ref`.

These describe a deliberate negative case. A negative target or build cannot replace the primary journey's identity or result. A correction may change the observation wrapper identity while retaining its original operation, carrier and capture instants.

| Control | Required underlying facts |
| --- | --- |
| Wrong target | An explicit negative target distinct from the primary locator and an integer `http_status` of 404. |
| Stale capture | A named `input_ref` and SHA-256, an `input_captured_at` earlier than the explicitly stated `required_not_before` comparison, and `stale_disclosed: true`. The comparison cannot be later than the witness observation. The old input time is intentionally outside the newer interval; no universal freshness TTL is invented. |
| Different build | An explicit negative target, an expected `protected_sha` equal to the primary observation's protected SHA, and a well-formed, distinct `observed_deployed_sha` for the negative case. The primary journey may correctly have a MATCH relationship. |
| Different viewport or data state | Two referenced screenshots from the supplied capture with actually decoded, different dimensions; alternatively a bound JSON witness identifying `first_artifact_ref` and `second_artifact_ref` among its references, whose qualified JSON snapshots contain distinct `data_state` values and distinct digests. |
| Missing screenshot bytes | A safe `attempted_artifact_ref` absent from the resolved evidence, `screenshot_bytes_present: false`, and `refusal_code: SCREENSHOT_BYTES_REQUIRED`. The verifier does not probe undeclared paths. |
| Broken browser connection | A named `provider_ref` relevant to the primary target and `connection_state: DISCONNECTED`. A generic degraded runtime label is insufficient. |
| Excluded account surface | An explicit refused proposal for the existing `MANAGED_CHAIRMAN_ACCOUNT` class, a distinct target, `refusal_code: TARGET_CLASS_EXCLUDED`, and `access_attempted: false`. This is refusal before access and grants no account interaction. |

OWNER_EVIDENCE controls report DETECTED; CONTRACT_REFUSAL controls report REFUSED. Conflicting relevant witness facts invalidate a control even if another cited artifact supports its label. NOT_EXERCISED remains honest representable partial data and cannot establish PROVEN_LIVE. Historical empty evidence references remain representable but cannot verify an exercised control.

### Effect, correction and cleanup witnesses

Every cited ordinary effect JSON receipt must agree with the observation's state, operation and carrier. A CORRECTION's predecessor must itself have a closed, safely traversable record shape, valid times and consistent declared identities. Both parsed capture instants are preserved. The verifier compares predecessor declarations without reopening historical artifact paths, which may now hold the newly declared current evidence.

Changing an effect state requires an actually added or changed, currently qualified effect receipt that supports the new state and appears in `changed_input_refs`. Deleting an older receipt is insufficient. The original operation and carrier remain fixed. These checks do not create fresh authority or authenticate the purported owner.

A positive REMOVED or NOT_CREATED profile claim names an optional observation field, `cleanup.temporary_profile_id`, which is semantically required for that positive claim. The referenced cleanup JSON must bind the same intended identity. A REMOVED witness carries `pre_removal` and `post_removal` objects with that identity, typed `present: true` then `present: false`, and ordered UTC `observed_at` values. Empty objects or string booleans are insufficient.

A NOT_CREATED witness carries a before-state with typed absence plus a `creation` object naming the same profile, `created: false`, an explicit `owner_ref` and an ordered observation time. Positive CLEAN claims also require absent temporary processes and unchanged shared resources in the supplied witness. Any stated operation/carrier binding must agree with the original operation. Contradictory profile or disposition facts invalidate the claim. Historical UNKNOWN/INCOMPLETE records may omit the new identity field and retain their original limitations.
