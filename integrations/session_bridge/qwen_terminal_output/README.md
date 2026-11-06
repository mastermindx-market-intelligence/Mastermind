# Qwen terminal response framing

Prospective repair for the existing `qwen_exec.sh` path. The installed credential
manager `bailian_keys.py` is unchanged.
There is no new dispatcher, result owner, acceptance path or lifecycle.

The existing JSONL formatter prints `command_execution` items and every assistant
message. The wrapper tees each turn into its outer stdout before its continuation
loop finishes. A real review consequently delivered 116,882 bytes, including tool
transcripts, despite a 7,040-byte final answer and an 8,000-byte request bound.
That original run remains settled and NOT_ACCEPTED; this proposal does not
reframe, retrieve or accept its historical output.

The candidate creates a credential-free response formatter inside the existing
private Qwen run directory. Its Python source is separately visible for scanning
and tests verify byte identity with the embedded wrapper helper. The projection
requires a captured thread identity, a complete turn
and an assistant message, and refuses malformed, failed or ambiguous terminal
streams before publishing any answer. Tool output cannot impersonate an assistant
response. The legacy key-manager stream invocation retains its original behavior because
that module is not modified or copied into this production candidate.

The Qwen wrapper uses that projection privately, preserves raw events for its
existing limit/diagnostic scanner, checks both provider and projection exit codes,
and publishes the final turn's response once after the existing continuation loop
settles successfully. It does not truncate an oversized answer, alter a verdict,
mark it accepted or change account selection, credentials, leases, continuation
budgets or signal cleanup. Existing process capture then attests the projected
stdout under its existing contract. This does not add historical raw-event
retention; private run files retain their existing cleanup lifetime.

## Verification

`tests/test_qwen_terminal_output.py`: 17 failures / 1 pass against the exact
installed baseline; 19 passes against the candidate (including embedded-source parity). The installed
Qwen initial-terminal, outer-account and signal suites pass all 26 checks against
the candidate wrapper in an isolated synthetic fixture. Their assertions are
unchanged; the inert CLI fixture is wrapped in the actual Codex JSONL protocol
now that the wrapper uses the real formatter rather than a stub formatter. No provider or credential
is used by those checks. Independent review and release/install status are
recorded in the existing Fabric program carrier, not inferred from this source.

## Installation and boundaries

`SOURCE.json` pins the exact installed wrapper preimage and candidate postimage,
and records the preserved key-manager hash.
Only a normally released and qualified candidate may replace that exact local
wrapper. A different preimage requires reconciliation, never overwrite. Future
immutable support bundles carry the change through normal admission; already
launched support releases, retained results and original refusals stay unchanged.
Actual new-run output behavior remains to be demonstrated after installation.
