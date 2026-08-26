# Executive Capacity CF2-H0 host preparation implementation plan

> **Carrier:** `sol/executive-capacity-cf2h0-host-preparation-20260825`
> **Base:** `205640da8e4e21c02960d4f409cd1d24bb485ce5`
> **Stop state:** reviewed, merged, secret-free host-preparation tooling; services stopped; no credentials or provider calls

## Observable mission

Turn the P0 result `NO_SAFE_CF1_ACQUISITION_PATH` into one installable, fail-closed host
foundation. The installed Mac must have the exact accepted Macro CF1 Git source, an isolated
root-owned Python/PyYAML runtime, one closed source configuration, and the already-reviewed three
Personal Pro principals and private empty homes. This wave does not authenticate, observe a
provider, start a service, route a job, or implement CF2-I.

## Existing surfaces to extend

- Reuse `ops/executive_os/bootstrap-host.sh` and `provider_worker_slots.py` for service identities,
  UID/GID allocation, exact group membership, home ownership and mode.
- Reuse the installed PSF Python 3.12.10 attestation from
  `provision-python-runtime.sh`; do not replace or duplicate the base runtime.
- Install Macro CF1 as a grounded partial Git checkout that retains `.git` and contains the strict
  wrapper plus every material source named by accepted CF1.
- Add only a source/runtime/config preparation surface. Do not add a queue, daemon, credential
  store, provider normalizer, worker lifecycle or routing plane.

## Frozen identities

- Macro repository: `https://github.com/mastermindx-market-intelligence/macro.git`
- Macro commit: `dcdd939c45b23abce5ba04f95e330ac914a3904b`
- Entry point: `scripts/build_provider_capacity.py`
- Base Python: `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`
- PyYAML: `6.0.3`, macOS 11 arm64 CPython 3.12 wheel SHA-256
  `fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0`
- Personal Pro realms: exactly `codex-pro-01`, `codex-pro-02`, `codex-pro-03`, in existing catalog
  order, owned only by `_mastermind_codex_01/02/03`.

## TDD sequence

### 1. Closed contract and deterministic receipts

Create `tests/test_executive_capacity_source_contract.py` first. Tests must require:

- exact fixed producer/runtime/realm constants;
- closed config and receipt schemas with canonical SHA-256 digests;
- exact three-home order derived from the existing slot catalog;
- refusal on unknown fields, wrong commit, wrong wheel, reordered/aliased homes, a false material
  match bit, or any credential-shaped field;
- deterministic public rendering that contains no account, browser, token or credential value.

Implement `ops/executive_os/capacity_source_contract.py` only after those tests fail.

### 2. Root preparation shell and non-root tests

Create `tests/test_executive_capacity_host_preparation.py` first. Static and sandboxed tests must
require:

- root and Darwin refusal before mutation;
- exact Mastermind carrier identity and clean source verification;
- isolated Git environment, fixed HTTPS origin, detached exact commit, sparse material allowlist,
  no local checkout copy and retained `.git`;
- exact PSF runtime receipt verification before the venv is created;
- download/copy-to-stage followed by exact wheel hash before installation;
- venv execution with `-I -B`, user site disabled, and PyYAML origin/RECORD contained in the
  root-owned runtime;
- staging plus adjacent atomic moves, failure archival and restoration of prior accepted config
  and receipt without recursive deletion;
- bootstrap invocation only after source/runtime candidates pass;
- exact Pro-group negative membership and negative-traversal probes;
- no auth-file open/copy/hash, provider command, launchctl load/start/kickstart, service-control,
  database mutation or CF2-I operation;
- verify-only mode that performs no mutation;
- idempotent success when the exact installed objects already match and refusal on drift.

Implement `ops/executive_os/prepare-capacity-host.sh` after the red tests. The script may download
only the fixed public Macro Git objects and fixed PyYAML wheel. It must preserve ambiguous or failed
objects in the fixed archive root and issue no acceptance receipt until every final invariant passes.

### 3. Runbook and acceptance boundary

Update `ops/executive_os/HOST_PREREQUISITES.md` with a new CF2-H0 stage that:

1. performs all review, CI and exact-head checks before privilege;
2. runs the merged exact `origin/master` script with an explicit expected Mastermind SHA;
3. runs `--verify-only` immediately after installation;
4. records only sanitized digests, ownership/mode and service-stopped state;
5. reruns CF2-P0 before releasing CF2-I.

The runbook must state that OAuth/device ceremonies, provider calls, services, routing and worker
fan-out remain held.

## Verification

Run focused new tests, the existing provider-slot/bootstrap/runtime/launchd suites, shell syntax,
Python compile checks, and the full repository test suite. Obtain an independent adversarial review
of the exact head. Merge only with all exact-head CI and CodeQL checks green. Privileged host
preparation occurs only from the exact merged protected commit, followed by `--verify-only` and a
fresh P0 census.
