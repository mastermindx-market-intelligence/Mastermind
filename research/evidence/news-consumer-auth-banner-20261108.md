# News consumer: exact revoked-token banner classification

## Production observation

The News programme's released Mastermind consumer is commit `eaf849bf808b3f1fdaaa81ec9e7e4dc154da9233` ([deployment receipt](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2280#issuecomment-6719783950)). Its live service PID was `2799428`; the installed bot, portfolio lens and bridge blobs were separately verified. One ordinary authenticated HTTP request reached the deployed `/chat` service on 2026-11-08, from 10:12:38.117542 to 10:12:44.075317 UTC.

The proof identity is `mm-news-eaf849-20261108-001 / nvda-proof-001`, request SHA-256 `6aa11b9d898105df8d880020ae301572488bfa39a7d5fb1c1f255d2e7e98299f`. The request asked for exactly one `mcp__bot__get_intelligence(NVDA)` and one `mcp__bot__get_decision_matrix(NVDA, name)`, with no other actions.

The service returned HTTP 200, a public `advisor_chat_unavailable` event and a terminal SDK session `b2952c62-691c-4234-b6a5-45291c4633a0`, cost zero and an empty tool list. Its result text was:

> Failed to authenticate. API Error: 401 OAuth access token has been revoked.

This is a completed failed request, **zero observed bot tools and no News consumer acceptance**. The sanitized machine receipt is [news-consumer-attempt-20261108.json](news-consumer-attempt-20261108.json). An earlier local script failed at Python parsing/execution setup before any HTTP request; it is not a second provider attempt. The corrected request consumed the complete response iterator.

## Exact source diagnosis

This repair starts from current protected master `5c3d3885234358aefb97ecdbc59be0864df14f8b`. Its `brain/key_rotor.py` blob `61b3c5ba331dec783c7e97c56d12e16c068338a1` is identical to the deployed classifier.

The existing handler deliberately distinguishes loose exception/error matching from strict response-text matching. Generic `401` and `revoked` classify only on the error path. The observed complete banner was missing from the strict list, so a generic SDK exception plus this result text can finish without an auth classification. The focused regression demonstrates that exact false-negative. It does not establish the private exception from the live request or identify its selected key.

The current bridge contains additional application-selection fences compared with the deployed source. Those fences are preserved. The post-stream classification and bookkeeping section is byte-identical between the deployed and test source; this PR does not edit the bridge.

The product change adds only the distinctive complete lowercased banner to the existing strict list. Generic 401/revocation language remains excluded from response-text matching. No routing, authentication, admission, credential, cooldown duration, logging, retry or provider-selection mechanism is replaced.

## Focused verification

Run in a source-pinned sparse checkout:

```sh
python -m pytest -q --noconftest -c /dev/null \
  tests/test_key_rotor.py::TestClassifyFailure \
  tests/test_key_rotor.py::TestClassifySourceStrictness \
  tests/test_key_rotor.py::TestChatStreamAuthBanner
```

Six new cases cover the exact banner and case-insensitive matching, plus the actual `chat_stream` receiving assistant-block or final-result text. An ordinary answer mentioning 401 and revocation remains a negative control. The stream fixtures use the real handler and classifier with inert SDK, MCP and log sinks. They assert one selected fixture key, one SDK invocation, one auth-cooling call only for the complete banner, no second candidate or subprocess replay, public exception redaction, terminal session metadata and the existing logging call.

Before the product change: **4 failed / 36 passed**. Red log SHA-256: `828e630640353ed4d6368d2f1fa41e26447adcf4d7bf4381d4a8d57b1b1a1550`.

After the change: **40 passed**, no skips. The final run also injected inherited Fabric selector values into the parent test process; each SDK fixture explicitly isolated its local selector inputs without altering production fences. Green log SHA-256: `c31d969a7c1cf00bc287f5bba1ff0d22db462b6b6fa4b05e8792c989b4e312b9`.

The regressions belong to the already existing `tests/test_key_rotor.py` module. The separately attested 12-case advisor suite and CI budgets remain unchanged. The full native CI and normal protected release controls are still required.

## Unresolved operational boundary

A read-only diagnostic at 10:17:28 UTC found no matching response-log metadata or cooling row. At 10:24:05, both response-log disable flags and the root override were absent, but the expected daily directory did not exist. The response logger is asynchronous and best-effort; its absence does not distinguish failed classification, a missing key binding or persistence failure.

The failed key identity remains unproven. A later candidate snapshot lists provisioned non-cooling slots, which is not credential-health evidence. No slot was retrospectively cooled, forced, renewed or selected by this investigation.

Recognizing the banner does not restore the revoked grant. Credential recovery belongs to the legitimate credential-owner flow. The original SDK turn is not idempotent merely because it has a turn ID. No new live inference, credential operation, production deployment or denial-bypassing retry is authorized or claimed by this source proof. Future consumer acceptance still needs a legitimate authenticated request whose exact two tool results are retained.
