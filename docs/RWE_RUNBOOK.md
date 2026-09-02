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

This picks the lock for your platform (override with `--lock PATH` --
refused if that path resolves outside the repository root, checked before
any venv work), refuses if the platform has no lock yet, if the lock is
**stale relative to `pyproject.toml`** (its `# pyproject.toml sha256:`
header no longer matches the live file -- warn-only, not refused, for a
hand-built lock carrying no such header), or if the resolved interpreter is
not CPython 3.12. It then creates a brand-new venv at `--dest` (refuses if
it already exists unless you pass `--force`), installs
`--require-hashes --only-binary=:all: -r <lock>`, installs a **pinned build
backend** (`setuptools`/`wheel` at the exact versions in
`scripts/rwe_env.py::PINNED_BUILD_BACKEND`), then
`pip install -e . --no-deps --no-build-isolation` (so the editable install
uses exactly that pinned backend, not one pip would otherwise resolve from
PyPI at install time), runs `pip check`, and writes
`<dest>/rwe_receipt.json`.

Override the interpreter explicitly with `--python /path/to/python3.12` if
your platform's default location differs (e.g. a different Homebrew prefix).

## Run the gate

```
python scripts/rwe_env.py gate --env /path/to/venv
```

Refuses first (before anything else, including any subprocess call) if the
environment's interpreter is no longer CPython 3.12, or if a prior receipt
exists and the lock file it recorded has since changed content on disk
(re-realize instead of trusting a venv against a lock that moved under it).
Then runs the full discovery-first `scripts/ci_pytest.py` gate using the
realized environment's interpreter (refuses if `vendor/macro_src` is absent
-- see Prerequisites). Or run a bounded subset:

```
python scripts/rwe_env.py gate --env /path/to/venv --subset tests/test_executive_service.py
```

An absolute `--subset` path is still used verbatim to actually invoke
pytest, but the **receipt** only ever records it repo-relativized (or the
literal placeholder `<subset>` when it resolves outside the repository) --
a host-specific absolute path (which can embed a username or home
directory) never reaches the receipt.

Either way, the outcome (command, exit code, discovered/collected count,
wall time) is appended to `<dest>/rwe_receipt.json` under `proof.gate`. The
command's own exit code mirrors the underlying pytest/gate exit code, so it
composes normally in shell scripts and CI steps. A successful **full**
gate run clears a stale `full_gate_unavailable:vendor_absent` degraded flag
left over from an earlier subset-only run.

## Re-emit a receipt

```
python scripts/rwe_env.py receipt --env /path/to/venv
```

Refuses first if the environment's interpreter is no longer CPython 3.12,
if the recorded lock's content has changed since realize, or if the lock is
stale relative to the live `pyproject.toml` (see Realize, above). Otherwise
recomputes the platform/package/proof facts for an already-realized
environment and rewrites its receipt (carrying forward any prior `gate`
result and `build_backend` record). Useful after manually poking at a venv,
or just to get a fresh `pip check`.

## What the receipt means

`<dest>/rwe_receipt.json` is schema `mastermind.worker_environment/v1`:

- `environment_id` -- a short deterministic id derived from the lock's
  content digest, the platform triple, **and the venv interpreter's FULL
  version (incl. patch, e.g. `3.12.13`)**, queried from the venv's own
  interpreter -- never the driver's. Two realizations from the same lock,
  platform, and interpreter patch version always produce the same id; a
  lock edit, or even a patch-level interpreter change, changes it.
- `definition` -- `kind: "pip-hash-lock"`, the source `pyproject.toml`
  digest, the lock's repo-relative path, and its digest.
- `platform` -- OS, architecture, interpreter implementation, `python_version`
  (the **full** `platform.python_version()`, e.g. `3.12.13`), and a
  **class** for the interpreter's origin (`homebrew` / `framework` /
  `toolcache` / `other`) -- never the raw filesystem path.
- `packages_installed` -- a count and a digest of the sorted `pip freeze`
  output. Never the raw package list, and never any path an editable
  install might otherwise print.
- `build_backend` -- the pinned `setuptools`/`wheel` versions the editable
  project install ran with (`{"setuptools": "...", "wheel": "..."}`).
- `vendored_inputs` -- the pinned macro `ref` (read live from
  `.github/workflows/ci.yml`), the **measured** `resolved_ref` (the vendored
  checkout's actual `git rev-parse HEAD`, or `null` when
  `vendor/macro_src/.git` is absent/unreadable), `match` (`true`/`false`
  when both are known, `null` otherwise), the repo-relative destination, and
  whether the vendor dir was actually present when the receipt was built.
- `proof` -- `pip_check` (`"ok"` or the error text, scrubbed of absolute
  host paths and truncated to 400 chars) and, once `gate` has run,
  `gate: {command, exit, discovered, seconds}`. `discovered` sums every
  category on the pytest summary line (`"1 failed, 36 passed"` -> `37`), and
  a true `0` (e.g. `"0 passed"`) is never dropped in favor of a stderr
  fallback.
- `degraded` -- notes when something ran in a reduced mode, e.g.
  `full_gate_unavailable:vendor_absent` when a `--subset` gate ran without
  the vendored input present. Cleared automatically the next time a full
  gate run succeeds.

The receipt never contains secrets, environment-variable dumps, raw host
names, raw user/home paths, or provider identity -- only content digests and
path *classes*. `DIR` (wherever you chose to realize the venv) is recorded
as the fixed placeholder `<env>` in any command string, never verbatim, and
an absolute `--subset` path is repo-relativized (or replaced with the
placeholder `<subset>` when it resolves outside the repo) before it is ever
written into a command string.

## Refusal cases (summary)

`realize`, `receipt`, and `gate` all refuse fail-closed (`EnvError`, one-line
stderr message, exit 2) rather than silently degrading:

- Unsupported interpreter (not CPython 3.12 exactly) -- checked at the head
  of all three subcommands, not only `realize`.
- `--lock` resolves outside the repository root (`realize`, checked before
  any venv work).
- The platform has no registered/committed lock yet.
- The lock is stale relative to the live `pyproject.toml`'s digest
  (`realize`, `receipt`; warn-only if the lock carries no
  `# pyproject.toml sha256:` header).
- The lock file's content has changed since a prior receipt recorded it
  (`receipt`, `gate` -- names both the recorded and current digest).
- `vendor/macro_src` is absent and no `--subset` was given (`gate`, full-gate
  path only).

## Rollback

There is nothing to roll back at the repository level -- locks are
additive, versioned files, and realized environments are disposable. To
undo a realization: `rm -rf /path/to/venv`. To stop using a lock: simply
stop invoking `rwe_env.py` against it; nothing else in the repository reads
these files.
