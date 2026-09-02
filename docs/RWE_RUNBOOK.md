# RWE-P0 Runbook: hash-locked test-gate environment

Pilot scope only: this covers **the repository test-gate environment** --
the `pytest` gate that `.github/workflows/ci.yml` runs on hosted CI, and
that worker Macs run locally. It does not touch, replace, or wrap the
Executive host install, provider accounts, or any deployment/runtime path.
Program reference: `research/REPRODUCIBLE_WORKER_ENVIRONMENTS_MASTERPLAN_V1.md`
(macro repo) §5-6.

## Adoption scope (read this first)

- **In scope:** a fresh, disposable venv for running `scripts/ci_pytest.py`
  (or a bounded `pytest` subset), built from a hash-pinned lock.
- **Out of scope / unchanged:** `.github/workflows/ci.yml`'s own
  `pip install -e ".[dev]"` step is untouched -- this is a **shadow**
  capability, not a replacement. There is no lifecycle, provider-account, or
  secrets ownership here (charter hard boundary). Adopting this more broadly
  (e.g. making it authoritative for CI) is a separate, later decision.

## Prerequisites

- A platform lock under `requirements/` for your OS/arch (currently macOS
  arm64 and Linux x86_64; see `requirements/README.md`).
- The interpreter it expects: CPython 3.12 exactly (`/opt/homebrew/bin/python3.12`
  on macOS by default, `python3.12` resolved on `PATH` on Linux). Anything
  else is refused, not silently substituted.
- For the **full** repository gate (not a bounded subset): the vendored
  Macro engine/lib surface at `vendor/macro_src`, populated the same way
  `.github/workflows/ci.yml` does it:

  ```
  git clone --no-checkout https://github.com/mastermindx-market-intelligence/macro.git vendor/macro_src
  cd vendor/macro_src
  git sparse-checkout init --cone
  git sparse-checkout set engine lib
  git checkout <ref pinned in .github/workflows/ci.yml>
  cd -
  ```

  `python scripts/rwe_env.py gate --env DIR` (no `--subset`) prints this
  exact command and refuses if `vendor/macro_src` is absent -- it does not
  auto-clone. Pass `--subset tests/some_test.py` to run a bounded,
  vendor-independent probe instead (see D0 bakeoff report: several suites --
  e.g. `tests/test_executive_service.py` -- never touch `engine`/`lib` and
  are a valid equivalence check on their own).

## Realize a fresh environment

```
python scripts/rwe_env.py realize --dest /path/to/venv
```

This picks the lock for your platform (override with `--lock PATH`),
refuses if the platform has no lock yet or the resolved interpreter is not
CPython 3.12, creates a brand-new venv at `--dest` (refuses if it already
exists unless you pass `--force`), installs
`--require-hashes --only-binary=:all: -r <lock>` followed by
`pip install -e . --no-deps`, runs `pip check`, and writes
`<dest>/rwe_receipt.json`.

Override the interpreter explicitly with `--python /path/to/python3.12` if
your platform's default location differs (e.g. a different Homebrew prefix).

## Run the gate

```
python scripts/rwe_env.py gate --env /path/to/venv
```

Runs the full discovery-first `scripts/ci_pytest.py` gate using the
realized environment's interpreter (refuses first if `vendor/macro_src` is
absent -- see Prerequisites). Or run a bounded subset:

```
python scripts/rwe_env.py gate --env /path/to/venv --subset tests/test_executive_service.py
```

Either way, the outcome (command, exit code, discovered/collected count,
wall time) is appended to `<dest>/rwe_receipt.json` under `proof.gate`. The
command's own exit code mirrors the underlying pytest/gate exit code, so it
composes normally in shell scripts and CI steps.

## Re-emit a receipt

```
python scripts/rwe_env.py receipt --env /path/to/venv
```

Recomputes the platform/package/proof facts for an already-realized
environment and rewrites its receipt (carrying forward any prior `gate`
result). Useful after manually poking at a venv, or just to get a fresh
`pip check`.

## What the receipt means

`<dest>/rwe_receipt.json` is schema `mastermind.worker_environment/v1`:

- `environment_id` -- a short deterministic id derived from the lock's
  content digest and the platform triple. Two realizations from the same
  lock on the same platform always produce the same id; a lock edit (a
  version bump, a new hash) changes it.
- `definition` -- `kind: "pip-hash-lock"`, the source `pyproject.toml`
  digest, the lock's repo-relative path, and its digest.
- `platform` -- OS, architecture, interpreter implementation/version, and a
  **class** for the interpreter's origin (`homebrew` / `framework` /
  `toolcache` / `other`) -- never the raw filesystem path.
- `packages_installed` -- a count and a digest of the sorted `pip freeze`
  output. Never the raw package list, and never any path an editable
  install might otherwise print.
- `vendored_inputs` -- the pinned macro `ref` (read live from
  `.github/workflows/ci.yml`), the repo-relative destination, and whether it
  was actually present when the receipt was built.
- `proof` -- `pip_check` (`"ok"` or the error text) and, once `gate` has
  run, `gate: {command, exit, discovered, seconds}`.
- `degraded` -- notes when something ran in a reduced mode, e.g.
  `full_gate_unavailable:vendor_absent` when a `--subset` gate ran without
  the vendored input present.

The receipt never contains secrets, environment-variable dumps, raw host
names, raw user/home paths, or provider identity -- only content digests and
path *classes*. `DIR` (wherever you chose to realize the venv) is recorded
as the fixed placeholder `<env>` in any command string, never verbatim.

## Rollback

There is nothing to roll back at the repository level -- locks are
additive, versioned files, and realized environments are disposable. To
undo a realization: `rm -rf /path/to/venv`. To stop using a lock: simply
stop invoking `rwe_env.py` against it; nothing else in the repository reads
these files.
