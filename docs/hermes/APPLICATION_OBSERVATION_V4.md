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
