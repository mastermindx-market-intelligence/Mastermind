# Business Sol Plugin Packages — Current OpenAI Platform Contract Amendment

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement the parent plan task-by-task. This amendment has narrow precedence over the parent plan and planning self-review amendment where explicitly stated.

**Parent plan:** `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md`

**Companion amendment:** `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-self-review-amendment.md`

**Verification date:** 2026-08-29

**Purpose:** Align BSC-P1’s exact marketplace and native-plugin manifest contract with the current official OpenAI workspace-marketplace and plugin-packaging documentation verified after the plan self-review.

**Capability state:** `SPEC_ONLY / RECORDS_ONLY`. This amendment creates no marketplace, plugin, app, MCP server, OAuth connection, Business workspace effect, or Mastermind runtime effect.

---

## P1. Verified current platform facts

Current official OpenAI contracts establish:

1. Workspace GitHub import recognizes `.agents/plugins/marketplace.json` as a Codex marketplace with a `plugins` array.
2. Same-repository plugins use `source: {"source": "local", "path": "./plugins/<name>"}` and the path is relative to the selected marketplace root.
3. A workspace admin may pin import to an exact branch, tag, or commit.
4. GitHub import/sync does not apply repository installation/authentication policy; workspace admins configure plugin policy and app access separately.
5. Skills-only plugins are supported and need no app connection.
6. A minimal skills plugin requires `.codex-plugin/plugin.json` with `name`, `version`, `description`, and `skills`.
7. Rich install-surface metadata is optional. When used, current complete examples include `displayName`, `shortDescription`, `longDescription`, `developerName`, `category`, and `capabilities`.
8. `.app.json` references existing registered apps; the manifest points to it with `apps: "./.app.json"` only in the later app-bound generation.
9. `mcp.json`, `.mcp.json`, and inline bundled-MCP declarations make an imported plugin Desktop only, so they remain prohibited for the ChatGPT-web target.
10. Marketplace import does not grant app access or authenticate members.

These are platform assumptions, not permanent Mastermind law. BSC-P1 re-verifies them at START and stops with `PLATFORM_CONTRACT_CHANGED` if they move materially.

---

## P2. Add `longDescription` to the exact P1 interface contract

The parent plan’s rich interface object omitted `longDescription` even though current complete OpenAI examples include it. P1 intentionally uses rich install-surface metadata, so the exact interface key set becomes:

```python
INTERFACE_KEYS = frozenset(
    {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
    }
)
```

Update `_valid_fixture()` and both repository manifests accordingly.

### `mastermind-sol` interface

```json
{
  "displayName": "Mastermind Sol",
  "shortDescription": "Governed Chairman and Sol operating workflows",
  "longDescription": "Recover current Mastermind truth, reconcile company state, draft bounded CEO intent, review returns and pull requests, and close out accepted work without creating another control plane.",
  "developerName": "Mastermind-X",
  "category": "Productivity",
  "capabilities": [
    "Read"
  ]
}
```

### `mastermind-operator` interface

```json
{
  "displayName": "Mastermind Operator",
  "shortDescription": "Bound operator and company-dialogue workflows",
  "longDescription": "Receive one already-bound operation, return progress or a decision request, and finish the operation through the governed company-dialogue lifecycle without generic Slack or runtime authority.",
  "developerName": "Mastermind-X",
  "category": "Productivity",
  "capabilities": [
    "Read"
  ]
}
```

Add this assertion to the repository manifest test:

```python
assert isinstance(value["interface"]["longDescription"], str)
assert len(value["interface"]["longDescription"]) >= 80
```

The capability label `Read` is install-surface metadata for this production-inert skills-only generation. It does not grant a read tool, repository access, connected-app access, or Mastermind authority. The skill may guide reasoning/review workflows, but P1 contains no app/tool action. U1 must re-derive capability metadata from the exact installed app generation rather than copying `Read` blindly.

---

## P3. Preserve the minimal-manifest compatibility bar

The validator’s accepted P1 manifest is intentionally a richer subset of the current optional manifest fields. It must not claim that every OpenAI plugin globally requires the P1 exact keys.

Validator and error wording therefore say:

```text
Mastermind P1 manifest contract
```

not:

```text
OpenAI plugin schema requires these exact keys
```

This distinction prevents a Mastermind policy validator from misrepresenting an external platform schema.

The P1 validator may reject optional fields such as `homepage`, `repository`, `license`, `keywords`, assets, hooks, legal links, and prompts because they are outside this bounded wave—not because OpenAI forbids them. Any future addition is a separately reviewed P1.x/plugin-generation change.

---

## P4. Marketplace policy remains outside the repository manifest

The current workspace import contract explicitly states that repository installation/authentication policies are not applied during GitHub import/sync. Therefore the P1 marketplace remains exactly:

```json
{
  "name": "mastermind-x",
  "interface": {
    "displayName": "Mastermind-X"
  },
  "plugins": [
    {
      "name": "mastermind-sol",
      "source": {
        "source": "local",
        "path": "./plugins/mastermind-sol"
      }
    },
    {
      "name": "mastermind-operator",
      "source": {
        "source": "local",
        "path": "./plugins/mastermind-operator"
      }
    }
  ]
}
```

Do not add repository `policy`, `AVAILABLE`, `INSTALLED_BY_DEFAULT`, `ON_INSTALL`, `ON_USE`, role assignment, or authentication settings. BSC-U1 owns the real workspace policy ceremony and proof.

---

## P5. Exact app-generation distinction

P1 remains skills-only:

```text
no .app.json
no apps field
no mcpServers field
no mcp.json / .mcp.json
```

BSC-U1 later creates an app-bound plugin generation with all of:

```text
new reviewed plugin version
real .app.json using supported current app IDs
manifest apps = ./.app.json
capability metadata re-derived from the actual app actions
workspace app access/authentication configured separately
```

The current platform has two forms of identifiers visible in documentation and UI flows: underlying app IDs such as `asdk_app_...`, `connector_...`, or `templated_apps_...`, and plugin/UI identifiers that may include `plugin_...`. BSC-U1 must copy the exact underlying app ID required by the then-current workspace import contract and must not guess by stripping or adding prefixes.

---

## P6. Planning-source precedence and implementation receipt

The complete current BSC-P1 plan set is:

1. `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md`
2. `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-self-review-amendment.md`
3. `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-platform-contract-amendment.md`

The implementation PR must cite all three. Where they conflict:

```text
platform-contract amendment
→ self-review amendment
→ parent P1 plan
```

All non-conflicting parent-plan requirements remain controlling.

Before implementation START, run:

```bash
python3 - <<'PY'
from pathlib import Path
paths = [
    Path('docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md'),
    Path('docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-self-review-amendment.md'),
    Path('docs/superpowers/plans/2026-08-29-business-sol-plugin-packages-platform-contract-amendment.md'),
]
for path in paths:
    assert path.read_text(encoding='utf-8').strip(), path
print('BSC_P1_CURRENT_PLAN_SET_PRESENT')
PY
```

If current official OpenAI documentation at START no longer supports this marketplace/manifest shape, stop before writing implementation and return the exact platform-contract delta to Sol.
