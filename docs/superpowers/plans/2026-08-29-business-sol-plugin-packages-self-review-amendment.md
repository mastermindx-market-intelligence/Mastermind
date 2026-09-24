# Business Sol Plugin Packages — Planning Self-Review Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement the parent plan task-by-task. This amendment has narrow precedence over the parent plan where explicitly stated.

**Parent plan:** `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md`

**Purpose:** Close deterministic-output, error-code, AST-fence, changed-base-command, and capability-wording defects found during the required post-plan self-review. All other parent-plan scope, skill contents, file topology, TDD order, no-rebuild laws, acceptance tests, and stop conditions remain controlling.

**Capability state:** `SPEC_ONLY / RECORDS_ONLY`. This amendment creates no plugin, validator, app, MCP server, OAuth client, tunnel, Business workspace effect, or Mastermind runtime effect.

---

## A1. Deterministic error paths must be repository-relative

The parent plan states that validator JSON contains no host-specific paths, but its initial `_error(path, ...)` sketch serializes an absolute path after `root.resolve()`. This amendment replaces that sketch.

Use these exact helpers:

```python
def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "<outside-root>"


def _error(root: Path, path: Path, code: str, message: str) -> dict[str, str]:
    return {
        "path": _display_path(root, path),
        "code": code,
        "message": message,
    }
```

Every validator helper receives `root: Path` and calls `_error(root, path, ...)`. No exception message containing an absolute path crosses into the result. Decode/JSON exceptions are mapped to bounded messages such as:

```text
file is not UTF-8
file is not valid JSON
required file is absent
```

Add this test to Task 1:

```python
def test_invalid_fixture_errors_are_repository_relative(tmp_path: Path) -> None:
    _valid_fixture(tmp_path)
    path = tmp_path / "plugins/mastermind-sol/.codex-plugin/plugin.json"
    path.write_text("{not-json}\n", encoding="utf-8")
    result = validate_repository(tmp_path)
    assert result["ok"] is False
    assert all(not error["path"].startswith("/") for error in result["errors"])
    assert str(tmp_path) not in json.dumps(result)
```

---

## A2. Specific forbidden-authority errors precede generic key errors

The parent RED tests require `LIVE_APP_BINDING_FORBIDDEN` when a manifest contains `apps`. An exact-key check alone would instead emit `INVALID_KEYS`. Apply this explicit order inside `_validate_plugin`:

```python
if isinstance(manifest, Mapping):
    if "apps" in manifest:
        errors.append(
            _error(
                root,
                manifest_path,
                "LIVE_APP_BINDING_FORBIDDEN",
                "P1 manifests must not reference .app.json",
            )
        )
    if "mcpServers" in manifest or "mcp_servers" in manifest:
        errors.append(
            _error(
                root,
                manifest_path,
                "MCP_DECLARATION_FORBIDDEN",
                "P1 manifests must not declare MCP servers",
            )
        )
    _exact_keys(
        root,
        manifest,
        PLUGIN_MANIFEST_KEYS,
        path=manifest_path,
        name="plugin manifest",
        errors=errors,
    )
```

The validator may emit both the specific authority error and `INVALID_KEYS`; the RED test requires that the specific code is present. Do not suppress structural errors to make one test pass.

Likewise, `_scan_forbidden_files` runs even when another package error already exists, so `.app.json`, `mcp.json`, and `.mcp.json` cannot hide behind an earlier failure.

---

## A3. Task 1 validator behavior is fully closed before later repository files exist

The parent Task 1 line “implement helpers with the closed requirements in Tasks 2–6” is too indirect for an executor seeing one task. The Task 1 implementation must support the isolated fixture completely with these exact rules:

### Marketplace

```text
path = .agents/plugins/marketplace.json
top-level keys = name, interface, plugins
name = mastermind-x
interface = {displayName: Mastermind-X}
plugins = exactly mastermind-sol then mastermind-operator
source = {source: local, path: ./plugins/<plugin>}
```

### Manifest

```text
exact keys = name, version, description, author, skills, interface
name = directory/plugin name
version = 0.1.0
author = {name: Mastermind-X}
skills = ./skills/
interface exact keys = displayName, shortDescription, developerName, category, capabilities
category = Productivity
capabilities = [Read]
apps and MCP fields = specific refusal
```

