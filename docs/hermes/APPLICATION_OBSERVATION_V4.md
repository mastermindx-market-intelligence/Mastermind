# APPLICATION return observations in the native EVAL path

## Architecture decision

Hermes owns the persistent conversation and bot lifecycle. Executive OS retains admission and physical placement; the existing APPLICATION owner retains each inference operation, route and uncertainty. Native EVAL observes the original execution and publishes only what its retained evidence supports.

The native request observer now has an APPLICATION contribution. It does not construct a Broker client, dispatch another task, select an account, retry an inference, move a session, add a store, or activate a service.

## Versioned evidence

The outer request envelope remains `mastermind.hermes_request_observation/v3`. Existing HTTPX-only executions retain transport v3, and historical v1–v3 documents keep their existing interpretation.

An execution that observes an original APPLICATION client uses transport v4. It retains one shared call/dispatch graph with two explicitly different attempt arrays:

- `attempts`: original synchronous HTTPX send observations.
- `application_attempts`: source-qualified APPLICATION create entry and return observations.

Both arrays consume the incumbent attempt cap and shared 16 KiB metadata budget. APPLICATION terminal projections reserve their bounded maximum before the original invocation. Overflow is explicit. The final document is detached; late returns cannot append evidence after the original scope seals.

## Original identity and response

The observer captures the exact original `ApplicationBinding` and `NativeCall` at create entry. The request commitment includes operation, session, task, turn and API-request identity. Task identity must match the original native caller, not a later mutable agent label.

The original create method executes once and receives its original arguments. Its result or exception remains unchanged. Before a successful result reaches Hermes, the observer detaches only the closed APPLICATION observation subtree. It never serializes the answer, headers, credentials or tool output and never consults a cached last observation.

The retained native content digest describes the observer's entry snapshot. Owner original and routed request digests describe the incumbent owner's separate translated-wire commitments. These digests are deliberately distinct. The observer does not claim independent equivalence between them or revalidate a receipt by supplying its own digest as an expected digest.

The source-qualified original client has already required the typed, validated owner response. Historical validation checks the retained projection's shape, bounds and joins; it does not independently establish producer authenticity.

## Publication and limits

Publication joins the union of HTTPX and APPLICATION attempts to the original calls, dispatches and selected-input assemblies. A successful path cannot hide an unfinished, unsupported, missing or overflowing sibling path. APPLICATION does not provide an HTTPX API-key witness.

Timing, process identity, native identity and observed request labels remain subject to their existing independent gates. Provider coverage is PARTIAL. A serving-model label is retained as owner-reported evidence; it is not promoted to verified model identity.

This contribution retains:

- `complete_evaluation=False`
- `provider_delivery_proven=False`
- `model_identity_verified=False`
- Whole-run `EFFECT_UNKNOWN`
- Cleanup `UNPROVEN`

A terminal inference receipt resolves that inference's disposition; it does not settle tool effects or whole-agent cleanup. This slice does not make a Trial VALID and does not open the existing learning promotion or runtime admission gates.

## Verification boundary

Focused tests exercise the actual pinned native caller/worker and original APPLICATION adapter. Their admitted owner and immutable owner-response type are explicitly declared fixtures; they do not qualify Broker networking, credentials, a provider, a deployed service or a live Trial.

The checks cover exact/AUTO return capture, wrong or reused identity, immutable retained metadata after response mutation, unsupported or missing evidence, original exception behavior, sealing, shared limits, mixed transport paths, closed historical schemas and conservative publication. Existing HTTPX and native publication tests remain applicable.

The complete native producer still needs the evidence specified in `NATIVE_EVAL_PRODUCER_CONTRACT.md`, including actual runtime policy measurements, supported randomness semantics, complete coverage, effect settlement and cleanup. Those gates must be supplied by their existing owners.

## Source qualification

