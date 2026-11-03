# Source Continuity Bounded Read Retry Implementation Plan

**Predecessor:** `2026-11-02-source-continuity-macro-1500-scale.md` (Mastermind #1972), whose residual risk names this follow-up
**Consumers:** release gate 4 for the Macro vertical carriers (macro#7870, macro#8250), currently met by a manual five-leg substitute
**Capability ceiling:** source-only until normal review and release gates

## Goal

Stop one slow or dropped read from ending a complete Macro-scale census. Both live runs at about 1,560 reads lost one read: a 20 s timeout on a saturated PR's `git/trees` read, and a failure the transport did not identify. Each ended rc=2 `REMOTE_PROBE_FAILED`.

This change repeats an idempotent GET in place after a transient failure, inside the invocation's shared call, byte and time budget. When a refusal follows a failed read, it also records which read failed and why. The census still covers every open PR, and every failure that is not transient still refuses on its first occurrence.

## Bound evidence

- Measurement run (2026-11-02, macro#7870, 903 open PRs): 1,537 calls. One `git/trees` read of macro PR 7084 timed out at 20 s, and a re-probe took 0.56 s.
- Shipped-caps run (2026-11-03 00:35Z, 908 open PRs): 1,561 calls, 465.6 s. It ended `REMOTE_PROBE_FAILED` on one read that `_stdlib_http_get` reported as a bare `_RemoteProbeError` with no cause. The next API call hit a TLS handshake timeout.
- Before this change, `_stdlib_http_get` did not catch `http.client.HTTPException`. An `IncompleteRead` or `BadStatusLine` escaped raw and was refused `PROBE_INTERNAL_ERROR`.

## Closed profile

```text
attempts per logical read:   3
backoff before attempt 2, 3: 1.0 s, 2.0 s  (module-level time.sleep)
minimum call window:         2.0 s left after the backoff, or no retry
transient (repeat in place):  timeout, connection (any other OSError below HTTP),
                              incomplete_response, protocol (other HTTPException),
                              HTTP 500, 502, 503, 504
never repeated:               401, 403 (auth and rate limit), 404, 429, every other
                              status, tls_verify, missing_etag, not_modified_body,
                              body_too_large, invalid_json, invalid_url, no_token,
                              invalid_validator, invalid_representation, unlabelled
```

Budget accounting:

- Every attempt is one `_admit_call` against `_MAX_HTTP_CALLS` (4,096) and the 900 s deadline.
- Before sleeping, `_backoff` declines the retry if the call budget is spent, or if the backoff plus a 2.0 s minimum call window would reach the deadline. That avoids a sleep followed by a refusal, and a retry whose clipped timeout is too short to succeed.
- A declined retry re-raises the failure it would have repeated, recorded with the attempts actually made. The run keeps the refusal that failure earned (`REMOTE_PROBE_FAILED` for a transient read failure), not `REMOTE_CENSUS_INCOMPLETE`, so the receipt says the remote read failed rather than that the estate was too large.
- A logical read costs at most 3 calls and at most 3 × 20 s + 3 s of wall clock.

Failure causes are attributes set by `_labelled(error, cause, transient=...)`, like the existing resource-missing marker. So an injected transport can label its own exception types. Labels outside the closed list read as `unclassified`.

## Diagnostic

stdout still carries exactly one receipt line. On a refusal with a recorded failure, stderr gets one canonical JSON line:

```json
{"attempts":3,"cause":"timeout","diagnostic":"READ_FAILED","endpoint":"repos/OWNER/REPO/pulls/7084/files?per_page=100&page=1","failed_reads":1,"recovered_reads":4,"retryable":true}
```

- `endpoint` is the request path after `https://api.github.com/`, checked against a closed character class and at most 1,024 characters. Anything else, including a foreign host, prints `unrecognized`. The token never appears, because the cause is a closed label and the endpoint carries no headers.
- The first failure in time is kept. With four parallel census workers, `failed_reads` counts every read that failed for good, and the kept failure may belong to a different worker than the exception that ended the run. Both are real failed reads. The line is advisory and is never parsed as a receipt.
- A refusal with only recovered failures, or one caused by anything other than a read (a budget exhaustion between reads, a semantic refusal), prints nothing to stderr. A successful run never prints to stderr.

## Preserved semantics

- The pure verifier `control_plane/source_continuity.py` is unchanged. Receipt, refusal and writer-gate schemas are unchanged.
- Each logical read is admitted, validated and accounted as before. A retried read is accounted once, on the attempt that succeeds. Strict ETag fences, conditional replay semantics, saturated-PR tree proofs and page-30 sentinels are unchanged.
- A lawful absence (an optional read's 404, or a recorded absence re-checked on the second observation) is an observation, not a failure. It is neither repeated nor recorded.
- A required read that returns 404 still refuses `REMOTE_PROBE_FAILED` after one attempt.
- The refusal codes keep their meaning, and a run with no retry refuses exactly as before. The one intentional change: `IncompleteRead` and other `HTTPException` failures, including a failed body read inside the 304 handler, are now classified, repeated, and refused `REMOTE_PROBE_FAILED` instead of `PROBE_INTERNAL_ERROR`.
- `invalid_url` covers the pre-I/O URL guard, `http.client.InvalidURL`, and a `URLError` whose reason is a string (such as `unknown url type`). A `URLError` with any other unrecognized reason stays a non-transient `connection` failure.
- `not_modified_body` covers a 304 with a body, whether the transport or the replay check sees it.
- The stderr diagnostic is best-effort. With `sys.stderr` missing or unwritable it is dropped, stdout still carries exactly one receipt line, and the exit code is unchanged. After a failed write, stderr's descriptor is pointed at `/dev/null`. Otherwise the bytes left in its buffer fail again at interpreter exit, and CPython exits 120 instead of 2.
- No failover, cache, cursor, persistence, auth widening or authority. Retry supersedes the predecessor's "no retry" only for idempotent GETs of the same URL, with the same token and validator.

## RED-first evidence

Against the #1972 head source (`f9bf6c5ff`), 77 of the 78 new cases and the updated census-budget auth case fail. Most fail on the missing API (`_read_cause`, `_diagnostic_endpoint`, `sleep`). A behavioral check runs a copy of the tests that tolerates the missing `sleep` attribute and sends unlabelled errors. There, every single-failure recovery case (timeout, connection, 502, two failures, conditional replay, parallel census read, writer-gate read) ends rc=2 `REMOTE_PROBE_FAILED` on the old source. Only the lawful-absence case passes on both sources, as it should.

Under the new source, all 673 `tests/test_source_continuity*.py` cases pass (662 before the review repairs below).

The new tests pin:

- recovery that leaves the receipt byte-identical, with exactly one extra transport read per recovered failure;
- exhaustion after 3 attempts with sleeps `[1.0, 2.0]`;
- a single read for every non-transient cause, auth and unlabelled exceptions included;
- the call budget (a cap of 2 refuses after 2 attempts, and a recovered failure costs exactly one call);
- the deadline (a backoff that would cross it refuses without sleeping);
- conditional replays, parallel foreign-PR reads and writer-gate reads;
- `_stdlib_http_get` classification of every transport, status and body failure;
- endpoint and cause sanitizing, and that the token stays out of stderr.

Review repairs (independent review, PASS_WITH_MINORS). A declined retry keeps its failure's refusal and diagnostic. Retries need a 2.0 s minimum call window, pinned at the boundary: 3.0 s left refuses without sleeping, 3.01 s left sleeps and recovers. `InvalidURL` and string-reason `URLError` read as `invalid_url`. The 304 handler's body read is classified. The replay check labels a 304 with a body `not_modified_body`. The stderr write cannot break the receipt. Against the pre-repair head (`8a8757ebf`), 11 of the new and updated tests fail. One of them shows that the old `print(..., file=sys.stderr)` with `sys.stderr` set to `None` writes the diagnostic to stdout, which would have produced a second stdout line. The reviewer also noted that census workers already running keep going after another worker's failure; that was accepted, because they share the call, byte and time budget.

The delta review passed with one note: a real stderr pipe with no reader still changed the exit code. The caught `BrokenPipeError` left the line in stderr's buffer, the flush at interpreter exit failed again, and the process exited 120 instead of 2. A subprocess test with a closed pipe reproduces rc 120 against `216c3d7f2`. The repair points stderr's descriptor at `/dev/null` after a failed write, never the descriptor that carries the receipt.

## Live proof

One real-path run on 2026-11-03 at 03:51Z: production transport, shipped caps, `8a8757ebf` (before the review repairs, which only change refusal paths), macro#7870 at `9eac8744`, 918 open PRs.

- First observation: complete. 1,570 calls, 270,858,424 normalized bytes, 280.46 s. Collision `OVERLAP` with 301 colliders, census complete. This is the first first observation to complete at Macro scale. No read failed, so no retry ran.
- Second observation: refused `REMOTE_PROBE_FAILED` after 17 more calls (the roster revalidation). No read failed and stderr was empty, so the refusal was semantic.
- Totals: 1,587 calls, 293,012,191 bytes, 292.57 s.

Cause, inferred from the call count and a creation timestamp rather than instrumented: macro#10641 was opened at 03:56:16Z, during the second roster read. The roster pages newest-first by offset, so the new PR pushed one row onto the next page, the row appeared twice, and the census's duplicate check refused. The retry cannot help here, because no read failed. See the residual risk below.

## Exact source scope

1. `scripts/source_continuity.py`: the retry profile, cause labels, the `_BoundedHTTPGet._read` loop and its use by strict, collision, replay and absence reads, `_stdlib_http_get` labelling, and the stderr diagnostic in `_emit`
2. `tests/test_source_continuity_read_retry.py` (new)
3. `tests/test_source_continuity_census_budget.py` (stderr contract in `run_cli`)
4. this plan

## Residual risk

- A retry spends shared token quota. At Macro scale a few retried reads cost a few calls out of about 1,560. A run with widespread 5xx failures can spend up to three times its reads before refusing, still bounded by the 4,096-call budget.
- Three attempts with 3 s of total backoff cover the observed single-read stalls. They do not ride out a GitHub incident that lasts minutes; that still refuses fail-closed, now naming the read.
- The roster is read newest-first with offset paging. A PR opened while a roster is being read shifts every later row by one page, and the duplicate it produces refuses `REMOTE_PROBE_FAILED`. Macro opens PRs often enough that this ended the live proof's second observation. That needs its own change: page oldest-first (`sort=created&direction=asc`) so that new PRs append after the rows already read, or re-read the roster once on a duplicate. It is out of scope here.
- A semantic refusal writes no diagnostic, so the cause above had to be inferred.
- 403 secondary rate limits stay `AUTH_UNAVAILABLE` and are never repeated, as before.

A merge grants no runtime, deployment, ranking, serving or trading authority.
