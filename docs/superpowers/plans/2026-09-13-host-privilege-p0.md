# Host Privilege P0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Web CEO and Codex CEO passwordless access to a closed set of existing Executive OS root operations without exposing the Chairman's administrator password or raw sudo.

**Architecture:** Reuse the installed Executive OS release, `_mastermind_ops`, existing autonomy transaction owner, and macOS sudoers. A root-owned fixed bridge derives the installed SHA from protected control config and accepts only typed verbs; an unprivileged client calls only that bridge through `sudo -n`. No daemon, shell server, queue, permission database, or retry plane is added.

**Tech Stack:** Python 3 standard library, POSIX shell, macOS sudo/sudoers/visudo, existing Executive OS `autonomy_control.py`, `service-control.sh`, `release_manifest.py`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-13-host-privilege-p0-design.md`

## Global Constraints

- Raw Desktop Commander `sudo`, `su`, `passwd`, and `visudo` stay blocked.
- No administrator password or 1Password secret enters source, arguments, environment, receipts, or logs.
- Executive OS remains lifecycle/admission/autonomy authority; the bridge only adapts OS privilege.
- Caller never supplies release SHA, executable path, launchd label, plist, user, interpreter, or shell command.
- Common effect truth is `NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`.
- Mac Studio is the first production proof host; Admin Mini and MacBook are not installation targets until Executive OS exists there.
- The first bridge installation is one explicit root bootstrap; normal operations after install are non-interactive.

---

### Task 1: Freeze the bridge API with RED tests

**Files:**
- Create: `tests/test_executive_admin_bridge.py`
- Create later: `ops/executive_os/admin_bridge.py`

**Interfaces:**
- Produces `main(argv, *, host=None, environ=None) -> int` in `admin_bridge.py`.
- Produces `BridgeHost` protocol with `identity()`, `autonomy(argv)`, `service_state()`, `ensure_ready()`, and `ensure_stopped()` methods so hermetic tests exercise parser/effect behavior without root.
- Produces JSON schema `mastermind.executive_admin_bridge/v1` with keys `schema_version`, `ok`, `action`, `effect`, `code`, `release_sha`, and `result`.

- [ ] Write failing tests that import `ops.executive_os.admin_bridge` and prove the module does not yet exist.
- [ ] Cover read-only `status`, `autonomy status`, forwarding for `autonomy arm`, `autonomy disarm`, `service ensure-ready`, and `service ensure-stopped`.
- [ ] Assert parser refusal for `sudo`, `shell`, `exec`, `restart`, `launchctl`, caller-supplied SHA/path/service-label flags, extra positional arguments, and `--` passthrough.
- [ ] Assert `autonomy arm --gate-b-receipt` rejects relative paths and paths outside `/Library/Application Support/MastermindExecutive` or `/var/db/mastermind-executive` before dispatch.
- [ ] Assert read-only actions return `effect=NOT_APPLIED`; convergent service no-op returns `NOT_APPLIED`; changed convergence returns `APPLIED`; unresolved post-action state returns `EFFECT_UNKNOWN`.
- [ ] Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -p no:cacheprovider -o addopts= -q tests/test_executive_admin_bridge.py` and record the expected RED caused by the missing module.
- [ ] Commit the RED test alone.

### Task 2: Implement the root bridge to GREEN

**Files:**
- Create: `ops/executive_os/admin_bridge.py`
- Test: `tests/test_executive_admin_bridge.py`

**Interfaces:**
- `InstalledIdentity(release_sha: str, release_root: Path, caller: str)`.
- `ProductionBridgeHost.identity() -> InstalledIdentity` validates Darwin, EUID 0, `SUDO_USER`/`SUDO_UID`, `_mastermind_ops` membership, root-owned `control.json`, and exact release manifest.
- `ProductionBridgeHost.autonomy(args: Sequence[str]) -> ChildResult` executes the installed release's existing autonomy module using the pinned Executive Python and a fixed import path.
- `ProductionBridgeHost.ensure_ready()` and `ensure_stopped()` invoke only the installed release's fixed `service-control.sh` and re-observe the two frozen labels.

- [ ] Implement a closed argparse parser with exact commands `status`, `autonomy {status,arm,disarm}`, and `service {ensure-ready,ensure-stopped}`.
- [ ] Implement JSON output and `BridgeRefusal` / `BridgeEffectUnknown` mapping without swallowing existing autonomy JSON.
- [ ] Implement installed identity validation: direct root-owned control config, `_mastermind_exec` group/mode `0440`, no ACL, exact `proof_base_sha`, direct root:wheel release root, root-owned release manifest, and `release_manifest.verify(...)` using the manifest's own tree SHA only after its commit SHA equals the root-derived release SHA.
- [ ] Implement sudo-caller validation from environment and local group database; reject root/missing/inconsistent/non-ops callers.
- [ ] Implement gate-B lexical resolution under the two frozen system roots with no symlink final object before forwarding; leave root ownership/content authority to existing `autonomy_control.py`.
- [ ] Implement service convergence without a `restart` command. `ensure-ready` observes first and does nothing if ready; otherwise it calls the fixed start path once and must prove final ready. `ensure-stopped` similarly proves both labels absent.
- [ ] Run the focused test until GREEN, then run existing `tests/test_executive_autonomy_control.py` and `tests/test_executive_launchd_config.py` to prove no regression.
- [ ] Commit implementation and green tests.

