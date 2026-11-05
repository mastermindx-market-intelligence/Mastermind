# Session reliability: preserve typed Executive MCP failures

## Existing programme and exact scope

This is a source implementation under Mastermind #917 / delivery task tree #1957.
Operation: `session-reliability-result-contract-20261102-web-001`.
The containing Git commit identifies this candidate. Pickup base:
`ab93f3ede66486e82e995c88a86e662677973732`.

The later protected `7f1242bfa90f0f0448e66e400e054bd5aa5fa15a`
adds #1924 review routing. Its changed paths do not intersect this candidate's
source or tests. The new review-routing guide was consumed. Existing #1362 and
#1621 touch the same server file in other regions; their branches and effects
are preserved. The active #1957 writer and Executive #1893 runtime recovery
are not transferred by this child.

## Reproduced defects and implementation

A real attended Executive read returned canonical `backend_unavailable` in text
while the connector's structured wrapper reported `INVALID_ARGUMENT`.
The server omitted the canonical structured failure object. The Personal Read
builder also returned a bare content list, so the SDK labelled failed reads
`isError=false`.

The Personal Read and shared Business/Web CEO profile now retain the already
sanitized canonical failure object in MCP `structuredContent`. Personal Read
sets `isError` from the actual outcome. Existing text, authentication, OAuth
challenge metadata, source classification and original request identity remain
authoritative. Successful responses retain their previous text-only wire shape.

The existing shared-profile byte guard still measures the final serialized MCP
result. A regression proves duplicated error data that crosses that budget falls
back to the same original request's `effect_unknown`, retaining reconciliation
instructions and forbidding inferred resubmission.

## Actual validation

- RED on the pickup source: 12 targeted contract failures (four Personal Read
  failure-flag cases and eight missing structured reconciliation outcomes).
- GREEN: 51 tests across structured errors, Personal Read and request reconciliation.
- Compatibility: 117 tests across App composition, recovery guidance, Web CEO
  sessions and release tools. **168 tests passed in total.**
- New tests exercise authenticated MCP HTTP plus actual temporary Unix sockets:
  missing listener, live backend refusal, dropped response and invalid input.
  They assert zero/one backend attempts, redacted details, matching text/structured
  data, preserved uncertain-effect identity, output budget and unchanged success.
- Python 3.12; MCP 1.28.1, pytest 9.1.1, httpx 0.28.1 and cryptography 50.0.1.
  Dependencies came from the protected Executive runtime hash lock in an isolated
  workspace environment. No production service or provider credential was used.
- `git diff --check` passed.

## Remaining acceptance and original effects

Independent review, required CI, protected merge, exact-source installation and
an attended native-client read remain separate gates. This source result does
not restore the intentionally disabled Executive Control service, prove that
ChatGPT's wrapper consumes the field, or prove fleet-wide session improvement.
Use the incumbent #1893 release owner for runtime composition and actual read proof.

Original paid #1967 review `reliability-1967-independent-source-review-20261102-001`,
root `session-reliability-integration-20261102-web-001`, is terminal rc75,
root verified, unaccepted. Its retained reason is
`host_temperature_at_or_above_limit`, response SHA256
`75c266163aab663ad1e8118dd46f887c79358c90d2f4f0392d255fc70d68f373`.
Retry is false; that review was not repeated or moved. This separate, small
critical-path source repair is not a substitute attempt to obtain that denied review.
