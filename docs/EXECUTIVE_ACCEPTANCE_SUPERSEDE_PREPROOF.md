# Preserve an acceptance interrupted after canary activation but before any proof Job

The explicit `supersede_preproof_v1` maintenance branch carries an interrupted
V2, `supersede_unstarted_v1`, or `supersede_prejob_v1` acceptance that reached
`start_and_attest_services` and replaced the live secret-canary receipt with
its own envelope but failed before any proof Job (e.g. the installed release
`bcf4a2f72538682f2fbe4902f6417e59cd038678` failed its first `status.sh` call).
It never replays the failed acceptance, credits it with PASS, rebaselines
Runtime, recovers historical capacity or arms a service. Admitting this class
requires the new exact rule below; every other strict check that protects
`supersede_prejob_v1` and `supersede_unstarted_v1` remains exactly as strong.

## What this class admits

A `supersede_preproof_v1` descriptor may point at a selected release whose
sealed bundle and acceptance directory together hold exactly the receipts
left by a successful service-start and canary activation that ran no Job:

1. The eight control-owned JSON receipts `Acceptance.start_and_attest_services`
   produces in order:
   - `assignment-root-nonlistability.json`
   - `awaiting-canary-status.json` (`AWAITING_CANARY` Control status, via
     `_control_request("status", persist=...)`)
   - `failure-control-status.json` (from `_capture_failure_observability` via
     `_control_request("status")`)
   - `launchd-principals.json`
   - `nonexecutive-launchd-before.json`
   - `protected-group-membership.json`
   - `secret-canary-envelope.json`
   - `worker-broker-startup.json`
2. Exactly one `control-environment-probe-<pid>.json`, where `<pid>` is the
   live control PID (a non-zero unsigned decimal; the regex
   `r"control-environment-probe-[1-9][0-9]{0,9}\.json"` matches one and only
   one such name under the interrupted acceptance dir).
3. Optionally, the bounded `host-service-status-failure.txt` the harness writes
   when its first `status.sh` call fails; the optional name is the only other
   presence accepted.

The selected bundle still has its six sealed files plus an exact run marker
(`run-started.json`) binding the interrupted release's own descriptor, just
like `supersede_prejob_v1`. The legacy sealed empty
`prestate.sqlite3-wal`/`prestate.sqlite3-shm` pair is admitted as today. A
second probe, a `*-job-*` or `*dispatch*` or `backup-*` name,
`health-before-success.json`, `registered-worker.json`, `host-status.txt`,
`final-host-status-failure.txt`, any `leakage-*.json`, the
`acceptance-summary.json` written on PASS, or any dot-temp file refuses with
`interrupted acceptance is not a pre-proof prefix`. A missing core receipt, a
probe-less acceptance dir, or any other shape drift refuses with the same
message.

Strict checks that remain exactly as strong:
- The selected bundle's sealed `prior-secret-canary.json` must still digest
  to the selected descriptor's `prior_canary_sha256`.
- The sealed `baseline.json`, `inventory.json`, `prestate.sqlite3`,
  `before` equality, `artifacts` equality, and `schema_migrations` v5 rule
  remain exactly bound.
- Reused validators for `nonexecutive-launchd-before.json` and
  `protected-group-membership.json` (current eight-key form only;
  `historical=True` is reserved for the carry-chain walk of legacy
  six-key receipts).
- `extract` ownership/mode/nlink/ACL/S_ISREG checks for every receipt
  and the optional `.txt`; size cap 256 KiB on the optional failure
  artifact; no decode, parse, or print of its bytes. Presence of the
  optional `.txt` is decided by its directory entry, and any entry that
  is not a regular file (a symlink, dangling or not, or a FIFO) refuses
  with `interrupted acceptance receipt is unsafe` before it is opened.
- `awaiting-canary-status.json` must be the verbatim Control `status`
  response that `start_and_attest_services` persists: `ok` is `true` and
  `result.service_state` is `AWAITING_CANARY`, else
  `interrupted acceptance did not reach AWAITING_CANARY`.
- Trusted canonical `Runtime` `/var` alias handling is unchanged. The
  namespace before/after identity recheck (`interrupted acceptance
  namespace changed`) covers both directories and every receipt read,
  including the optional `.txt`, as `prejob_evidence` does.
- `recovery_permitted`, the `v1` predecessor-recovery path, and any
  V1-specific grant stay refused.

## Changed exactly-once binding (independent review required)

For every selected pre-proof link the expected canary is that run's own
envelope — bound inside the `preproof_evidence_sha256` digest and re-asserted
through `descriptor["prior_canary_sha256"]` — instead of the live receipt at
every depth of the chain. The rule is:

1. `digest(parsed envelope)` must equal `descriptor["prior_canary_sha256"]`,
   else `interrupted pre-proof canary binding drifted`.
2. When `prior_canary` is not `None` (the strict calls in `prepare` and
   `Maintenance.__init__` always pass it), `prior_canary` must equal the
   parsed envelope value, else `interrupted pre-proof canary binding drifted`.
3. The selected bundle's sealed `prior-secret-canary.json` digest must still
   equal `descriptor["prior_canary_sha256"]` (the existing binding check),
   and the `prior_canary is not None and canary != prior_canary` legacy
   comparison is replaced by rule (2) for this link.
4. In `validate_superseded_binding`, after a `supersede_preproof_v1` link
   validates and `prior_canary` is not `None`, the expected canary for every
   deeper link becomes the selected bundle's sealed prior canary: re-read
   `sealed_json(bundle_path(selected_sha)/"prior-secret-canary.json")`, require
   `digest == selected["prior_canary_sha256"]` (else
   `superseded sealed baseline drifted`), and pass that parsed value as
   `prior_canary` to the next iteration. SUPERSEDE and PREJOB inner links
   then inherit that exact canary in the walk — no free variable is
   introduced, since every selected bundle in the interrupted run was sealed
   with the same live receipt.

The rationale is the immediate host fact recorded at base: the interrupted
run replaced the live secret-canary receipt with its own envelope (the
`Acceptance._activate_live_canary` -> `install_secret_canary_receipt` path),
so the live receipt equals the envelope and every deeper link's sealed
prior canary also equals it; the per-link rule re-asserts that equality in
the same place the strict `canary` check used to do, and rule (4) keeps
deeper iteration bound to the same sealed value rather than to a value
that could drift underneath us.

This binding is **independent-review required**: any change that loosens
or side-steps rule (2) or the sealed `prior_canary_sha256` digest check,
or that re-introduces a free variable into deeper iterations of the walk,
is a regime change and must re-open this admission.

## Operator command shape

The reviewed preparation owner runs once with the actual protected successor
SHA, naming the new class through the exclusive flag:

```sh
python3 /path/to/qualified-release/ops/executive_os/acceptance_maintenance.py \
  --predecessor-sha <actual accepted ancestor SHA> \
  --successor-sha CURRENT_PROTECTED_PREPROOF_SHA \
  --root-job-id JOB-003 \
  --carry-terminal-dispatch \
  --supersede-preproof-sha <interrupted installed release SHA> \
  --superseded-descriptor-sha256 <interrupted descriptor digest>
```

Do not supply `--supersede-unstarted-sha` or `--supersede-prejob-sha` alongside
this mode (the three selection flags are mutually exclusive). The predecessor
flag is the actual accepted ancestor, not the selected interrupted release.
Retain the printed descriptor digest for that single successor operation.

Tests use isolated files and Runtime fixtures with explicit principal/service
test seams. They establish source behavior, not live installation or
execution.