The focused Python 3.12 qualification used OpenAI 2.54.0 and HTTPX 0.28.1. All 19 APPLICATION cases and 37 historical HTTPX cases passed without failures or skips. The 136 existing native publication cases also passed. The final owner-identity comparison was followed by a passing repeat of the same 19 APPLICATION cases; that repeat is not an additional 19 distinct cases.

These results qualify the source contribution and declared fixture boundaries above. They do not assert hosted CI completion, protected merge, installation, a live VALID Trial, or an uptime measurement.

## Qualified observed serving label

The publisher can populate `execution.model_served` from a complete APPLICATION-only call graph when every original owner receipt's selected and serving-model commitments match the bytes of the frozen model label. This is an observed owner-reported label, with `model_identity_verified=False`. A different observed digest records an observation conflict; it is not decoded into an invented model name. AUTO selectors do not become concrete models, and a mixed HTTPX/APPLICATION run cannot inherit the APPLICATION subset's serving label.

The serving-label addition has 27 passing APPLICATION tests, including eight cases that exercise the actual pinned native assembly and dispatch with explicit selected-input delivery fixtures. They cover exact matches, a different frozen label, AUTO selection, mixed routes, and incomplete assembly/attempt coverage. The 27 cases include the original 19; they are not additional to them. Existing effect, cleanup, coverage and validity gates are unchanged.

## Unbound transport calls

A synchronous HTTPX send or original APPLICATION create can occur inside an
admission without a matching native dispatch context. The observer now records
the existing bounded `unsupported_dispatch` error on that admission before
forwarding the original invocation. It does not invent an attempt identity or
inspect the unbound request, response, headers or credentials.

The gap belongs only to the captured original scope. The existing event-stream
lock and scope lock protect the closed/current check. A foreign dispatch context
marks the verified current admission without borrowing the foreign identity.
Closed, stale and copied old scopes cannot redirect this contribution into a
later admission. Repeated gaps retain one enum in the existing error set.

The ownership guard contains ordinary observation exceptions, and the original
transport invocation remains outside that exception handler. The original call
therefore executes once with its original arguments; its return or exception is
preserved. Matching contexts retain all existing source, client, identity and
sealing checks.

The existing publication gate consumes the gap error and withholds scalar
observations from the retained subset. Independently qualified timing and
process observations can remain available. An unbound APPLICATION call alone
does not select transport v4. Absence of a recorded gap is still not complete
coverage, including when observation itself failed.

The regression matrix uses original HTTPX/APPLICATION methods with declared
in-process I/O edges. It covers missing, foreign, absent, closed and stale
contexts; copied old scopes; observer/classification exceptions; unchanged
original outcomes; bounded deduplication; and the real publication consumer
after an unbound call followed by a qualified call. On the unchanged source,
36 new cases produced 16 expected failures and no errors or skips; both
publication cases exposed an incorrectly retained serving-model label.

The repaired source passes all 100 cases in the HTTPX and APPLICATION modules
(37 HTTPX and 63 APPLICATION, including the 36 new regression cases), with zero
failures, errors or skips. Two separately selected native publication cases also
pass: the actual SDK/pinned-worker receipt journey and the duplicate-event
rejection journey. The latter two completed in 14.626 and 14.366 seconds.

The attempted 236-case three-module run exceeded its 180-second process budget
before completion and is not a passing qualification. The 100-case run and the
two selected publication cases are completed source qualifications; the baseline
and incomplete larger run must not be added to their distinct test count.

Retained JUnit SHA-256 digests:

- Baseline: `96f9bdd4ae46b6e826c2c0403933915592e8ad5935a27873a62dcdd93bf6427f`
- Two transport modules: `3004fec05eadc1ec92142c8084c8564f614da57298c5bf177cc71f079e0c5d0a`
- Two native publication cases: `109b547405965adb59703c7596ed028e58f4da0daa1b37caad4482cea2770870`

These checks exercise in-process fixtures and the original source consumer. They
do not establish installed acceptance, complete coverage, effect settlement,
cleanup or learning efficacy.
