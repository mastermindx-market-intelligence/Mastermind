# B-BOARD: dev-board agent JWT secret provisioning (2026-11-14)

## Problem

The PF dev board (127.0.0.1:3196, instance `pf-board`) was started without
`PAPERCLIP_AGENT_JWT_SECRET`. Its start banner said `Agent JWT missing (run
npx paperclipai onboard)`. The board's process adapter therefore spawned
`tools/mmos_teammate/wake_carrier.py` without `PAPERCLIP_API_KEY`, and the
carrier refuses a run when a required env var is missing (`wake_carrier.py`
`main()`, exit 2). Issue PFD-1 went `blocked` with
`legacy_execution_requires_reconciliation`, run error "Process exited with
code 2". This is the gap already on the deputy's later list: the ruling-14
dev launcher must export `PAPERCLIP_AGENT_JWT_SECRET` or every dev carrier
run is blocked.

## Fix (tools/mmos_dev/paperclip_dev.sh)

- `up` provisions a per-instance secret file at
  `<dev-home>/instances/<id>/secrets/agent-jwt.hex`: dir 0700, file 0600,
  32 random bytes as hex (`openssl rand -hex 32`, python `secrets` fallback),
  written straight to the file under `umask 077`. Created once, reused
  unchanged on every later start. The value is never echoed, logged,
  exported or placed on a command line.
- The path is derived from the dev instance root. `ensure_agent_jwt_secret`
  resolves it (following symlinks) and refuses (exit 3) when it lands under
  `~/.paperclip` or anywhere other than this instance's `secrets/`; a
  symlinked secret file is refused too.
- Only the file PATH rides in the launch environment
  (`MMOS_DEV_AGENT_JWT_SECRET_FILE`). The generated `launch-server.mjs`
  reads the file itself and sets `process.env.PAPERCLIP_AGENT_JWT_SECRET`
  (and `BETTER_AUTH_SECRET` only if unset) BEFORE importing the server
  entry, so the banner shows `Agent JWT set` and the adapter can mint
  per-run tokens.
- `SCRUB_ENV` now also unsets ambient `PAPERCLIP_AGENT_JWT_SECRET` and
  `BETTER_AUTH_SECRET` so another instance's secret can never leak in.
- `up` reads the Agent JWT status word from the start banner (ANSI stripped,
  ruling-14 order: banner before any request) and kills the tree + exit 1
  unless it is exactly `set`.

## Tests (tests/test_paperclip_dev_launcher.py)

Six new tests on the existing fake-process harness: 0600 creation + reuse
across a down/up restart; value absent from the server log, launcher text,
config, every recorded argv and the launch env (with hostile ambient
secrets); symlink-into-`~/.paperclip` refusal before any launch; banner
`Agent JWT missing` failure; the generated launcher exercised with the real
node against a recording entry (env set before import, `BETTER_AUTH_SECRET`
only-if-unset, no value on stdout/stderr); source-level secret-handling
contracts. Red: 9 passed / 6 failed (the six new). Green: 15 passed.

Run: `TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q -p no:cacheprovider tests/test_paperclip_dev_launcher.py`

## Operational effect

Restarting the PF dev board through the fixed launcher (`down` + `up`, same
home/instance/port 3196/db 54396) provisions the secret and unblocks carrier
runs. Evidence: `~/.mastermind/mmos_evidence/pf-20261114/board2/`.
## Review REV-JWT (qwen4-max-preview, 2026-11-14) and repairs

Verdict PASS_WITH_FINDINGS. Q2 (value never printed, logged, in argv or env dumps) and Q3 (no argument reaches a real root) confirmed.

- F1 (MAJOR): `resolve_dir` normalised a not-yet-existing path lexically, so a symlinked ancestor (`instances -> ~/.paperclip/instances`) passed both checks. Now `os.path.realpath`. Test: symlinked instance root refused, nothing written at the target.
- F2/F3: generation goes to a private `mktemp` in `secrets/` and is published with `ln` (atomic, never overwrites); a failed generation leaves nothing, and the next `up` recovers. Concurrent first `up`s converge on one value. Test with a failing `openssl`.
- F4: `secrets/` is created under umask 077 (0700 from creation).
- F5: tests added for a symlink at the secret file, an intermediate symlink, and failed generation. The F1 and F2 tests fail on the pre-repair script.

`tests/test_paperclip_dev_launcher.py`: 18 passed.
