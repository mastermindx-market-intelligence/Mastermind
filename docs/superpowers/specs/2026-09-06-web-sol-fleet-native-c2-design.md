# Web-Sol census: native machine access and fleet display

Status: `SPEC_ONLY / REVIEW_REQUIRED / PRODUCTION_INERT`. Operation: `web-sol-fleet-wire-f0-20260906-sol-001`. Parent: `WS:CHAIRMAN-CONTROL-ROOM` / MAS-198 / #501. Protected architecture read: `4fe4d6bc93d9543f77320f68342a10c5af4d4f49`; same-SHA Skillpack 1.0.1, bootstrap 1. This proposal does not admit implementation or installation.

## 1. Outcome and capability ruler

Chris should open the existing Control Room and see which enrolled browser environments are observable, how many ChatGPT tabs they contain, which show a generation cue, their uncertainty/freshness, and eventually qualified visible model/effort. A machine consumer should receive the same closed facts without reading transcripts. Neither should confuse a tab with a job, a profile with an account, or a model picker with the model that served an earlier turn.

The value is trustworthy coordination of the existing reasoning fleet without session hunting, hidden missing coverage, or duplicated authority. Completion is a visible multi-profile product using real installed adapters, plus the same machine projection and explicit degraded states—not another codec, store, schema, or architecture document.

## 2. Recovered estate and no-rebuild boundary

The reviewed #502 collector already supports up to 128 retained normal ChatGPT tab rows, sleeping/unreachable states, duplicate coordinates, and unknown model fields. Its popup is a useful profile-local consumer. #503 repaired coherent content observations. Neither establishes native census or installed fleet proof.

The native bridge already supplies one wrapper-fixed, profile-derived socket; a two-challenge/version/capability handshake; one nonblocking action gate; bounded framed JSON; strict request/receipt correlation; and late/invalid-channel refusal. Reuse those owners. `surface_bindings` supplies navigation coordinates, not runtime authority or account entitlement. Executive OS, RuntimeBinding, Macro Provider Control, and Agent OS retain their separate facts.

#502 release maintenance and #509 complete-bundle repair are occupied existing operations. C2 waits for their accepted/protected descendants or an explicitly reviewed dependency stack; it never edits their active branches. #340 owns installed proof/rollback, #359 owns disposable resources, #480/#473 own provider-visible model semantics, #364 owns usage policy, and #355 owns ChatGPT runtime readiness.

## 3. Empirical constraints

The companion executed probe finds a 128-row ordinary snapshot of 72,049 bytes versus the native codec's 65,536-byte guard. All rows survive a 31,105-byte columnar experiment with exact round trip through the real codec. The mixed sleeping fixture still exceeds the raw guard. Results are synthetic fixtures, not a worst-case bound or browser execution.

The v1 request validator refuses CENSUS. A generic JSON frame is not an admitted operation. The collector's 5,000 ms sweep also equals the five-second whole-exchange native/client budget: a full sweep has no handshake/framing allowance. This is static budget composition, not measured provider latency.

## 4. Selected architecture and alternatives

Select a separately versioned, read-only CENSUS contract over the existing socket/native port, a compact lossless single frame, and the existing Control Room as final consumer. Reject raw forwarding because the existing guard demonstrably refuses supported cardinality. Reject increasing every frame limit, lossy truncation, chunk/reassembly state, a WebSocket/HTTP side bridge, browser debugger service, new session registry, or persistent event collector.

Release C2 is one independently useful native-to-machine vertical: a validated existing binding selects one profile, the installed extension performs a bounded census, and a command-line consumer prints its complete observation. Release C3 adds the existing Control Room's multi-profile gather/projection/display. The total product is not complete at C2, but C2 is useful without C3 and contains a real producer and consumer.

## 5. C2 contract proposed for review

