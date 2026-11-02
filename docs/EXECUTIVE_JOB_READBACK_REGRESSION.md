# Executive installed Job-readback regression gate: JOB-002 and JOB-025

**Scope:** source test coverage plus a **read-only, live-only post-release gate** for the two installed Executive Job reads observed to fail with `backend_unavailable` on October 22, 2026. This document does **not** authorize a deployment, release staging, credentials, runtime activation, retry, Job creation or direct database access.

## Source tests (hosted CI)

The original source PR #1726 tests under `tests/test_executive_job_terminal_result_read.py` exercise real temporary Runtime→MCP→App readback for historical LOST/FAILED/RATE_LIMITED requeues, subsequent reclaim and completion, lease fencing, duplicated bounded projections and unsafe forged documents.

The October 22 independent review required these additional checks:
- reject any `CANCELLED` predecessor in a `QUEUED` Job's entire history;
- accept the Runtime's active operator-harness `ohf_lease_expired_fenced` result **only** for a still-pointer-bound active Attempt with the matching Job status; reject unbound, sealed-worker or wrong-reason cases;
- reject `COMPLETED` Job or Attempt records with a missing persisted result;
- require real UTC timestamp syntax and chronological Job creation/update and Attempt start/finish order (while allowing the Runtime's empty unset Attempt timestamp fields).

These are *source contract tests*, not tests of the installed release. They neither prove that `JOB-002` or `JOB-025` have any particular underlying Attempt topology nor authorize relabeling an installed `backend_unavailable` error as a successful read. Longer-range future lease timestamp plausibility remains a separate producer-contract concern.

## Live-only post-install acceptance (two exact identities)

1. First establish an approved and installed **exact protected release SHA** through the existing source-review/release authority, with no substitution of an unmerged PR head. Keep the CEO disarmed and use only the already authorized read-only Executive V3 tool.
2. On that **installed** runtime, call `executive_job` for `{"job_id":"JOB-002"}` and separately for `{"job_id":"JOB-025"}`. Preserve each returned **decoded `mastermind.executive_mcp_result.v1` JSON envelope** in a private directory as `JOB-002.json` and `JOB-025.json`. A plugin wrapper containing a quoted JSON `text` property must be decoded *once* first. A failed response, including `backend_unavailable`, must be captured as a failed response rather than repaired or fabricated.
3. Keep that directory **outside** the repository, protected from other users; never commit raw Job content, access tokens, provider secrets, personal messages or production state. Then run from the original PR checkout against the captured envelopes:

```sh
MMX_EXECUTIVE_LIVE_READBACK_DIR=/private/secured/executive-readback   /opt/homebrew/bin/python3.12 -m pytest -q   tests/test_executive_job_terminal_result_read.py   -k installed_job_readback_regression_when_captured
```

Both parametrized cases must **PASS**: `ok is True`, `mode == readonly`, `tool == executive_job`, matching exact `job_id` and full App contract validation. Any error or invalid document must FAIL. With no captures, the tests intentionally **SKIP**, never silently pass. Independent source tests also prove the gate rejects a simulated `backend_unavailable` envelope.

4. Preserve only redacted validation summaries, actual installed source SHA, and time-bounded read-only proof in MAS-158 and the original source PR. **Source CI passing is not live acceptance.** The native supervised CEO→Worker→original-parent H1–H8 acceptance remains separately gated, including company-admin credential qualification.

**Reference identities:** Mastermind [PR #1726](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1726), Linear [MAS-158](https://linear.app/mastermindx/issue/MAS-158/autonomy-v1-final-governed-end-to-end-integration-acceptance).