### Symbolic binding template

```text
exact top-level keys = schema, plugin, plugin_version, generated_file, generated_by_wave, bindings
schema = mastermind.plugin_app_bindings_template.v1
plugin/plugin_version match manifest
generated_file = .app.json
generated_by_wave = BSC-U1
bindings equal EXPECTED_BINDINGS order
binding exact keys = logical_name, required, contract_owner, app_id
required is true
app_id is null
```

### Skills

```text
exact skill directory set = EXPECTED_PLUGINS[plugin]
file = skills/<name>/SKILL.md
frontmatter exact keys = name, description
frontmatter name = directory name
description = non-empty one-line text
Mastermind Sol body contains all SOL_GATE_MARKERS
Mastermind Operator body contains “one already-bound operation and dialogue”
```

### References

```text
mastermind-sol requires references/authority-boundaries.md
mastermind-operator requires references/dialogue-boundary.md
both files are non-empty UTF-8 text
```

Task 1 may implement these rules before the real repository package exists because `_valid_fixture()` creates the complete isolated package. Tasks 2–5 then add the same contract to the repository.

---

## A4. AST/import fence checks imports, not ordinary policy vocabulary

The parent Task 6 proposed forbidding the raw source token `slack`, while the validator itself lawfully defines Slack identity patterns and generic-Slack-authority phrases. That would make its own accepted implementation impossible.

Replace that test with an AST import census:

```python
import ast


def test_validator_uses_stdlib_only() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts/validate_mastermind_plugins.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert imported <= {
        "__future__",
        "argparse",
        "json",
        "re",
        "sys",
        "pathlib",
        "typing",
    }
```

Add a separate executable-surface test:

```python
def test_validator_has_no_network_persistence_or_runtime_calls() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts/validate_mastermind_plugins.py").read_text(encoding="utf-8")
    for forbidden in (
        "requests.",
        "httpx.",
        "urllib.",
        "socket.",
        "subprocess.",
        "sqlite3.",
        "keyring.",
        "control_plane.",
        "integrations.",
        "os.system",
        "Popen(",
    ):
        assert forbidden not in text
```

The words Slack, Linear, GitHub, Executive, RuntimeBinding, and app are allowed as validated policy text. They are not imports or actions.

---

## A5. Changed-base census command contains no symbolic shell token

Replace:

```bash
git diff --name-only <current-protected-master>...HEAD
```

with:

```bash
git fetch origin master
BASE=$(git merge-base origin/master HEAD)
printf 'merge_base=%s\n' "$BASE"
git diff --name-only "$BASE"...HEAD
```

Immediately before push and final review, also require:

```bash
test "$BASE" = "$(git rev-parse origin/master)"
```

If protected `master` moved after implementation pickup, history-preservingly reconcile the same carrier, rerun affected verification, and recompute the census. Do not reset, force-push, or reuse stale green checks.

---

## A6. P1 prepares an importable package; it does not prove workspace import

The parent program plan’s independently useful capability is interpreted narrowly:

```text
A reviewer/admin has a deterministic marketplace/package source that conforms to the currently verified GitHub import contract and can be pinned for a later Business import canary.
```

P1 does **not** claim:

```text
workspace import succeeded
plugin is visible in ChatGPT web
plugin is installable for a role
app setup is complete
skills invoke correctly in a real Business conversation
```

Those claims remain owned by BSC-U1/BSC-C1.

---

## A7. Final self-review acceptance

Before opening the BSC-P1 implementation carrier, verify the executor used both the parent plan and this amendment:

```bash
python3 - <<'PY'
from pathlib import Path
parent = Path('docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md')
amend = Path('docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-self-review-amendment.md')
for path in (parent, amend):
    text = path.read_text(encoding='utf-8')
    assert text.strip()
    assert 'implement later' not in text.lower()
    assert 'similar to task' not in text.lower()
print('BSC_P1_PLAN_SET_PRESENT')
PY
```

The implementation PR body must cite both files. A worker following only the parent plan without this amendment is not current to the accepted P1 planning source.