Keep `mastermind.web_sol_surface_action.v1`, INSPECT, FOREGROUND, and their effect/receipt semantics unchanged. Introduce `mastermind.web_sol_census_request.v1` and `mastermind.web_sol_census_receipt.v1`; no arbitrary action, script, selector, URL, account, profile path, or socket override is accepted. Proposed package generation is 0.2.0 with transport protocol major 1 and a revised fixed capability document/digest. All generated config, native/client/extension versions and bundle assets must agree. Do not retrofit an unadvertised action into an old 0.1.0 installation.

The census request's exact fields are `schema`, `adapter_instance_id`, `operation_key`, `nonce`, `issued_at`, and `expires_at`. Existing managed-binding validation derives the expected instance and socket. A census is profile-scoped, not a request to elect one conversation. A connection with a mismatched generation refuses before the browser request; unknown capability is not permission to try another transport.

The receipt's exact fields are `schema`, `adapter_instance_id`, `operation_key`, `nonce`, `status`, and `snapshot`. Repeat the exact request identity. `status` is one of `COLLECTED`, `COLLECTOR_UNAVAILABLE`, `READ_DEADLINE_EXCEEDED`, `RESULT_TOO_LARGE`, or `INVALID_OBSERVATION`. Non-collected receipts carry `snapshot=null`; they never encode a zero-tab success. Transport failure is represented separately by the client, not forged as a browser receipt.

For COLLECTED, snapshot is the version-frozen header plus a fixed-order 19-column row table equivalent to the current local census. Production does not accept caller-defined columns. A deterministic decoder reconstructs the local row shape exactly. Reject unknown/missing fields, duplicate JSON keys, nonfinite numbers, invalid enum/types, oversized strings, invalid fingerprints/timestamps, inconsistent counts, and more than 128 retained rows. Prove the entire enveloped receipt is at most 60 KiB under declared worst-case values; the native 64 KiB guard is unchanged. A compact result that cannot satisfy that bound returns RESULT_TOO_LARGE rather than silently dropping rows.

The current source's null model/effort fields and UNVERIFIED document binding are preserved. Do not use this schema to invent a Chrome documentId or provider execution attestation. The raw-source Git commit, raw profile identity, titles, URLs, transcript text, DOM, prompts, responses, cookies, storage, and free-form exceptions remain outside public receipts. Artifact/code provenance belongs to trusted installed-proof records; advertised package/digest or matching caller hashes alone are not authenticated source.

## 6. Admission, deadlines, and service-worker lifecycle

Use the existing native action gate for one active native exchange per profile. No waiting work queue, automatic retry, persistent scan cache, or extra receiver thread is introduced. Do not map a generic refused/closed connection to a proven BUSY cause when the current transport does not expose that cause.

Proposed C2 read budget is ten seconds measured from connection start, not ten seconds renewed after handshake. Keep the existing five-second bound for handshake/request acquisition and all legacy operations. After a validated CENSUS discriminator, the native side uses the same start point with a fixed ten-second outer deadline; the client uses that same total budget. Browser collection retains its five-second budget. Tests must demonstrate the complete path, boundary expiration, and that no stage resets its deadline. Ten seconds is a proposed finite allocation, not a performance promise; it is accepted only after local/installed evidence, with timeout reported as unknown rather than silently enlarged.

A timeout or service-worker restart must not make a late reply usable by a later nonce or boot generation. Preserve existing identity-mismatch/channel-refusal semantics and no blind retry. A hard process interruption loses transient observations; it does not reconstruct current state from prior JSON. A request starts a new finite observation only under current admission.

Moving collection into the service worker makes its probe budget profile-wide. The existing popup and the native request must share that one collection admission path; otherwise two JS worlds could each admit eight unresolved reads. Preserve the existing popup UI and snapshot shape, but route its refresh through the fixed read-only broker. Do not inject scripts into or wake frozen/discarded tabs. Hold slots until underlying reads settle; elapsed time alone does not cancel Chrome promises.

The popup broker admits only the exact extension-owned census page, not an arbitrary content-script/page message sharing the extension ID. Validate the fixed message schema and trusted sender context before performing a census; reject a sender tab, foreign extension page, subframe, or unconfigured adapter. Native requests stay on the handshaken native port. Keep refresh-generation fencing in the UI so a prior response cannot overwrite a newer manual refresh.

