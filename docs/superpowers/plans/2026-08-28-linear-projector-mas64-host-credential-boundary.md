# Linear Projector MAS-64 H0 Host Credential Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one fixed, no-echo, root-owned local credential enrollment/verification boundary for the `Mastermind Portfolio Projector` OAuth client without creating a daemon, generic secret store or network/mutation capability.

**Architecture:** A single standard-library Python module under `ops/linear_projector/` owns fixed production coordinates and three commands: `prepare`, `enroll`, `verify`. It reuses the proven security shape of C1 enrollment—opaque errors, fixed paths, `O_EXCL`, `O_NOFOLLOW`, ownership/mode/link checks, fsync and no-echo stdin—but remains fully independent from Executive OS and MAS-115 Keychain coordinates.

**Tech Stack:** Python 3 standard library (`argparse`, `hashlib`, `json`, `os`, `pathlib`, `stat`, `sys`, `termios`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-28-linear-projector-mas64-host-credential-boundary.md`

## Global Constraints

- Protected architecture owner remains MAS-64 / MAS-188 under OSC-L1; no new workstream or runtime lifecycle.
- Production root is exactly `/Library/Application Support/MastermindPortfolioProjector`; never MastermindExecutive.
- No network calls, Linear mutation, OAuth token exchange, daemon, scheduler, launchd, queue, DB, Keychain abstraction or caller-selectable secret path.
- Secret bytes may enter only via stdin and the fixed `oauth-client-secret` file; never argv/env/stdout/stderr/logs/repo/temp files.
- Final secret/config writes are create-once; existing/ambiguous state is refusal, never overwrite/retry.
- No production code before a discriminating failing test has been observed.

---

### Task 1: Freeze constants, parser and secret-surface refusal

**Files:**
- Create: `ops/linear_projector/__init__.py`
- Create: `ops/linear_projector/host_enrollment.py`
- Create: `tests/test_linear_projector_host_enrollment.py`

**Interfaces:**
- Produces constants `ROOT`, `CONFIG_DIR`, `CONFIG_PATH`, `SECRET_PATH`, `WORKSPACE_ID`, `TEAM_ID`, `TEAM_KEY`, `APP_NAME`, `CONFIG_SCHEMA`.
- Produces `ProjectorHostError(code: str)` and `build_parser() -> argparse.ArgumentParser`.
- Produces `assert_secret_surfaces_clean(*, argv: Sequence[str], environ: Mapping[str, str]) -> None`.

- [ ] **Step 1: Write the failing constant/parser tests**

Add tests that import `ops.linear_projector.host_enrollment`, assert all fixed production coordinates exactly, assert none contains `MastermindExecutive`, assert no MAS-115 service/account string exists in the module constants, and assert parser accepts only `prepare`, `enroll --client-id`, and `verify --expected-client-id`.

```python
def test_production_coordinates_are_fixed_and_separate_from_executive():
    assert mod.ROOT == Path("/Library/Application Support/MastermindPortfolioProjector")
    assert mod.CONFIG_DIR == mod.ROOT / "config"
    assert mod.CONFIG_PATH == mod.CONFIG_DIR / "projector.json"
    assert mod.SECRET_PATH == mod.CONFIG_DIR / "oauth-client-secret"
    joined = "\n".join(map(str, (mod.ROOT, mod.CONFIG_DIR, mod.CONFIG_PATH, mod.SECRET_PATH)))
    assert "MastermindExecutive" not in joined


def test_cli_has_no_generic_path_or_rotation_surface():
    parser = mod.build_parser()
    assert parser.parse_args(["prepare"]).command == "prepare"
    assert parser.parse_args(["enroll", "--client-id", "abc123"]).client_id == "abc123"
    assert parser.parse_args(["verify", "--expected-client-id", "abc123"]).expected_client_id == "abc123"
    with pytest.raises(mod.ProjectorHostError):
        parser.parse_args(["enroll", "--path", "/tmp/x", "--client-id", "abc123"])
```

- [ ] **Step 2: Run the focused test and observe RED**

Run:

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py
```

Expected: import/attribute failure because the H0 package/module does not exist yet.

- [ ] **Step 3: Implement only constants, opaque parser and secret-surface scan**

Create `ops/linear_projector/__init__.py` as an empty package marker. In `host_enrollment.py`, define the exact constants from the spec, a closed `ERROR_CODES` set, `ProjectorHostError`, an `argparse.ArgumentParser` subclass whose `.error()` raises `PROJECTOR_HOST_ARGUMENTS_REFUSED`, and `assert_secret_surfaces_clean()` that refuses:

```python
SECRET_ENV_KEYS = {
    "LINEAR_CLIENT_SECRET",
    "LINEAR_ACCESS_TOKEN",
    "LINEAR_API_KEY",
    "MASTERMIND_LINEAR_CLIENT_SECRET",
    "MASTERMIND_LINEAR_ACCESS_TOKEN",
}
```

Also refuse argv/env values matching obvious `lin_api_`, `Bearer ` or OAuth-secret-shaped values. Never include the offending value in the exception.

- [ ] **Step 4: Run focused tests GREEN**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py
python3 -m py_compile ops/linear_projector/host_enrollment.py
```

- [ ] **Step 5: Commit**

```bash
git add ops/linear_projector tests/test_linear_projector_host_enrollment.py
git commit -m "test(linear): specify projector host credential boundary"
```

### Task 2: Implement no-echo bounded secret input

**Files:**
- Modify: `ops/linear_projector/host_enrollment.py`
- Modify: `tests/test_linear_projector_host_enrollment.py`

**Interfaces:**
- Produces `_decode_secret_bytes(raw: bytes) -> bytes`.
- Produces `read_secret_from_stdin(stream: BinaryIO) -> bytes`.

- [ ] **Step 1: Add RED tests for malformed input and terminal restoration**

Tests must cover empty, >4096 bytes, leading/trailing whitespace, internal whitespace/control characters, multiple lines, and non-ASCII bytes. Add a fake TTY/termios adapter seam so a test proves ECHO is removed for the read and original attributes are restored even when decoding refuses.

```python
@pytest.mark.parametrize("raw", [b"", b" secret\n", b"secret \n", b"secret value\n", b"a\nsecond\n"])
def test_decode_secret_refuses_malformed_input(raw):
    with pytest.raises(mod.ProjectorHostError) as exc:
        mod._decode_secret_bytes(raw)
    assert exc.value.code == "PROJECTOR_HOST_INPUT_REFUSED"
```

- [ ] **Step 2: Observe RED**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "secret or echo"
```

Expected: missing input functions / failing terminal behavior.

- [ ] **Step 3: Implement minimal input functions**

Use one bounded `readline(MAX_SECRET_BYTES + 2)`. For a real TTY, obtain `termios.tcgetattr`, clear `termios.ECHO`, set immediately, read, then restore in `finally`. Return bytes, not `str`, so the secret is not copied through formatting/logging code. `_decode_secret_bytes` strips one terminal newline only, refuses whitespace/control characters and enforces the bound.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "secret or echo"
```

- [ ] **Step 5: Commit**

```bash
git add ops/linear_projector/host_enrollment.py tests/test_linear_projector_host_enrollment.py
git commit -m "feat(linear): add hidden bounded projector secret input"
```

### Task 3: Prepare safe fixed directories

**Files:**
- Modify: `ops/linear_projector/host_enrollment.py`
- Modify: `tests/test_linear_projector_host_enrollment.py`

**Interfaces:**
- Produces `prepare_host(*, root: Path = ROOT, uid: int = 0, gid: int = 0) -> None` for internal dependency-injected tests while the CLI always uses production constants/root IDs.
- Produces `_assert_safe_directory(path, *, uid, gid, mode) -> None`.

- [ ] **Step 1: Add RED filesystem tests**

Use `tmp_path` and current test UID/GID. Test fresh creation, exact `0750`, symlink refusal, non-directory refusal, unsafe existing mode refusal and wrong-owner refusal (skip owner mutation where platform privileges make it impossible; test the validator with patched stat objects rather than weakening production checks).

- [ ] **Step 2: Observe RED**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "prepare or directory"
```

- [ ] **Step 3: Implement prepare-only behavior**

Create only `ROOT` and `CONFIG_DIR`, one level at a time, with `mkdir(mode=0o750)` and post-create `lstat` verification. Never create config/secret files. Existing safe exact directories are idempotent; any unsafe type/symlink/owner/group/mode is refusal. The CLI `prepare` requires effective UID 0; tests call the internal function with injected UID/GID.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "prepare or directory"
```

- [ ] **Step 5: Commit**

```bash
git add ops/linear_projector/host_enrollment.py tests/test_linear_projector_host_enrollment.py
git commit -m "feat(linear): prepare fixed projector credential root"
```

### Task 4: Create-once config and secret enrollment

**Files:**
- Modify: `ops/linear_projector/host_enrollment.py`
- Modify: `tests/test_linear_projector_host_enrollment.py`

**Interfaces:**
- Produces `build_config_document(*, client_id: str) -> dict[str, str]`.
- Produces `write_new_private_file(path, payload, *, uid, gid, mode) -> None`.
- Produces `enroll(*, client_id: str, secret: bytes, root: Path = ROOT, uid: int = 0, gid: int = 0) -> None`.

- [ ] **Step 1: Add RED tests**

Prove exact config schema/IDs/app name, bounded client-ID validation, config mode `0640`, secret mode `0600`, exact secret bytes, one link, no overwrite, symlink final-path refusal, wrong/unsafe prepared directory refusal, and that a simulated second-file write failure does not trigger a retry or overwrite.

- [ ] **Step 2: Observe RED**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "enroll or config or write_new"
```

- [ ] **Step 3: Implement create-once writes**

Use `os.open` with `O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC` and `O_NOFOLLOW` where available. Verify regular file/link count/owner/group, `fchown` when needed, `fchmod`, write all bytes, `fsync`, close, re-`lstat`, and fsync parent. Write non-secret config first, then secret; if secret creation fails after config exists, return a typed collision/write refusal and require explicit operator cleanup/reconciliation—do not automatically delete or retry an effect-unknown write.

Serialize config with deterministic JSON (`sort_keys=True`, compact separators, trailing newline). Never include the secret.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "enroll or config or write_new"
```

- [ ] **Step 5: Commit**

```bash
git add ops/linear_projector/host_enrollment.py tests/test_linear_projector_host_enrollment.py
git commit -m "feat(linear): enroll projector OAuth secret create-once"
```

### Task 5: Read-only verification and opaque receipts

**Files:**
- Modify: `ops/linear_projector/host_enrollment.py`
- Modify: `tests/test_linear_projector_host_enrollment.py`

**Interfaces:**
- Produces `verify_boundary(*, expected_client_id: str, root: Path = ROOT, uid: int = 0, gid: int = 0) -> str` returning the client-id SHA-256 hex only after metadata/config verification.
- Produces `main(*, argv=None, environ=None, stdin=None, stdout=None, stderr=None) -> int`.

- [ ] **Step 1: Add RED tests for verification and output secrecy**

Create a valid temp fixture and assert verification succeeds without reading secret contents by replacing secret-file byte-reading helpers with a sentinel that would fail if invoked; verification may only `lstat` the secret. Mutate file mode/type/link count/config schema/workspace/team/client ID and assert fixed refusal codes. Capture stdout/stderr for a known secret and arbitrary injected exception text and prove neither appears.

- [ ] **Step 2: Observe RED**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py -k "verify or stdout or stderr or receipt"
```

- [ ] **Step 3: Implement verifier and CLI main**

`verify_boundary` validates safe directories, exact config file metadata/content, exact client ID, and secret file metadata only. `main` runs `assert_secret_surfaces_clean` before command behavior, requires root only for production `prepare/enroll/verify`, reads secret only for `enroll`, and prints exactly:

```text
LINEAR_PROJECTOR_HOST_PREPARED
LINEAR_PROJECTOR_CREDENTIAL_ENROLLED
LINEAR_PROJECTOR_CREDENTIAL_BOUNDARY_VERIFIED client_id_sha256=<64hex>
```

On every expected or unexpected failure, stderr contains only `REFUSED: <closed_error_code>` and return code 2. Never forward exception text.

- [ ] **Step 4: Run complete focused suite GREEN**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py
python3 -m py_compile ops/linear_projector/host_enrollment.py
```

- [ ] **Step 5: Commit**

```bash
git add ops/linear_projector/host_enrollment.py tests/test_linear_projector_host_enrollment.py
git commit -m "feat(linear): verify projector credential boundary opaquely"
```

### Task 6: Adversarial no-network/no-generic-secret proof and documentation

**Files:**
- Modify: `tests/test_linear_projector_host_enrollment.py`
- Create: `docs/LINEAR_PORTFOLIO_PROJECTOR_HOST.md`

**Interfaces:**
- Documents only the fixed H0 ceremony and non-secret receipts; it must never contain example secret/token values.

- [ ] **Step 1: Add final hostile tests**

Add a source-level import/AST assertion that production H0 imports no `urllib`, `http`, `requests`, Linear client or Executive control module; assert no public CLI option contains `path`, `service`, `account`, `token`, `secret`, `rotate`, `delete`, `daemon` or `schedule` except the fixed `enroll` secret input path itself. Assert config serialization never includes keys containing `secret`, `token`, `authorization`, `cookie` or `refresh`.

- [ ] **Step 2: Observe any missing-fence RED and implement only required correction**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py
```

If every hostile test already passes, do not invent extra production code. If a test fails, make the smallest production correction and rerun.

- [ ] **Step 3: Write operator documentation**

Document:

```text
sudo python3 -m ops.linear_projector.host_enrollment prepare
sudo python3 -m ops.linear_projector.host_enrollment enroll --client-id <NON_SECRET_CLIENT_ID>
sudo python3 -m ops.linear_projector.host_enrollment verify --expected-client-id <NON_SECRET_CLIENT_ID>
```

State that the `enroll` command prompts natively with echo disabled and the secret must never be pasted into ChatGPT/Slack/GitHub. State that H0 performs no OAuth/token exchange and no Linear mutation.

- [ ] **Step 4: Run full verification**

```bash
python3 -m pytest -q tests/test_linear_projector_host_enrollment.py
python3 -m compileall -q ops/linear_projector
python3 -m pytest -q tests/test_c1_native_enrollment.py tests/test_nonseat_canary.py
```

Then run the repository's normal exact-head CI/security gates. Confirm changed files remain limited to the MAS-188 spec/plan/docs/package/tests.

- [ ] **Step 5: Independent review and stop**

Review against MAS-188/MAS-64/OSC-L1. Required conclusion before merge: H0 creates no app, no network path, no Linear mutation, no Executive ownership, no generic secret manager and no scheduled service. Stop before any real credential enrollment; the next real action is the MAS-64 Chairman/admin app creation + native hidden enrollment ceremony.