### Task 3: Add the passwordless client and one-time root installer

**Files:**
- Create: `ops/executive_os/mmx-admin-bridge`
- Create: `ops/executive_os/mmx-adminctl`
- Create: `ops/executive_os/install-admin-bridge.sh`
- Create: `tests/test_executive_admin_bridge_install.py`

**Interfaces:**
- Installed privileged launcher: `/Library/Application Support/MastermindExecutive/admin/mmx-admin-bridge`.
- Installed Python module: `/Library/Application Support/MastermindExecutive/admin/admin_bridge.py`.
- Installed client: `/usr/local/bin/mmx-adminctl`.
- Sudoers fragment: `/etc/sudoers.d/mastermind-executive-admin`.

- [ ] Write RED source-contract tests first. Require fixed absolute paths, `sudo -n`, no password/stdin handling, no `eval`, no arbitrary interpreter/path flags, root:wheel mode intent, `_mastermind_ops`, `visudo -cf`, atomic temp+rename installation, and an uninstall path limited to the three P0 artifacts plus exact sudoers fragment.
- [ ] Run the install-contract test and record RED because the three source artifacts do not exist.
- [ ] Implement `mmx-admin-bridge` as a tiny root-owned launcher that `exec`s the pinned Executive Python with `-I -S -B` and the fixed installed module path, forwarding arguments without evaluation.
- [ ] Implement `mmx-adminctl` as a tiny unprivileged launcher that `exec`s `/usr/bin/sudo -n` for the one fixed privileged launcher path; it contains no password prompt fallback.
- [ ] Implement `install-admin-bridge.sh`: require root/Darwin/existing `_mastermind_ops`; require source release beneath the exact Executive releases root; verify release manifest; stage bridge/module/client/sudoers temp files; chown/chmod; validate sudoers with `/usr/sbin/visudo -cf`; atomically rename; fsync parent directories where supported; then read back metadata and output a non-secret JSON receipt.
- [ ] Make installer rollback remove staged temporary files on pre-commit failure. Once the sudoers fragment is committed, any uncertain failure must report `EFFECT_UNKNOWN` rather than blindly reinstalling.
- [ ] Implement `--uninstall` with exact identity/path checks and no Executive OS service/config/account deletion.
- [ ] Run focused install-contract tests to GREEN and run `bash -n` on both shell launchers/installer.
- [ ] Commit the installer/client vertical.

### Task 4: Integration falsifiers and source proof

**Files:**
- Modify: `tests/test_executive_admin_bridge.py`
- Modify: `tests/test_executive_admin_bridge_install.py`
- Create: `docs/runbooks/host-privilege-p0.md`

**Interfaces:**
- Runbook defines only one Chairman bootstrap command and all subsequent CEO commands through `mmx-adminctl`.

- [ ] Add falsifiers for shell metacharacters as literal data, gate-B symlink escape, malformed control config, incorrect release manifest commit, non-ops caller, and ambiguous service final state.
- [ ] Add assertions that the sudoers template contains exactly one command path and does not grant shell/interpreter/package-manager/launchctl/`ALL` command authority.
- [ ] Document `ADMIN_GATE_REQUIRED` classifications for TCC/FDA/MDM/SecureToken/FileVault and explicitly forbid attempts to bypass them through P0.
- [ ] Run focused suites plus `python3 -m py_compile ops/executive_os/admin_bridge.py` and `git diff --check`.
- [ ] Open a Draft PR from `sol/host-privilege-p0-20260913` to `master`; let the repository's natural `test` and security checks run.
- [ ] Do not merge or install while source checks/review are incomplete.

### Task 5: One-time Mac Studio bootstrap and real Web CEO proof

**Files:**
- No source mutation unless production proof finds a source defect.

**Interfaces:**
- One root bootstrap command from the exact accepted release.
- Thereafter `/usr/local/bin/mmx-adminctl ...` is the only CEO-facing privilege interface.

- [ ] After source acceptance and an exact installed release containing P0, run the installer once with Chairman-authorized root elevation on Mac Studio.
- [ ] Read back root ownership, modes, ACL absence, sudoers validation, and `_mastermind_ops` membership.
- [ ] Re-read Desktop Commander configuration and prove raw `sudo` remains blocked.
- [ ] Through the real Web CEO Remote Desktop Commander path, run `mmx-adminctl status` and `mmx-adminctl autonomy status` as ordinary `chriswong` without password prompt.
- [ ] Run one admitted convergent service action and prove the returned effect plus final state.
- [ ] Run one forbidden verb and prove `REFUSED / NOT_APPLIED`.
- [ ] For Codex, allow only `/usr/local/bin/mmx-adminctl` in the provider command policy and prove the same read + one bounded mutator without granting raw sudo.
- [ ] Record production receipts and capability transition. P0 becomes `PROVEN_LIVE` only after both the host path and security invariants are observed.
