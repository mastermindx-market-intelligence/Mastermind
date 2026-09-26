# Codex Fabric attended bootstrap implementation plan

> Execute inline with test-driven development. This is client composition, not a worker launcher.

**Goal:** Prepare the existing attended Codex principal's Executive connection without login, global configuration edits, or provider execution; make the eventual launch reproducible.

**Architecture:** Consume #633's reviewed parent profile, bare Executive MCP registration, and existing Keychain header helper. A stateless attended-client bootstrap renders explicit Codex overrides and pins the helper working directory independently of the project directory. It adds no authentication, lifecycle, dispatch, placement, retry, or identity authority.

**Tech stack:** Python standard library, existing Codex CLI configuration interface, existing registration validator.

**Spec:** `docs/runbooks/codex-astra-fabric-delegation.md` and `docs/superpowers/specs/2026-09-14-astra-external-fabric-client-auth-amendment.md` at #633 `d347248b119379ab12f62e7f749d8dcc5ccd3f9d`.

## Assignment and source

Current Chairman continuation explicitly excludes account login/onboarding. Protected procedure pin: `0d12bb45c4429a7441614fac8eff4830db5e7c0d`, compatible Skillpack 1.0.1 / bootstrap 1. Source operation: `codex-fabric-no-login-bootstrap-20260926-sol-001`; carrier: Studio Direct; canonical workspace acquired through mmx-workspace. New paths only, stacked on #633; do not displace its historical writer or alter its 12 existing candidate paths.

Direct execution rationale: CRITICAL_PATH_SHORTCUT / LOWER_TOTAL_OVERHEAD for this small client-only seam. No worker or provider is dispatched.

## Constraints

- Default preflight may perform only the existing local `codex --cd <project> mcp list --json` census; never add a server, log in, call the header helper, or start a provider.
- Explicit `--launch` is a future attended action after onboarding, not permission to launch in this turn.
- Require one exact enabled bare loopback Executive registration; refuse native OAuth or ambiguous auth status rather than override credential precedence.
- Preserve global Codex configuration and the separately attested repository `.codex/config.toml`.
- Keep native agents disabled and expose only the existing five Executive tool names on this server; do not weaken approval or sandbox settings.
- Quote paths and TOML values separately. The helper uses reviewed-source cwd; Codex uses the selected project cwd.
- Never touch the prior Auth0 DCR EFFECT_UNKNOWN marker, retry registration, or assert authenticated tool discovery from preparation.

## Review focus

Path whitespace/metacharacters; conflicting registrations or credential sources; missing/malformed census; absent/invalid profile or executable; launch failure must not trigger fallback/retry. Each is covered by the task's tests.

## Task 1: Compose and prove the client bootstrap

Files: new `ops/codex_fabric/attended_parent.py`, new `tests/test_codex_fabric_attended_parent.py`, this plan, and a new bounded runbook supplement.

Interface: `prepare_launch(server_url, *, codex_bin, python_bin, project_dir, source_root) -> LaunchPlan`; `main(argv=None) -> int` defaults to secret-free JSON preflight, with explicit `--launch` replacing the wrapper process.

- [x] Write behavioral tests using a fake local Codex executable; observe missing implementation failure.
- [x] Implement composition through the existing registration parser without authentication imports.
- [x] Prove preflight calls only census; prove actual generated helper cwd/quoting with a fake interpreter; prove explicit launch executes only the prepared argv.
- [ ] Prove closed refusals and no fallback on malformed/conflicting input, plus unchanged existing candidate files.
- [ ] Run targeted client regressions, compile check, and diff checks. Report unavailable full-suite dependencies truthfully.
- [ ] Publish a Draft stacked source result and checkpoint exact evidence under #633; no merge, deployment, login, or live provider canary.

## Progress

Ruling: bind metadata census to the target project, not the launcher cwd. A discriminating test failed before the repair and passed afterward.

Ruling: native Codex 0.154.0 returns `unsupported` for the empty-account fixture. Upstream `codex-rs/cli/src/mcp_cmd.rs` also uses Unsupported when status data is absent. Preserve a prepared-but-held result; never reinterpret this as absent credentials or permission to launch. Both new held-state tests failed before implementation.

Verified: 103 tests and 18 subtests passed across all six client test modules, using an isolated test environment with the repository-pinned PyJWT[crypto]==2.13.0. The first system-Python regression attempt stopped at the missing PyJWT dependency; it is not accepted proof. Compilation and exact source/publication checks are recorded in the owning PR checkpoint.

Native no-account verification: Codex 0.154.0, temporary empty HOME/CODEX_HOME with file-only credential stores, one loopback fixture registration. Default preparation returns PREPARED_AUTH_STATUS_UNRESOLVED / launch_allowed=false. Native parsing of the prepared override shape succeeds after substituting /usr/bin/false for the real auth helper; the native census redacts the configured helper. No model turn, real header-helper invocation, login, token exchange, or provider effect occurred.

Only four new paths are owned. Existing #633 candidate files, Auth0 uncertainty, global configuration and production services remain untouched. Mission incomplete; required full-repository CI, independent review, protected-source integration, installed client qualification and all real end-to-end gates remain open. No autonomous wake or execution custody transfer is claimed.