## 7. C3 fleet projection and existing Control Room

The expected set is derived from the existing validated navigation-binding document and deduplicated by the existing adapter-instance function. It is explicitly an enrolled-profile coverage set, not all accounts or all provider sessions. Do not read arbitrary Chrome profiles, guess socket directories, select by title/recency, or create bindings to make coverage look complete. Missing or invalid expected-set input means coverage unknown.

Within a finite request, cap eight expected profiles, two concurrent native reads, and thirty seconds total. Retain not-started, failed, unsupported, and unavailable profiles as unknown. More expected profiles are explicitly omitted from this view rather than inferred idle. The caps are conservative proposal constants to be validated under host load; no timer or persistent queue keeps work alive after the request ends.

Group tab duplicates only by `(adapter_instance_id, conversation_fingerprint)`. Equal conversation coordinates in different profiles do not establish the same account. Report observed tab count and observed generation-cue count separately from unique scoped coordinates. Withheld global totals remain null when expected coverage is incomplete. A complete empty profile legitimately contributes zero; a missing profile does not.

The Control Room uses its existing server composition/cache-generation owner, browser-origin checks, and rendering conventions. Add a separately timestamped observation component, not a separate service or state store. Do not let the slow Agent OS/git composition refresh reset old browser observations to a new timestamp. Do not infer present liveness from wall-clock subtraction across suspension or clock regression. Reuse the existing qualified freshness path where it actually applies; otherwise label the values only as an as-of observation and withdraw current badges until a new bounded read. No unqualified browser clock or source-reported timestamp becomes a liveness oracle.

The UI shows expected/observed/unknown profiles, tabs, duplicate-coordinate indicators, observed generation cues, sleeping/unavailable reasons, observation window, and unverified model/effort. Empty, all-unavailable, partial, stale, and changed-inventory states receive their own copy. Provide manual read/refresh first. Event-driven updates are a later bounded change through the same owner after overhead and background-tab behavior are proven; no continuous polling loop is smuggled into C2/C3.

## 8. Model/effort remains a distinct evidence question

#480 must qualify the visible selected control and its per-chat/next-turn scope on approved disposable provider resources. Observing a current picker does not identify an already-running or historical turn. Retain separate selected configuration, supported submitted-turn evidence, and supported provider-reported result concepts. Unavailable evidence stays null with a typed reason. Network interception, model self-description, response quality, elapsed time, or a plan entitlement cannot fill the gap.

## 9. Acceptance and release sequence

C2 starts only with an accepted source contract, disjoint/exact current paths, and explicit source assignment. RED tests first; then one native request, real collector, compact return, real client, and command-line output using synthetic tabs and actual native pipes/private scratch socket in an isolated integration fixture. Test two profile-local hosts, duplicate coordinates, frozen/discarded/missing-script tabs, malformed frames, wrong nonce/instance/generation, deadline/restart/late replies, byte limit, popup/native concurrency, and legacy regression. Fixture transports are not installed Chrome proof.

Obtain independent exact-head source review and required latest-base checks. C2 remains BUILT_NOT_PROVEN until #340 or its explicitly authorized continuation installs the exact reviewed generation into the eligible disposable profiles and proves native round trip, faults, and rollback. C3 then proves the existing Control Room's real two-profile user journey, including one unavailable profile; browser screenshots and machine output must agree. This does not prove #480 model extraction, quota, Executive execution, or unattended hierarchy.

## 10. Stop and continuation

Stop for source-owner collision, unsupported/moved dependency, protocol ambiguity, required permission widening, unexpected private data, unknown prior effect, missing trusted installed-generation evidence, or impossible time/size bounds. Return the concrete finding to the existing Sol owner on the exact carrier. Never reset another worktree, build a second transport, silently raise guards, elect an account/session, restart a provider turn, or promote a fixture to production.

The full implementation instructions are in `docs/superpowers/plans/2026-09-06-web-sol-fleet-native-c2.md`. This six-file research PR changes no runtime behavior. Its acceptance establishes a bounded next source plan only.
